# ---------------------------------------------------------------------------
# SLAYQL — Self-Generated Semantic Assertions (SGSA) Validator
# ---------------------------------------------------------------------------
# This module acts as independent middleware between SQL execution and result
# acceptance.  It validates a Pandas DataFrame against a JSON dictionary of
# assertions that the LLM generated alongside the SQL query.
#
# DESIGN PRINCIPLE — Immutable Semantic Contract:
#   Assertions are generated ONCE during the initial SQL generation step and
#   are FROZEN throughout the revision loop.  The LLM is never allowed to
#   relax or rewrite them, preventing Reward Hacking / Constraint Relaxation.
# ---------------------------------------------------------------------------

import json
import re
import warnings
from typing import Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame, assertions: Dict) -> List[str]:
    """
    Validate a DataFrame against a dictionary of semantic assertions.

    Parameters
    ----------
    df : pd.DataFrame
        The result of executing the SQL query.
    assertions : dict
        A JSON-compatible dictionary with any combination of:
          - expected_row_count : int
          - unique_columns     : list[str]
          - value_bounds       : dict[str, {"min": num, "max": num}]
          - no_nulls           : list[str]

    Returns
    -------
    list[str]
        A list of human-readable ``[SEMANTIC ERROR] …`` strings.
        An empty list means all assertions passed.
    """
    if not assertions or not isinstance(assertions, dict):
        return []

    if df is None:
        return ["[SEMANTIC ERROR] DataFrame is None — cannot validate."]

    errors: List[str] = []

    # Build a case-insensitive column lookup:  lower(name) → actual name
    col_lookup = {c.lower(): c for c in df.columns}

    # ------------------------------------------------------------------
    # 1.  expected_row_count
    # ------------------------------------------------------------------
    if "expected_row_count" in assertions:
        try:
            expected = int(assertions["expected_row_count"])
            actual = len(df)
            if actual != expected:
                errors.append(
                    f"[SEMANTIC ERROR] Expected exactly {expected} row(s), "
                    f"but query returned {actual} row(s).  "
                    f"Check LIMIT / TOP-N / aggregation logic."
                )
        except (TypeError, ValueError):
            warnings.warn(
                f"[SGSA] Invalid expected_row_count value: "
                f"{assertions['expected_row_count']!r} — skipping check."
            )

    # ------------------------------------------------------------------
    # 2.  unique_columns — no duplicates allowed
    # ------------------------------------------------------------------
    if "unique_columns" in assertions:
        unique_cols = assertions["unique_columns"]
        if isinstance(unique_cols, list):
            for col_name in unique_cols:
                actual_col = col_lookup.get(str(col_name).lower())
                if actual_col is None:
                    errors.append(
                        f"[SEMANTIC ERROR] Assertion specifies unique column "
                        f"'{col_name}', but it does not exist in the result. "
                        f"Available columns: {list(df.columns)}"
                    )
                    continue
                if df[actual_col].duplicated().any():
                    dup_vals = (
                        df[actual_col][df[actual_col].duplicated(keep=False)]
                        .unique()[:3]
                        .tolist()
                    )
                    total_dups = int(df[actual_col].duplicated().sum())
                    errors.append(
                        f"[SEMANTIC ERROR] Column '{actual_col}' must be unique "
                        f"but contains {total_dups} duplicate(s).  "
                        f"Sample duplicated values: {dup_vals}.  "
                        f"This may indicate a JOIN explosion — consider "
                        f"adding DISTINCT or reviewing JOIN conditions."
                    )

    # ------------------------------------------------------------------
    # 3.  value_bounds — numeric range enforcement
    # ------------------------------------------------------------------
    if "value_bounds" in assertions:
        bounds = assertions["value_bounds"]
        if isinstance(bounds, dict):
            for col_name, bound_spec in bounds.items():
                actual_col = col_lookup.get(str(col_name).lower())
                if actual_col is None:
                    errors.append(
                        f"[SEMANTIC ERROR] Assertion specifies value bounds for "
                        f"column '{col_name}', but it does not exist in the "
                        f"result.  Available columns: {list(df.columns)}"
                    )
                    continue
                if not isinstance(bound_spec, dict):
                    continue

                series = pd.to_numeric(df[actual_col], errors="coerce")
                non_null_series = series.dropna()

                if non_null_series.empty:
                    continue  # all values coerced to NaN — nothing to check

                lo = bound_spec.get("min")
                hi = bound_spec.get("max")

                if lo is not None:
                    try:
                        lo = float(lo)
                        min_val = float(non_null_series.min())
                        if min_val < lo:
                            errors.append(
                                f"[SEMANTIC ERROR] Column '{actual_col}' has "
                                f"minimum value {min_val}, which is below the "
                                f"expected lower bound of {lo}.  "
                                f"Check calculation logic (e.g., negative "
                                f"values where only positives are expected)."
                            )
                    except (TypeError, ValueError):
                        pass

                if hi is not None:
                    try:
                        hi = float(hi)
                        max_val = float(non_null_series.max())
                        if max_val > hi:
                            errors.append(
                                f"[SEMANTIC ERROR] Column '{actual_col}' has "
                                f"maximum value {max_val}, which exceeds the "
                                f"expected upper bound of {hi}.  "
                                f"Check calculation logic (e.g., percentage "
                                f"exceeding 100, or missing denominator)."
                            )
                    except (TypeError, ValueError):
                        pass

    # ------------------------------------------------------------------
    # 4.  no_nulls — columns must not be entirely null
    # ------------------------------------------------------------------
    if "no_nulls" in assertions:
        no_null_cols = assertions["no_nulls"]
        if isinstance(no_null_cols, list):
            for col_name in no_null_cols:
                actual_col = col_lookup.get(str(col_name).lower())
                if actual_col is None:
                    errors.append(
                        f"[SEMANTIC ERROR] Assertion specifies no-null check "
                        f"for column '{col_name}', but it does not exist in "
                        f"the result.  Available columns: {list(df.columns)}"
                    )
                    continue
                if df[actual_col].isnull().all():
                    errors.append(
                        f"[SEMANTIC ERROR] Column '{actual_col}' is entirely "
                        f"NULL.  The query may be joining on a non-matching "
                        f"key or selecting from an empty partition."
                    )

    return errors


# ---------------------------------------------------------------------------
# Assertion Parsing Helpers
# ---------------------------------------------------------------------------

def parse_assertions_from_output(model_output: str) -> Dict:
    """
    Extract the first valid JSON block from the LLM's model output.

    The LLM is prompted to output assertions inside a ```json ... ``` block
    BEFORE the ```sql ... ``` block.  This function finds and parses it.

    Parameters
    ----------
    model_output : str
        The raw text output from the LLM.

    Returns
    -------
    dict
        Parsed assertions dictionary.  Returns ``{}`` if no valid JSON block
        is found (graceful fallback — never crashes the pipeline).
    """
    if not model_output:
        return {}

    # Strategy 1: Find ```json ... ``` fenced blocks
    json_blocks = re.findall(
        r"```json\s*\n(.*?)\n\s*```", model_output, re.DOTALL
    )

    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Strategy 2: Find any ``` ... ``` block that parses as JSON dict
    generic_blocks = re.findall(
        r"```\s*\n(.*?)\n\s*```", model_output, re.DOTALL
    )
    for block in generic_blocks:
        block_stripped = block.strip()
        if block_stripped.startswith("{"):
            try:
                parsed = json.loads(block_stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    return {}


def format_errors_for_llm(errors: List[str]) -> str:
    """
    Format a list of semantic error strings into a single message suitable
    for appending to the LLM's conversation history.

    Parameters
    ----------
    errors : list[str]
        List of ``[SEMANTIC ERROR] …`` strings from ``validate()``.

    Returns
    -------
    str
        A formatted error message for the LLM.
    """
    if not errors:
        return ""

    header = (
        "The SQL query executed successfully (no database engine errors), "
        "but the result data FAILED semantic validation.  The following "
        "data quality issues were detected:\n\n"
    )

    body = "\n".join(f"  • {e}" for e in errors)

    footer = (
        "\n\nPlease revise the SQL query to fix these semantic issues.  "
        "Do NOT change the assertions — they represent the ground truth "
        "constraints derived from the user's original question.  "
        "Common fixes include: adding DISTINCT, fixing GROUP BY, "
        "correcting mathematical formulas (e.g., multiply by 100 for "
        "percentages), adding proper LIMIT clauses, or reviewing "
        "JOIN conditions to prevent row explosion."
    )

    return header + body + footer


def load_assertions(assertions_path: str) -> Dict:
    """
    Load a frozen assertions JSON file from disk.

    Parameters
    ----------
    assertions_path : str
        Path to the assertions.json file.

    Returns
    -------
    dict
        The assertions dictionary, or ``{}`` if the file doesn't exist
        or cannot be parsed.
    """
    try:
        with open(assertions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

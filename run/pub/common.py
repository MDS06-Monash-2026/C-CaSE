"""Shared paths, parsers and statistics for the publication analysis scripts."""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

RUN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = RUN_DIR.parent
RESULTS_DIR = RUN_DIR / "pub_results"
BIRD_DEV_ROOT = REPO_ROOT / "dev" / "dev_20240627"
GOLD_SQL_DIR = REPO_ROOT / "evaluation_suite" / "gold" / "sql"

if str(RUN_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DIR))

# Windows consoles default to cp1252; results contain characters such as "Δ".
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

TABLE_HEADER = re.compile(r"^###Table full name:\s*(.+?)\s*$")
COLUMN_LINE = re.compile(r"^\s{2,}(.+?) \(Type:")

# Usage stages recorded by the dataset pipeline, grouped for the paper.
STAGE_GROUPS = {
    "schema_completion": "linking",
    "sql_generation": "generation",
    "sql_revision": "revision",
    "semantic_revision": "revision",
    "selector_tournament": "selection",
    "selector_verification": "selection",
    "selection": "selection",
}
STAGE_GROUP_NAMES = ("linking", "generation", "revision", "selection", "other")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_text_any(path: Path) -> str:
    """Read a text file that may be UTF-8 or UTF-16 (PowerShell `>` redirection writes UTF-16)."""
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or raw[:200].count(b"\x00") > 20:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def read_csv(path: Path) -> List[Dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def last_part(name: str) -> str:
    return str(name).strip().strip("`\"[]").split(".")[-1].strip("`\"[]").lower()


def parse_schema_prompt(text: str) -> Dict[str, Any]:
    """Parse a SlayQL schema prompt into table names and (table, column) pairs."""
    tables: List[str] = []
    columns: List[Tuple[str, str]] = []
    current: Optional[str] = None
    block_lines: List[str] = []
    in_block = False
    for line in text.splitlines():
        header = TABLE_HEADER.match(line)
        if header:
            current = header.group(1)
            tables.append(current)
            block_lines.append(line)
            continue
        if current is not None and line.strip() == "[":
            in_block = True
            block_lines.append(line)
            continue
        if in_block and line.strip() == "]":
            in_block = False
            block_lines.append(line)
            continue
        if in_block:
            block_lines.append(line)
            column = COLUMN_LINE.match(line)
            if column:
                columns.append((current, column.group(1).strip()))
    return {
        "tables_full": tables,
        "tables": {last_part(table) for table in tables},
        "columns": {column.strip("`\"").lower() for _, column in columns},
        "table_columns": {(last_part(table), column.strip("`\"").lower()) for table, column in columns},
        "n_tables": len(set(tables)),
        "n_columns": len(set(columns)),
        "table_block_text": "\n".join(block_lines),
    }


def compact_schema(table_columns: Dict[str, Iterable[str]]) -> str:
    """Render a schema the same way for linked and full schemas so token counts are comparable."""
    return "\n".join(f"{table}({', '.join(sorted(set(columns)))})" for table, columns in sorted(table_columns.items()))


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # pragma: no cover - fallback when tiktoken is unavailable
        return None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    encoder = _encoder()
    if encoder is None:
        return int(round(len(text.split()) * 1.3))
    return len(encoder.encode(text, disallowed_special=()))


def sql_refs(sql: str, instance_id: str) -> Dict[str, set]:
    """Tables and columns referenced by a SQL query (same parser as evaluate_dataset.py)."""
    from evaluate_dataset import _sql_refs
    return _sql_refs(sql or "", instance_id)


def gold_refs(sql: str, instance_id: str) -> Dict[str, Any]:
    """Tables and columns referenced by gold SQL, robust to scripts and CTEs.

    Unlike sql_refs, this parses statement by statement when the whole script fails (for
    example BigQuery DECLARE blocks) and removes CTE names, which sqlglot reports as tables.
    """
    import sqlglot
    from evaluate_dataset import _dialect

    dialect = _dialect(instance_id)
    expressions: List[Any] = []
    parsed_ok = True
    try:
        expressions = [item for item in sqlglot.parse(sql or "", read=dialect) if item is not None]
    except Exception:
        parsed_ok = False
        for part in (sql or "").split(";"):
            if not part.strip():
                continue
            try:
                expressions.extend(item for item in sqlglot.parse(part, read=dialect) if item is not None)
            except Exception:
                continue
    tables, columns, ctes = set(), set(), set()
    for expression in expressions:
        ctes.update(str(cte.alias_or_name).lower() for cte in expression.find_all(sqlglot.exp.CTE))
        tables.update(last_part(item.name) for item in expression.find_all(sqlglot.exp.Table) if item.name)
        columns.update(str(item.name).lower() for item in expression.find_all(sqlglot.exp.Column) if item.name)
    return {"tables": tables - ctes, "columns": columns, "parsed_whole": parsed_ok,
            "parsed_any": bool(expressions)}


def set_metrics(predicted: set, gold: set) -> Dict[str, float]:
    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "strict_recall": 1.0 if gold and gold.issubset(predicted) else 0.0,
        "predicted": len(predicted), "gold": len(gold), "true_positive": true_positive,
    }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> Tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def bootstrap_mean(values: Sequence[float], resamples: int = 10_000, seed: int = 20260813) -> Tuple[float, float, float]:
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, data.size, size=(resamples, data.size))
    means = data[indices].mean(axis=1)
    return float(data.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_bootstrap_diff(a: Sequence[float], b: Sequence[float], resamples: int = 10_000,
                          seed: int = 20260813) -> Tuple[float, float, float]:
    """Mean of (b - a) with a paired bootstrap 95% interval."""
    left, right = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if left.size != right.size:
        raise ValueError("Paired bootstrap needs equal-length inputs")
    return bootstrap_mean(right - left, resamples, seed)


def mcnemar_exact(a_correct: Sequence[bool], b_correct: Sequence[bool]) -> Dict[str, float]:
    """Exact McNemar test on paired correctness (two-sided binomial test on discordant pairs)."""
    from scipy.stats import binomtest
    only_a = sum(1 for left, right in zip(a_correct, b_correct) if left and not right)
    only_b = sum(1 for left, right in zip(a_correct, b_correct) if right and not left)
    discordant = only_a + only_b
    p_value = binomtest(only_a, discordant, 0.5).pvalue if discordant else 1.0
    return {"only_a": only_a, "only_b": only_b, "p_value": float(p_value)}


def holm_adjust(p_values: Dict[str, float]) -> Dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    total = len(ordered)
    adjusted: Dict[str, float] = {}
    running = 0.0
    for rank, (key, value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[key] = running
    return adjusted


def fmt_pct(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else f"{100 * value:.{digits}f}"


def md_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)

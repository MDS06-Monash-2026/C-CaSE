import os
import re
import pickle
from rank_bm25 import BM25Okapi

# ---------------------------------------------------------------------------
# SLAYQL Value Grounder — Enhanced BM25 Grounding
# ---------------------------------------------------------------------------
# ROOT CAUSE OF EX DEGRADATION:
#   The original extract_literals() pulled out every quoted word, capitalized
#   token, and number.  This caused two issues:
#
#   1.  Numeric noise: small integers like "5", "10", "100" are ubiquitous
#       in SQL questions ("top 10", "last 5 days") and rarely correspond to
#       actual DB cell values.  Matching them produced spurious [Value Hint]
#       injections pointing to completely unrelated columns.
#
#   2.  Stop-word / SQL-keyword pollution: words like "average", "count",
#       "top" were being treated as potential cell values, yielding hints that
#       told the LLM a non-existent value existed in a numeric column.
#
#   3.  Too many hints per prompt: injecting 10+ hints cluttered the system
#       message and caused the model to focus on grounding rather than
#       correct SQL structure.
#
# FIX:
#   1.  Enhanced extract_literals — filters pure integers < 1000, stop-words,
#       SQL structural keywords, and tokens shorter than 3 characters.
#   2.  Stricter BM25 threshold via an exact-match bonus and a configurable
#       high-confidence threshold (default = 5.0, previously 2.0).
#   3.  Hard cap of MAX_HINTS_PER_PROMPT (= 3) injected hints per prompt.
# ---------------------------------------------------------------------------

# Maximum number of value hints injected into a single prompt.
MAX_HINTS_PER_PROMPT: int = 3

# BM25 score threshold.  Only scores above this are considered trustworthy.
# The previous default of 2.0 was too permissive.
DEFAULT_THRESHOLD: float = 5.0

# Words that should never be treated as candidate entity literals.
# Combines generic stop-words with common SQL structural keywords.
_FILTER_WORDS = frozenset([
    # English stop-words
    "the", "a", "an", "of", "in", "for", "on", "with", "by", "to",
    "from", "is", "are", "was", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should",
    "what", "which", "who", "where", "when", "how", "many", "much",
    "each", "all", "any", "and", "or", "not", "this", "that", "those",
    "these", "than", "more", "most", "some", "other", "per", "its",
    # SQL structural keywords (should never be matched as cell values)
    "select", "from", "where", "group", "order", "having", "join",
    "inner", "outer", "left", "right", "full", "cross", "on", "union",
    "except", "intersect", "as", "distinct", "limit", "offset",
    "count", "sum", "avg", "min", "max", "average", "total", "top",
    "bottom", "first", "last", "between", "like", "null", "true",
    "false", "case", "when", "then", "else", "end", "over", "partition",
    "row", "rows", "rank", "dense", "lag", "lead", "with", "cte",
    "pivot", "unpivot", "into", "values", "insert", "update", "delete",
    "create", "drop", "alter", "index", "table", "view", "database",
    "cumulative", "running", "rolling", "number", "value", "column",
    "row", "field", "record", "entry", "list", "every", "return",
])

# Integer threshold: integers BELOW this value are always filtered out.
# (e.g., "5", "10", "100" are structural, not entity names.)
_MAX_FILTER_INTEGER: int = 1000


# ---------------------------------------------------------------------------
# Literal extraction
# ---------------------------------------------------------------------------

def extract_literals(query: str) -> list:
    """
    Extract candidate entity/value literals from the user question.

    Filtering rules (in order):
      1. Include tokens that appear inside quotation marks (high confidence
         these are explicit values the user has in mind).
      2. Include capitalized sequences of ≥ 2 words (named entities).
      3. Include numbers ONLY if they are ≥ 1000 (likely year / ID / zipcode).
      4. Exclude any token that is a SQL stop-word or structural keyword.
      5. Exclude any token shorter than 3 characters.
      6. Deduplicate.

    Returns
    -------
    List[str] of cleaned literal candidates.
    """
    candidates = []

    # -----------------------------------------------------------------------
    # (a) Quoted strings — highest confidence, always include.
    # -----------------------------------------------------------------------
    quoted = re.findall(r'["\']([^"\']{2,})["\']', query)
    candidates.extend(quoted)

    # -----------------------------------------------------------------------
    # (b) Capitalized named-entity sequences (≥ 2 adjacent tokens).
    #   E.g. "United States", "New York" — multi-word proper nouns.
    # -----------------------------------------------------------------------
    cap_sequences = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', query)
    candidates.extend(cap_sequences)

    # -----------------------------------------------------------------------
    # (c) Single capitalized words — only include if NOT in _FILTER_WORDS.
    # -----------------------------------------------------------------------
    single_caps = re.findall(r'\b([A-Z][a-z]{2,})\b', query)
    for tok in single_caps:
        if tok.lower() not in _FILTER_WORDS:
            candidates.append(tok)

    # -----------------------------------------------------------------------
    # (d) Numbers — only include if ≥ _MAX_FILTER_INTEGER.
    # -----------------------------------------------------------------------
    numbers = re.findall(r'\b(\d{4,}|\d{1,3}(?:,\d{3})+)\b', query)
    # Also grab plain large integers (≥ 1000) without commas.
    plain_numbers = re.findall(r'\b(\d+)\b', query)
    for n in plain_numbers:
        try:
            if int(n) >= _MAX_FILTER_INTEGER:
                numbers.append(n)
        except ValueError:
            pass
    candidates.extend(numbers)

    # -----------------------------------------------------------------------
    # Final filter: remove stop-words, SQL keywords, and short tokens.
    # -----------------------------------------------------------------------
    cleaned = []
    seen = set()
    for tok in candidates:
        tok_clean = tok.strip()
        tok_lower = tok_clean.lower()

        if len(tok_clean) < 3:
            continue
        if tok_lower in _FILTER_WORDS:
            continue
        # Skip if the literal is a "small" pure integer (structural noise).
        try:
            if int(tok_clean) < _MAX_FILTER_INTEGER:
                continue
        except ValueError:
            pass  # Not an integer — keep it.

        if tok_lower not in seen:
            seen.add(tok_lower)
            cleaned.append(tok_clean)

    return cleaned


# ---------------------------------------------------------------------------
# Offline index construction  (unchanged API, kept for compatibility)
# ---------------------------------------------------------------------------

def build_db_value_index(
    db_connection,
    db_id: str,
    output_dir: str = "bm25_indices",
) -> None:
    """
    Build and persist a BM25 index of textual cell values for the given DB.

    Scans all TEXT/VARCHAR/CHAR columns, collects up to 1000 distinct values
    per column, tokenizes them, and saves to a pickle file.

    Args
    ----
    db_connection : SQLite connection object.
    db_id         : Identifier used when naming the output file.
    output_dir    : Directory where index files are stored.
    """
    os.makedirs(output_dir, exist_ok=True)
    cursor = db_connection.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    corpus = []
    mapping = []

    for (table_name,) in tables:
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        columns = cursor.fetchall()
        for col in columns:
            col_name = col[1]
            col_type = col[2].upper()
            if any(t in col_type for t in ("TEXT", "VARCHAR", "CHAR")):
                try:
                    cursor.execute(
                        f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                        f'WHERE "{col_name}" IS NOT NULL LIMIT 1000'
                    )
                    values = cursor.fetchall()
                    for (val,) in values:
                        if isinstance(val, str) and val.strip():
                            corpus.append(val.split())
                            mapping.append(f"{table_name}.{col_name}")
                except Exception as e:
                    print(f"[ValueGrounder] Error reading {table_name}.{col_name}: {e}")

    if corpus:
        bm25 = BM25Okapi(corpus)
        index_data = {
            "bm25": bm25,
            "mapping": mapping,
            "corpus_strings": [" ".join(c) for c in corpus],
        }
        with open(os.path.join(output_dir, f"{db_id}_bm25.pkl"), "wb") as f:
            pickle.dump(index_data, f)


# ---------------------------------------------------------------------------
# Online value matching
# ---------------------------------------------------------------------------

def get_value_hints(
    query: str,
    db_id: str,
    indices_dir: str = "bm25_indices",
    threshold: float = DEFAULT_THRESHOLD,
    max_hints: int = MAX_HINTS_PER_PROMPT,
) -> str:
    """
    Match user query literals to actual database cell values via BM25.

    Improvements
    ------------
    •  Uses enhanced extract_literals() that filters stop-words, SQL keywords,
       and small integers, dramatically reducing spurious matches.
    •  Applies an exact-match bonus: if the top-scoring BM25 entry is an
       exact case-insensitive match for the literal, the hint is always
       included regardless of the numeric threshold.
    •  Hard caps the number of injected hints at `max_hints` (default 3).

    Args
    ----
    query       : User's natural-language question.
    db_id       : Database identifier used to locate the BM25 index file.
    indices_dir : Directory containing pre-built BM25 index pickle files.
    threshold   : Minimum BM25 score for a match to be included.
                  Default raised from 2.0 → 5.0 to reduce false positives.
    max_hints   : Maximum number of hints to inject into the prompt (default 3).

    Returns
    -------
    A formatted string ready to be prepended to the LLM prompt, or "" if no
    high-confidence matches were found.
    """
    index_path = os.path.join(indices_dir, f"{db_id}_bm25.pkl")
    if not os.path.exists(index_path):
        # No index for this DB — silently skip (BQ/Snowflake may not have one).
        return ""

    with open(index_path, "rb") as f:
        index_data = pickle.load(f)

    bm25: BM25Okapi = index_data["bm25"]
    mapping: list = index_data["mapping"]
    corpus_strings: list = index_data["corpus_strings"]

    # Extract filtered literals from the query.
    literals = extract_literals(query)
    if not literals:
        return ""

    hints = []

    for literal in literals:
        tokenized_literal = literal.split()
        if not tokenized_literal:
            continue

        scores = bm25.get_scores(tokenized_literal)
        if len(scores) == 0:
            continue

        best_idx = int(np.argmax(scores)) if hasattr(scores, "__len__") else max(
            range(len(scores)), key=lambda i: scores[i]
        )
        best_score = float(scores[best_idx])
        matched_value = corpus_strings[best_idx]
        col_path = mapping[best_idx]

        # Exact-match check (case-insensitive): always include if exact.
        is_exact = literal.lower() == matched_value.lower()

        if is_exact or best_score > threshold:
            hints.append(
                f"[Value Hint: '{literal}' → '{matched_value}' in column '{col_path}' "
                f"(score={best_score:.2f}{'  EXACT MATCH' if is_exact else ''})]"
            )

        # Stop once we have reached the per-prompt cap.
        if len(hints) >= max_hints:
            break

    if hints:
        return "\n[VALUE HINTS — use these to verify column/value existence]\n" + "\n".join(hints) + "\n"
    return ""


# ---------------------------------------------------------------------------
# Compatibility shim: expose np.argmax without forcing a top-level import
# ---------------------------------------------------------------------------
try:
    import numpy as np
except ImportError:
    # If numpy is somehow not available, fall back to a pure-Python max.
    class _NpShim:
        @staticmethod
        def argmax(seq):
            return max(range(len(seq)), key=lambda i: seq[i])
    np = _NpShim()

import re
import numpy as np
import networkx as nx
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# SLAYQL RBP (Relevance-Based Propagation)
# ---------------------------------------------------------------------------
# ROOT CAUSE OF EX DEGRADATION:
#   The original implementation used a static alpha=0.7 and propagated scores
#   unconditionally to ALL neighboring tables, including massive "hub" tables
#   with hundreds of columns.  This caused two problems:
#
#   1.  Context window pollution: hub tables with 50+ columns that received
#       propagated relevance would be included in the schema prompt, filling
#       the context window with irrelevant columns and crowding out the truly
#       important columns.
#
#   2.  Over-smoothing for confident queries: when the retriever was already
#       highly confident (low entropy → high alpha should dominate), the
#       propagation step still diluted the sharp signal with graph-neighbour
#       scores, promoting unrelated tables.
#
# FIX:
#   1.  Dynamic alpha: scale alpha as a function of retrieval entropy.
#       • High confidence (low entropy)  → alpha ≈ 0.9 (minimal propagation)
#       • High uncertainty (high entropy) → alpha ≈ 0.7 (more graph exploration)
#   2.  Top-K truncation during propagation: only propagate scores to a
#       neighbour table if it is "small" (< MAX_COLUMNS_FOR_PROPAGATION cols)
#       OR shares at least one meaningful BM25 keyword with the query.
#       This prevents score leaking to schema-wide hub tables.
# ---------------------------------------------------------------------------

# Maximum number of columns a neighbour table may have to receive propagated
# scores unconditionally.  Tables with more columns require a keyword match.
MAX_COLUMNS_FOR_PROPAGATION: int = 20

# Entropy range used to linearly interpolate alpha.
_ALPHA_LOW_ENTROPY: float = 0.9   # used when entropy ≤ ENTROPY_ALPHA_LOW
_ALPHA_HIGH_ENTROPY: float = 0.7  # used when entropy ≥ ENTROPY_ALPHA_HIGH
_ENTROPY_ALPHA_LOW: float = 0.3   # below this → treat as high-confidence
_ENTROPY_ALPHA_HIGH: float = 0.7  # above this → treat as high-uncertainty

# Common SQL stop-words that should be excluded from keyword matching.
_STOPWORDS = frozenset([
    "the", "a", "an", "of", "in", "for", "on", "with", "by", "to",
    "from", "is", "are", "was", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should",
    "what", "which", "how", "many", "much", "each", "all", "any",
    "and", "or", "not", "select", "where", "group", "order", "having",
    "join", "inner", "outer", "left", "right", "full", "cross", "on",
    "union", "except", "intersect", "as", "distinct", "limit", "top",
    "count", "sum", "avg", "min", "max", "between", "like", "in",
    "null", "true", "false",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dynamic_alpha(entropy: float) -> float:
    """
    Compute a dynamic damping factor alpha based on retrieval entropy.

    When entropy is LOW (retriever is confident) → alpha → 0.9
       Almost all of the column's final score comes from its own raw
       cosine similarity; very little leaks in from graph neighbours.

    When entropy is HIGH (retriever is uncertain) → alpha → 0.7
       More weight is given to graph-propagated table context so that
       structurally important bridging tables can still be promoted.

    Linear interpolation between the two boundary values.
    """
    entropy = float(np.clip(entropy, 0.0, 1.0))

    if entropy <= _ENTROPY_ALPHA_LOW:
        return _ALPHA_LOW_ENTROPY
    elif entropy >= _ENTROPY_ALPHA_HIGH:
        return _ALPHA_HIGH_ENTROPY
    else:
        # Linear interpolation
        t = (entropy - _ENTROPY_ALPHA_LOW) / (_ENTROPY_ALPHA_HIGH - _ENTROPY_ALPHA_LOW)
        return _ALPHA_LOW_ENTROPY + t * (_ALPHA_HIGH_ENTROPY - _ALPHA_LOW_ENTROPY)


def _extract_query_keywords(query: str) -> frozenset:
    """
    Tokenize and filter the query into a set of meaningful keywords,
    removing stop-words, pure integers, and short tokens.
    """
    tokens = re.findall(r"[a-zA-Z_]\w*", query.lower())
    keywords = frozenset(
        t for t in tokens
        if t not in _STOPWORDS and len(t) >= 3
    )
    return keywords


def _count_table_columns(db_metadata: Dict[str, Any], table_name: str) -> int:
    """
    Best-effort count of the number of columns in a given table,
    extracted from db_metadata if available.  Returns 0 if unknown.
    """
    table_info = db_metadata.get("table_info", {})
    t_lower = table_name.lower()

    # Try direct match or case-insensitive match.
    if t_lower in table_info:
        return len(table_info[t_lower].get("columns", {}))
    for k, v in table_info.items():
        if k.lower() == t_lower:
            return len(v.get("columns", {}))
    return 0


def _table_shares_keywords(
    table_name: str,
    db_metadata: Dict[str, Any],
    query_keywords: frozenset,
) -> bool:
    """
    Check whether a table is keyword-relevant to the user query.

    Checks:
      (a) The table name itself contains a query keyword.
      (b) Any column name in the table matches a query keyword.

    This is intentionally lightweight (no BM25, no embeddings) because it
    runs once per neighbour per retrieval batch.
    """
    if not query_keywords:
        return False

    # (a) Table name check
    t_tokens = frozenset(re.findall(r"[a-zA-Z_]\w*", table_name.lower()))
    if t_tokens & query_keywords:
        return True

    # (b) Column name check using table_info if available
    table_info = db_metadata.get("table_info", {})
    for k, v in table_info.items():
        if k.lower() == table_name.lower():
            col_names = v.get("columns", {}).keys()
            col_tokens = frozenset(
                tok
                for col in col_names
                for tok in re.findall(r"[a-zA-Z_]\w*", col.lower())
            )
            if col_tokens & query_keywords:
                return True
    return False


# ---------------------------------------------------------------------------
# Core graph functions
# ---------------------------------------------------------------------------

def build_schema_graph(db_metadata: Dict[str, Any]) -> nx.Graph:
    """
    Construct the schema graph G from db_metadata.

    Nodes  = tables (lowercase).
    Edges  = PK-FK relationships (explicit) or shared column-name heuristic.

    Args
    ----
    db_metadata : dict containing at minimum a 'tables' key and optionally
                  'foreign_keys' or 'table_info'.

    Returns
    -------
    nx.Graph
    """
    G = nx.Graph()

    if "foreign_keys" in db_metadata and db_metadata["foreign_keys"]:
        # Preferred path: explicit FK relationships.
        for fk in db_metadata["foreign_keys"]:
            if len(fk) >= 4:
                t1, _, t2, _ = fk[:4]
                G.add_edge(t1.lower(), t2.lower())
    elif "table_info" in db_metadata:
        # Heuristic fallback: link tables that share normalized column names.
        table_info = db_metadata["table_info"]
        tables = list(table_info.keys())
        for i in range(len(tables)):
            for j in range(i + 1, len(tables)):
                t1, t2 = tables[i], tables[j]
                c1 = table_info[t1].get("columns", {}).keys()
                c2 = table_info[t2].get("columns", {}).keys()
                # Standardize: lowercase + strip underscores.
                norm_c1 = {c.lower().replace("_", "") for c in c1}
                norm_c2 = {c.lower().replace("_", "") for c in c2}
                if norm_c1 & norm_c2:
                    G.add_edge(t1.lower(), t2.lower())

    # Ensure every table appears as a node (even isolated ones).
    if "tables" in db_metadata:
        for table in db_metadata["tables"]:
            t_name = table.lower()
            if t_name not in G:
                G.add_node(t_name)

    return G


def propagate_relevance(
    initial_similarities: Dict[str, float],
    db_metadata: Dict[str, Any],
    alpha: float = 0.7,               # kept for backward-compatibility
    entropy: Optional[float] = None,  # NEW: if provided, overrides static alpha
    query: str = "",                  # NEW: used for keyword-based truncation
) -> Dict[str, float]:
    """
    Propagate semantic relevance across the schema graph (RBP).

    Improvements over AutoLink baseline
    ------------------------------------
    1.  Dynamic alpha: when `entropy` is supplied, alpha is computed as a
        function of retrieval confidence instead of using a fixed value.
        High confidence → alpha → 0.9 (almost no propagation).
        Low confidence  → alpha → 0.7 (more graph exploration).

    2.  Top-K truncation: propagation to a neighbour table is SKIPPED if:
          (a) the table has ≥ MAX_COLUMNS_FOR_PROPAGATION columns, AND
          (b) the table shares no keyword with the user query.
        This prevents massive hub tables from polluting the context window.

    Args
    ----
    initial_similarities : Mapping 'table.column' → raw cosine similarity.
    db_metadata          : Schema info dict (PK/FK, tables, table_info …).
    alpha                : Static damping factor used when entropy=None.
    entropy              : Normalized retrieval entropy from IT-EE module.
    query                : User's natural-language question.

    Returns
    -------
    Dict mapping 'table.column' → propagated similarity score.
    """
    # ------------------------------------------------------------------
    # Step 1: Resolve the effective alpha.
    # ------------------------------------------------------------------
    if entropy is not None:
        effective_alpha = _dynamic_alpha(entropy)
        print(
            f"[RBP] Dynamic alpha = {effective_alpha:.3f} "
            f"(entropy={entropy:.3f})"
        )
    else:
        effective_alpha = alpha

    # ------------------------------------------------------------------
    # Step 2: Build the schema graph.
    # ------------------------------------------------------------------
    G = build_schema_graph(db_metadata)
    tables = list(G.nodes())

    if not tables:
        # No graph topology available; return similarities unchanged.
        return initial_similarities

    table_to_idx = {t: i for i, t in enumerate(tables)}
    n_tables = len(tables)

    # ------------------------------------------------------------------
    # Step 3: Extract query keywords for selective propagation.
    # ------------------------------------------------------------------
    query_keywords = _extract_query_keywords(query) if query else frozenset()

    # ------------------------------------------------------------------
    # Step 4: Build a MASKED adjacency matrix.
    #   We zero-out edges leading to tables that are:
    #     (a) large hub tables (≥ MAX_COLUMNS_FOR_PROPAGATION cols), AND
    #     (b) keyword-irrelevant to the user query.
    # ------------------------------------------------------------------
    A_raw = nx.adjacency_matrix(G, nodelist=tables).toarray().astype(float)

    # Build per-table mask: 1 = allow propagation into this table, 0 = block.
    allow_mask = np.ones(n_tables, dtype=float)
    for i, table in enumerate(tables):
        col_count = _count_table_columns(db_metadata, table)
        is_large = col_count >= MAX_COLUMNS_FOR_PROPAGATION
        has_keyword_match = _table_shares_keywords(table, db_metadata, query_keywords)

        if is_large and not has_keyword_match:
            # Block propagation INTO this table (zero out its column).
            allow_mask[i] = 0.0
            print(
                f"[RBP] Blocked propagation to hub table '{table}' "
                f"({col_count} cols, no keyword match)."
            )

    # Apply mask: zero out columns corresponding to blocked tables.
    A_masked = A_raw * allow_mask[np.newaxis, :]  # broadcast along columns

    # ------------------------------------------------------------------
    # Step 5: Build the row-normalised transition matrix W = D^{-1} A_masked.
    # ------------------------------------------------------------------
    D_diag = A_masked.sum(axis=1)
    W = np.zeros_like(A_masked, dtype=float)
    for i in range(n_tables):
        if D_diag[i] > 0:
            W[i] = A_masked[i] / D_diag[i]
        else:
            # Isolated node (or all neighbours blocked) → self-loop.
            W[i, i] = 1.0

    # ------------------------------------------------------------------
    # Step 6: Compute table-level initial similarities.
    #   For each table, take the MAX similarity among retrieved columns.
    # ------------------------------------------------------------------
    S_dense = np.zeros(n_tables)
    for col_path, sim in initial_similarities.items():
        if "." in col_path:
            t_name = col_path.split(".")[0].lower()
            if t_name in table_to_idx:
                idx = table_to_idx[t_name]
                if sim > S_dense[idx]:
                    S_dense[idx] = sim

    # ------------------------------------------------------------------
    # Step 7: One-step propagation.
    #   S_prop = alpha * S_dense + (1 - alpha) * W @ S_dense
    # ------------------------------------------------------------------
    S_table_propagated = (
        effective_alpha * S_dense
        + (1 - effective_alpha) * np.dot(W, S_dense)
    )

    # ------------------------------------------------------------------
    # Step 8: Map propagated table scores back to column level.
    #   Final column score = alpha * col_sim + (1-alpha) * table_prop_score
    # ------------------------------------------------------------------
    S_propagated: Dict[str, float] = {}
    for col_path, sim in initial_similarities.items():
        if "." in col_path:
            t_name = col_path.split(".")[0].lower()
            if t_name in table_to_idx:
                idx = table_to_idx[t_name]
                S_propagated[col_path] = (
                    effective_alpha * sim
                    + (1 - effective_alpha) * S_table_propagated[idx]
                )
            else:
                S_propagated[col_path] = sim
        else:
            S_propagated[col_path] = sim

    return S_propagated

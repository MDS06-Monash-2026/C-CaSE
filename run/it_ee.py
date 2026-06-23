import math
import re
from typing import Tuple, List

# ---------------------------------------------------------------------------
# SLAYQL IT-EE  (Information-Theoretic Early Exit)
# ---------------------------------------------------------------------------
# ROOT CAUSE OF EX DEGRADATION ("Entropy Fallacy"):
#   The original determine_budget() set dynamic_t_max = 0 whenever
#   entropy < threshold.  For structurally complex queries (dates, JSON,
#   aggregations), the dense retriever can be highly confident about a
#   NARROW set of columns that look relevant—but the LLM still needs at
#   least one round of @schema_retrieval to discover date/string formats,
#   bridging columns, and nested structures.  Bypassing the loop entirely
#   left the LLM generating SQL with missing FORMAT() calls, wrong column
#   aliases, or no JOIN keys → catastrophic EX drop.
#
# FIX:
#   1.  ComplexityAnalyzer — if the query contains temporal, aggregation, or
#       structural signals, force should_early_exit = False regardless of entropy.
#   2.  Safe-Exit mode — even for truly simple queries, allocate a minimal
#       budget of 2 turns so the agent can at least run @explore_schema and
#       @verify_schema before stopping.
# ---------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# Patterns that indicate temporal or date-sensitive queries.
# Matching any of these forces a full exploration loop.
TEMPORAL_PATTERNS = [
    r"\b(month|year|day|hour|minute|second|week|quarter)\b",
    r"\b(last|past|previous|next)\s+\d+\s+(day|week|month|year)s?\b",
    r"\b\d{4}\b",                           # four-digit year literal
    r"\b(date|datetime|timestamp|time)\b",
    r"\b(since|between|before|after|from|to)\b.*\d",
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\b(q[1-4]|quarter)\b",
]

# Patterns that indicate mathematical aggregation.
AGGREGATION_PATTERNS = [
    r"\b(sum|total|average|avg|mean|median|cumulative|running|rolling)\b",
    r"\b(count|number\s+of|how\s+many|frequency)\b",
    r"\b(min|max|minimum|maximum|highest|lowest|top|bottom)\b",
    r"\b(percent|percentage|ratio|rate|growth|change|delta)\b",
    r"\b(rank|ranked|ranking)\b",
]

# Patterns that indicate nested or structural complexity (JSON, subqueries, etc.).
STRUCTURAL_PATTERNS = [
    r"\b(json|nested|array|struct|variant)\b",
    r"\b(subquery|sub-query|inner\s+query|correlated)\b",
    r"\b(for\s+each|grouped\s+by|group\s+by|partition)\b",
    r"\b(pivot|unpivot|cross\s+join|self\s+join)\b",
    r"\b(having|with\s+cte|recursive)\b",
]

# Minimum turn budget when the "Safe Exit" mode is triggered.
# 2 turns allows: turn-0 = @explore_schema / @schema_retrieval,
#                 turn-1 = @verify_schema / @sql_draft before @stop.
SAFE_EXIT_MIN_TURNS: int = 2


def analyze_complexity(query: str) -> dict:
    """
    Examine the natural-language query for signals that demand deeper schema
    exploration, regardless of how confident the dense retriever is.

    Returns
    -------
    dict with keys:
        has_temporal       : bool  – query mentions dates/times
        has_aggregation    : bool  – query mentions aggregation operations
        has_structural     : bool  – query mentions JSON/nested/CTE patterns
        force_full_explore : bool  – True if ANY category fires
        reason             : str   – human-readable explanation for logging
    """
    q_lower = query.lower()
    reasons = []

    has_temporal = any(re.search(p, q_lower) for p in TEMPORAL_PATTERNS)
    has_aggregation = any(re.search(p, q_lower) for p in AGGREGATION_PATTERNS)
    has_structural = any(re.search(p, q_lower) for p in STRUCTURAL_PATTERNS)

    if has_temporal:
        reasons.append("temporal keywords detected (date/time-sensitive query)")
    if has_aggregation:
        reasons.append("aggregation keywords detected (math/grouping required)")
    if has_structural:
        reasons.append("structural keywords detected (JSON/CTE/nested query)")

    force_full_explore = has_temporal or has_aggregation or has_structural

    return {
        "has_temporal": has_temporal,
        "has_aggregation": has_aggregation,
        "has_structural": has_structural,
        "force_full_explore": force_full_explore,
        "reason": "; ".join(reasons) if reasons else "query appears simple",
    }


def calculate_retrieval_entropy(similarities: List[float], temp: float = 0.1) -> float:
    """
    Calculate the normalized Shannon Entropy of the retrieved column similarities.

    A HIGH entropy (→ 1.0) means the retriever is uncertain — scores are spread
    across many columns.  A LOW entropy (→ 0.0) means the retriever is confident
    — one or a few columns dominate.

    Args
    ----
    similarities : list of top-K cosine similarity scores from FAISS.
    temp         : temperature scaling parameter. Lower = sharper distribution.

    Returns
    -------
    Normalized entropy H(P) in [0, 1].
    """
    if not similarities:
        return 0.0

    K = len(similarities)
    if K <= 1:
        # With only one candidate there is no uncertainty by definition.
        return 0.0

    # Apply temperature scaling then softmax to convert distances to probabilities.
    exp_sims = [math.exp(s / temp) for s in similarities]
    sum_exp = sum(exp_sims)

    if sum_exp == 0:
        return 0.0

    probs = [e / sum_exp for e in exp_sims]

    # Shannon entropy H = -Σ p * log(p)
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log(p)

    # Normalize by log(K) so the result is always in [0, 1].
    normalized_entropy = entropy / math.log(K)
    return normalized_entropy


def determine_budget(
    entropy: float,
    query: str = "",
    base_turns: int = 10,
    threshold: float = 0.4,
) -> Tuple[bool, int]:
    """
    Determine the exploration budget for the schema-completion agent.

    DESIGN DECISION — "Safe Exit" instead of hard early exit:
        Even when entropy is below the threshold (high confidence), we no longer
        return (True, 0).  Instead we return (False, SAFE_EXIT_MIN_TURNS).
        This guarantees the agent performs at least one @schema_retrieval and one
        @verify_schema call, which catches:
          • date/timestamp format mismatches
          • missing bridging columns for JOINs
          • column aliases that differ from the schema text

    COMPLEXITY OVERRIDE:
        If ComplexityAnalyzer detects temporal / aggregation / structural signals,
        we force should_early_exit=False and restore the full dynamic budget,
        ignoring the entropy score entirely.

    Args
    ----
    entropy    : Normalized Shannon entropy from calculate_retrieval_entropy().
    query      : The natural-language user question (used by ComplexityAnalyzer).
    base_turns : Baseline maximum turns T_baseline (default 10).
    threshold  : Low-entropy threshold τ below which Safe Exit triggers.

    Returns
    -------
    should_early_exit : bool – ALWAYS False in this refactored version.
                                Kept for API compatibility; consumers can check
                                dynamic_t_max == SAFE_EXIT_MIN_TURNS to detect
                                safe-exit mode.
    dynamic_t_max     : int  – Turn budget to allocate.
    """
    # -----------------------------------------------------------------------
    # Step 1: Run ComplexityAnalyzer if a query string is provided.
    # -----------------------------------------------------------------------
    if query:
        complexity = analyze_complexity(query)
        if complexity["force_full_explore"]:
            # Complexity override: allocate the FULL dynamic budget regardless
            # of how confident the retriever appears.
            dynamic_t_max = max(SAFE_EXIT_MIN_TURNS, round(base_turns * max(entropy, 0.5)))
            print(
                f"[IT-EE] ComplexityAnalyzer OVERRIDE — skipping early exit. "
                f"Reason: {complexity['reason']}. Budget: {dynamic_t_max} turns."
            )
            return False, dynamic_t_max

    # -----------------------------------------------------------------------
    # Step 2: Entropy-based decision.
    # -----------------------------------------------------------------------
    if entropy < threshold:
        # LOW ENTROPY — retriever is confident.
        # Previously this returned (True, 0) — the root cause of EX degradation.
        # Now: Safe Exit — allocate a minimal budget so at least one
        # exploration + one verification call is made.
        print(
            f"[IT-EE] Entropy {entropy:.3f} < threshold {threshold}. "
            f"Safe Exit activated: {SAFE_EXIT_MIN_TURNS} turns allocated "
            f"(instead of bypassing the loop entirely)."
        )
        return False, SAFE_EXIT_MIN_TURNS
    else:
        # HIGH ENTROPY — retriever is uncertain; give proportionally more turns.
        dynamic_t_max = round(base_turns * entropy)
        # Clamp to at least SAFE_EXIT_MIN_TURNS just in case rounding yields 0 or 1.
        dynamic_t_max = max(dynamic_t_max, SAFE_EXIT_MIN_TURNS)
        print(
            f"[IT-EE] Entropy {entropy:.3f} >= threshold {threshold}. "
            f"Full exploration: {dynamic_t_max} turns allocated."
        )
        return False, dynamic_t_max

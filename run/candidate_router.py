"""Deterministic candidate-specific relation routing for SlayQL v1.6+."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple


_TABLE_RE = re.compile(r"^###Table full name:\s*(.*?)\s*$", re.MULTILINE)
_TAIL_MARKERS = (
    "-- SLAYQL_INTERACTION_EVIDENCE_V12 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V13 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V14 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V15 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V16 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V17 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V18 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V19 --",
)


def _key(value: Any) -> str:
    unqualified = str(value or "").lower().split(".")[-1]
    return re.sub(r"[^a-z0-9_]", "", unqualified)


def _split_schema(schema: str) -> Tuple[str, List[Tuple[str, str]], str]:
    matches = list(_TABLE_RE.finditer(schema))
    if not matches:
        return schema, [], ""
    prefix = schema[:matches[0].start()].strip()
    tail_start = len(schema)
    for marker in _TAIL_MARKERS:
        position = schema.find(marker, matches[-1].end())
        if position >= 0:
            tail_start = min(tail_start, position)
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else tail_start
        blocks.append((match.group(1).strip(), schema[match.start():end].strip()))
    tail = schema[tail_start:].strip() if tail_start < len(schema) else ""
    return prefix, blocks, tail


def _table_scores(evidence: Dict[str, Any], available: Sequence[str]) -> Dict[str, float]:
    scores = {_key(table): 0.0 for table in available}
    for entry in evidence.get("lexical_matches", []):
        table = _key(entry.get("table"))
        if table in scores:
            scores[table] = max(scores[table], float(entry.get("score", 0.0)))
    for table in evidence.get("relational_closure", {}).get("seed_tables", []):
        if _key(table) in scores:
            scores[_key(table)] += 1.5
    for link in evidence.get("value_links", []):
        table = _key(link.get("table"))
        if table in scores:
            scores[table] += 8.0 if link.get("exact_match") else 5.0
    return scores


def _graph(evidence: Dict[str, Any], available: Sequence[str]) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]]]:
    allowed = {_key(table) for table in available}
    edges = evidence.get("relationship_catalog", []) or evidence.get("relationships", [])
    adjacency: Dict[str, List[str]] = defaultdict(list)
    retained = []
    seen = set()
    for edge in edges:
        left, right = _key(edge.get("from_table")), _key(edge.get("to_table"))
        identity = (left, _key(edge.get("from_column")), right, _key(edge.get("to_column")))
        if not left or not right or left not in allowed or right not in allowed or identity in seen:
            continue
        seen.add(identity)
        adjacency[left].append(right)
        adjacency[right].append(left)
        retained.append(edge)
    for table in adjacency:
        adjacency[table] = sorted(set(adjacency[table]))
    return dict(adjacency), retained


def _simple_paths(adjacency: Dict[str, List[str]], start: str, target: str, max_edges: int = 4) -> List[Tuple[str, ...]]:
    paths: List[Tuple[str, ...]] = []

    def visit(node: str, path: Tuple[str, ...]) -> None:
        if len(path) - 1 > max_edges:
            return
        if node == target:
            paths.append(path)
            return
        for neighbor in adjacency.get(node, []):
            if neighbor not in path:
                visit(neighbor, path + (neighbor,))

    visit(start, (start,))
    return sorted(paths, key=lambda path: (len(path), path))[:4]


def _v19_mandatory_keys(
    blocks: Sequence[Tuple[str, str]], evidence: Dict[str, Any],
) -> List[str]:
    """Find tables that cannot be hidden by a candidate-specific schema view."""
    available = {_key(table): block for table, block in blocks}
    contract = evidence.get("semantic_contract", {}) or {}
    output = contract.get("output", {}) or {}
    required = {
        _key(column) for column in (
            contract.get("required_columns", [])
            + output.get("physical_output_columns", [])
        ) if _key(column)
    }
    mandatory: List[str] = []
    for key, block in available.items():
        columns = {
            _key(match.group(1))
            for match in re.finditer(r"^\s{4}([^\s(]+)\s+\(Type:", block, re.MULTILINE)
        }
        if columns & required and key not in mandatory:
            mandatory.append(key)
    plan = evidence.get("answer_plan", {}) or {}
    for table in plan.get("likely_tables", []):
        key = _key(table)
        if key in available and key not in mandatory:
            mandatory.append(key)
    return mandatory


def build_route_hypotheses(
    schema: str, evidence: Dict[str, Any], max_routes: int = 4,
) -> Dict[str, Any]:
    _, blocks, _ = _split_schema(schema)
    available_names = [table for table, _ in blocks]
    available = [_key(table) for table in available_names]
    display = {_key(table): table for table in available_names}
    scores = _table_scores(evidence, available_names)
    adjacency, edges = _graph(evidence, available_names)
    anchors = sorted(available, key=lambda table: (-scores.get(table, 0.0), available.index(table)))
    positive = [table for table in anchors if scores.get(table, 0.0) > 0][:6]
    anchors = positive or anchors[:4]
    candidates: List[Tuple[str, ...]] = []

    contract = evidence.get("question_contract", {})
    if not contract.get("join_likely"):
        candidates.extend((table,) for table in anchors[:4])

    # Connector-centred alternatives force different fact/bridge tables when
    # several relations can connect the same question anchors.
    anchor_set = set(anchors)
    for connector in available:
        neighbors = [table for table in adjacency.get(connector, []) if table in anchor_set]
        route = tuple(dict.fromkeys([connector] + sorted(neighbors, key=lambda table: anchors.index(table))))
        if len(route) >= 2:
            candidates.append(route)

    for left_index, left in enumerate(anchors[:5]):
        for right in anchors[left_index + 1:5]:
            candidates.extend(_simple_paths(adjacency, left, right))

    closure = tuple(
        table for table in (_key(value) for value in evidence.get("relational_closure", {}).get("tables", []))
        if table in display
    )
    if closure:
        candidates.append(closure[:5])
    candidates.append(tuple(available[: min(4, len(available))]))

    mandatory: List[str] = []
    if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9":
        mandatory = _v19_mandatory_keys(blocks, evidence)
        if mandatory:
            # Every routed view retains the output-bearing tables.  Route
            # alternatives still differ in connector/anchor choices.
            candidates = [tuple(dict.fromkeys((*mandatory, *route))) for route in candidates]
            candidates.append(tuple(mandatory))

    unique = []
    seen = set()
    for route in candidates:
        normalized = tuple(dict.fromkeys(table for table in route if table in display))
        identity = frozenset(normalized)
        if not normalized or identity in seen:
            continue
        seen.add(identity)
        unique.append(normalized)

    value_tables = {_key(link.get("table")) for link in evidence.get("value_links", [])}

    def route_score(route: Tuple[str, ...]) -> float:
        coverage = sum(scores.get(table, 0.0) for table in route)
        value_coverage = 4.0 * len(set(route) & value_tables)
        connected_bonus = 1.5 if len(route) > 1 else 0.0
        mandatory_bonus = 3.0 * len(set(route) & set(mandatory)) if mandatory else 0.0
        return coverage + value_coverage + connected_bonus + mandatory_bonus - 0.35 * len(route)

    ranked = sorted(unique, key=lambda route: (-route_score(route), len(route), route))
    selected: List[Tuple[str, ...]] = []
    while ranked and len(selected) < max_routes:
        if not selected:
            selected.append(ranked.pop(0))
            continue
        best = max(
            ranked,
            key=lambda route: (
                route_score(route)
                + 4.0 * min(
                    1.0 - len(set(route) & set(chosen)) / max(1, len(set(route) | set(chosen)))
                    for chosen in selected
                ),
                -len(route),
            ),
        )
        ranked.remove(best)
        selected.append(best)

    routes = [
        {
            "route_id": index,
            "tables": [display[table] for table in route],
            "table_keys": list(route),
            "score": route_score(route),
            "mandatory_tables": [display[table] for table in mandatory if table in route],
        }
        for index, route in enumerate(selected)
    ]
    return {
        "schema_version": "1.0", "available_tables": available_names,
        "table_scores": scores, "routes": routes, "relationship_count": len(edges),
    }


def route_for_candidate(plan: Dict[str, Any], candidate_idx: int) -> Dict[str, Any]:
    routes = plan.get("routes", [])
    # Candidate 2 is the recall fallback and sees the complete focused schema.
    if candidate_idx % 5 == 2 or not routes:
        return {
            "route_id": "full", "tables": plan.get("available_tables", []),
            "table_keys": [_key(table) for table in plan.get("available_tables", [])],
            "score": None, "full_schema": True,
        }
    mapping = {0: 0, 1: 1, 3: 2, 4: 3}
    route_index = mapping.get(candidate_idx % 5, 0)
    route = dict(routes[min(route_index, len(routes) - 1)])
    route["full_schema"] = False
    return route


def render_routed_schema(schema: str, route: Dict[str, Any], candidate_idx: int) -> str:
    marker = (
        "SLAYQL_V19_ROUTE" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else
        "SLAYQL_V18_ROUTE" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.8" else
        "SLAYQL_V17_ROUTE" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.7" else
        "SLAYQL_V16_ROUTE"
    )
    prefix, blocks, tail = _split_schema(schema)
    if not blocks or route.get("full_schema"):
        header = (
            f"-- {marker} full --\n"
            "This is the recall fallback. Use the smallest supported relation path and return only requested fields."
        )
        return "\n\n".join(part for part in (header, schema.strip()) if part).rstrip() + "\n"
    allowed = set(route.get("table_keys", []))
    chosen = [block for table, block in blocks if _key(table) in allowed]
    header = (
        f"-- {marker} {route.get('route_id')} CANDIDATE {candidate_idx} --\n"
        f"Assigned relation hypothesis: {route.get('tables', [])}\n"
        + ("Mandatory output-bearing tables are retained in this view. " if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else "")
        + "Use only the assigned tables for this candidate. Do not silently switch to the dominant path; "
        "the full-schema fallback is generated separately."
    )
    return "\n\n".join(
        part for part in [header, prefix, *chosen, tail] if str(part).strip()
    ).rstrip() + "\n"

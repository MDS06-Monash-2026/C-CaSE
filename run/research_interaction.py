"""Query-specific, low-token database evidence for the SlayQL v1.2 harness.

This stage does not call an LLM. It makes small, cached catalog/value probes and
adds their results to the existing schema prompt, allowing the generation agent
to interact with the database without increasing the fixed prompt/turn budget.
"""

from __future__ import annotations

import argparse
import heapq
import hashlib
import json
import os
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from artifact_store import atomic_write_json, atomic_write_text
from semantic_contract import compile_semantic_contract, semantic_contract_prompt


_STOPWORDS = {
    "about", "after", "again", "among", "before", "between", "could", "does",
    "from", "have", "into", "list", "more", "most", "only", "such", "than",
    "that", "their", "there", "these", "they", "this", "those", "under", "what",
    "when", "where", "which", "with", "would", "show", "find", "return", "give",
}

# These words occur in many schemas but are weak evidence for choosing a
# table. Keeping them out of v1.3 linkage prevents generic id/name columns
# from pulling unrelated join edges into every prompt.
_GENERIC_LINK_TOKENS = {
    "column", "data", "date", "field", "full", "id", "name", "number",
    "record", "records", "result", "status", "table", "time", "total",
    "type", "value", "year",
}

_V15_LINK_STOPWORDS = {
    "and", "are", "been", "being", "evidence", "had", "has", "her", "him",
    "his", "indicate", "its", "our", "please", "refers", "she", "the", "was",
    "were", "who", "whom", "whose", "you", "your",
}


def _interaction_marker(compact: bool = False) -> str:
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9":
        return "-- SLAYQL_INTERACTION_EVIDENCE_V19 --"
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.8":
        return "-- SLAYQL_INTERACTION_EVIDENCE_V18 --"
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.7":
        return "-- SLAYQL_INTERACTION_EVIDENCE_V17 --"
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.6":
        return "-- SLAYQL_INTERACTION_EVIDENCE_V16 --"
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.5":
        return "-- SLAYQL_INTERACTION_EVIDENCE_V15 --"
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.4":
        return "-- SLAYQL_INTERACTION_EVIDENCE_V14 --"
    return "-- SLAYQL_INTERACTION_EVIDENCE_V13 --" if compact else "-- SLAYQL_INTERACTION_EVIDENCE_V12 --"


def _question_contract(question: str, compact: bool = False) -> Dict[str, Any]:
    lowered = re.sub(r"\s+", " ", str(question or "").strip().lower())
    ranking_pattern = r"\b(top|bottom|highest|lowest|rank|latest|earliest|chronological|ordered|sorted)\b"
    if compact:
        ranking_pattern = r"\b(top|bottom|highest|lowest|rank(?:ed)?|latest|earliest|chronological|ordered|sorted|fastest|quickest|slowest|tallest|shortest)\b"
    return {
        "operations": [name for name, pattern in (
            ("count", r"\b(how many|number of|count)\b"),
            ("average", r"\b(average|mean)\b"),
            ("sum", r"\b(sum|total|revenue|sales|quantity)\b"),
            ("maximum_or_top", r"\b(maximum|max|highest|top|largest|most)\b"),
            ("minimum_or_bottom", r"\b(minimum|min|lowest|bottom|smallest|least)\b"),
        ) if re.search(pattern, lowered)],
        "grouping": bool(re.search(r"\b(for each|per|group(?:ed)? by|by month|by year|by day)\b", lowered)),
        "ranking_or_order": bool(re.search(ranking_pattern, lowered)),
        "distinct": bool(re.search(r"\b(distinct|unique)\b", lowered)),
        "time_constraint": bool(re.search(r"\b(date|day|week|month|quarter|year|before|after|between|during|ending)\b|\b(?:19|20)\d{2}\b", lowered)),
        "set_behavior": [name for name, pattern in (
            ("exclude", r"\b(excluding|except|without|but not|had no|neither)\b"),
            ("intersect", r"\b(both|in common|intersection)\b"),
            ("combine", r"\b(either|combined|union)\b"),
        ) if re.search(pattern, lowered)],
        "join_likely": bool(re.search(r"\b(join|customer|user|visitor|order|product|author|department|related|each)\b", lowered)),
        "literals": _literal_tokens(question),
    }


def _tokens(text: str) -> List[str]:
    return sorted({
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text or "")
        if token.lower() not in _STOPWORDS
    })


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _sqlite_answer_plan(
    db_path: str,
    question: str,
    tables: List[Dict[str, Any]],
    relationships: List[Dict[str, str]],
    recommended_joins: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Build a small, cached execution plan from database observations.

    These probes are deliberately deterministic and bounded.  They expose
    relationship cardinality and fan-out risks to the SQL generator without
    asking the model to spend another turn discovering basic join facts.
    """
    contract = _question_contract(question, compact=True)
    route_edges = list(dict.fromkeys(
        (str(edge.get("from_table", "")), str(edge.get("from_column", "")),
         str(edge.get("to_table", "")), str(edge.get("to_column", "")))
        for edge in (recommended_joins or relationships)
        if edge.get("from_table") and edge.get("to_table")
    ))[:4]
    table_names = list(dict.fromkeys(
        [str(edge[0]) for edge in route_edges] + [str(edge[2]) for edge in route_edges]
        + _rank_seed_tables(tables, _tokens(question), limit=4)
    ))[:8]
    plan: Dict[str, Any] = {
        "status": "ready",
        "question_contract": contract,
        "likely_tables": table_names,
        "join_routes": [],
        "table_profiles": [],
        "guidance": [
            "Use a join route only when it satisfies a question obligation.",
            "Check fan-out before aggregating; aggregate at the requested grain.",
            "Treat observed cardinalities as evidence, not as a replacement for the question.",
        ],
    }
    if not route_edges and not table_names:
        plan["status"] = "no_relation_probe"
        return plan
    try:
        with sqlite3.connect(db_path) as connection:
            for table_name in table_names:
                try:
                    row_count = int(connection.execute(
                        f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
                    ).fetchone()[0])
                except sqlite3.Error:
                    row_count = None
                plan["table_profiles"].append({"table": table_name, "row_count": row_count})
            for from_table, from_column, to_table, to_column in route_edges:
                left_rows = right_rows = joined_rows = left_distinct = right_distinct = None
                try:
                    left_rows = int(connection.execute(
                        f"SELECT COUNT(*) FROM {_quote_identifier(from_table)}"
                    ).fetchone()[0])
                    right_rows = int(connection.execute(
                        f"SELECT COUNT(*) FROM {_quote_identifier(to_table)}"
                    ).fetchone()[0])
                    joined_rows, left_distinct, right_distinct = connection.execute(
                        "SELECT COUNT(*), COUNT(DISTINCT l_col), COUNT(DISTINCT r_col) "
                        f"FROM (SELECT l.{_quote_identifier(from_column)} AS l_col, "
                        f"r.{_quote_identifier(to_column)} AS r_col "
                        f"FROM {_quote_identifier(from_table)} l "
                        f"JOIN {_quote_identifier(to_table)} r "
                        f"ON l.{_quote_identifier(from_column)} = r.{_quote_identifier(to_column)})"
                    ).fetchone()
                    joined_rows = int(joined_rows)
                    left_distinct = int(left_distinct)
                    right_distinct = int(right_distinct)
                except (sqlite3.Error, TypeError, ValueError):
                    pass
                plan["join_routes"].append({
                    "from_table": from_table, "from_column": from_column,
                    "to_table": to_table, "to_column": to_column,
                    "source": next((str(edge.get("source", "")) for edge in (recommended_joins or relationships)
                                     if str(edge.get("from_table")) == from_table
                                     and str(edge.get("from_column")) == from_column
                                     and str(edge.get("to_table")) == to_table
                                     and str(edge.get("to_column")) == to_column), "unknown"),
                    "left_rows": left_rows, "right_rows": right_rows,
                    "joined_rows": joined_rows, "left_distinct": left_distinct,
                    "right_distinct": right_distinct,
                    "fanout_over_left": round(joined_rows / max(left_rows, 1), 4)
                    if joined_rows is not None and left_rows is not None else None,
                    "fanout_over_right": round(joined_rows / max(right_rows, 1), 4)
                    if joined_rows is not None and right_rows is not None else None,
                    "many_to_many_risk": bool(
                        joined_rows is not None and left_distinct is not None and right_distinct is not None
                        and joined_rows > max(left_distinct, right_distinct)
                    ),
                })
    except (OSError, sqlite3.Error):
        plan["status"] = "probe_failed"
    plan["join_probe_count"] = len(plan["join_routes"])
    return plan


def _literal_tokens(text: str) -> List[str]:
    quoted = re.findall(r"['\"]([^'\"]{1,80})['\"]", text or "")
    return sorted({value.strip().lower() for value in quoted if value.strip()})[:8]


def _short_identifier_tokens(text: str) -> set[str]:
    ignored = {"and", "in", "max", "min", "or", "sql"}
    return {
        token.lower() for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]{1,}\b", text or "")
        if (any(character.isdigit() for character in token) or token.isupper())
        and token.lower() not in ignored
    }


def _field_parts(value: str) -> List[str]:
    return [
        part.lower() for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", str(value).replace("_", " "))
        if part
    ]


def _field_match(token: str, field: str, fuzzy: bool = False) -> bool:
    normalized_token = token.lower().rstrip("s")
    normalized_field = re.sub(r"[^a-z0-9]", "", str(field).lower()).rstrip("s")
    if normalized_token and normalized_token in normalized_field:
        return True
    if not fuzzy or len(normalized_token) < 5:
        return False
    return any(
        len(part) >= 5 and SequenceMatcher(None, normalized_token, part.rstrip("s")).ratio() >= 0.88
        for part in _field_parts(field)
    )


def _relational_closure(
    relationships: List[Dict[str, str]], seed_tables: Iterable[str], max_edges: int = 16,
) -> Dict[str, Any]:
    """Return deterministic shortest join paths connecting question-linked tables."""
    seeds = list(dict.fromkeys(str(table) for table in seed_tables if table))[:6]
    ordered_edges = sorted(
        relationships,
        key=lambda edge: (
            str(edge.get("from_table", "")).lower(), str(edge.get("to_table", "")).lower(),
            str(edge.get("from_column", "")).lower(), str(edge.get("to_column", "")).lower(),
        ),
    )
    adjacency: Dict[str, List[Tuple[str, int]]] = {}
    for index, edge in enumerate(ordered_edges):
        left, right = str(edge.get("from_table", "")), str(edge.get("to_table", ""))
        if not left or not right:
            continue
        adjacency.setdefault(left, []).append((right, index))
        adjacency.setdefault(right, []).append((left, index))

    chosen: List[int] = []

    def add_shortest_path(start: str, target: str) -> None:
        queue: List[Tuple[int, int, str, Tuple[int, ...]]] = [(0, 0, start, ())]
        best: Dict[str, Tuple[int, int]] = {start: (0, 0)}
        target_path: Optional[Tuple[int, ...]] = None
        while queue:
            cost, hops, node, path = heapq.heappop(queue)
            if best.get(node) != (cost, hops):
                continue
            if node == target:
                target_path = path
                break
            for neighbor, edge_index in adjacency.get(node, []):
                edge = ordered_edges[edge_index]
                edge_cost = 1 if edge.get("source") == "foreign_key" else 3
                candidate = (cost + edge_cost, hops + 1)
                if neighbor not in best or candidate < best[neighbor]:
                    best[neighbor] = candidate
                    heapq.heappush(queue, (*candidate, neighbor, path + (edge_index,)))
        if target_path is None:
            return
        for edge_index in target_path:
            if edge_index not in chosen and len(chosen) < max_edges:
                chosen.append(edge_index)

    for left_index, left in enumerate(seeds):
        for right in seeds[left_index + 1:]:
            add_shortest_path(left, right)
    if not chosen:
        per_neighbor: Dict[str, int] = {}
        for seed in seeds:
            for neighbor, index in adjacency.get(seed, []):
                if per_neighbor.get(neighbor, 0) >= 2:
                    continue
                chosen.append(index)
                per_neighbor[neighbor] = per_neighbor.get(neighbor, 0) + 1
                if len(chosen) >= max_edges:
                    break

    edges = [ordered_edges[index] for index in chosen[:max_edges]]
    closure_tables = list(seeds)
    for edge in edges:
        for key in ("from_table", "to_table"):
            table = str(edge.get(key, ""))
            if table and table not in closure_tables:
                closure_tables.append(table)
    return {"seed_tables": seeds, "tables": closure_tables, "edges": edges}


def _rank_seed_tables(tables: List[Dict[str, Any]], link_tokens: Iterable[str], limit: int = 6) -> List[str]:
    """Rank tables by distinct question concepts covered, avoiding wide-table bias."""
    tokens = set(link_tokens)
    ranked = []
    for table in tables:
        table_name = str(table.get("name", ""))
        fields = [table_name] + [
            str(column.get("name", "") if isinstance(column, dict) else column)
            for column in table.get("columns", [])
        ]
        coverage = {token for token in tokens if any(_field_match(token, field, fuzzy=True) for field in fields)}
        if coverage:
            normalized_table = table_name.lower().rstrip("s")
            table_hits = sum(
                _field_match(token, normalized_table) for token in coverage
            )
            exact_columns = sum(
                token == field.lower() for token in coverage for field in fields[1:]
            )
            ranked.append((-len(coverage), -table_hits, -exact_columns, table_name.lower(), table_name))
    return [entry[-1] for entry in sorted(ranked)[:limit]]


def _sqlite_catalog(db_path: str, question: str, compact: bool = False) -> Dict[str, Any]:
    tokens = set(_tokens(question))
    link_tokens = tokens - _GENERIC_LINK_TOKENS if compact else tokens
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.5", "1.6", "1.7", "1.8", "1.9"}:
        link_tokens -= _V15_LINK_STOPWORDS
        link_tokens |= _short_identifier_tokens(question)
    literals = _literal_tokens(question)
    tables: List[Dict[str, Any]] = []
    relationships: List[Dict[str, str]] = []
    lexical_matches: List[Dict[str, Any]] = []
    value_probes: List[Dict[str, Any]] = []
    has_relational_catalog = compact and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.5", "1.6", "1.7", "1.8", "1.9"}
    with sqlite3.connect(db_path) as connection:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        all_columns: List[Tuple[str, str, str]] = []
        for (table_name,) in table_rows:
            escaped = str(table_name).replace("'", "''")
            columns = []
            for row in connection.execute(f"PRAGMA table_info('{escaped}')").fetchall():
                _, name, col_type, not_null, default, primary_key = row
                column = {
                    "name": str(name), "type": str(col_type or "unknown"),
                    "primary_key": bool(primary_key), "not_null": bool(not_null),
                }
                columns.append(column)
                all_columns.append((str(table_name), str(name), str(col_type or "")))
            tables.append({"name": str(table_name), "columns": columns})
            for row in connection.execute(f"PRAGMA foreign_key_list('{escaped}')").fetchall():
                relationships.append({
                    "from_table": str(table_name), "from_column": str(row[3]),
                    "to_table": str(row[2]), "to_column": str(row[4]), "source": "foreign_key",
                })

        # Conservative inferred edges help databases without declared FKs.
        inferred_edges = set()
        for left in all_columns:
            left_name = left[1].lower().replace("-", "_")
            if not left_name.endswith("_id"):
                continue
            for right in all_columns:
                right_name = right[1].lower().replace("-", "_")
                if left[0] != right[0] and left_name == right_name:
                    edge = (left[0], left[1], right[0], right[1])
                    if edge not in inferred_edges:
                        inferred_edges.add(edge)
                        relationships.append({
                            "from_table": left[0], "from_column": left[1],
                            "to_table": right[0], "to_column": right[1], "source": "inferred_id",
                        })

        for table in tables:
            table_name = table["name"]
            table_score = sum(_field_match(token, table_name, fuzzy=has_relational_catalog) for token in link_tokens)
            table_entry_added = False
            for column_index, column in enumerate(table["columns"]):
                column_name = column["name"]
                column_score = sum(_field_match(token, column_name, fuzzy=has_relational_catalog) for token in link_tokens)
                reason = "question_token_overlap"
                if has_relational_catalog:
                    score = column_score
                    if score == 0 and table_score and not table_entry_added and (column["primary_key"] or column_index == 0):
                        score = table_score
                        reason = "question_table_overlap"
                        table_entry_added = True
                else:
                    score = table_score + column_score
                if score:
                    lexical_matches.append({
                        "table": table_name, "column": column_name, "score": score,
                        "reason": reason,
                    })
                # Probe only text-like columns whose names overlap the question or
                # whose type is textual; cap probes to avoid scanning large tables.
                probe_limit = 6 if compact else 12
                if len(value_probes) >= probe_limit:
                    continue
                type_name = column["type"].upper()
                if not any(marker in type_name for marker in ("CHAR", "TEXT", "CLOB")):
                    continue
                if score == 0 and not literals:
                    continue
                if compact and not literals and score < 2:
                    continue
                sql = (
                    f"SELECT {_quote_identifier(column_name)} FROM {_quote_identifier(table_name)} "
                    f"WHERE {_quote_identifier(column_name)} IS NOT NULL LIMIT 5"
                )
                try:
                    values = []
                    probe_reason = "sample"
                    if literals:
                        literal_sql = (
                            f"SELECT {_quote_identifier(column_name)} FROM {_quote_identifier(table_name)} "
                            f"WHERE {_quote_identifier(column_name)} IS NOT NULL "
                            f"AND LOWER(CAST({_quote_identifier(column_name)} AS TEXT)) LIKE ? LIMIT 5"
                        )
                        for literal in literals[:2]:
                            values.extend(
                                row[0] for row in connection.execute(literal_sql, (f"%{literal}%",)).fetchall()
                            )
                        if values:
                            sql = literal_sql
                            probe_reason = "question_literal_match"
                    if not values:
                        values = [row[0] for row in connection.execute(sql).fetchall()]
                    values = list(dict.fromkeys(values))
                except sqlite3.Error:
                    values = []
                    probe_reason = "failed"
                if values:
                    value_probes.append({
                        "table": table_name, "column": column_name,
                        "values": [str(value)[:80] for value in values],
                        "probe": sql, "reason": probe_reason,
                    })

    lexical_matches.sort(key=lambda item: (-item["score"], item["table"], item["column"]))
    relationship_catalog = list(relationships)
    matched_table_order = list(dict.fromkeys(
        entry["table"] for entry in lexical_matches[:(12 if compact else 24)]
    ))
    matched_tables = set(matched_table_order)
    relational_closure: Dict[str, Any] = {"seed_tables": [], "tables": [], "edges": []}
    if compact:
        if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.5", "1.6", "1.7", "1.8", "1.9"}:
            seed_tables = _rank_seed_tables(tables, link_tokens)
            relational_closure = _relational_closure(relationships, seed_tables, max_edges=16)
            relationships = relational_closure["edges"]
            recommended_joins = relationships[:12]
        elif len(matched_tables) > 1:
            relevant_relationships = [
                edge for edge in relationships
                if edge["from_table"] in matched_tables and edge["to_table"] in matched_tables
            ]
            relationships = relevant_relationships[:10]
            recommended_joins = relationships[:8]
        else:
            relevant_relationships = [
                edge for edge in relationships
                if edge["from_table"] in matched_tables or edge["to_table"] in matched_tables
            ]
            relationships = relevant_relationships[:10]
            recommended_joins = relationships[:8]
    else:
        recommended_joins = [
            edge for edge in relationships
            if edge["from_table"] in matched_tables or edge["to_table"] in matched_tables
        ][:24]
    answer_plan = _sqlite_answer_plan(
        db_path, question, tables, relationship_catalog, recommended_joins
    ) if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.8", "1.9"} else {}
    return {
        "dialect": "sqlite", "database": str(Path(db_path).resolve()),
        "tables": tables, "relationships": relationships[:(10 if compact else 120)],
        "lexical_matches": lexical_matches[:(20 if compact else 40)], "recommended_joins": recommended_joins,
        "relational_closure": relational_closure,
        "relationship_catalog": relationship_catalog[:120] if has_relational_catalog else [],
        "literal_hints": literals, "question_contract": _question_contract(question, compact=compact),
        "value_probes": value_probes, "answer_plan": answer_plan,
        "interaction_mode": "answer_plan_execution_grounded" if answer_plan else (
            "selective_query_linked" if compact else "broad_query_evidence"
        ),
    }


def _cloud_catalog(item: Dict[str, Any], base_dir: Path, compact: bool = False) -> Dict[str, Any]:
    dialect = "bigquery" if str(item.get("backend", "")).lower() in {"bigquery", "bq"} else "snowflake"
    document_candidates = (
        base_dir / "documents" / f"{dialect}.json",
        base_dir / "run" / "documents" / f"{dialect}.json",
    )
    document = next((candidate for candidate in document_candidates if candidate.exists()), document_candidates[0])
    try:
        payload = json.loads(document.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    database = payload.get(item.get("db_name"), {}) if isinstance(payload, dict) else {}
    tables = []
    for table_name, metadata in database.items() if isinstance(database, dict) else []:
        columns = metadata.get("columns", {}) if isinstance(metadata, dict) else {}
        tables.append({"name": str(table_name), "columns": [str(name) for name in columns]})
    tokens = set(_tokens(item.get("question", "")))
    if compact:
        tokens -= _GENERIC_LINK_TOKENS
    if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.5", "1.6", "1.7", "1.8", "1.9"}:
        tokens -= _V15_LINK_STOPWORDS
        tokens |= _short_identifier_tokens(item.get("question", ""))
    matches = [
        {"table": table["name"], "column": column, "score": sum(token in f"{table['name']} {column}".lower() for token in tokens), "reason": "document_token_overlap"}
        for table in tables for column in table["columns"]
        if any(token in f"{table['name']} {column}".lower() for token in tokens)
    ]
    matches.sort(key=lambda entry: (-entry["score"], entry["table"], entry["column"]))
    return {
        "dialect": dialect, "database": item.get("db_name"), "tables": tables,
        "relationships": [], "recommended_joins": [], "lexical_matches": matches[:(20 if compact else 40)],
        "literal_hints": _literal_tokens(item.get("question", "")),
        "question_contract": _question_contract(item.get("question", ""), compact=compact), "value_probes": [],
        "answer_plan": {
            "status": "cloud_probe_unavailable",
            "question_contract": _question_contract(item.get("question", ""), compact=True),
            "likely_tables": [str(table.get("name")) for table in tables[:8]],
            "join_routes": [], "table_profiles": [],
            "guidance": [
                "Use the declared relation metadata and execution results to validate joins.",
                "Do not infer cardinality that was not observed from the backend.",
            ],
        } if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.8", "1.9"} else {},
        "interaction_mode": "selective_query_linked" if compact else "broad_query_evidence",
    }


def _append_bm25_value_links(
    evidence: Dict[str, Any], item: Dict[str, Any], instance_id: str, output: Path,
) -> Dict[str, Any]:
    if os.environ.get("SLAYQL_RESEARCH_VERSION") not in {"1.5", "1.6", "1.7", "1.8", "1.9"} or not item.get("db_name"):
        return evidence
    trace_dir = output / "interaction_value_traces"
    try:
        from value_grounder import get_value_hints

        get_value_hints(
            query=item.get("question", ""), db_id=item.get("db_name", ""),
            indices_dir=os.environ.get("SLAYQL_BM25_DIR", "bm25_indices"),
            threshold=float(os.environ.get("SLAYQL_BM25_THRESHOLD", "5.0")),
            normalized=os.environ.get("SLAYQL_BM25_NORMALIZED", "0") == "1",
            max_hints=5, trace_id=instance_id, trace_dir=str(trace_dir),
        )
        trace_path = trace_dir / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', instance_id)}.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {}
    except (ImportError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return evidence

    value_links = []
    for match in trace.get("matches", []):
        if not match.get("admitted"):
            continue
        parts = str(match.get("column", "")).split(".")
        if len(parts) < 2:
            continue
        table, column = parts[-2], parts[-1]
        value_links.append({
            "table": table, "column": column, "literal": match.get("literal"),
            "matched_value": match.get("matched_value"), "exact_match": bool(match.get("exact_match")),
            "score": float(match.get("raw_score", 0.0)), "reason": "bm25_value_match",
        })
    value_links = value_links[:6]
    if not value_links:
        return evidence
    evidence["value_links"] = value_links
    for link in value_links:
        evidence.setdefault("lexical_matches", []).append({
            "table": link["table"], "column": link["column"],
            "score": 6.0 if link["exact_match"] else 3.0, "reason": "bm25_value_match",
        })
    evidence["lexical_matches"] = sorted(
        evidence["lexical_matches"],
        key=lambda entry: (-float(entry.get("score", 0.0)), str(entry.get("table", "")), str(entry.get("column", ""))),
    )[:26]
    value_tables = [link["table"] for link in value_links]
    existing_seeds = evidence.get("relational_closure", {}).get("seed_tables", [])
    seeds = list(dict.fromkeys(value_tables + existing_seeds))[:6]
    evidence["relational_closure"] = _relational_closure(
        evidence.get("relationship_catalog", []), seeds, max_edges=16,
    )
    evidence["relationships"] = evidence["relational_closure"]["edges"]
    evidence["recommended_joins"] = evidence["relationships"][:12]
    evidence["interaction_mode"] = "relational_closure_value_linked"
    return evidence


def _context_text(evidence: Dict[str, Any], max_chars: int, compact: bool = False) -> str:
    relationships = evidence.get("relationships", [])
    recommended_joins = evidence.get("recommended_joins", [])
    matches = evidence.get("lexical_matches", [])[:(10 if compact else 16)]
    probes = evidence.get("value_probes", [])[:(6 if compact else 8)]
    lines = [
        _interaction_marker(compact),
        "Use this query-specific database evidence as observations, not assumptions.",
        f"Dialect: {evidence.get('dialect', 'unknown')}",
    ]
    contract = evidence.get("question_contract", {})
    if contract:
        lines.extend([
            "Question obligations to verify:",
            f"- Operations: {contract.get('operations') or ['direct projection']}",
            f"- Grouping={contract.get('grouping')}; ranking/order={contract.get('ranking_or_order')}; "
            f"distinct={contract.get('distinct')}; time constraint={contract.get('time_constraint')}",
            f"- Join likely={contract.get('join_likely')}; set behavior={contract.get('set_behavior') or ['none detected']}",
            "- Prefer the linked fields below; do not invent a join or filter that the question and schema do not support.",
        ])
    if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.4":
        lines.extend([
            "Question plan (v1.4):",
            "- Resolve the requested entity and output grain before choosing tables.",
            "- Treat relationship edges as join candidates; verify endpoint columns in the schema.",
            "- Treat value probes as database observations, never as permission to relax the question filter.",
        ])
    if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.5":
        closure = evidence.get("relational_closure", {})
        lines.extend([
            "Question plan (v1.5 relational multi-path):",
            "- Fix the requested output columns and row grain before choosing a relation path.",
            "- Compare plausible relation paths; closure edges may include a required bridge table.",
            "- Do not add DISTINCT, latest-per-entity, concatenation, or deduplication unless requested.",
            f"- Relational closure tables: {closure.get('tables') or ['none discovered']}",
        ])
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"}:
        closure = evidence.get("relational_closure", {})
        version = os.environ.get("SLAYQL_RESEARCH_VERSION")
        lines.extend([
            f"Question plan (v{version} semantic contract and routed candidates):",
            "- Follow dataset evidence literally; do not replace its formula or row semantics with a plausible alternative.",
            "- Return the minimal requested projection; helper fields used to filter, join, group, or order stay hidden.",
            "- Candidate relation routes are assigned later; the full-schema fallback preserves recall.",
            f"- Relational closure tables: {closure.get('tables') or ['none discovered']}",
        ])
        semantic = evidence.get("semantic_contract")
        if semantic:
            lines.append(semantic_contract_prompt(semantic))
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.8", "1.9"}:
        closure = evidence.get("relational_closure", {})
        plan = evidence.get("answer_plan", {})
        lines.extend([
            f"Question plan (v{os.environ.get('SLAYQL_RESEARCH_VERSION')} execution-grounded answer plan):",
            "- Treat the requested output grain and dataset evidence as authoritative.",
            "- Prefer a measured join route when it satisfies the question; avoid joins that introduce fan-out.",
            "- Validate filters before aggregation and keep helper columns out of the final projection.",
            f"- Relational closure tables: {closure.get('tables') or ['none discovered']}",
        ])
        if plan:
            lines.append(f"- Answer-plan status: {plan.get('status', 'unknown')}; likely tables: {plan.get('likely_tables') or ['none']}")
            for route in plan.get("join_routes", [])[:6]:
                lines.append(
                    f"- Measured route {route.get('from_table')}.{route.get('from_column')} = "
                    f"{route.get('to_table')}.{route.get('to_column')}: "
                    f"joined_rows={route.get('joined_rows')}, fanout_left={route.get('fanout_over_left')}, "
                    f"fanout_right={route.get('fanout_over_right')}, many_to_many_risk={route.get('many_to_many_risk')}"
                )
            for profile in plan.get("table_profiles", [])[:6]:
                lines.append(f"- Observed table size {profile.get('table')}: {profile.get('row_count')} rows")
    if relationships:
        lines.append("Relationship edges:")
        lines.extend(
            f"- {edge['from_table']}.{edge['from_column']} -> {edge['to_table']}.{edge['to_column']} ({edge['source']})"
            for edge in relationships[:(10 if compact else 24)]
        )
    if recommended_joins:
        lines.append("Priority join path candidates (verify against the question):")
        lines.extend(
            f"- {edge['from_table']}.{edge['from_column']} = {edge['to_table']}.{edge['to_column']} ({edge['source']})"
            for edge in recommended_joins[:(8 if compact else 24)]
        )
    if matches:
        lines.append("Question-linked fields:")
        lines.extend(f"- {entry['table']}.{entry['column']} (score={entry['score']})" for entry in matches)
    if probes:
        lines.append("Observed sample values:")
        lines.extend(f"- {probe['table']}.{probe['column']}: {probe['values']}" for probe in probes)
    if evidence.get("value_links"):
        lines.append("High-confidence value-linked fields:")
        lines.extend(
            f"- {link['literal']} -> {link['table']}.{link['column']} = {link['matched_value']}"
            for link in evidence["value_links"][:6]
        )
    if evidence.get("literal_hints"):
        lines.append(f"Question literals to verify: {evidence['literal_hints']}")
    return "\n".join(lines)[:max_chars] + "\n"


def build(
    data_file: str, schema_dir: str, output_root: str, base_dir: str = ".",
    max_context_chars: int = 12000, compact: bool = False,
) -> Dict[str, Any]:
    data = json.loads(Path(data_file).read_text(encoding="utf-8"))
    output = Path(output_root)
    evidence_dir = output / "interaction"
    context_dir = output / "interaction_context"
    manifest_items = []
    for instance_id, item in sorted(data.items()):
        db_path = item.get("db_path")
        if db_path and Path(db_path).is_file():
            evidence = _sqlite_catalog(str(Path(db_path)), item.get("question", ""), compact=compact)
        else:
            evidence = _cloud_catalog(item, Path(base_dir), compact=compact)
        evidence = _append_bm25_value_links(evidence, item, instance_id, output)
        if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"}:
            evidence["semantic_contract"] = compile_semantic_contract(item)
            evidence["interaction_mode"] = (
                "answer_plan_execution_grounded_tournament"
                if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.8", "1.9"} else "prompt_learning_execution_grounded_repair"
                if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.7"
                else "semantic_contract_relational_routes"
            )
        if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.8", "1.9"} and db_path and Path(db_path).is_file():
            evidence["answer_plan"] = _sqlite_answer_plan(
                str(Path(db_path)), item.get("question", ""), evidence.get("tables", []),
                evidence.get("relationship_catalog", []) or evidence.get("relationships", []),
                evidence.get("recommended_joins", []),
            )
        evidence["instance_id"] = instance_id
        evidence["question_hash"] = hashlib.sha256(str(item.get("question", "")).encode("utf-8")).hexdigest()
        atomic_write_json(str(evidence_dir / f"{instance_id}.json"), evidence)
        context = _context_text(evidence, max_context_chars, compact=compact)
        atomic_write_text(str(context_dir / f"{instance_id}.txt"), context)
        schema_path = Path(schema_dir) / f"{instance_id}.txt"
        if schema_path.exists():
            current = schema_path.read_text(encoding="utf-8", errors="replace")
            marker = _interaction_marker(compact)
            if marker not in current:
                atomic_write_text(str(schema_path), current.rstrip() + "\n\n" + context)
        manifest_items.append({
            "instance_id": instance_id,
            "evidence_path": str((evidence_dir / f"{instance_id}.json").resolve()),
            "context_path": str((context_dir / f"{instance_id}.txt").resolve()),
            "relationship_count": len(evidence.get("relationships", [])),
            "probe_count": len(evidence.get("value_probes", [])),
            "answer_plan_join_probe_count": len(evidence.get("answer_plan", {}).get("join_routes", [])),
            "interaction_mode": evidence.get("interaction_mode"),
        })
    manifest = {
        "schema_version": (
            "1.9" if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else
            "1.8" if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.8" else
            "1.7" if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.7" else
            "1.6" if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.6" else
            "1.5" if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.5" else
            "1.4" if compact and os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.4" else
            "1.3" if compact else "1.2"
        ), "stage": "interaction_context",
        "record_count": len(manifest_items), "instances": manifest_items,
        "max_context_chars": max_context_chars, "compact": compact,
    }
    atomic_write_json(str(output / "interaction_manifest.json"), manifest)
    return manifest


def append_cached(output_root: str, schema_dir: str) -> Dict[str, Any]:
    output = Path(output_root)
    context_dir = output / "interaction_context"
    appended = 0
    skipped = 0
    for context_path in sorted(context_dir.glob("*.txt")):
        schema_path = Path(schema_dir) / context_path.name
        if not schema_path.exists():
            skipped += 1
            continue
        current = schema_path.read_text(encoding="utf-8", errors="replace")
        if any(marker in current for marker in (
            "-- SLAYQL_INTERACTION_EVIDENCE_V12 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V13 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V14 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V15 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V16 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V17 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V18 --",
            "-- SLAYQL_INTERACTION_EVIDENCE_V19 --",
        )):
            skipped += 1
            continue
        atomic_write_text(str(schema_path), current.rstrip() + "\n\n" + context_path.read_text(encoding="utf-8") )
        appended += 1
    manifest_path = output / "interaction_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest["appended_schema_dirs"] = sorted(set(manifest.get("appended_schema_dirs", [])) | {str(Path(schema_dir).resolve())})
    manifest["appended_count"] = int(manifest.get("appended_count", 0)) + appended
    manifest["skipped_count"] = int(manifest.get("skipped_count", 0)) + skipped
    atomic_write_json(str(manifest_path), manifest)
    return {"appended": appended, "skipped": skipped, "schema_dir": str(Path(schema_dir).resolve())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cached SlayQL interaction evidence")
    parser.add_argument("--data_file", required=True)
    parser.add_argument("--schema_dir", required=True)
    parser.add_argument("--output_root", required=True)
    parser.add_argument("--base_dir", default=".")
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--append-cached", action="store_true")
    parser.add_argument("--compact", action="store_true", help="Use versioned selective linkage and compact evidence")
    args = parser.parse_args()
    if args.append_cached:
        result = append_cached(args.output_root, args.schema_dir)
        print(f"Cached interaction evidence appended: {result['appended']} schemas", flush=True)
    else:
        values = vars(args).copy()
        values.pop("append_cached", None)
        manifest = build(**values)
        print(f"Interaction evidence ready: {manifest['record_count']} instances", flush=True)


if __name__ == "__main__":
    main()

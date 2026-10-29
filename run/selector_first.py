"""Conservative selector-first v1.1 candidate selection.

This keeps all generated/executed v1 candidates, applies mechanical safety
gates, scores evidence already present, and calls a model only on disagreement.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import random
import re
import sqlite3
import subprocess
import tempfile
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from openai import OpenAI

from artifact_store import atomic_write_json, atomic_write_text, sha256_file
from semantic_validator import dataframe_signature
from semantic_contract import assess_semantic_contract, compile_semantic_contract, physical_projection_check
from usage_accounting import record_response_usage

try:
    import sqlglot
except ImportError:  # pragma: no cover - requirements includes sqlglot
    sqlglot = None


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_frame(path: Path) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError):
        return None


def _dialect(instance_id: str) -> str:
    if instance_id.startswith(("bq", "ga")):
        return "bigquery"
    if instance_id.startswith("sf"):
        return "snowflake"
    return "sqlite"


def _canonical_sql(sql: str, instance_id: str) -> str:
    if not sql:
        return ""
    if sqlglot is None:
        return re.sub(r"\s+", " ", sql.strip().lower())
    try:
        return "; ".join(
            expression.sql(dialect=_dialect(instance_id), pretty=False)
            for expression in sqlglot.parse(sql, read=_dialect(instance_id))
        )
    except Exception:
        return re.sub(r"\s+", " ", sql.strip().lower())


def _parse_sql(sql: str, instance_id: str) -> Optional[Any]:
    if not sql or sqlglot is None:
        return None
    try:
        expressions = sqlglot.parse(sql, read=_dialect(instance_id))
        return expressions if expressions and all(expression is not None for expression in expressions) else None
    except Exception:
        return None


def _node_sql(node: Any, instance_id: str) -> str:
    if node is None:
        return ""
    try:
        return re.sub(r"\s+", " ", node.sql(dialect=_dialect(instance_id), pretty=False)).strip().lower()
    except Exception:
        return re.sub(r"\s+", " ", str(node)).strip().lower()


def _candidate_structure(sql: str, instance_id: str) -> Dict[str, Any]:
    statements = _parse_sql(sql, instance_id) or []
    structure: Dict[str, Any] = {
        "statement_count": len(statements),
        "statement_types": [type(statement).__name__.lower() for statement in statements],
        "query_only": bool(statements) and all(isinstance(statement, sqlglot.exp.Query) for statement in statements),
        "tables": [], "columns": [], "joins": [], "predicates": [],
        "projections": [], "projection_aliases": [], "projection_count": 0,
        "aggregations": [], "group_by": [], "order_by": [], "limit": None,
        "set_operations": [], "literals": [], "time_literals": [],
        "select_distinct": False, "aggregate_distinct": False,
        "division_count": 0, "denominator_protected": False,
        "has_time_filter": False, "grain": "unknown",
    }
    if not statements:
        return structure

    cte_names = {
        str(cte.alias_or_name).lower()
        for statement in statements
        for cte in statement.find_all(sqlglot.exp.CTE)
        if cte.alias_or_name
    }
    table_names = {
        str(table.name).lower()
        for statement in statements
        for table in statement.find_all(sqlglot.exp.Table)
        if table.name and str(table.name).lower() not in cte_names
    }
    structure["tables"] = sorted(table_names)
    structure["columns"] = sorted({
        str(column.name).lower()
        for statement in statements
        for column in statement.find_all(sqlglot.exp.Column)
        if column.name
    })

    joins = []
    for statement in statements:
        for join in statement.find_all(sqlglot.exp.Join):
            joins.append({
                "side": str(join.args.get("side") or "").lower(),
                "kind": str(join.args.get("kind") or "inner").lower(),
                "table": _node_sql(join.this, instance_id),
                "on": _node_sql(join.args.get("on"), instance_id),
            })
    structure["joins"] = joins

    predicates = []
    for statement in statements:
        for node_type in (sqlglot.exp.Where, sqlglot.exp.Having, sqlglot.exp.Qualify):
            predicates.extend(_node_sql(node.this, instance_id) for node in statement.find_all(node_type))
    structure["predicates"] = sorted(set(filter(None, predicates)))

    selects = [select for statement in statements for select in statement.find_all(sqlglot.exp.Select)]
    outer_select = selects[0] if selects else None
    if outer_select is not None:
        structure["projections"] = [_node_sql(node, instance_id) for node in outer_select.expressions]
        structure["projection_aliases"] = [
            str(node.alias_or_name).lower() for node in outer_select.expressions if node.alias_or_name
        ]
        structure["projection_count"] = len(outer_select.expressions)
        structure["select_distinct"] = bool(outer_select.args.get("distinct"))

    aggregate_nodes = [
        aggregate
        for statement in statements
        for aggregate in statement.find_all(sqlglot.exp.AggFunc)
    ]
    structure["aggregations"] = sorted({str(aggregate.key).lower() for aggregate in aggregate_nodes})
    structure["aggregate_distinct"] = any(
        next(aggregate.find_all(sqlglot.exp.Distinct), None) is not None
        for aggregate in aggregate_nodes
    )
    groups = [
        _node_sql(expression, instance_id)
        for statement in statements
        for group in statement.find_all(sqlglot.exp.Group)
        for expression in group.expressions
    ]
    structure["group_by"] = sorted(set(filter(None, groups)))

    ordering = []
    for statement in statements:
        for order in statement.find_all(sqlglot.exp.Order):
            for ordered in order.expressions:
                ordering.append({
                    "expression": _node_sql(ordered.this, instance_id),
                    "descending": bool(ordered.args.get("desc")),
                })
    structure["order_by"] = ordering
    limit = next((node for statement in statements for node in statement.find_all(sqlglot.exp.Limit)), None)
    if limit is not None:
        limit_expression = limit.args.get("expression")
        rendered = _node_sql(limit_expression, instance_id)
        structure["limit"] = int(rendered) if rendered.isdigit() else rendered or None

    structure["set_operations"] = sorted({
        type(node).__name__.lower()
        for statement in statements
        for node in statement.walk()
        if type(node).__name__.lower() in {"union", "intersect", "except"}
    })
    literals = sorted({
        str(literal.this).strip().lower()
        for statement in statements
        for literal in statement.find_all(sqlglot.exp.Literal)
    })
    structure["literals"] = literals
    structure["time_literals"] = [
        literal for literal in literals
        if re.search(r"(?:19|20)\d{2}|\d{1,2}[-/:]\d{1,2}|\d{2}:\d{2}", literal)
    ]
    structure["division_count"] = sum(
        1 for statement in statements for _ in statement.find_all(sqlglot.exp.Div)
    )
    upper_sql = sql.upper()
    structure["denominator_protected"] = any(token in upper_sql for token in ("NULLIF(", "SAFE_DIVIDE(", "CASE "))
    structure["has_time_filter"] = bool(
        structure["time_literals"]
        or re.search(r"\b(date|time|timestamp|datetime|interval|extract|date_trunc)\b", sql, re.IGNORECASE)
    )
    if structure["set_operations"]:
        structure["grain"] = "set"
    elif structure["group_by"]:
        structure["grain"] = "grouped"
    elif structure["aggregations"]:
        structure["grain"] = "scalar_aggregate"
    else:
        structure["grain"] = "detail"
    return structure


def _sql_references(sql: str, instance_id: str) -> Dict[str, List[str]]:
    structure = _candidate_structure(sql, instance_id)
    return {"tables": structure["tables"], "columns": structure["columns"]}


@lru_cache(maxsize=256)
def _sqlite_schema_catalog(db_path: str) -> Dict[str, Any]:
    tables: Dict[str, List[str]] = {}
    try:
        with sqlite3.connect(db_path) as connection:
            names = connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for (table_name,) in names:
                escaped = str(table_name).replace("'", "''")
                columns = connection.execute(f"PRAGMA table_info('{escaped}')").fetchall()
                tables[str(table_name).lower()] = sorted(str(row[1]).lower() for row in columns)
    except (OSError, sqlite3.Error):
        return {"complete": False, "tables": {}}
    return {"complete": True, "tables": tables}


def _schema_catalog(dataset_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    db_path = str((dataset_item or {}).get("db_path") or "")
    if db_path and Path(db_path).is_file():
        return _sqlite_schema_catalog(str(Path(db_path).resolve()))
    return {"complete": False, "tables": {}}


def _question_contract(question: str) -> Dict[str, Any]:
    lowered = re.sub(r"\s+", " ", (question or "").strip().lower())
    quoted_literals = sorted({
        value.strip().lower()
        for value in re.findall(r"['\"]([^'\"]+)['\"]", question or "")
        if value.strip()
    })
    date_literals = sorted(set(
        re.findall(
            r"\b(?:19|20)\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|"
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)"
            r"\s+\d{1,2}(?:,\s*(?:19|20)\d{2})?",
            lowered,
        )
    ))
    top_match = re.search(r"\b(?:top|bottom|first|last)\s+(\d+)\b", lowered)
    ordinal_match = re.search(
        r"\b(?:ranked|placed|finished|came in)\s+(?:the\s+)?(\d+)(?:st|nd|rd|th)\b",
        lowered,
    )
    expected_aggregations = []
    for name, pattern in (
        ("count", r"\b(how many|number of|count)\b"),
        ("avg", r"\b(average|mean)\b"),
        ("sum", r"\b(sum|total (?:amount|value|revenue|sales|cost|price|duration|distance|quantity))\b"),
        ("max", r"\b(maximum|max|highest|largest|most)\b"),
        ("min", r"\b(minimum|min|lowest|smallest|least)\b"),
    ):
        if re.search(pattern, lowered):
            expected_aggregations.append(name)
    expects_grouping = bool(re.search(
        r"\b(for each|per each|grouped by|broken down by|per (?!cent\b|centage\b))",
        lowered,
    ))
    ranking_pattern = r"\b(top|bottom|highest|lowest|most|least|rank|latest|earliest|newest|oldest)\b"
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        ranking_pattern = r"\b(top|bottom|highest|lowest|most|least|rank(?:ed)?|latest|earliest|newest|oldest|fastest|quickest|slowest|tallest|shortest)\b"
    expects_ranking = bool(re.search(ranking_pattern, lowered))
    expects_order = expects_ranking or bool(re.search(r"\b(order(?:ed)?|sort(?:ed)?|chronological)\b", lowered))
    expects_distinct = bool(re.search(r"\b(distinct|unique)\b", lowered))
    expects_time_filter = bool(date_literals or re.search(
        r"\b(date|day|week|month|quarter|year|hour|minute|time|before|after|between|ending on)\b",
        lowered,
    ))
    expects_ratio = bool(re.search(r"\b(ratio|percentage|percent|rate|share|proportion)\b", lowered))
    set_intent = []
    if re.search(r"\b(excluding|except|but not|without|had no|neither)\b", lowered):
        set_intent.append("exclusion")
    if re.search(r"\b(both|intersection|in common)\b", lowered):
        set_intent.append("intersection")
    if re.search(r"\b(either|combined|union)\b", lowered):
        set_intent.append("union")
    expects_entity_name = bool(re.search(
        r"\b(full\s+name|name|who|which\s+(?:person|player|racer|driver|customer))\b",
        lowered,
    ))
    if expects_grouping:
        expected_grain = "grouped"
    elif expected_aggregations and not expects_ranking and not (expects_entity_name and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}):
        expected_grain = "scalar_aggregate"
    else:
        expected_grain = None
    return {
        "expected_aggregations": expected_aggregations,
        "expected_grain": expected_grain,
        "expects_grouping": expects_grouping,
        "expects_ranking": expects_ranking,
        "expects_order": expects_order,
        "expects_distinct": expects_distinct,
        "expects_time_filter": expects_time_filter,
        "expects_ratio": expects_ratio,
        "expected_limit": int(top_match.group(1)) if top_match else None,
        "ordinal_limit": int(ordinal_match.group(1)) if ordinal_match else None,
        "expects_entity_name": expects_entity_name,
        "set_intent": set_intent,
        "quoted_literals": quoted_literals,
        "date_literals": date_literals,
    }


def _check(name: str, passed: Optional[bool], reason: str, *, material: bool = True, weight: float = 1.0) -> Dict[str, Any]:
    return {
        "name": name, "passed": passed, "severity": "soft", "reason": reason,
        "material": material, "weight": weight,
    }


def _contract_checks(candidate: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    structure = candidate["structure"]
    checks: List[Dict[str, Any]] = []
    expected_aggregations = set(contract["expected_aggregations"])
    actual_aggregations = set(structure["aggregations"])
    for aggregation in sorted(expected_aggregations):
        alternatives = {aggregation}
        if aggregation == "max" and contract["expects_ranking"]:
            alternatives.add("order_limit")
        if aggregation == "min" and contract["expects_ranking"]:
            alternatives.add("order_limit")
        passed = aggregation in actual_aggregations or (
            "order_limit" in alternatives and bool(structure["order_by"]) and structure["limit"] is not None
        )
        checks.append(_check(f"aggregation_{aggregation}", passed, f"expected {aggregation}; found {sorted(actual_aggregations)}"))
    if contract["expects_grouping"]:
        checks.append(_check("grouping", bool(structure["group_by"]), "question requests per-group output"))
    if contract["expects_order"]:
        checks.append(_check("ordering", bool(structure["order_by"]), "question requests ordered or ranked output"))
    expected_limit = contract["expected_limit"]
    if expected_limit is None and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        expected_limit = contract.get("ordinal_limit")
    if expected_limit is not None:
        checks.append(_check(
            "limit", structure["limit"] == expected_limit,
            f"expected LIMIT {expected_limit}; found {structure['limit']}",
        ))
    if contract["expects_distinct"]:
        checks.append(_check(
            "distinct", bool(structure["select_distinct"] or structure["aggregate_distinct"]),
            "question requests distinct/unique values",
        ))
    if contract["expects_time_filter"]:
        checks.append(_check("time_filter", bool(structure["has_time_filter"]), "question contains a time constraint"))
    if contract["expects_ratio"]:
        checks.append(_check("ratio", structure["division_count"] > 0, "question requests a ratio/rate/percentage"))
        if structure["division_count"]:
            checks.append(_check(
                "denominator_protection", bool(structure["denominator_protected"]),
                "division should guard a possible zero denominator", material=False, weight=0.35,
            ))
    sql_lower = candidate["sql"].lower()
    for intent in contract["set_intent"]:
        if intent == "exclusion":
            passed = bool(
                "except" in structure["set_operations"]
                or re.search(r"\b(not\s+exists|not\s+in|anti\s+join|left\s+join)\b", sql_lower)
                or re.search(r"(?:<>|!=)", sql_lower)
            )
        elif intent == "intersection":
            passed = bool(
                "intersect" in structure["set_operations"]
                or re.search(r"\b(having|exists)\b", sql_lower)
            )
        else:
            passed = bool(
                "union" in structure["set_operations"]
                or re.search(r"\bor\b", sql_lower)
            )
        checks.append(_check(
            f"set_behavior_{intent}", passed,
            f"question requests {intent} behavior; SQL evidence {'found' if passed else 'not found'}",
            weight=0.7,
        ))
    if contract["expected_grain"]:
        checks.append(_check(
            "output_grain", structure["grain"] == contract["expected_grain"],
            f"expected {contract['expected_grain']}; found {structure['grain']}",
        ))
    for literal in contract["quoted_literals"]:
        checks.append(_check(
            f"literal:{literal[:40]}", literal in sql_lower,
            "quoted question literal should normally be grounded in SQL", weight=0.7,
        ))
    if contract["date_literals"]:
        normalized_sql = re.sub(r"[^a-z0-9]+", "", sql_lower)
        matched_dates = sum(
            re.sub(r"[^a-z0-9]+", "", literal) in normalized_sql
            for literal in contract["date_literals"]
        )
        checks.append(_check(
            "time_literals", matched_dates > 0 or bool(structure["time_literals"]),
            f"matched {matched_dates}/{len(contract['date_literals'])} explicit time literals", weight=0.8,
        ))
    passed_weight = sum(check["weight"] for check in checks if check["passed"] is True)
    available_weight = sum(check["weight"] for check in checks if check["passed"] is not None)
    failed_weight = sum(check["weight"] for check in checks if check["passed"] is False)
    return {
        "checks": checks,
        "coverage": passed_weight / available_weight if available_weight else 0.5,
        "soft_penalty": failed_weight / available_weight if available_weight else 0.0,
        "high_risk": any(check["passed"] is False and check["material"] for check in checks),
    }


def _result_hash(frame: Optional[pd.DataFrame], ignore_order: bool = True) -> Optional[str]:
    if frame is None:
        return None
    payload = repr(dataframe_signature(frame, ignore_order=ignore_order)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_paths(log_path: Path, task: str, instance_id: str, candidate_id: int) -> Dict[str, Path]:
    root = log_path / "sql_gen"
    paths = {
        "sql": root / f"{task}_sql_{candidate_id}" / f"{instance_id}.sql",
        "result": root / f"{task}_execution_result_{candidate_id}" / f"{instance_id}.csv",
        "error": root / f"{task}_execution_error_{candidate_id}" / f"{instance_id}.txt",
        "revised_sql": log_path / "sql_revise" / f"{task}_sql_{candidate_id}" / f"{instance_id}.sql",
        "revised_result": log_path / "sql_revise" / f"{task}_sql_{candidate_id}" / f"{instance_id}.csv",
        "revised_error": log_path / "sql_revise" / f"{task}_sql_{candidate_id}" / f"{instance_id}.txt",
    }
    return paths


def collect_candidates(log_path: Path, task: str, instance_id: str, count: int) -> List[Dict[str, Any]]:
    value_evidence = []
    for trace_path in sorted((log_path / "bm25_traces").glob(f"{instance_id}_*.json")):
        try:
            value_evidence.extend(
                match for match in json.loads(trace_path.read_text(encoding="utf-8")).get("matches", [])
                if match.get("admitted")
            )
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    candidates = []

    def append_candidate(
        candidate_id: int, sql: Optional[str], frame: Optional[pd.DataFrame],
        error: Optional[str], source: str, parent_candidate_id: Optional[int] = None,
    ) -> None:
        parsed = _parse_sql(sql or "", instance_id)
        structure = _candidate_structure(sql or "", instance_id)
        record = {
            "candidate_id": candidate_id,
            "sql": (sql or "").strip(),
            "source": source,
            "frame": frame,
            "error": error,
            "executed": frame is not None and error is None,
            "parseable": parsed is not None,
            "canonical_sql": _canonical_sql(sql or "", instance_id),
            "structure": structure,
            "references": {"tables": structure["tables"], "columns": structure["columns"]},
            "result_hash": _result_hash(frame),
            "ordered_result_hash": _result_hash(frame, ignore_order=False),
            "result_shape": {
                "rows": int(len(frame)) if frame is not None else None,
                "columns": int(len(frame.columns)) if frame is not None else None,
                "column_names": [str(column) for column in frame.columns] if frame is not None else [],
                "null_columns": [str(column) for column in frame.columns if frame[column].isna().all()] if frame is not None else [],
                "dtypes": {str(column): str(frame[column].dtype) for column in frame.columns} if frame is not None else {},
            },
            "error_class": (error.split(":", 1)[0].strip() if error else None),
            "value_evidence": value_evidence,
        }
        if parent_candidate_id is not None:
            record["parent_candidate_id"] = parent_candidate_id
        candidates.append(record)

    for candidate_id in range(count):
        paths = _candidate_paths(log_path, task, instance_id, candidate_id)
        sql = _read_text(paths["sql"])
        frame = _read_frame(paths["result"])
        error = _read_text(paths["error"])
        source = "generated"
        if frame is None and paths["revised_result"].exists():
            sql = _read_text(paths["revised_sql"]) or sql
            frame = _read_frame(paths["revised_result"])
            error = _read_text(paths["revised_error"])
            source = "revised"
        append_candidate(candidate_id, sql, frame, error, source)

    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.7", "1.8", "1.9"}:
        decision_path = log_path / "semantic_revise" / "decisions" / f"{instance_id}.json"
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            decision = {}
        if decision.get("status") == "complete" and decision.get("accepted"):
            candidate_id = int(decision.get("output_candidate", count))
            repair_root = log_path / "semantic_revise" / f"{task}_sql_{candidate_id}"
            sql = _read_text(repair_root / f"{instance_id}.sql")
            frame = _read_frame(repair_root / f"{instance_id}.csv")
            if sql and frame is not None:
                append_candidate(
                    candidate_id, sql, frame, None, "semantic_revision",
                    int(decision.get("parent_candidate", 0)),
                )
    return candidates


def _hard_gates(candidate: Dict[str, Any], schema_catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    structure = candidate["structure"]
    known_tables = set(schema_catalog.get("tables", {}))
    invalid_tables = sorted(set(structure["tables"]) - known_tables) if schema_catalog.get("complete") else []
    gates = [
        {"name": "parseable", "passed": candidate["parseable"], "reason": "SQL parsed for target dialect" if candidate["parseable"] else "SQL parse failed"},
        {"name": "single_statement", "passed": structure["statement_count"] == 1, "reason": f"statement_count={structure['statement_count']}"},
        {"name": "execution", "passed": candidate["executed"], "reason": "result artifact present" if candidate["executed"] else candidate["error"] or "execution result missing"},
        {"name": "query_only", "passed": structure["query_only"], "reason": "query-only SQL" if structure["query_only"] else f"statement_types={structure['statement_types']}"},
        {
            "name": "schema_tables", "passed": not invalid_tables,
            "reason": f"invalid table references: {invalid_tables}" if invalid_tables else (
                "all table references exist in the complete schema catalog"
                if schema_catalog.get("complete") else "schema catalog incomplete; table check is neutral"
            ),
            "authoritative": bool(schema_catalog.get("complete")),
        },
    ]
    return gates


def _shape_score(candidate: Dict[str, Any], contract: Dict[str, Any]) -> float:
    structure = candidate["structure"]
    frame = candidate.get("frame")
    observations: List[bool] = []
    if contract["expected_grain"]:
        observations.append(structure["grain"] == contract["expected_grain"])
    if contract["expects_order"]:
        observations.append(bool(structure["order_by"]))
    expected_limit = contract["expected_limit"]
    if expected_limit is None and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        expected_limit = contract.get("ordinal_limit")
    if expected_limit is not None:
        observations.append(structure["limit"] == expected_limit)
    if contract["expects_distinct"]:
        observations.append(bool(structure["select_distinct"] or structure["aggregate_distinct"]))
    if frame is not None:
        observations.append(len(frame.columns) > 0)
        if contract["expected_grain"] == "scalar_aggregate":
            observations.append(len(frame) <= 1)
    return sum(observations) / len(observations) if observations else (1.0 if frame is not None else 0.0)


def _interaction_grounding(candidate: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> float:
    """Score whether a candidate uses the query-linked tables and join evidence."""
    if not evidence:
        return 0.0
    candidate_tables = {str(value).lower().split(".")[-1].strip('`"') for value in candidate["structure"].get("tables", [])}
    linked_tables = {
        str(entry.get("table", "")).lower().split(".")[-1].strip('`"')
        for entry in evidence.get("lexical_matches", []) if entry.get("table")
    }
    if not linked_tables or not candidate_tables:
        return 0.0
    table_overlap = len(candidate_tables & linked_tables) / max(1, len(candidate_tables))
    joins = candidate["structure"].get("joins", [])
    recommended = evidence.get("recommended_joins", [])
    if not recommended or not joins:
        return min(1.0, table_overlap)
    sql_lower = str(candidate.get("sql", "")).lower()
    matched_edges = 0
    for edge in recommended:
        edge_tables = {
            str(edge.get("from_table", "")).lower().split(".")[-1],
            str(edge.get("to_table", "")).lower().split(".")[-1],
        }
        edge_columns = {
            str(edge.get("from_column", "")).lower(),
            str(edge.get("to_column", "")).lower(),
        }
        if edge_tables.issubset(candidate_tables) and any(column in sql_lower for column in edge_columns):
            matched_edges += 1
    join_score = matched_edges / max(1, len(recommended))
    return min(1.0, 0.65 * table_overlap + 0.35 * join_score)


def _answer_plan_grounding(candidate: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> float:
    """Score agreement with measured table sizes and join cardinalities."""
    if not evidence or not evidence.get("answer_plan"):
        return 0.0
    plan = evidence.get("answer_plan", {})
    candidate_tables = {
        str(value).lower().split(".")[-1].strip('`"')
        for value in candidate.get("structure", {}).get("tables", [])
    }
    likely_tables = {
        str(value).lower().split(".")[-1].strip('`"')
        for value in plan.get("likely_tables", [])
    }
    score = 0.5 if candidate_tables and likely_tables and candidate_tables & likely_tables else 0.0
    sql_lower = str(candidate.get("sql", "")).lower()
    matched = 0
    risky = 0
    for route in plan.get("join_routes", []):
        endpoints = {
            str(route.get("from_table", "")).lower(), str(route.get("to_table", "")).lower(),
            str(route.get("from_column", "")).lower(), str(route.get("to_column", "")).lower(),
        }
        endpoints.discard("")
        if endpoints and sum(token in sql_lower for token in endpoints) >= 2:
            matched += 1
            if route.get("many_to_many_risk") and candidate.get("structure", {}).get("aggregations"):
                risky += 1
    if plan.get("join_routes"):
        score += 0.5 * min(1.0, matched / len(plan["join_routes"]))
    if risky:
        score -= min(0.5, 0.2 * risky)
    return max(0.0, min(1.0, score))


def _structure_fingerprint(candidate: Dict[str, Any]) -> str:
    structure = candidate["structure"]
    fields = {
        key: structure[key]
        for key in (
            "tables", "joins", "predicates", "projections", "aggregations", "group_by",
            "order_by", "limit", "set_operations", "select_distinct", "aggregate_distinct", "grain",
        )
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode("utf-8")).hexdigest()


def _score_candidates(
    instance_id: str, candidates: List[Dict[str, Any]], question: str,
    schema_catalog: Optional[Dict[str, Any]] = None,
    interaction_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract = _question_contract(question)
    schema_catalog = schema_catalog or {"complete": False, "tables": {}}
    for candidate in candidates:
        candidate.setdefault("structure", _candidate_structure(candidate.get("sql", ""), instance_id))
        if not candidate.get("ordered_result_hash"):
            candidate["ordered_result_hash"] = _result_hash(candidate.get("frame"), ignore_order=False)
        if not candidate.get("result_hash"):
            candidate["result_hash"] = _result_hash(candidate.get("frame"))
    structural_counts: Dict[str, int] = defaultdict(int)
    result_counts: Dict[str, int] = defaultdict(int)
    for candidate in candidates:
        structural_counts[_structure_fingerprint(candidate)] += 1
        if candidate.get("result_hash"):
            result_counts[str(candidate["result_hash"])] += 1
    weights = {
        "execution": float(os.environ.get("SLAYQL_SELECTOR_W_EXEC", "0.36")),
        "contract": float(os.environ.get("SLAYQL_SELECTOR_W_CONTRACT", "0.24")),
        "shape": float(os.environ.get("SLAYQL_SELECTOR_W_SHAPE", "0.20")),
        "value": float(os.environ.get("SLAYQL_SELECTOR_W_VALUE", "0.08")),
        "evidence": float(os.environ.get(
            "SLAYQL_SELECTOR_W_EVIDENCE", "0.10" if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"} else "0.0"
        )),
        "semantic": float(os.environ.get(
            "SLAYQL_SELECTOR_W_SEMANTIC", "0.22" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else "0.18" if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8"} else "0.0"
        )),
        "consensus": float(os.environ.get(
            "SLAYQL_SELECTOR_W_CONSENSUS", "0.08" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else "0.10" if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.7", "1.8"} else "0.0"
        )),
        "answer_plan": float(os.environ.get(
            "SLAYQL_SELECTOR_W_ANSWER_PLAN", "0.16" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else "0.14" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.8" else "0.0"
        )),
        "diversity": float(os.environ.get("SLAYQL_SELECTOR_W_DIVERSITY", "0.04")),
        "risk": float(os.environ.get("SLAYQL_SELECTOR_W_RISK", "0.12")),
    }
    semantic_contract = (
        interaction_evidence.get("semantic_contract", {}) if interaction_evidence else {}
    )
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"} and not semantic_contract:
        semantic_contract = compile_semantic_contract({"question": question})
    for candidate in candidates:
        checks = _contract_checks(candidate, contract)
        semantic_checks = (
            assess_semantic_contract(candidate.get("sql", ""), candidate["structure"], semantic_contract)
            if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"} else {"score": 0.0, "penalty": 0.0, "checks": []}
        )
        candidate["contract_checks"] = checks["checks"]
        candidate["semantic_contract_checks"] = semantic_checks["checks"]
        fingerprint = _structure_fingerprint(candidate)
        repair_penalty = 0.0
        if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.8", "1.9"} and candidate.get("source") == "semantic_revision":
            repair_penalty = float(os.environ.get("SLAYQL_SELECTOR_REPAIR_PENALTY", "0.20"))
        candidate["score_parts"] = {
            "execution": 1.0 if candidate["executed"] else 0.0,
            "contract": checks["coverage"],
            "shape": _shape_score(candidate, contract),
            "value": 1.0 if any(
                str(evidence.get("matched_value", "")).lower() in candidate["sql"].lower()
                or str(evidence.get("literal", "")).lower() in candidate["sql"].lower()
                for evidence in candidate.get("value_evidence", [])
            ) else 0.0,
            "evidence": _interaction_grounding(candidate, interaction_evidence),
            "answer_plan": _answer_plan_grounding(candidate, interaction_evidence),
            "semantic": semantic_checks["score"],
            "consensus": (
                result_counts.get(str(candidate.get("result_hash")), 0)
                / max(1, sum(bool(item.get("result_hash")) for item in candidates))
            ),
            "diversity": 1.0 / structural_counts[fingerprint],
            "repair_penalty": repair_penalty,
            "risk_penalty": checks["soft_penalty"] + 0.75 * semantic_checks["penalty"] + repair_penalty,
        }
        candidate["soft_risk"] = checks["high_risk"]
        candidate["score"] = sum(
            weights[name] * candidate["score_parts"][name]
            for name in ("execution", "contract", "shape", "value", "evidence", "answer_plan", "semantic", "consensus", "diversity")
        ) - weights["risk"] * candidate["score_parts"]["risk_penalty"]
        candidate["hard_gates"] = _hard_gates(candidate, schema_catalog)
        if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9":
            physical = physical_projection_check(
                candidate.get("sql", ""), candidate["structure"], semantic_contract,
            )
            candidate["physical_projection_check"] = physical
            if physical.get("passed") is False:
                candidate["hard_gates"].append({
                    "name": "physical_output_projection",
                    "passed": False,
                    "reason": physical.get("reason", "physical output contract mismatch"),
                    "authoritative": True,
                })
        candidate["eligible"] = all(gate["passed"] for gate in candidate["hard_gates"])
    return contract


def _deduplicate_candidates(
    candidates: List[Dict[str, Any]], *, order_sensitive: bool,
) -> List[Dict[str, Any]]:
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            same_sql = bool(left.get("canonical_sql")) and left.get("canonical_sql") == right.get("canonical_sql")
            result_key = "ordered_result_hash" if order_sensitive else "result_hash"
            same_result = bool(left.get(result_key)) and left.get(result_key) == right.get(result_key)
            if same_sql or (left.get("executed") and right.get("executed") and same_result):
                union(left_index, right_index)

    groups: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        groups[find(index)].append(candidate)
    representatives = []
    for group_index, group in enumerate(groups.values(), start=1):
        representative = max(
            group,
            key=lambda candidate: (
                bool(candidate.get("eligible")), bool(candidate.get("executed")),
                float(candidate.get("score", 0.0)), -int(candidate["candidate_id"]),
            ),
        )
        member_ids = sorted(int(candidate["candidate_id"]) for candidate in group)
        representative["duplicate_group"] = group_index
        representative["duplicate_members"] = member_ids
        representative["duplicate_count"] = len(group) - 1
        for candidate in group:
            candidate["duplicate_group"] = group_index
            candidate["duplicate_members"] = member_ids
            if candidate is not representative:
                candidate["duplicate_of"] = representative["candidate_id"]
                candidate["duplicate_reason"] = (
                    "canonical_sql" if candidate.get("canonical_sql") == representative.get("canonical_sql")
                    else "equivalent_ordered_result" if order_sensitive
                    else "equivalent_result"
                )
        representatives.append(representative)
    return representatives


def _material_disagreement(
    left: Dict[str, Any], right: Dict[str, Any], contract: Dict[str, Any], *, order_sensitive: bool,
) -> Dict[str, Any]:
    left_structure, right_structure = left["structure"], right["structure"]
    comparisons = {
        "output_grain": (left_structure["grain"], right_structure["grain"]),
        "projections": (left_structure["projections"], right_structure["projections"]),
        "aggregations": (left_structure["aggregations"], right_structure["aggregations"]),
        "grouping": (left_structure["group_by"], right_structure["group_by"]),
        "tables": (left_structure["tables"], right_structure["tables"]),
        "joins": (left_structure["joins"], right_structure["joins"]),
        "filters": (left_structure["predicates"], right_structure["predicates"]),
        "literals": (left_structure["literals"], right_structure["literals"]),
        "set_operations": (left_structure["set_operations"], right_structure["set_operations"]),
        "distinct_placement": (
            (left_structure["select_distinct"], left_structure["aggregate_distinct"]),
            (right_structure["select_distinct"], right_structure["aggregate_distinct"]),
        ),
        "ratio_logic": (
            (left_structure["division_count"], left_structure["denominator_protected"]),
            (right_structure["division_count"], right_structure["denominator_protected"]),
        ),
        "time_boundary": (
            (left_structure["has_time_filter"], left_structure["time_literals"]),
            (right_structure["has_time_filter"], right_structure["time_literals"]),
        ),
    }
    if (
        contract["expects_order"]
        or contract["expected_limit"] is not None
        or (os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"} and contract.get("ordinal_limit") is not None)
    ):
        comparisons["ranking"] = (
            (left_structure["order_by"], left_structure["limit"]),
            (right_structure["order_by"], right_structure["limit"]),
        )
    result_key = "ordered_result_hash" if order_sensitive else "result_hash"
    if left.get(result_key) and right.get(result_key):
        comparisons["execution_result"] = (left[result_key], right[result_key])
    reasons = [name for name, values in comparisons.items() if values[0] != values[1]]
    return {
        "material": bool(reasons),
        "reasons": reasons,
        "left_candidate": left["candidate_id"],
        "right_candidate": right["candidate_id"],
    }


def _selector_client() -> OpenAI:
    """Create an independent client for one selector worker."""
    kwargs = {
        "api_key": os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"),
        "base_url": os.environ.get("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1",
        "timeout": float(os.environ.get("SLAYQL_SELECTOR_TIMEOUT", "180")),
    }
    # Disable SDK-level retries so the bounded retry policy below is the only
    # retry loop and usage accounting remains easy to interpret.
    try:
        return OpenAI(**kwargs, max_retries=0)
    except TypeError:  # compatibility with older openai clients
        return OpenAI(**kwargs)


def _selector_candidate_id(content: str) -> Optional[int]:
    match = re.search(r"candidate_id\s*[\":=]+\s*(\d+)", content or "")
    return int(match.group(1)) if match else None


def _selector_exception_retryable(exc: Exception) -> bool:
    """Avoid wasting retries on permanent authentication/request errors."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) if response is not None else None
    return status not in {400, 401, 403, 404}


def _selector_completion(
    client: OpenAI, prompt: str, *, stage: str, instance_id: str,
    allowed_candidate_ids: Sequence[int],
) -> Dict[str, Any]:
    """Call the selector with bounded retries and strict response validation."""
    attempts_limit = max(1, int(os.environ.get("SLAYQL_SELECTOR_RETRIES", "5")))
    backoff = max(0.0, float(os.environ.get("SLAYQL_SELECTOR_BACKOFF", "2.0")))
    allowed = {int(candidate_id) for candidate_id in allowed_candidate_ids}
    last_content = ""
    last_error: Optional[str] = None
    attempts = 0

    for attempt in range(1, attempts_limit + 1):
        attempts = attempt
        request_started = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=os.environ.get("MODEL_NAME"),
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = (time.monotonic() - request_started) * 1000
            try:
                record_response_usage(
                    response, stage=stage, instance_id=instance_id,
                    attempt=attempt, latency_ms=latency_ms,
                )
            except Exception:
                # Usage persistence must not turn a valid provider response
                # into a failed selection.
                pass
            last_content = response.choices[0].message.content or ""
            chosen_id = _selector_candidate_id(last_content)
            if chosen_id in allowed:
                return {
                    "status": "selected", "candidate_id": chosen_id,
                    "content": last_content, "attempts": attempts,
                }
            last_error = "empty_or_invalid_candidate_id"
        except Exception as exc:
            latency_ms = (time.monotonic() - request_started) * 1000
            try:
                record_response_usage(
                    None, stage=stage, instance_id=instance_id,
                    attempt=attempt, latency_ms=latency_ms,
                )
            except Exception:
                pass
            last_error = str(exc)[:1000]
            if not _selector_exception_retryable(exc):
                break

        if attempt < attempts_limit:
            delay = min(60.0, backoff * (2 ** (attempt - 1)))
            if delay:
                # Small jitter prevents a rate-limit retry wave when many
                # independent selector workers fail together.
                time.sleep(delay + random.uniform(0.0, min(1.0, delay * 0.25)))

    status = "invalid_response" if last_content and last_error == "empty_or_invalid_candidate_id" else "error"
    return {
        "status": status, "candidate_id": None, "content": last_content,
        "attempts": attempts, "error": last_error,
    }


def _verify(
    instance_id: str, question: str, contract: Dict[str, Any],
    candidates: List[Dict[str, Any]], selected: Dict[str, Any],
    disagreement: Dict[str, Any], *, allow_verification: bool = True,
) -> Dict[str, Any]:
    if not allow_verification:
        selected["verification"] = {"status": "offline_disabled"}
        return selected
    if os.environ.get("SLAYQL_SELECTOR_VERIFY", "1").lower() in {"0", "false", "no"}:
        selected["verification"] = {"status": "disabled"}
        return selected
    if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        selected["verification"] = {"status": "unavailable_no_api_key"}
        return selected
    compact = []
    for candidate in candidates:
        compact.append({
            "candidate_id": candidate["candidate_id"], "sql": candidate["sql"],
            "score": candidate["score"], "score_parts": candidate["score_parts"],
            "contract_checks": candidate.get("contract_checks", []),
            "references": candidate.get("references", {}),
            "executed": candidate.get("executed", False),
            "result_shape": candidate.get("result_shape") or (
                {"rows": len(candidate["frame"]), "columns": len(candidate["frame"].columns)}
                if candidate.get("frame") is not None else None
            ),
            "structure": candidate.get("structure", {}),
        })
    prompt = (
        "Choose the candidate ID that best answers the question. Return only JSON "
        "with candidate_id and a short reason. Do not write new SQL.\n"
        f"Question: {question}\nContract: {json.dumps(contract, default=str)}\n"
        f"Disagreement: {json.dumps(disagreement, default=str)}\n"
        f"Candidates: {json.dumps(compact, default=str)}"
    )
    try:
        completion = _selector_completion(
            _selector_client(), prompt, stage="selector_verification", instance_id=instance_id,
            allowed_candidate_ids=[candidate["candidate_id"] for candidate in candidates if candidate.get("eligible")],
        )
        content = completion.get("content", "")
        chosen_id = completion.get("candidate_id")
        chosen = next((item for item in candidates if item["candidate_id"] == chosen_id and item["eligible"]), None)
        if chosen:
            chosen["selection"] = dict(selected.get("selection", {}))
            chosen["verification"] = {
                "status": "selected", "attempts": completion.get("attempts", 1),
                "reason": content[:1000],
            }
            return chosen
        selected["verification"] = {
            "status": completion.get("status", "invalid_response"),
            "attempts": completion.get("attempts", 1),
            "reason": content[:1000], "error": completion.get("error"),
        }
    except Exception as exc:
        selected["verification"] = {"status": "error", "error": str(exc)[:1000]}
    return selected


def _result_preview(candidate: Dict[str, Any], max_rows: int = 5, max_columns: int = 10) -> Dict[str, Any]:
    frame = candidate.get("frame")
    if frame is None:
        return {"columns": [], "rows": [], "error": candidate.get("error")}
    preview = frame.iloc[:max_rows, :max_columns].astype(object)
    preview = preview.where(pd.notna(preview), None)
    rows = []
    for row in preview.to_dict(orient="records"):
        bounded = {}
        for key, value in row.items():
            if value is None or isinstance(value, (bool, int, float)):
                bounded[str(key)] = value
            else:
                rendered = str(value)
                bounded[str(key)] = rendered if len(rendered) <= 160 else rendered[:157] + "..."
        rows.append(bounded)
    return {
        "columns": [str(column) for column in preview.columns],
        "rows": rows,
        "total_rows": int(len(frame)),
        "total_columns": int(len(frame.columns)),
    }


def _compact_interaction_evidence(evidence: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not evidence:
        return {}
    return {
        "question_contract": evidence.get("question_contract", {}),
        "relational_closure": evidence.get("relational_closure", {}),
        "answer_plan": evidence.get("answer_plan", {}),
        "question_linked_fields": evidence.get("lexical_matches", [])[:10],
        "observed_values": evidence.get("value_probes", [])[:5],
        "value_links": evidence.get("value_links", [])[:6],
        "semantic_contract": evidence.get("semantic_contract", {}),
    }


def _contract_result_verification(
    instance_id: str, question: str, contract: Dict[str, Any],
    candidates: List[Dict[str, Any]], selected: Dict[str, Any],
    interaction_evidence: Optional[Dict[str, Any]], *, allow_verification: bool = True,
) -> Dict[str, Any]:
    """Make one evidence-exact choice across distinct executed result groups."""
    version = os.environ.get("SLAYQL_RESEARCH_VERSION")
    method = (
        "single_contract_result_verification_v19" if version == "1.9" else
        "single_contract_result_verification_v18" if version == "1.8" else
        "single_contract_result_verification_v17" if version == "1.7" else
        "single_contract_result_verification"
    )
    if not allow_verification:
        selected["verification"] = {"status": "offline_disabled", "method": method}
        return selected
    if os.environ.get("SLAYQL_SELECTOR_VERIFY", "1").lower() in {"0", "false", "no"}:
        selected["verification"] = {"status": "disabled", "method": method}
        return selected
    if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        selected["verification"] = {"status": "unavailable_no_api_key", "method": method}
        return selected

    compact = []
    for candidate in candidates[:3]:
        compact.append({
            "candidate_id": candidate["candidate_id"], "sql": candidate["sql"],
            "deterministic_score": candidate["score"],
            "semantic_contract_checks": candidate.get("semantic_contract_checks", []),
            "contract_checks": candidate.get("contract_checks", []),
            "structure": candidate.get("structure", {}),
            "result": _result_preview(candidate),
        })
    evidence = _compact_interaction_evidence(interaction_evidence)
    learning = ""
    if version in {"1.7", "1.8", "1.9"} and os.environ.get("SLAYQL_RUN_ROOT"):
        learning_path = Path(os.environ["SLAYQL_RUN_ROOT"]) / "prompt_learning" / f"{instance_id}.json"
        try:
            learning = str(json.loads(learning_path.read_text(encoding="utf-8")).get("prompt") or "")[:5000]
        except (OSError, ValueError, json.JSONDecodeError):
            learning = ""
    prompt = (
        "Choose exactly one executed SQL candidate. Return only JSON with candidate_id and a short reason. "
        "Do not write new SQL. Judge against the question, dataset evidence, schema relations, returned columns, "
        "values, and row grain. Dataset evidence is authoritative even when a different real-world interpretation "
        "seems more natural. Prefer the minimal requested output: join/filter/order/helper columns are not useful "
        "extras. Reject invented DISTINCT, latest-row logic, deduplication, grouping, or formula substitutions.\n"
        f"Question: {question}\nLegacy contract: {json.dumps(contract, default=str)}\n"
        f"Database and semantic evidence: {json.dumps(evidence, default=str)}\n"
        f"Training-only structural lessons: {learning or 'none'}\n"
        f"Candidates: {json.dumps(compact, default=str)}"
    )
    try:
        completion = _selector_completion(
            _selector_client(), prompt, stage="selector_contract_verification", instance_id=instance_id,
            allowed_candidate_ids=[candidate["candidate_id"] for candidate in candidates if candidate.get("eligible")],
        )
        content = completion.get("content", "")
        chosen_id = completion.get("candidate_id")
        chosen = next(
            (candidate for candidate in candidates if candidate["candidate_id"] == chosen_id and candidate["eligible"]),
            None,
        )
        if chosen:
            chosen["selection"] = dict(selected.get("selection", {}))
            chosen["verification"] = {
                "status": "selected", "method": method,
                "attempts": completion.get("attempts", 1), "reason": content[:1000],
            }
            return chosen
        selected["verification"] = {
            "status": completion.get("status", "invalid_response"), "method": method,
            "attempts": completion.get("attempts", 1), "reason": content[:1000],
            "error": completion.get("error"),
        }
    except Exception as exc:
        selected["verification"] = {"status": "error", "method": method, "error": str(exc)[:1000]}
    return selected


def _pairwise_result_tournament(
    instance_id: str, question: str, contract: Dict[str, Any],
    candidates: List[Dict[str, Any]], selected: Dict[str, Any],
    interaction_evidence: Optional[Dict[str, Any]], *, allow_verification: bool = True,
) -> Dict[str, Any]:
    """Select among unique execution results using bounded pairwise comparisons."""
    if not allow_verification:
        selected["verification"] = {"status": "offline_disabled", "method": "pairwise_result_tournament"}
        return selected
    if os.environ.get("SLAYQL_SELECTOR_VERIFY", "1").lower() in {"0", "false", "no"}:
        selected["verification"] = {"status": "disabled", "method": "pairwise_result_tournament"}
        return selected
    if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        selected["verification"] = {"status": "unavailable_no_api_key", "method": "pairwise_result_tournament"}
        return selected

    tournament_size = max(2, min(len(candidates), int(os.environ.get("SLAYQL_SELECTOR_TOURNAMENT_SIZE", "4"))))
    participants = candidates[:tournament_size]
    client = _selector_client()
    votes = {int(candidate["candidate_id"]): 0 for candidate in participants}
    outcomes = []
    evidence = _compact_interaction_evidence(interaction_evidence)
    for left_index, left in enumerate(participants):
        for right in participants[left_index + 1:]:
            pair = []
            for candidate in (left, right):
                pair.append({
                    "candidate_id": candidate["candidate_id"],
                    "sql": candidate["sql"],
                    "deterministic_score": candidate["score"],
                    "contract_checks": candidate.get("contract_checks", []),
                    "structure": candidate.get("structure", {}),
                    "result": _result_preview(candidate),
                })
            prompt = (
                "Compare these two executed SQL candidates. Choose the candidate whose returned columns, values, "
                "row grain, filters, and relation path best answer the question. Database observations and requested "
                "output arity outrank plausible business assumptions. Do not write new SQL. Return only JSON with "
                "candidate_id and a short reason.\n"
                f"Question: {question}\nContract: {json.dumps(contract, default=str)}\n"
                f"Database evidence: {json.dumps(evidence, default=str)}\n"
                f"Candidates: {json.dumps(pair, default=str)}"
            )
            try:
                completion = _selector_completion(
                    client, prompt, stage="selector_tournament", instance_id=instance_id,
                    allowed_candidate_ids=[left["candidate_id"], right["candidate_id"]],
                )
                content = completion.get("content", "")
                chosen_id = completion.get("candidate_id")
                pair_ids = {int(left["candidate_id"]), int(right["candidate_id"])}
                if completion.get("status") != "selected" or chosen_id not in pair_ids:
                    outcomes.append({
                        "pair": sorted(pair_ids), "status": completion.get("status", "invalid_response"),
                        "attempts": completion.get("attempts", 1), "response": content[:600],
                        "error": completion.get("error"),
                    })
                    continue
                votes[chosen_id] += 1
                outcomes.append({
                    "pair": sorted(pair_ids), "status": "selected", "winner": chosen_id,
                    "attempts": completion.get("attempts", 1), "reason": content[:600],
                })
            except Exception as exc:
                outcomes.append({
                    "pair": sorted((int(left["candidate_id"]), int(right["candidate_id"]))),
                    "status": "error", "error": str(exc)[:600],
                })

    completed = [outcome for outcome in outcomes if outcome.get("status") == "selected"]
    if not completed:
        selected["verification"] = {
            "status": "error", "method": "pairwise_result_tournament", "votes": votes, "outcomes": outcomes,
        }
        return selected
    winner = max(
        participants,
        key=lambda candidate: (
            votes[int(candidate["candidate_id"])], float(candidate.get("score", 0.0)),
            -int(candidate["candidate_id"]),
        ),
    )
    winner["selection"] = dict(selected.get("selection", {}))
    winner["verification"] = {
        "status": "selected", "method": "pairwise_result_tournament",
        "votes": votes, "outcomes": outcomes,
    }
    return winner


def select_instance(
    instance_id: str, candidates: List[Dict[str, Any]], question: str,
    dataset_item: Optional[Dict[str, Any]] = None, *, allow_verification: bool = True,
) -> Dict[str, Any]:
    interaction_evidence = None
    run_root = os.environ.get("SLAYQL_RUN_ROOT")
    if run_root:
        evidence_path = Path(run_root) / "interaction" / f"{instance_id}.json"
        if evidence_path.exists():
            try:
                interaction_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                interaction_evidence = None
    contract = _score_candidates(
        instance_id, candidates, question, _schema_catalog(dataset_item), interaction_evidence
    )
    order_sensitive = bool(contract["expects_order"])
    representatives = _deduplicate_candidates(candidates, order_sensitive=order_sensitive)
    eligible = [candidate for candidate in representatives if candidate["eligible"]]
    pool = eligible or [candidate for candidate in representatives if candidate["executed"]] or representatives
    ranked = sorted(pool, key=lambda candidate: (candidate["score"], -candidate["candidate_id"]), reverse=True)
    selected = ranked[0]
    margin = selected["score"] - ranked[1]["score"] if len(ranked) > 1 else 1.0
    threshold = float(os.environ.get("SLAYQL_SELECTOR_MARGIN", "0.10"))
    minimum_score = float(os.environ.get("SLAYQL_SELECTOR_MIN_SCORE", "0.35"))
    disagreement = (
        _material_disagreement(selected, ranked[1], contract, order_sensitive=order_sensitive)
        if len(ranked) > 1 else {"material": False, "reasons": []}
    )
    verification_reasons = []
    if margin < threshold:
        verification_reasons.append("close_score_margin")
    if disagreement["material"]:
        verification_reasons.append("material_structural_disagreement")
    if selected["score"] < minimum_score:
        verification_reasons.append("below_minimum_validity_score")
    selected["selection"] = {
        "method": "deterministic", "margin": margin, "threshold": threshold,
        "minimum_score": minimum_score, "top_score": selected["score"],
        "eligible_candidate_count": len(eligible), "representative_count": len(representatives),
        "disagreement": disagreement, "verification_reasons": verification_reasons,
    }
    version = os.environ.get("SLAYQL_RESEARCH_VERSION")
    tournament_margin = float(os.environ.get("SLAYQL_SELECTOR_TOURNAMENT_MARGIN", "0.20"))
    should_verify = len(ranked) > 1 and (
        margin < threshold and disagreement["material"]
        or version in {"1.8", "1.9"} and disagreement["material"] and margin < tournament_margin
    )
    if should_verify:
        if version == "1.9":
            selected = _contract_result_verification(
                instance_id, question, contract, ranked[: min(2, len(ranked))], selected,
                interaction_evidence, allow_verification=allow_verification,
            )
            selected.setdefault("selection", {})["method"] = (
                "single_contract_result_verification_v19"
                if selected.get("verification", {}).get("status") == "selected"
                else "deterministic_fallback"
            )
        elif version == "1.8":
            selected = _pairwise_result_tournament(
                instance_id, question, contract, ranked[: min(4, len(ranked))], selected,
                interaction_evidence, allow_verification=allow_verification,
            )
            selected.setdefault("selection", {})["method"] = (
                "pairwise_result_tournament_v18"
                if selected.get("verification", {}).get("status") == "selected"
                else "deterministic_fallback"
            )
        elif version in {"1.6", "1.7"}:
            selected = _contract_result_verification(
                instance_id, question, contract, ranked[: min(3, len(ranked))], selected,
                interaction_evidence, allow_verification=allow_verification,
            )
            selected.setdefault("selection", {})["method"] = (
                ("single_contract_result_verification_v17" if version == "1.7" else "single_contract_result_verification")
                if selected.get("verification", {}).get("status") == "selected"
                else "deterministic_fallback"
            )
        elif os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.5":
            selected = _pairwise_result_tournament(
                instance_id, question, contract, ranked[: min(3, len(ranked))], selected,
                interaction_evidence, allow_verification=allow_verification,
            )
            selected.setdefault("selection", {})["method"] = (
                "pairwise_result_tournament"
                if selected.get("verification", {}).get("status") == "selected"
                else "deterministic_fallback"
            )
        else:
            selected = _verify(
                instance_id, question, contract, ranked[: min(3, len(ranked))], selected,
                disagreement, allow_verification=allow_verification,
            )
            selected.setdefault("selection", {})["method"] = "verification" if selected.get("verification", {}).get("status") == "selected" else "deterministic_fallback"
    else:
        selected["verification"] = {"status": "not_invoked", "reason": "verification requires both a close score and material disagreement"}
    return {
        "selected": selected, "candidates": candidates, "contract": contract,
        "eligible_candidate_count": len(eligible), "representative_count": len(representatives),
    }


def write_selection(run_root: Path, instance_id: str, result: Dict[str, Any]) -> None:
    selected = result["selected"]
    final_dir = run_root / "sql_selection_v1" / "final" / instance_id
    final_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(str(final_dir / "selected.sql"), selected.get("sql", ""))
    if selected.get("frame") is not None:
        file_descriptor, temporary = tempfile.mkstemp(prefix=".result.", suffix=".csv.tmp", dir=str(final_dir))
        os.close(file_descriptor)
        try:
            selected["frame"].to_csv(temporary, index=False)
            os.replace(temporary, final_dir / "result.csv")
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    else:
        atomic_write_text(str(final_dir / "error.txt"), selected.get("error") or "No executable candidate")
    record = {
        "instance_id": instance_id,
        "selected_candidate": selected.get("candidate_id"),
        "selection": selected.get("selection"),
        "verification": selected.get("verification"),
        "contract": result.get("contract", {}),
        "eligible_candidate_count": result.get("eligible_candidate_count", 0),
        "representative_count": result.get("representative_count", 0),
        "candidates": [{key: value for key, value in candidate.items() if key != "frame"} for candidate in result["candidates"]],
    }
    atomic_write_json(str(run_root / "selection" / f"{instance_id}.json"), record)


def _artifact_fingerprint(root: Path, paths: Iterable[Path]) -> Dict[str, Any]:
    records = []
    total_bytes = 0
    for path in sorted({Path(path).resolve() for path in paths if Path(path).is_file()}, key=str):
        try:
            relative = str(path.relative_to(root.resolve()))
        except ValueError:
            relative = str(path)
        size = path.stat().st_size
        total_bytes += size
        records.append({"path": relative, "size": size, "sha256": sha256_file(str(path))})
    digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode("utf-8")).hexdigest()
    return {"file_count": len(records), "total_bytes": total_bytes, "sha256": digest}


def _candidate_artifacts(source_root: Path, instance_ids: Sequence[str], task: str, count: int) -> List[Path]:
    paths: List[Path] = []
    for instance_id in instance_ids:
        for candidate_id in range(count):
            paths.extend(_candidate_paths(source_root, task, instance_id, candidate_id).values())
        paths.extend([
            source_root / "semantic_revise" / "decisions" / f"{instance_id}.json",
            source_root / "semantic_revise" / f"{task}_sql_{count}" / f"{instance_id}.sql",
            source_root / "semantic_revise" / f"{task}_sql_{count}" / f"{instance_id}.csv",
            source_root / "prompt_learning" / f"{instance_id}.json",
        ])
        paths.extend((source_root / "bm25_traces").glob(f"{instance_id}_*.json"))
    return paths


def _git_snapshot(repo_root: Path) -> Dict[str, Any]:
    def command(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ["git", *arguments], cwd=repo_root, check=True,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    # Replay outputs are intentionally untracked, so only tracked-file changes
    # participate in the stable Git snapshot. Relevant untracked code is hashed
    # explicitly in code_and_evaluator.
    status = command("status", "--short", "--untracked-files=no")
    return {
        "commit": command("rev-parse", "HEAD") or None,
        "branch": command("rev-parse", "--abbrev-ref", "HEAD") or None,
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def build_replay_manifest(
    source_root: Path, output_root: Path, data_file: Path,
    data: Dict[str, Dict[str, Any]], task: str, count: int,
    allow_verification: bool,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parent.parent
    evaluation_root = repo_root / "evaluation_suite"
    evaluator_files = [
        Path(__file__).resolve(), Path(__file__).resolve().parent / "semantic_validator.py",
        Path(__file__).resolve().parent / "semantic_contract.py",
        Path(__file__).resolve().parent / "prompt_learning.py",
        Path(__file__).resolve().parent / "semantic_revise.py",
        Path(__file__).resolve().parent / "evaluate_dataset.py",
        evaluation_root / "evaluate.py", evaluation_root / "evaluate_utils.py",
    ]
    gold_files = list((evaluation_root / "gold").rglob("*")) if (evaluation_root / "gold").exists() else []
    selector_environment_keys = (
        "MODEL_NAME", "OPENAI_BASE_URL", "SLAYQL_RESEARCH_VERSION",
        "SLAYQL_SELECTOR_MARGIN", "SLAYQL_SELECTOR_MIN_SCORE",
        "SLAYQL_SELECTOR_VERIFY", "SLAYQL_SELECTOR_W_EXEC", "SLAYQL_SELECTOR_W_CONTRACT",
        "SLAYQL_SELECTOR_W_SHAPE", "SLAYQL_SELECTOR_W_VALUE", "SLAYQL_SELECTOR_W_EVIDENCE",
        "SLAYQL_SELECTOR_W_SEMANTIC", "SLAYQL_SELECTOR_W_CONSENSUS", "SLAYQL_SELECTOR_W_DIVERSITY",
        "SLAYQL_SELECTOR_W_RISK", "SLAYQL_SELECTOR_W_ANSWER_PLAN",
        "SLAYQL_SELECTOR_TOURNAMENT_SIZE", "SLAYQL_SELECTOR_TOURNAMENT_MARGIN",
        "SLAYQL_SELECTOR_REPAIR_PENALTY",
        "SLAYQL_SELECTOR_WORKERS", "SLAYQL_SELECTOR_RETRIES",
        "SLAYQL_SELECTOR_BACKOFF", "SLAYQL_SELECTOR_TIMEOUT",
    )
    candidate_fingerprint = _artifact_fingerprint(
        source_root, _candidate_artifacts(source_root, sorted(data), task, count),
    )
    schema_catalogs = {
        str(Path(str(item.get("db_path"))).resolve()): _schema_catalog(item)
        for item in data.values() if item.get("db_path") and Path(str(item.get("db_path"))).is_file()
    }
    source_metadata_files = [
        source_root / name for name in (
            "run_manifest.json", "dataset_manifest.json", "subset_manifest.json", "resolved_config.json"
        )
    ]
    stable_configuration = {
        "source_root": str(source_root), "dataset_sha256": sha256_file(str(data_file)),
        "record_count": len(data), "instance_ids_sha256": hashlib.sha256(
            json.dumps(sorted(data)).encode("utf-8")
        ).hexdigest(),
        "task": task, "num_candidates": count, "verification_enabled": allow_verification,
        "candidate_artifacts": candidate_fingerprint,
        "source_run_metadata": _artifact_fingerprint(source_root, source_metadata_files),
        "schema_catalogs_sha256": hashlib.sha256(
            json.dumps(schema_catalogs, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "schema_catalog_count": len(schema_catalogs),
        "selector_environment": {
            key: os.environ.get(key) for key in selector_environment_keys if os.environ.get(key) is not None
        },
        "code_and_evaluator": _artifact_fingerprint(repo_root, evaluator_files),
        "gold_assets": _artifact_fingerprint(repo_root, gold_files),
        "git": _git_snapshot(repo_root),
    }
    return {
        "schema_version": "1.1", "mode": "offline_selector_replay",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_root": str(source_root), "output_root": str(output_root),
        "status": "prepared", "configuration": stable_configuration,
        "replay_fingerprint": hashlib.sha256(
            json.dumps(stable_configuration, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def _selection_worker(
    source_root: Path, output_root: Path, instance_id: str, item: Dict[str, Any],
    task: str, count: int, allow_verification: bool,
) -> str:
    """Select and persist one instance; each worker owns its local state."""
    final = output_root / "sql_selection_v1" / "final" / instance_id / "selected.sql"
    artifact = output_root / "selection" / f"{instance_id}.json"
    if final.exists() and artifact.exists():
        return "skipped"
    result = select_instance(
        instance_id,
        collect_candidates(source_root, task, instance_id, count),
        item.get("question", ""), item,
        allow_verification=allow_verification,
    )
    write_selection(output_root, instance_id, result)
    return "selected"


def _run_selection_batch(
    source_root: Path, output_root: Path, data: Dict[str, Dict[str, Any]],
    task: str, count: int, *, allow_verification: bool, max_workers: int,
) -> None:
    """Run independent instance selections concurrently with resumable writes."""
    pending = []
    for instance_id, item in sorted(data.items()):
        final = output_root / "sql_selection_v1" / "final" / instance_id / "selected.sql"
        artifact = output_root / "selection" / f"{instance_id}.json"
        if not (final.exists() and artifact.exists()):
            pending.append((instance_id, item))
    if not pending:
        print("Selector: no pending instances; all selection artifacts are already complete.", flush=True)
        return

    workers = max(1, min(25, int(max_workers)))
    print(
        f"Selector: {len(pending)} pending instances using {workers} concurrent workers",
        flush=True,
    )
    failures = []
    completed = 0
    progress_interval = max(1, min(25, len(pending) // 20 or 1))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="selector") as executor:
        futures = {
            executor.submit(
                _selection_worker, source_root, output_root, instance_id, item,
                task, count, allow_verification,
            ): instance_id
            for instance_id, item in pending
        }
        for future in as_completed(futures):
            instance_id = futures[future]
            try:
                future.result()
            except Exception as exc:
                failures.append({"instance_id": instance_id, "error": str(exc)[:2000]})
            completed += 1
            if completed == len(pending) or completed % progress_interval == 0:
                print(f"Selector progress: {completed}/{len(pending)}", flush=True)

    failure_path = output_root / "selection_failures.json"
    atomic_write_json(str(failure_path), {
        "status": "incomplete" if failures else "complete",
        "pending_at_start": len(pending), "completed": len(pending) - len(failures),
        "max_workers": workers, "failures": failures,
    })
    if failures:
        raise RuntimeError(
            f"Selector failed for {len(failures)} instance(s); successful selections are preserved. "
            "Rerun the same command to retry only the failed instances."
        )


def run_offline_replay(args: argparse.Namespace) -> None:
    source_root = Path(args.log_path).resolve()
    output_root = Path(args.offline_replay_output).resolve()
    if source_root == output_root:
        raise ValueError("Offline replay output must differ from the source run")
    source_dataset = source_root / "dataset.json"
    data_file = source_dataset if source_dataset.exists() else Path(args.data_file).resolve()
    data = json.loads(data_file.read_text(encoding="utf-8"))
    manifest = build_replay_manifest(
        source_root, output_root, data_file, data, args.task, args.num_candidates,
        bool(args.allow_replay_verification),
    )
    existing_manifest = output_root / "offline_replay_manifest.json"
    if output_root.exists() and any(output_root.iterdir()):
        if not existing_manifest.exists():
            raise RuntimeError(f"Offline replay output is non-empty and has no replay manifest: {output_root}")
        existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if existing.get("replay_fingerprint") != manifest["replay_fingerprint"]:
            raise RuntimeError("Offline replay source artifacts or frozen configuration changed")
        manifest = existing
    else:
        output_root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(str(existing_manifest), manifest)

    _run_selection_batch(
        source_root, output_root, data, args.task, args.num_candidates,
        allow_verification=bool(args.allow_replay_verification),
        max_workers=getattr(args, "selector_workers", 25),
    )
    manifest["status"] = "complete"
    manifest["completed_instances"] = len(list((output_root / "selection").glob("*.json")))
    atomic_write_json(str(existing_manifest), manifest)


def run(args: argparse.Namespace) -> None:
    if args.offline_replay_output:
        run_offline_replay(args)
        return
    log_root = Path(args.log_path).resolve()
    data = json.loads((log_root / "dataset.json").read_text(encoding="utf-8")) if (log_root / "dataset.json").exists() else json.loads(Path(args.data_file).read_text(encoding="utf-8"))
    _run_selection_batch(
        log_root, log_root, data, args.task, args.num_candidates,
        allow_verification=True, max_workers=getattr(args, "selector_workers", 25),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_path", required=True)
    parser.add_argument("--data_file", required=True)
    parser.add_argument("--num_candidates", type=int, default=5)
    parser.add_argument("--task", default="r1_lite")
    parser.add_argument(
        "--selector-workers", type=int,
        default=int(os.environ.get("SLAYQL_SELECTOR_WORKERS", "25")),
        help="Maximum concurrent independent instance selections (default: 25)",
    )
    parser.add_argument(
        "--selector-retries", type=int,
        default=int(os.environ.get("SLAYQL_SELECTOR_RETRIES", "5")),
        help="Provider attempts per selector call (default: 5)",
    )
    parser.add_argument(
        "--offline-replay-output",
        help="Replay selection from --log_path candidate artifacts into a separate output directory",
    )
    parser.add_argument(
        "--allow-replay-verification", action="store_true",
        help="Allow provider verification during offline replay (disabled by default)",
    )
    args = parser.parse_args()
    os.environ["SLAYQL_SELECTOR_RETRIES"] = str(max(1, args.selector_retries))
    run(args)


if __name__ == "__main__":
    main()

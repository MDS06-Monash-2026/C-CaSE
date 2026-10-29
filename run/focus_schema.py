"""Deterministically focus completed schema prompts for SlayQL v1.4-v1.9.

The completion agent still receives the normal retrieval and database tools.
This post-completion pass reduces prompt noise for SQL generation while keeping
linked columns, join endpoints, and a bounded fallback from each selected table.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from artifact_store import atomic_write_json, atomic_write_text


_TABLE_RE = re.compile(r"^###Table full name:\s*(.*?)\s*$", re.MULTILINE)
_COLUMN_RE = re.compile(r"^\s{4}([^\s(]+)\s+\(Type:", re.MULTILINE)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_MARKERS = (
    "-- SLAYQL_INTERACTION_EVIDENCE_V12 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V13 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V14 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V15 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V16 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V17 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V18 --",
    "-- SLAYQL_INTERACTION_EVIDENCE_V19 --",
)
_FOCUS_MARKER = "-- SLAYQL_SCHEMA_FOCUS_V14 --"
_FOCUS_MARKERS = (_FOCUS_MARKER, "-- SLAYQL_SCHEMA_FOCUS_V15 --", "-- SLAYQL_SCHEMA_FOCUS_V16 --", "-- SLAYQL_SCHEMA_FOCUS_V17 --", "-- SLAYQL_SCHEMA_FOCUS_V18 --", "-- SLAYQL_SCHEMA_FOCUS_V19 --")
_KEY_NAMES = {"id", "name", "code", "date", "year", "key"}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value or "").lower())


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "")}


def _table_key(value: Any) -> str:
    return _norm(str(value or "").split(".")[-1])


def _suite_version(version: str | None = None) -> str:
    return version or os.environ.get("SLAYQL_RESEARCH_VERSION", "1.4")


def _focus_marker(version: str | None = None) -> str:
    suite_version = _suite_version(version)
    if suite_version == "1.9":
        return "-- SLAYQL_SCHEMA_FOCUS_V19 --"
    if suite_version == "1.8":
        return "-- SLAYQL_SCHEMA_FOCUS_V18 --"
    if suite_version == "1.7":
        return "-- SLAYQL_SCHEMA_FOCUS_V17 --"
    if suite_version == "1.6":
        return "-- SLAYQL_SCHEMA_FOCUS_V16 --"
    return "-- SLAYQL_SCHEMA_FOCUS_V15 --" if suite_version == "1.5" else _FOCUS_MARKER


def _split_schema(schema: str) -> Tuple[str, List[Tuple[str, str]], str]:
    matches = list(_TABLE_RE.finditer(schema))
    if not matches:
        return schema, [], ""
    prefix = schema[: matches[0].start()]
    tail_start = len(schema)
    for marker in _MARKERS:
        marker_pos = schema.find(marker, matches[-1].end())
        if marker_pos >= 0:
            tail_start = min(tail_start, marker_pos)
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else tail_start
        blocks.append((match.group(1).strip(), schema[match.start():end].strip()))
    tail = schema[tail_start:].strip() if tail_start < len(schema) else ""
    return prefix, blocks, tail


def _evidence_tables(evidence: Dict[str, Any]) -> Tuple[Dict[str, float], set[str], set[str]]:
    table_scores: Dict[str, float] = {}
    linked_columns: set[str] = set()
    linked_tables: set[str] = set()
    for entry in evidence.get("lexical_matches", []):
        table = _table_key(entry.get("table"))
        column = _norm(entry.get("column"))
        if not table:
            continue
        linked_tables.add(table)
        table_scores[table] = max(table_scores.get(table, 0.0), float(entry.get("score", 0.0)))
        if column:
            linked_columns.add(f"{table}.{column}")
    closure = evidence.get("relational_closure", {})
    for table in closure.get("tables", []):
        table_key = _table_key(table)
        if table_key:
            linked_tables.add(table_key)
            table_scores.setdefault(table_key, 0.5)
    edges = (
        closure.get("edges", [])
        + evidence.get("recommended_joins", [])
        + evidence.get("relationships", [])
    )
    for edge in edges:
        left, right = _table_key(edge.get("from_table")), _table_key(edge.get("to_table"))
        if left and right and (left in linked_tables or right in linked_tables):
            linked_tables.update((left, right))
            linked_columns.update({
                f"{left}.{_norm(edge.get('from_column'))}",
                f"{right}.{_norm(edge.get('to_column'))}",
            })
    return table_scores, linked_tables, linked_columns


def question_plan(question: str, evidence: Dict[str, Any], version: str | None = None) -> str:
    contract = evidence.get("question_contract", {})
    lowered = str(question or "").lower()
    if re.search(r"\b(how many|number of|count)\b", lowered):
        output = "count"
    elif re.search(r"\b(average|mean|sum|total|maximum|minimum|max|min)\b", lowered):
        output = "aggregate"
    elif re.search(r"\b(full name|name|who|which person|which player|which racer|which driver)\b", lowered):
        output = "entity attributes (preserve every requested name/identity column)"
    else:
        output = "direct projection"
    operations = contract.get("operations") or ["direct projection"]
    ordering = "required" if contract.get("ranking_or_order") else "not implied"
    joins = "required or verify a join path" if contract.get("join_likely") else "avoid unless the question requires it"
    time_filter = "required" if contract.get("time_constraint") else "not implied"
    plan_version = _suite_version(version)
    guardrails = (
        "- Preserve requested output arity; do not invent DISTINCT, concatenation, latest-per-entity, or deduplication.\n"
        "- Compare the direct table path with relational-closure alternatives before committing to a join.\n"
        if plan_version in {"1.5", "1.6", "1.7", "1.8", "1.9"} else ""
    )
    return (
        f"-- SLAYQL_V{plan_version.replace('.', '')}_QUESTION_PLAN --\n"
        f"- Output intent: {output}\n"
        f"- Operations: {operations}; grouping={bool(contract.get('grouping'))}\n"
        f"- Ordering/ranking: {ordering}; time filter: {time_filter}\n"
        f"- Join behavior: {joins}\n"
        f"{guardrails}"
        "- Use only fields supported by the focused schema and evidence; verify the final answer grain.\n"
    )


def _focus_block(
    table: str, block: str, question: str, linked_columns: set[str],
    max_columns: int,
) -> Tuple[str, int]:
    lines = block.splitlines()
    column_lines = []
    for index, line in enumerate(lines):
        match = re.match(r"^\s{4}([^\s(]+)\s+\(Type:", line)
        if match:
            column_lines.append((index, match.group(1), line))
    if len(column_lines) <= max_columns:
        return block, len(column_lines)
    table_key = _table_key(table)
    query_tokens = _tokens(question)
    scored = []
    for original_index, column, line in column_lines:
        column_key = _norm(column)
        score = 0.0
        if f"{table_key}.{column_key}" in linked_columns:
            score += 100.0
        score += 4.0 * sum(token in column_key for token in query_tokens)
        simple_name = column_key.rstrip("0123456789")
        if simple_name in _KEY_NAMES or simple_name.endswith("id") or simple_name.endswith("key"):
            score += 2.0
        scored.append((score, -original_index, original_index, line))
    keep = {item[2] for item in sorted(scored, reverse=True)[:max_columns]}
    output = [line for index, line in enumerate(lines) if index not in {item[0] for item in column_lines} or index in keep]
    return "\n".join(output), len(keep)


def _v19_mandatory_tables(
    blocks: List[Tuple[str, str]], evidence: Dict[str, Any],
) -> Tuple[List[Tuple[str, str]], set[str]]:
    """Return tables/columns required by the semantic output contract.

    v1.8's ranked closure could still spend the table budget on join evidence
    while omitting a physical output column.  v1.9 reserves the first schema
    slots for exact contract columns and measured answer-plan tables, then lets
    the normal ranking fill the remaining slots.
    """
    contract = evidence.get("semantic_contract", {}) or {}
    output = contract.get("output", {}) or {}
    required_columns = {
        _norm(value) for value in (
            contract.get("required_columns", [])
            + output.get("physical_output_columns", [])
        ) if _norm(value)
    }
    available = { _table_key(table): (table, block) for table, block in blocks }
    mandatory_keys: List[str] = []
    for table, block in blocks:
        columns = {_norm(match.group(1)) for match in re.finditer(r"^\s{4}([^\s(]+)\s+\(Type:", block, re.MULTILINE)}
        if columns & required_columns and _table_key(table) not in mandatory_keys:
            mandatory_keys.append(_table_key(table))
    for table in (evidence.get("answer_plan", {}) or {}).get("likely_tables", []):
        key = _table_key(table)
        if key in available and key not in mandatory_keys:
            mandatory_keys.append(key)
    linked_columns = {
        f"{_table_key(table)}.{_norm(column)}"
        for key, (table, block) in available.items() if key in mandatory_keys
        for column in re.findall(r"^\s{4}([^\s(]+)\s+\(Type:", block, re.MULTILINE)
        if _norm(column) in required_columns
    }
    return [available[key] for key in mandatory_keys], linked_columns


def focus_one(schema: str, question: str, evidence: Dict[str, Any], *, max_tables: int = 5,
              max_columns_per_table: int = 12, max_columns_total: int = 48,
              version: str | None = None) -> Tuple[str, Dict[str, Any]]:
    marker = _focus_marker(version)
    if marker in schema:
        return schema, {"focused": True, "reason": "already_focused", "mode": "post_completion_question_grounded"}
    prefix, blocks, tail = _split_schema(schema)
    if not blocks:
        return schema, {"focused": False, "reason": "no_table_blocks"}
    table_scores, linked_tables, linked_columns = _evidence_tables(evidence)
    closure_seeds = {
        _table_key(table) for table in evidence.get("relational_closure", {}).get("seed_tables", [])
    }
    ranked_tables = sorted(
        blocks,
        key=lambda item: (
            2 if _table_key(item[0]) in closure_seeds else 1 if _table_key(item[0]) in linked_tables else 0,
            table_scores.get(_table_key(item[0]), -1.0),
            -blocks.index(item),
        ),
        reverse=True,
    )
    mandatory_items: List[Tuple[str, str]] = []
    mandatory_columns: set[str] = set()
    if _suite_version(version) == "1.9":
        mandatory_items, mandatory_columns = _v19_mandatory_tables(blocks, evidence)
        linked_columns.update(mandatory_columns)
    if _suite_version(version) == "1.9" and mandatory_items:
        selected = mandatory_items[:max_tables]
        for item in ranked_tables:
            if item not in selected and len(selected) < max_tables:
                selected.append(item)
    elif _suite_version(version) in {"1.5", "1.6", "1.7", "1.8"} and linked_tables:
        # Relational closure augments semantic retrieval. Keep two slots for
        # the original RBP order so a noisy closure cannot erase alternatives.
        evidence_quota = max(1, max_tables - min(2, max_tables))
        selected = [
            item for item in ranked_tables if _table_key(item[0]) in linked_tables
        ][:evidence_quota]
        for item in blocks:
            if item not in selected and len(selected) < max_tables:
                selected.append(item)
        for item in ranked_tables:
            if item not in selected and len(selected) < max_tables:
                selected.append(item)
    else:
        selected = ranked_tables[:max_tables] if linked_tables else blocks[:max_tables]
    selected_keys = {_table_key(item[0]) for item in selected}
    focused_blocks = []
    total_columns = 0
    for table, block in selected:
        remaining = max(0, max_columns_total - total_columns)
        if remaining == 0:
            break
        focused, column_count = _focus_block(
            table, block, question, linked_columns,
            min(max_columns_per_table, remaining),
        )
        focused_blocks.append(focused)
        total_columns += column_count
    plan = question_plan(question, evidence, version=version)
    output_parts = [prefix.rstrip(), marker, plan.rstrip()] + focused_blocks
    if tail:
        output_parts.append(tail)
    output = "\n\n".join(part for part in output_parts if part.strip()).rstrip() + "\n"
    return output, {
        "focused": True,
        "source_tables": len(blocks),
        "selected_tables": len(selected),
        "selected_table_names": [item[0] for item in selected],
        "selected_columns": total_columns,
        "linked_tables": sorted(linked_tables),
        "relational_closure_tables": evidence.get("relational_closure", {}).get("tables", []),
        "relational_closure_seeds": evidence.get("relational_closure", {}).get("seed_tables", []),
        "mode": "post_completion_question_grounded",
    }


def build(data_file: str, schema_dir: str, evidence_dir: str, output_root: str,
          max_tables: int = 5, max_columns_per_table: int = 12,
          max_columns_total: int = 48, version: str | None = None) -> Dict[str, Any]:
    data = json.loads(Path(data_file).read_text(encoding="utf-8"))
    schema_root, evidence_root, output = Path(schema_dir), Path(evidence_dir), Path(output_root)
    items = []
    for instance_id, item in sorted(data.items()):
        schema_path = schema_root / f"{instance_id}.txt"
        evidence_path = evidence_root / f"{instance_id}.json"
        if not schema_path.exists():
            items.append({"instance_id": instance_id, "focused": False, "reason": "schema_missing"})
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {}
            focused, details = focus_one(
                schema_path.read_text(encoding="utf-8", errors="replace"), item.get("question", ""), evidence,
                max_tables=max_tables, max_columns_per_table=max_columns_per_table,
                max_columns_total=max_columns_total, version=version,
            )
            atomic_write_text(str(schema_path), focused)
            items.append({"instance_id": instance_id, **details})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            items.append({"instance_id": instance_id, "focused": False, "reason": str(error)[:200]})
    manifest = {
        "schema_version": _suite_version(version), "stage": "schema_focus", "record_count": len(items),
        "max_tables": max_tables, "max_columns_per_table": max_columns_per_table,
        "max_columns_total": max_columns_total, "instances": items,
    }
    atomic_write_json(str(output / "schema_focus_manifest.json"), manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Focus completed schemas for SlayQL v1.4-v1.9")
    parser.add_argument("--data_file", required=True)
    parser.add_argument("--schema_dir", required=True)
    parser.add_argument("--evidence_dir", required=True)
    parser.add_argument("--output_root", required=True)
    parser.add_argument("--max-tables", type=int, default=5)
    parser.add_argument("--max-columns-per-table", type=int, default=12)
    parser.add_argument("--max-columns-total", type=int, default=48)
    parser.add_argument("--version", choices=("1.4", "1.5", "1.6", "1.7", "1.8", "1.9"))
    args = parser.parse_args()
    result = build(
        args.data_file, args.schema_dir, args.evidence_dir, args.output_root,
        args.max_tables, args.max_columns_per_table, args.max_columns_total, args.version,
    )
    print(f"Focused schemas ready: {result['record_count']} instances", flush=True)


if __name__ == "__main__":
    main()

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from dialect import resolve_dialect


_GENERIC_RELATIONSHIP_COLUMNS = {
    "id",
    "name",
    "date",
    "time",
    "value",
    "type",
    "text",
    "code",
    "status",
    "description",
}


def _column_type(metadata: Any) -> str:
    if isinstance(metadata, dict):
        return str(metadata.get("type") or metadata.get("column_type") or "")
    match = re.search(r"column type:\s*([^\n]+)", str(metadata), re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _document_path(dialect: str, base_dir: str) -> str:
    return os.path.join(base_dir, "documents", f"{dialect}.json")


def _load_cloud_metadata(db_name: str, dialect: str, base_dir: str) -> Dict[str, Any]:
    document_name = "bigquery" if dialect == "bigquery" else "snowflake"
    path = _document_path(document_name, base_dir)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            database = json.load(handle).get(db_name, {})
    except (OSError, json.JSONDecodeError):
        database = {}

    table_info = {}
    for table_name, table_metadata in database.items():
        columns = {}
        if isinstance(table_metadata, dict):
            for column_name, metadata in table_metadata.get("columns", {}).items():
                columns[column_name] = {"type": _column_type(metadata)}
        table_info[table_name] = {"columns": columns}
    return {"tables": list(table_info), "table_info": table_info, "foreign_keys": []}


def _sqlite_candidates(db_name: str, base_dir: str) -> Iterable[Path]:
    resource = Path(base_dir) / "resource" / "databases"
    yield resource / "spider2-localdb" / f"{db_name}.sqlite"
    yield resource / f"{db_name}.sqlite"


def _load_sqlite_metadata(db_name: str, base_dir: str) -> Dict[str, Any]:
    db_path: Optional[Path] = next((path for path in _sqlite_candidates(db_name, base_dir) if path.exists()), None)
    if db_path is None:
        return {"tables": [], "table_info": {}, "foreign_keys": []}

    table_info: Dict[str, Any] = {}
    foreign_keys = []
    with sqlite3.connect(str(db_path)) as connection:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table_name,) in table_rows:
            columns = {}
            escaped = table_name.replace("'", "''")
            for row in connection.execute(f"PRAGMA table_info('{escaped}')").fetchall():
                columns[row[1]] = {"type": row[2], "primary_key": bool(row[5])}
            table_info[table_name] = {"columns": columns}
            for row in connection.execute(f"PRAGMA foreign_key_list('{escaped}')").fetchall():
                foreign_keys.append([table_name, row[3], row[2], row[4]])
    return {
        "tables": list(table_info),
        "table_info": table_info,
        "foreign_keys": foreign_keys,
    }


def _infer_relationships(metadata: Dict[str, Any], selected_tables: Optional[Iterable[str]]) -> list:
    selected = {item.lower() for item in selected_tables or []}
    table_info = metadata.get("table_info", {})
    candidates = []
    for table_name, info in table_info.items():
        if selected and table_name.lower() not in selected:
            continue
        for column_name, column_info in info.get("columns", {}).items():
            normalized = column_name.lower().replace("-", "_")
            if normalized in _GENERIC_RELATIONSHIP_COLUMNS or not normalized.endswith("_id"):
                continue
            candidates.append((table_name, column_name, normalized, column_info.get("type", "")))

    inferred = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if left[0] == right[0] or left[2] != right[2]:
                continue
            left_type, right_type = str(left[3]).upper(), str(right[3]).upper()
            if left_type and right_type and left_type != right_type:
                continue
            inferred.append([left[0], left[1], right[0], right[1], "inferred"])
    return inferred


def build_relationship_metadata(
    instance_id: str,
    db_name: str,
    base_dir: str = ".",
    selected_tables: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    dialect = resolve_dialect(instance_id).key
    if dialect == "sqlite":
        metadata = _load_sqlite_metadata(db_name, base_dir)
    else:
        metadata = _load_cloud_metadata(db_name, dialect, base_dir)

    explicit = list(metadata.get("foreign_keys", []))
    inferred = _infer_relationships(metadata, selected_tables)
    metadata["foreign_keys"] = explicit + [item[:4] for item in inferred]
    metadata["graph_stats"] = {
        "nodes": len(metadata.get("tables", [])),
        "explicit_edges": len(explicit),
        "inferred_edges": len(inferred),
        "edges": len(explicit) + len(inferred),
        "status": "ready" if explicit or inferred else "no_graph",
    }
    return metadata


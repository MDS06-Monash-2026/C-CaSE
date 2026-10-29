"""Build isolated schema documents, embeddings, and BM25 indexes for SQLite datasets."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from artifact_store import atomic_write_json, sha256_file
from value_grounder import build_db_value_index


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def inspect_database(db_path: Path) -> Dict[str, Any]:
    database: Dict[str, Any] = {}
    with sqlite3.connect(str(db_path)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (table_name,) in tables:
            escaped = table_name.replace("'", "''")
            columns = connection.execute(f"PRAGMA table_info('{escaped}')").fetchall()
            sample_rows: List[tuple] = []
            try:
                sample_rows = connection.execute(
                    f"SELECT * FROM {_quote_identifier(table_name)} LIMIT 5"
                ).fetchall()
            except sqlite3.Error:
                pass
            column_names = [row[1] for row in columns]
            column_types = [row[2] or "TEXT" for row in columns]
            sample_values = []
            descriptions = {}
            for index, (column_name, column_type) in enumerate(zip(column_names, column_types)):
                values = [str(row[index]) for row in sample_rows if index < len(row) and row[index] is not None]
                sample_values.append(values)
                descriptions[column_name] = (
                    f"column name: {column_name}\n"
                    f"column type: {column_type}\n"
                    f"table name: {table_name}\n"
                    f"description: SQLite column {table_name}.{column_name}\n"
                )
            foreign_keys = []
            for row in connection.execute(f"PRAGMA foreign_key_list('{escaped}')").fetchall():
                foreign_keys.append([table_name, row[3], row[2], row[4]])
            database[table_name] = {
                "similar_tables": [],
                "columns": descriptions,
                "column_types": column_types,
                "sample_values": sample_values,
                "foreign_keys": foreign_keys,
            }
    return database


def build(data_file: Path, output_root: Path, model_name: str) -> Dict[str, Any]:
    data = json.loads(data_file.read_text(encoding="utf-8"))
    database_paths = {}
    for item in data.values():
        if item.get("db_name") and item.get("db_path"):
            database_paths[item["db_name"]] = Path(item["db_path"])
    if not database_paths:
        raise ValueError("No SQLite databases were resolved in the dataset manifest")

    documents = {}
    for db_name, db_path in sorted(database_paths.items()):
        if not db_path.exists():
            raise FileNotFoundError(f"Missing SQLite database: {db_path}")
        documents[db_name] = inspect_database(db_path)

    documents_dir = output_root / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(documents_dir / "localdb.json"), documents)
    for placeholder in ("bigquery.json", "snowflake.json"):
        if not (documents_dir / placeholder).exists():
            atomic_write_json(str(documents_dir / placeholder), {})

    model = None
    embeddings_root = output_root / "embeddings" / "localdb"
    bm25_root = output_root / "bm25_indices"
    embeddings_root.mkdir(parents=True, exist_ok=True)
    bm25_root.mkdir(parents=True, exist_ok=True)

    manifest_path = output_root / "asset_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("model") != model_name:
            raise RuntimeError("Existing asset manifest uses a different embedding model")
    else:
        manifest = {"model": model_name, "databases": {}}
    checkpoint_root = output_root / "checkpoints" / "assets"
    for db_name, database in sorted(documents.items()):
        safe_db_name = "".join(character if character.isalnum() or character in "_.-" else "_" for character in db_name)
        checkpoint_path = checkpoint_root / f"{safe_db_name}.json"
        db_dir = embeddings_root / db_name
        index_path = db_dir / "index.faiss"
        metadata_path = db_dir / "metadata.json"
        if checkpoint_path.exists() and index_path.exists() and metadata_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if (checkpoint.get("index_sha256") == sha256_file(str(index_path)) and
                    checkpoint.get("metadata_sha256") == sha256_file(str(metadata_path))):
                continue
        if model is None:
            model = SentenceTransformer(model_name, device="cuda" if _cuda_available() else "cpu")
        metadata = []
        descriptions = []
        for table_name, table in database.items():
            for index, (column_name, description) in enumerate(table["columns"].items()):
                descriptions.append(description)
                metadata.append({
                    "table": table_name,
                    "column": column_name,
                    "column_type": table["column_types"][index],
                    "column_value": table["sample_values"][index],
                    "description": description,
                })
        if not metadata:
            raise ValueError(f"No schema columns found for {db_name}")
        vectors = model.encode(descriptions, convert_to_numpy=True, show_progress_bar=False)
        vectors = np.asarray(vectors, dtype=np.float32)
        db_dir.mkdir(parents=True, exist_ok=True)
        index = faiss.IndexFlatL2(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(db_dir / "index.faiss"))
        atomic_write_json(str(db_dir / "metadata.json"), metadata)
        with sqlite3.connect(str(database_paths[db_name])) as connection:
            build_db_value_index(connection, db_name, output_dir=str(bm25_root))
        manifest["databases"][db_name] = {
            "db_path": str(database_paths[db_name]),
            "tables": len(database),
            "columns": len(metadata),
        }
        atomic_write_json(str(manifest_path), manifest)
        atomic_write_json(str(checkpoint_path), {
            "db_name": db_name,
            "status": "complete",
            "index_sha256": sha256_file(str(index_path)),
            "metadata_sha256": sha256_file(str(metadata_path)),
        })
    atomic_write_json(str(manifest_path), manifest)
    return manifest


def _cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_file", required=True, type=Path)
    parser.add_argument("--output_root", required=True, type=Path)
    parser.add_argument("--model", default="BAAI/bge-large-en-v1.5")
    args = parser.parse_args()
    summary = build(args.data_file, args.output_root, args.model)
    print(f"Prepared {len(summary['databases'])} SQLite database asset sets")


if __name__ == "__main__":
    main()

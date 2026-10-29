"""Dataset-aware, checkpointed SlayQL v1.1 pipeline entry point.

The legacy Spider-2 scripts remain available. This module owns new run roots,
dataset normalization, smoke/subset manifests, local dataset preparation, and
stage orchestration so historical result directories are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from artifact_store import atomic_write_json, atomic_write_text, sha256_file
from dotenv import load_dotenv


RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parent
DEFAULT_SUBSET = RUN_DIR / "subset_diverse_20_evaluation.json"
DEFAULT_SPIDER2_DATA = RUN_DIR / "spider2_data.json"
load_dotenv(RUN_DIR / ".env")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    atomic_write_json(str(path), payload)


def _hash_json(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _safe_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_") or "unknown"


def _first_existing(root: Path, names: Sequence[str]) -> Optional[Path]:
    for name in names:
        direct = root / name
        if direct.exists():
            return direct
    for name in names:
        matches = sorted(root.rglob(name))
        if matches:
            return matches[0]
    return None


def _find_sqlite(root: Path, db_id: str) -> Optional[Path]:
    candidates = [
        root / db_id / f"{db_id}.sqlite",
        root / db_id / f"{db_id}.db",
        root / f"{db_id}.sqlite",
        root / f"{db_id}.db",
    ]
    for path in candidates:
        if path.exists():
            return path.resolve()
    for path in sorted(root.rglob("*.sqlite")) + sorted(root.rglob("*.db")):
        if path.stem.lower() == db_id.lower() or path.parent.name.lower() == db_id.lower():
            return path.resolve()
    return None


def _index_sqlite_databases(root: Path) -> Dict[str, Path]:
    """Index a dataset's SQLite paths once instead of rescanning per question."""
    indexed: Dict[str, Path] = {}
    for pattern in ("*.sqlite", "*.db"):
        for path in sorted(root.rglob(pattern)):
            if not path.is_file() or "__MACOSX" in path.parts:
                continue
            resolved = path.resolve()
            indexed.setdefault(path.stem.lower(), resolved)
            indexed.setdefault(path.parent.name.lower(), resolved)
    return indexed


def _discover_bird_files(root: Path, split: str) -> Dict[str, Optional[Path]]:
    split = split.lower()
    data = _first_existing(root, [f"{split}.json", f"{split}.jsonl"])
    sql = _first_existing(root, [f"{split}.sql", f"{split}_gold.sql"])
    database = _first_existing(root, [f"{split}_databases", "databases", "database"])
    if database is None:
        database = root
    return {"data": data, "sql": sql, "database": database}


def _prompt_bird_root(initial: Optional[str] = None) -> Path:
    if initial and os.environ.get("SLAYQL_NONINTERACTIVE") == "1":
        root = Path(initial).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"BIRD directory does not exist: {root}")
        print(f"BIRD dataset directory (non-interactive): {root}")
        return root
    suggestion = f" [{initial}]" if initial else " [suggested: D:\\Downloads\\train]"
    candidate = input(f"Enter the BIRD dataset directory{suggestion}: ").strip() or (initial or "")
    if not candidate:
        raise ValueError("A BIRD dataset directory is required")
    root = Path(candidate).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"BIRD directory does not exist: {root}")
    print(f"BIRD dataset directory: {root}")
    print("BIRD directory listing:")
    for item in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        kind = "DIR" if item.is_dir() else "FILE"
        print(f"  [{kind}] {item.name}")
    answer = input("Continue with this BIRD directory? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("BIRD directory selection was not confirmed")
    return root


def _load_records(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records
    payload = _read_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        return list(payload.values())
    raise ValueError(f"Unsupported dataset format: {path}")


def _load_sql_lines(path: Optional[Path]) -> List[str]:
    if path is None or not path.exists():
        return []
    return [line.split("\t", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _normalize_spider2(split: str, source: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    payload = _read_json(source)
    if not isinstance(payload, dict):
        raise ValueError("Spider 2.0-Lite data must be an object keyed by instance ID")
    records = {}
    for instance_id, value in payload.items():
        item = dict(value)
        item.setdefault("instance_id", instance_id)
        item.setdefault("split", split)
        item.setdefault("backend", "bigquery" if str(instance_id).startswith(("bq", "ga")) else "snowflake" if str(instance_id).startswith("sf") else "sqlite")
        records[str(instance_id)] = item
    manifest = {
        "dataset": "spider2-lite",
        "split": split,
        "source_files": [str(source)],
        "source_hashes": {str(source): sha256_file(str(source))},
        "record_count": len(records),
    }
    return records, manifest


def _normalize_spider1(split: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    root = REPO_ROOT / "spider_data" / "spider_data"
    source = root / f"{split}.json"
    if not source.exists():
        raise FileNotFoundError(f"Spider 1.0 split not found: {source}")
    raw = _load_records(source)
    records: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(raw):
        db_id = str(item.get("db_id") or item.get("database_id") or "")
        if not db_id:
            raise ValueError(f"Spider 1.0 record {index} has no db_id")
        instance_id = f"local_spider1_{split}_{index:05d}"
        database_root = root / ("test_database" if split.lower() == "test" else "database")
        db_path = _find_sqlite(database_root, db_id)
        records[instance_id] = {
            "instance_id": instance_id,
            "source_id": f"{db_id}:{index}",
            "db_name": db_id,
            "db_id": db_id,
            "question": item.get("question", ""),
            "gold_sql": item.get("query") or item.get("sql"),
            "backend": "sqlite",
            "dialect": "sqlite",
            "db_path": str(db_path) if db_path else None,
            "split": split,
        }
    return records, {
        "dataset": "spider1",
        "split": split,
        "source_files": [str(source)],
        "source_hashes": {str(source): sha256_file(str(source))},
        "record_count": len(records),
        "database_root": str((root / ("test_database" if split.lower() == "test" else "database")).resolve()),
    }


def _normalize_bird(split: str, bird_root: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    files = _discover_bird_files(bird_root, split)
    if files["data"] is None:
        raise FileNotFoundError(f"Could not find {split}.json/.jsonl below {bird_root}")
    raw = _load_records(files["data"])
    sql_lines = _load_sql_lines(files["sql"])
    database_root = files["database"] or bird_root
    database_paths = _index_sqlite_databases(database_root)
    records: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(raw):
        db_id = str(item.get("db_id") or item.get("database_id") or item.get("database") or "")
        if not db_id:
            raise ValueError(f"BIRD record {index} has no database identifier")
        question_id = item.get("question_id", index)
        instance_id = f"local_bird_{split}_{_safe_id(question_id)}_{index:05d}"
        gold_sql = item.get("SQL") or item.get("sql") or item.get("query")
        if not gold_sql and index < len(sql_lines):
            gold_sql = sql_lines[index]
        db_path = database_paths.get(db_id.lower())
        raw_question = item.get("question", "")
        evidence = item.get("evidence", "")
        records[instance_id] = {
            "instance_id": instance_id,
            "source_id": str(question_id),
            "db_name": db_id,
            "db_id": db_id,
            "question": f"{raw_question}\nEvidence: {evidence}" if evidence else raw_question,
            "raw_question": raw_question,
            "evidence": evidence,
            "gold_sql": gold_sql,
            "backend": "sqlite",
            "dialect": "sqlite",
            "db_path": str(db_path) if db_path else None,
            "split": split,
        }
    source_files = [str(files["data"])] + ([str(files["sql"])] if files["sql"] else [])
    return records, {
        "dataset": "bird",
        "split": split,
        "source_files": source_files,
        "source_hashes": {str(path): sha256_file(str(path)) for path in [files["data"], files["sql"]] if path},
        "record_count": len(records),
        "database_root": str(database_root.resolve()),
    }


def normalize_dataset(dataset: str, split: str, bird_root: Optional[str] = None) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    dataset = dataset.lower().replace("_", "-")
    if dataset in {"spider2", "spider2-lite", "spider2.0-lite"}:
        source = DEFAULT_SPIDER2_DATA
        if split == "subset20" and DEFAULT_SUBSET.exists():
            source = DEFAULT_SUBSET
        return _normalize_spider2(split, source)
    if dataset in {"spider1", "spider1.0"}:
        return _normalize_spider1(split)
    if dataset == "bird":
        root = _prompt_bird_root(bird_root)
        return _normalize_bird(split, root)
    raise ValueError(f"Unknown dataset: {dataset}")


def deterministic_ids(
    records: Dict[str, Dict[str, Any]],
    mode: str,
    seed: int = 20260813,
    smoke_count: int = 5,
    excluded_backends: Optional[Sequence[str]] = None,
) -> List[str]:
    excluded = {str(backend).strip().lower() for backend in (excluded_backends or []) if str(backend).strip()}
    ids = sorted(
        instance_id for instance_id, item in records.items()
        if str(item.get("backend", "")).lower() not in excluded
    )
    if not ids:
        raise ValueError(f"No records remain after excluding backends: {sorted(excluded)}")
    if mode == "full":
        return ids
    if mode == "smoke":
        if smoke_count < 1:
            raise ValueError("Smoke count must be at least 1")
        if excluded:
            by_backend: Dict[str, List[str]] = defaultdict(list)
            for instance_id in ids:
                by_backend[str(records[instance_id].get("backend", "unknown")).lower()].append(instance_id)
            balanced: List[str] = []
            backend_names = sorted(by_backend)
            offset = 0
            while len(balanced) < min(smoke_count, len(ids)):
                added = False
                for backend in backend_names:
                    if offset < len(by_backend[backend]):
                        balanced.append(by_backend[backend][offset])
                        added = True
                        if len(balanced) == smoke_count:
                            break
                if not added:
                    break
                offset += 1
            return sorted(balanced)
        return ids[:smoke_count]
    if mode == "subset20":
        if len(ids) <= 5:
            return ids
        count = max(1, int(round(len(ids) * 0.2)))
        rng = random.Random(seed)
        shuffled = ids[:]
        rng.shuffle(shuffled)
        return sorted(shuffled[:count])
    if mode == "backend-smoke":
        selected: List[str] = []
        for backend in ("snowflake", "bigquery", "sqlite"):
            if backend in excluded:
                continue
            matches = [iid for iid in ids if records[iid].get("backend") == backend]
            selected.extend(matches[:3])
        return sorted(selected)
    raise ValueError(f"Unknown run mode: {mode}")


def _sqlite_schema_prompt(db_path: Path) -> str:
    lines = [f"Database: {db_path.stem}", "Dialect: SQLite", ""]
    with sqlite3.connect(str(db_path)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (table,) in tables:
            lines.append(f"Table: {table}")
            escaped = str(table).replace("'", "''")
            for row in connection.execute(f"PRAGMA table_info('{escaped}')").fetchall():
                _, name, col_type, not_null, default, primary_key = row
                marker = " PRIMARY KEY" if primary_key else ""
                lines.append(f"  Column: {name} ({col_type or 'unknown'}){marker}")
            foreign_keys = connection.execute(f"PRAGMA foreign_key_list('{escaped}')").fetchall()
            for fk in foreign_keys:
                lines.append(f"  Foreign key: {fk[3]} -> {fk[2]}.{fk[4]}")
            lines.append("")
    return "\n".join(lines) + "\n"


def validate_local_assets(records: Dict[str, Dict[str, Any]]) -> None:
    for instance_id, item in records.items():
        db_path = item.get("db_path")
        if not db_path or not Path(db_path).exists():
            raise FileNotFoundError(f"Missing SQLite database for {instance_id}: {db_path}")


def make_run_manifest(
    dataset: str,
    split: str,
    mode: str,
    records: Dict[str, Dict[str, Any]],
    source_manifest: Dict[str, Any],
    run_root: Path,
    seed: int,
    smoke_count: int = 5,
    excluded_backends: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    source_is_preserved_subset = any("subset_diverse_20_evaluation.json" in path for path in source_manifest.get("source_files", []))
    selected_ids = (
        sorted(records)
        if source_is_preserved_subset and not excluded_backends
        else deterministic_ids(records, mode, seed, smoke_count, excluded_backends)
    )
    excluded = {str(backend).lower() for backend in (excluded_backends or [])}
    if mode == "backend-smoke":
        required_backends = {
            item.get("backend") for item in records.values()
            if str(item.get("backend", "")).lower() not in excluded
        }
        counts = {backend: sum(records[instance_id].get("backend") == backend for instance_id in selected_ids)
                  for backend in required_backends}
        incomplete = {backend: count for backend, count in counts.items() if count < min(3, sum(item.get("backend") == backend for item in records.values()))}
        if incomplete:
            raise RuntimeError(f"Backend smoke selection is incomplete: {incomplete}")
    selected = {iid: records[iid] for iid in selected_ids}
    subset_path = run_root / "dataset.json"
    _write_json(subset_path, selected)
    subset_manifest = {
        "mode": mode,
        "seed": seed,
        "smoke_count": smoke_count,
        "excluded_backends": sorted(excluded),
        "record_count": len(selected),
        "instance_ids": selected_ids,
        "hash": _hash_json(selected),
    }
    _write_json(run_root / "subset_manifest.json", subset_manifest)
    manifest = {
        "schema_version": "1.0",
        "dataset": dataset,
        "split": split,
        "mode": mode,
        "run_root": str(run_root.resolve()),
        "source": source_manifest,
        "record_count": len(selected),
        "instance_ids": selected_ids,
        "dataset_file": str(subset_path.resolve()),
        "subset_manifest": str((run_root / "subset_manifest.json").resolve()),
        "seed": seed,
        "smoke_count": smoke_count,
        "excluded_backends": sorted(excluded),
        "status": "prepared",
    }
    _write_json(run_root / "run_manifest.json", manifest)
    return manifest


def resolved_config(args: argparse.Namespace) -> Dict[str, Any]:
    environment_keys = (
        "SLAYQL_BM25_THRESHOLD", "SLAYQL_BM25_NORMALIZED", "SLAYQL_VALUE_HINT_CAP",
        "SLAYQL_TOP_N", "ABLATION_NO_BM25", "ABLATION_RBP_ALPHA",
        "ABLATION_ITEE_THRESHOLD", "ABLATION_NO_RBP", "ABLATION_NO_ITEE", "ABLATION_NO_QOC", "SLAYQL_SELECTOR_MARGIN", "SLAYQL_SELECTOR_MIN_SCORE",
        "SLAYQL_SELECTOR_VERIFY",
        "SLAYQL_SELECTOR_W_EXEC", "SLAYQL_SELECTOR_W_CONTRACT", "SLAYQL_SELECTOR_W_SHAPE",
        "SLAYQL_SELECTOR_W_VALUE", "SLAYQL_SELECTOR_W_EVIDENCE", "SLAYQL_SELECTOR_W_DIVERSITY", "SLAYQL_SELECTOR_W_RISK",
        "SLAYQL_SELECTOR_WORKERS", "SLAYQL_SELECTOR_RETRIES", "SLAYQL_SELECTOR_BACKOFF", "SLAYQL_SELECTOR_TIMEOUT",
        "MODEL_NAME", "OPENAI_BASE_URL",
    )
    config = {
        "schema_version": "1.0",
        "seed": args.seed,
        "smoke_count": args.smoke_count,
        "excluded_backends": sorted(set(args.exclude_backend or [])),
        "num_candidates": args.num_candidates,
        "workers": args.workers,
        "selector": "selector_first_v1.1_structural",
        "environment": {key: os.environ.get(key) for key in environment_keys if os.environ.get(key) is not None},
    }
    config["config_hash"] = _hash_json(config)
    return config


def _find_completed_gate(dataset: str, split: str, mode: str, config_hash: str, source_hash: str) -> Optional[Path]:
    for candidate in sorted(RUN_DIR.iterdir()):
        manifest_path = candidate / "run_manifest.json"
        summary_path = candidate / "aggregates" / "summary_metrics.json"
        if not manifest_path.exists() or not summary_path.exists():
            continue
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if (manifest.get("dataset"), manifest.get("split"), manifest.get("mode"), manifest.get("config_hash"), manifest.get("source_hash"), manifest.get("status")) == (dataset, split, mode, config_hash, source_hash, "complete"):
            return candidate
    return None


def enforce_run_gates(manifest: Dict[str, Any]) -> None:
    required = {
        "smoke": [],
        "backend-smoke": ["smoke"],
        "subset20": ["smoke", "backend-smoke"],
        "full": ["smoke", "backend-smoke", "subset20"],
    }[manifest["mode"]]
    missing = [mode for mode in required if not _find_completed_gate(
        manifest["dataset"], manifest["split"], mode, manifest["config_hash"], manifest["source_hash"]
    )]
    if missing:
        raise RuntimeError(
            "Required completed run gate(s) are missing for the same dataset, split, and resolved configuration: "
            + ", ".join(missing)
        )


def _checkpoint_path(run_root: Path) -> Path:
    path = run_root / "checkpoints" / "stages.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_checkpoint(run_root: Path) -> Dict[str, Any]:
    path = _checkpoint_path(run_root)
    if path.exists():
        return _read_json(path)
    return {"stages": {}, "instances": {}}


def mark_stage(run_root: Path, stage: str, status: str = "complete", details: Optional[Dict[str, Any]] = None) -> None:
    checkpoint = load_checkpoint(run_root)
    checkpoint.setdefault("stages", {})[stage] = {"status": status, **(details or {})}
    _write_json(_checkpoint_path(run_root), checkpoint)


def mark_instance_stage(run_root: Path, instance_id: str, stage: str, status: str, artifacts: Sequence[Path]) -> None:
    path = run_root / "checkpoints" / "instances" / f"{instance_id}.json"
    state = _read_json(path) if path.exists() else {"instance_id": instance_id, "stages": {}}
    state["stages"][stage] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": [
            {"path": str(artifact), "sha256": sha256_file(str(artifact))}
            for artifact in artifacts if artifact.exists() and artifact.is_file()
        ],
    }
    _write_json(path, state)


def _stage_artifacts(run_root: Path, stage: str, instance_id: str, candidates: int) -> List[Path]:
    if stage == "prompt_learning":
        return [run_root / "prompt_learning" / f"{instance_id}.json"]
    if stage == "sql_generation":
        artifacts = [
            run_root / "sql_gen" / f"r1_lite_sql_generation_{cid}" / f"{instance_id}.txt"
            for cid in range(candidates)
        ]
        if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"}:
            artifacts.extend(
                run_root / "candidate_routes" / f"{instance_id}_{cid}.json"
                for cid in range(candidates)
            )
        return artifacts
    if stage == "sql_execution":
        artifacts = []
        for cid in range(candidates):
            result = run_root / "sql_gen" / f"r1_lite_execution_result_{cid}" / f"{instance_id}.csv"
            error = run_root / "sql_gen" / f"r1_lite_execution_error_{cid}" / f"{instance_id}.txt"
            artifacts.append(result if result.exists() else error)
        return artifacts
    if stage == "selector_first":
        return [run_root / "sql_selection_v1" / "final" / instance_id / "selected.sql",
                run_root / "selection" / f"{instance_id}.json"]
    if stage == "semantic_revision":
        return [run_root / "semantic_revise" / "decisions" / f"{instance_id}.json"]
    if stage == "evaluation":
        return [run_root / "aggregates" / "summary_metrics.json",
                run_root / "aggregates" / "summary_metrics.jsonl"]
    return []


def validate_and_checkpoint_instances(run_root: Path, stage: str, records: Dict[str, Dict[str, Any]], candidates: int) -> None:
    if stage not in {"prompt_learning", "sql_generation", "sql_execution", "semantic_revision", "selector_first", "evaluation"}:
        return
    failures = []
    for instance_id in records:
        artifacts = _stage_artifacts(run_root, stage, instance_id, candidates)
        expected = (
            candidates * 2 if stage == "sql_generation" and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"}
            else candidates if stage in {"sql_generation", "sql_execution"} else 2
        )
        if stage in {"prompt_learning", "semantic_revision"}:
            expected = 1
        valid = len(artifacts) == expected and all(path.exists() and path.is_file() for path in artifacts)
        if valid and stage in {"prompt_learning", "semantic_revision"}:
            try:
                artifact_status = _read_json(artifacts[0]).get("status")
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                artifact_status = None
            valid = (
                artifact_status in {"ready", "disabled_no_training_source"}
                if stage == "prompt_learning" else artifact_status == "complete"
            )
        mark_instance_stage(run_root, instance_id, stage, "complete" if valid else "incomplete", artifacts)
        if not valid:
            failures.append(instance_id)
    if failures:
        raise RuntimeError(f"Stage {stage} has incomplete artifacts for {len(failures)} instance(s): {failures[:10]}")


def stage_checkpoint_is_valid(run_root: Path, stage: str, records: Dict[str, Dict[str, Any]], candidates: int) -> bool:
    checkpoint = load_checkpoint(run_root)
    if checkpoint.get("stages", {}).get(stage, {}).get("status") != "complete":
        return False
    if stage not in {"prompt_learning", "sql_generation", "sql_execution", "semantic_revision", "selector_first", "evaluation"}:
        return True
    for instance_id in records:
        artifacts = _stage_artifacts(run_root, stage, instance_id, candidates)
        expected = (
            candidates * 2 if stage == "sql_generation" and os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"}
            else candidates if stage in {"sql_generation", "sql_execution"} else 2
        )
        if stage in {"prompt_learning", "semantic_revision"}:
            expected = 1
        invalid = len(artifacts) != expected or any(not path.exists() or not path.is_file() for path in artifacts)
        if not invalid and stage in {"prompt_learning", "semantic_revision"}:
            try:
                artifact_status = _read_json(artifacts[0]).get("status")
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                artifact_status = None
            invalid = (
                artifact_status not in {"ready", "disabled_no_training_source"}
                if stage == "prompt_learning" else artifact_status != "complete"
            )
        if invalid:
            mark_stage(run_root, stage, "invalid", {"reason": f"missing artifact for {instance_id}"})
            return False
    return True


def _run_command(command: Sequence[str], env: Dict[str, str], cwd: Path) -> None:
    print("RUN:", " ".join(str(part) for part in command))
    subprocess.run(list(command), cwd=str(cwd), env=env, check=True)


def _common_env(run_root: Path, records: Dict[str, Dict[str, Any]], dataset: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(RUN_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["SLAYQL_RUN_ROOT"] = str(run_root.resolve())
    env["SLAYQL_DATASET_CONTEXT"] = str((run_root / "dataset.json").resolve())
    sqlite_paths = {iid: item.get("db_path") for iid, item in records.items() if item.get("db_path")}
    sqlite_db_paths = {item.get("db_name"): item.get("db_path") for item in records.values() if item.get("db_name") and item.get("db_path")}
    env["SLAYQL_SQLITE_PATHS"] = json.dumps(sqlite_paths)
    env["SLAYQL_SQLITE_DB_PATHS"] = json.dumps(sqlite_db_paths)
    env["SLAYQL_SQLITE_ROOT"] = str(REPO_ROOT.resolve())
    bm25_dir = run_root / "bm25_indices"
    if dataset == "spider2-lite":
        # Spider-2 indices are immutable corpus assets; thresholds and traces remain run-local.
        bm25_dir = RUN_DIR / "bm25_indices"
    env["SLAYQL_BM25_DIR"] = str(bm25_dir.resolve())
    env["SLAYQL_USAGE_DIR"] = str((run_root / "usage").resolve())
    env["SLAYQL_BM25_TRACE_DIR"] = str((run_root / "bm25_traces").resolve())
    return env


def _research_interaction_enabled() -> bool:
    return os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}


def _research_schema_focus_enabled() -> bool:
    return os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}


def _run_interaction_stage(
    run_root: Path,
    records: Dict[str, Dict[str, Any]],
    env: Dict[str, str],
    schema_dir: Path,
    stage: str,
    append_cached: bool = False,
) -> None:
    if not _research_interaction_enabled():
        return
    checkpoint = load_checkpoint(run_root)
    if checkpoint.get("stages", {}).get(stage, {}).get("status") == "complete":
        return
    command = [
        sys.executable,
        str(RUN_DIR / "research_interaction.py"),
        "--data_file", str((run_root / "dataset.json").resolve()),
        "--schema_dir", str(schema_dir.resolve()),
        "--output_root", str(run_root.resolve()),
        "--base_dir", str(REPO_ROOT),
        "--max-context-chars", os.environ.get("SLAYQL_RESEARCH_INTERACTION_CHARS", "12000"),
    ]
    if os.environ.get("SLAYQL_RESEARCH_COMPACT_INTERACTION") == "1":
        command.append("--compact")
    if append_cached:
        command.append("--append-cached")
    _run_command(command, env, RUN_DIR)
    mark_stage(run_root, stage, details={"schema_dir": str(schema_dir.resolve())})


def _run_schema_focus_stage(run_root: Path, env: Dict[str, str]) -> None:
    if not _research_schema_focus_enabled():
        return
    checkpoint = load_checkpoint(run_root)
    if checkpoint.get("stages", {}).get("schema_focus", {}).get("status") == "complete":
        return
    command = [
        sys.executable,
        str(RUN_DIR / "focus_schema.py"),
        "--data_file", str((run_root / "dataset.json").resolve()),
        "--schema_dir", str((run_root / "final_schema_prompts").resolve()),
        "--evidence_dir", str((run_root / "interaction").resolve()),
        "--output_root", str(run_root.resolve()),
    ]
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.5", "1.6", "1.7", "1.8", "1.9"}:
        command.extend([
            "--version", os.environ["SLAYQL_RESEARCH_VERSION"], "--max-tables", "8",
            "--max-columns-per-table", "16", "--max-columns-total", "72",
        ])
    _run_command(command, env, RUN_DIR)
    mark_stage(run_root, "schema_focus", details={
        "manifest": str((run_root / "schema_focus_manifest.json").resolve()),
    })


def _prepare_spider2(run_root: Path, records: Dict[str, Dict[str, Any]], env: Dict[str, str], workers: int, candidates: int) -> None:
    data_file = str((run_root / "dataset.json").resolve())
    log_path = str(run_root.resolve())
    commands = [
        [sys.executable, "build_value_indices.py", "--data_file", data_file],
        [sys.executable, "retrieve_topk_schema.py", "--log_path", log_path, "--top_n", env.get("SLAYQL_TOP_N", "100"), "--data_file", data_file],
        [sys.executable, "add_id.py", "--log_path", log_path, "--data_file", data_file],
        [sys.executable, "generate_schema.py", "--log_path", log_path, "--is_initial", "--data_file", data_file],
        [sys.executable, "complete_schema.py", "--log_path", log_path, "--data_file", data_file],
        [sys.executable, "postprocess.py", "--log_path", log_path],
        [sys.executable, "generate_schema.py", "--log_path", log_path, "--data_file", data_file],
    ]
    for index, command in enumerate(commands, 1):
        if index == 5:
            _run_interaction_stage(
                run_root, records, env, run_root / "schema_prompts", "interaction_initial"
            )
        stage = f"spider2_prepare_{index}"
        if stage_checkpoint_is_valid(run_root, stage, records, candidates):
            continue
        _run_command(command, env, RUN_DIR)
        validate_and_checkpoint_instances(run_root, stage, records, candidates)
        mark_stage(run_root, stage)


def _prepare_local(run_root: Path, records: Dict[str, Dict[str, Any]], env: Dict[str, str]) -> None:
    data_file = str((run_root / "dataset.json").resolve())
    commands = [
        ("local_assets", [sys.executable, str(RUN_DIR / "build_local_dataset_assets.py"), "--data_file", data_file, "--output_root", str(run_root)]),
        ("local_retrieval", [sys.executable, str(RUN_DIR / "retrieve_topk_schema.py"), "--log_path", str(run_root), "--top_n", env.get("SLAYQL_TOP_N", "100"), "--data_file", data_file]),
        ("local_add_id", [sys.executable, str(RUN_DIR / "add_id.py"), "--log_path", str(run_root), "--data_file", data_file]),
        ("local_initial_schema", [sys.executable, str(RUN_DIR / "generate_schema.py"), "--log_path", str(run_root), "--is_initial", "--data_file", data_file]),
        ("local_completion", [sys.executable, str(RUN_DIR / "complete_schema.py"), "--log_path", str(run_root), "--data_file", data_file]),
        ("local_postprocess", [sys.executable, str(RUN_DIR / "postprocess.py"), "--log_path", str(run_root)]),
        ("local_final_schema", [sys.executable, str(RUN_DIR / "generate_schema.py"), "--log_path", str(run_root), "--data_file", data_file]),
    ]
    for stage, command in commands:
        if stage == "local_completion":
            _run_interaction_stage(
                run_root, records, env, run_root / "schema_prompts", "interaction_initial"
            )
        checkpoint = load_checkpoint(run_root)
        if checkpoint.get("stages", {}).get(stage, {}).get("status") == "complete":
            continue
        _run_command(command, env, run_root)
        mark_stage(run_root, stage)


def run_inference(run_root: Path, dataset: str, records: Dict[str, Dict[str, Any]], candidates: int = 5, workers: int = 4) -> None:
    env = _common_env(run_root, records, dataset)
    data_file = str((run_root / "dataset.json").resolve())
    schema_dir = str((run_root / "final_schema_prompts").resolve())
    if dataset == "spider2-lite":
        _prepare_spider2(run_root, records, env, workers, candidates)
    else:
        _prepare_local(run_root, records, env)
    _run_interaction_stage(
        run_root, records, env, run_root / "final_schema_prompts", "interaction_final", append_cached=True
    )
    _run_schema_focus_stage(run_root, env)
    if _research_interaction_enabled():
        mark_stage(run_root, "interaction_context", details={"manifest": str((run_root / "interaction_manifest.json").resolve())})
    commands = []
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.7", "1.8", "1.9"}:
        prompt_learning = [
            sys.executable, "prompt_learning.py", "--data_file", data_file,
            "--output_root", str(run_root.resolve()), "--count",
            os.environ.get("SLAYQL_DEMONSTRATION_COUNT", "2"),
        ]
        if os.environ.get("SLAYQL_DEMONSTRATION_FILE"):
            prompt_learning.extend(["--demonstration-file", os.environ["SLAYQL_DEMONSTRATION_FILE"]])
        commands.append(("prompt_learning", prompt_learning))
    commands.extend([
        ("sql_generation", [sys.executable, "sql_generation.py", "--num_workers", str(workers), "--num_candidates", str(candidates), "--data_file", data_file, "--schema_dir", schema_dir, "--log_path", str(run_root.resolve()), "--task", "r1_lite"]),
        ("sql_execution", [sys.executable, "sql_execution.py", "--num_workers", str(workers), "--num_candidates", str(candidates), "--data_file", data_file, "--log_path", str(run_root.resolve()), "--task", "r1_lite"]),
        ("sql_revision", [sys.executable, "sql_revise.py", "--num_workers", str(workers), "--num_candidates", str(candidates), "--data_file", data_file, "--schema_dir", schema_dir, "--log_path", str(run_root.resolve()), "--task", "r1_lite"]),
    ])
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.7", "1.8", "1.9"}:
        commands.append(("semantic_revision", [
            sys.executable, "semantic_revise.py", "--num_workers", str(workers),
            "--num_candidates", str(candidates), "--data_file", data_file,
            "--schema_dir", schema_dir, "--log_path", str(run_root.resolve()),
            "--task", "r1_lite",
        ]))
    commands.extend([
        ("selector_first", [sys.executable, "selector_first.py", "--log_path", str(run_root.resolve()), "--num_candidates", str(candidates), "--data_file", data_file]),
        ("evaluation", [sys.executable, "evaluate_dataset.py", "--dataset", dataset, "--data_file", data_file, "--prediction_dir", str((run_root / "sql_selection_v1" / "final").resolve()), "--output", str((run_root / "aggregates" / "summary_metrics.json").resolve())]),
    ])
    for stage, command in commands:
        if stage_checkpoint_is_valid(run_root, stage, records, candidates):
            continue
        _run_command(command, env, RUN_DIR)
        validate_and_checkpoint_instances(run_root, stage, records, candidates)
        mark_stage(run_root, stage)


def prepare_run(args: argparse.Namespace) -> Path:
    dataset = args.dataset.lower().replace("_", "-")
    if dataset == "spider2":
        dataset = "spider2-lite"
    run_id = args.run_id or f"{dataset}_{args.split}_{args.mode}"
    run_root = (RUN_DIR / run_id).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    config = resolved_config(args)
    existing = run_root / "run_manifest.json"
    if existing.exists():
        if dataset == "bird":
            # BIRD paths are user-owned and must be re-confirmed on resume.
            confirmed_root = _prompt_bird_root(args.bird_root)
            manifest = _read_json(existing)
            configured_root = str(manifest.get("source", {}).get("database_root", ""))
            if configured_root and not configured_root.lower().startswith(str(confirmed_root).lower()):
                raise RuntimeError("Confirmed BIRD directory does not match the existing run manifest")
        manifest = _read_json(existing)
        if manifest.get("dataset") != dataset or manifest.get("split") != args.split or manifest.get("mode") != args.mode:
            raise RuntimeError(f"Existing run manifest conflicts with requested configuration: {existing}")
        if manifest.get("config_hash") != config["config_hash"]:
            raise RuntimeError("Existing run configuration differs from the current candidates/model/threshold settings")
        print(f"Resuming prepared run: {run_root}")
        return run_root
    records, source_manifest = normalize_dataset(dataset, args.split, args.bird_root)
    if dataset == "spider2-lite" and args.mode == "subset20" and DEFAULT_SUBSET.exists():
        records, source_manifest = _normalize_spider2(args.split, DEFAULT_SUBSET)
    manifest = make_run_manifest(
        dataset,
        args.split,
        args.mode,
        records,
        source_manifest,
        run_root,
        args.seed,
        args.smoke_count,
        args.exclude_backend,
    )
    _write_json(run_root / "dataset_manifest.json", source_manifest)
    _write_json(run_root / "resolved_config.json", config)
    manifest["config_hash"] = config["config_hash"]
    lineage_hashes = source_manifest.get("source_hashes", {})
    if dataset == "spider2-lite" and DEFAULT_SPIDER2_DATA.exists():
        lineage_hashes = {str(DEFAULT_SPIDER2_DATA): sha256_file(str(DEFAULT_SPIDER2_DATA))}
    manifest["source_hash"] = _hash_json(lineage_hashes)
    manifest["resolved_config"] = str((run_root / "resolved_config.json").resolve())
    _write_json(run_root / "run_manifest.json", manifest)
    if dataset != "spider2-lite":
        validate_local_assets(_read_json(run_root / "dataset.json"))
    return run_root


def load_run(run_root: Path) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    manifest = _read_json(run_root / "run_manifest.json")
    records = _read_json(run_root / "dataset.json")
    return manifest, records


def write_integrity_reports(run_root: Path, manifest: Dict[str, Any], records: Dict[str, Dict[str, Any]]) -> None:
    checkpoint = load_checkpoint(run_root)
    instance_files = sorted((run_root / "checkpoints" / "instances").glob("*.json"))
    incomplete = []
    for path in instance_files:
        state = _read_json(path)
        if any(stage.get("status") != "complete" for stage in state.get("stages", {}).values()):
            incomplete.append(state.get("instance_id", path.stem))
    integrity = {
        "schema_version": "1.0", "expected_instances": len(records),
        "instance_checkpoint_count": len(instance_files), "incomplete_instances": incomplete,
        "stages": checkpoint.get("stages", {}), "status": "complete" if not incomplete else "incomplete",
    }
    _write_json(run_root / "aggregates" / "checkpoint_integrity.json", integrity)
    code_files = [
        Path(__file__), RUN_DIR / "retrieve_topk_schema.py", RUN_DIR / "complete_schema.py",
        RUN_DIR / "sql_generation.py", RUN_DIR / "sql_execution.py", RUN_DIR / "sql_revise.py",
        RUN_DIR / "selector_first.py", RUN_DIR / "evaluate_dataset.py",
        RUN_DIR / "research_interaction.py", RUN_DIR / "research_subset.py",
        RUN_DIR / "focus_schema.py", RUN_DIR / "semantic_contract.py",
        RUN_DIR / "candidate_router.py", RUN_DIR / "prompt_learning.py",
        RUN_DIR / "semantic_revise.py",
        RUN_DIR / "research_suite.py", RUN_DIR / "research_suite_v18.py",
        RUN_DIR / "research_suite_v19.py",
    ]
    reproducibility = {
        "schema_version": "1.0", "dataset": manifest["dataset"], "split": manifest["split"],
        "mode": manifest["mode"], "source_hash": manifest["source_hash"],
        "dataset_sha256": sha256_file(str(run_root / "dataset.json")),
        "config_sha256": sha256_file(str(run_root / "resolved_config.json")),
        "code_hashes": {str(path.relative_to(REPO_ROOT)): sha256_file(str(path)) for path in code_files},
    }
    _write_json(run_root / "reproducibility_manifest.json", reproducibility)


def cli_prepare(args: argparse.Namespace) -> None:
    run_root = prepare_run(args)
    manifest, records = load_run(run_root)
    if args.mode == "backend-smoke":
        available = defaultdict(int)
        for item in records.values():
            available[item.get("backend", "unknown")] += 1
        print("Backend smoke availability:", dict(available))
        if args.dataset in {"bird", "spider1"}:
            print("Snowflake: not_applicable; BigQuery: not_applicable; SQLite: selected")
    print(json.dumps({"run_root": str(run_root), "records": len(records), "manifest": manifest}, indent=2))


def cli_run(args: argparse.Namespace) -> None:
    run_root = prepare_run(args)
    manifest, records = load_run(run_root)
    if args.enforce_gates:
        enforce_run_gates(manifest)
    run_inference(run_root, manifest["dataset"], records, args.num_candidates, args.workers)
    write_integrity_reports(run_root, manifest, records)
    manifest["status"] = "complete"
    _write_json(run_root / "run_manifest.json", manifest)
    print(f"Pipeline finished: {run_root}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Checkpointed SlayQL v1.1 dataset pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run"):
        child = sub.add_parser(command)
        child.add_argument("--dataset", required=True, choices=["bird", "spider1", "spider1.0", "spider2", "spider2-lite"])
        child.add_argument("--split", default="dev", choices=["dev", "train", "test"])
        child.add_argument("--mode", default="smoke", choices=["smoke", "backend-smoke", "subset20", "full"])
        child.add_argument("--bird-root")
        child.add_argument("--run-id")
        child.add_argument("--seed", type=int, default=20260813)
        child.add_argument("--smoke-count", type=int, default=5)
        child.add_argument(
            "--exclude-backend",
            action="append",
            choices=["snowflake", "bigquery", "sqlite"],
            default=[],
            help="Exclude a backend before selecting instances; repeat for multiple backends",
        )
        child.add_argument("--num-candidates", type=int, default=5)
        child.add_argument("--workers", type=int, default=4)
        child.add_argument(
            "--enforce-gates",
            action="store_true",
            help="Require completed smoke/backend-smoke/subset20 prerequisites before larger runs",
        )
        child.set_defaults(func=cli_prepare if command == "prepare" else cli_run)
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    parsed.func(parsed)

"""Leakage-safe, deterministic prompt learning for SlayQL v1.7.

This module does not train or update the API model.  It retrieves a small,
structurally relevant set of gold examples from an explicitly training-only
source and caches the resulting prompt block for every target instance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from artifact_store import atomic_write_json, sha256_file
from semantic_contract import compile_semantic_contract


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOPWORDS = {
    "and", "are", "for", "from", "give", "list", "return", "show", "that",
    "the", "their", "these", "this", "those", "what", "when", "where",
    "which", "with", "would",
}


def _read_records(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [dict(item) for item in payload["data"] if isinstance(item, dict)]
    if isinstance(payload, dict):
        records = []
        for key, item in payload.items():
            if isinstance(item, dict):
                record = dict(item)
                record.setdefault("instance_id", key)
                records.append(record)
        return records
    raise ValueError(f"Unsupported demonstration dataset format: {path}")


def _gold_sidecar(path: Path) -> Optional[Path]:
    stem = path.stem.lower()
    split = "train" if "train" in stem else stem
    for name in (f"{split}_gold.sql", f"{split}.sql", "train_gold.sql"):
        candidate = path.parent / name
        if candidate.is_file():
            return candidate
    return None


def demonstration_fingerprint(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {"enabled": False, "files": [], "sha256": None}
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Demonstration file does not exist: {source}")
    files = [source]
    sidecar = _gold_sidecar(source)
    if sidecar:
        files.append(sidecar.resolve())
    entries = [{"path": str(item), "sha256": sha256_file(str(item))} for item in files]
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode("utf-8")).hexdigest()
    return {"enabled": True, "files": entries, "sha256": digest}


def _tokens(text: str) -> set[str]:
    return {
        token.lower() for token in _TOKEN_RE.findall(str(text or ""))
        if token.lower() not in _STOPWORDS
    }


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    return len(left_set & right_set) / len(left_set | right_set) if left_set or right_set else 0.0


def _question(item: Dict[str, Any]) -> str:
    return str(item.get("raw_question") or item.get("question") or "").strip()


def _evidence(item: Dict[str, Any]) -> str:
    return str(item.get("evidence") or "").strip()


def _sql(item: Dict[str, Any]) -> str:
    return str(item.get("gold_sql") or item.get("SQL") or item.get("query") or item.get("sql") or "").strip()


def _canonical_id(item: Dict[str, Any], index: int) -> str:
    explicit = item.get("instance_id")
    if explicit:
        return str(explicit)
    db_id = str(item.get("db_id") or item.get("database_id") or item.get("db_name") or "unknown")
    source_id = item.get("source_id", item.get("question_id", index))
    return f"{db_id}:{source_id}"


def _normalize_source(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = _read_records(path)
    declared_splits = {
        str(item.get("split", "")).strip().lower() for item in raw if item.get("split")
    }
    path_is_train = "train" in path.name.lower() or any(part.lower() == "train" for part in path.parts)
    if declared_splits and declared_splits != {"train"}:
        raise ValueError(f"Demonstration records must be training-only; found splits: {sorted(declared_splits)}")
    if not declared_splits and not path_is_train:
        raise ValueError("Demonstration source must be explicitly marked as train by its records or filename/path")

    sidecar = _gold_sidecar(path)
    sql_lines: List[str] = []
    if sidecar:
        sql_lines = [
            line.split("\t", 1)[0].strip()
            for line in sidecar.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    normalized = []
    for index, item in enumerate(raw):
        sql = _sql(item) or (sql_lines[index] if index < len(sql_lines) else "")
        question = _question(item)
        if not question or not sql:
            continue
        normalized.append({
            "demo_id": _canonical_id(item, index),
            "source_index": index,
            "db_id": str(item.get("db_id") or item.get("database_id") or item.get("db_name") or ""),
            "question": question,
            "evidence": _evidence(item),
            "sql": sql,
            "contract": compile_semantic_contract(item),
        })
    if not normalized:
        suffix = f" or its sidecar {sidecar.name}" if sidecar else ""
        raise ValueError(f"No question/SQL demonstration pairs found in {path.name}{suffix}")
    return normalized, {
        "source": str(path.resolve()), "source_record_count": len(raw),
        "usable_record_count": len(normalized), "sidecar": str(sidecar.resolve()) if sidecar else None,
    }


def _target_overlap_keys(targets: Dict[str, Dict[str, Any]]) -> Tuple[set[str], set[str]]:
    ids, questions = set(), set()
    for instance_id, item in targets.items():
        ids.add(str(instance_id).lower())
        db_id = str(item.get("db_id") or item.get("db_name") or "")
        source_id = item.get("source_id")
        if db_id and source_id is not None:
            ids.add(f"{db_id}:{source_id}".lower())
        question = _question(item)
        if question:
            questions.add(hashlib.sha256(question.lower().encode("utf-8")).hexdigest())
    return ids, questions


def _rank(target: Dict[str, Any], demonstrations: Sequence[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any]]]:
    target_contract = compile_semantic_contract(target)
    target_tokens = _tokens(_question(target) + " " + _evidence(target))
    target_ops = set(target_contract.get("required_operations", []))
    target_output = target_contract.get("output", {})
    ranked = []
    for demo in demonstrations:
        demo_contract = demo["contract"]
        lexical = _jaccard(target_tokens, _tokens(demo["question"] + " " + demo["evidence"]))
        operation = _jaccard(target_ops, set(demo_contract.get("required_operations", [])))
        demo_output = demo_contract.get("output", {})
        shape = 0.0
        shape += 0.5 if bool(target_output.get("scalar")) == bool(demo_output.get("scalar")) else 0.0
        shape += 0.5 if target_output.get("expected_projection_count") == demo_output.get("expected_projection_count") else 0.0
        same_db = bool(demo["db_id"]) and demo["db_id"] == str(target.get("db_id") or target.get("db_name") or "")
        score = 3.0 * lexical + 1.25 * operation + 0.6 * shape + (0.2 if same_db else 0.0)
        ranked.append((score, demo))
    return sorted(ranked, key=lambda pair: (-pair[0], pair[1]["demo_id"], pair[1]["source_index"]))


def select_demonstrations(
    target: Dict[str, Any], demonstrations: Sequence[Dict[str, Any]], count: int,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    db_counts: Dict[str, int] = {}
    for score, demo in _rank(target, demonstrations):
        db_id = demo["db_id"]
        if db_id and db_counts.get(db_id, 0) >= 1 and len(selected) + 1 < count:
            continue
        selected.append({**demo, "retrieval_score": round(score, 6)})
        db_counts[db_id] = db_counts.get(db_id, 0) + 1
        if len(selected) >= count:
            break
    if len(selected) < count:
        chosen = {item["demo_id"] for item in selected}
        for score, demo in _rank(target, demonstrations):
            if demo["demo_id"] in chosen:
                continue
            selected.append({**demo, "retrieval_score": round(score, 6)})
            if len(selected) >= count:
                break
    return selected


def _prompt(examples: Sequence[Dict[str, Any]], max_chars: int = 7000) -> str:
    if not examples:
        return ""
    lines = [
        "[SLAYQL_V17_TRAINING_DEMONSTRATIONS]",
        "Use these training examples only as structural lessons. Re-ground every table, column, literal, join, and output field in the current schema; never copy identifiers blindly.",
    ]
    for index, item in enumerate(examples, 1):
        lines.extend([
            f"Example {index} question: {item['question']}",
            f"Example {index} evidence: {item['evidence'] or 'none'}",
            f"Example {index} SQL:\n```sql\n{item['sql']}\n```",
        ])
    return "\n".join(lines)[:max_chars]


def build(
    data_file: str, output_root: str, demonstration_file: Optional[str], count: int = 2,
) -> Dict[str, Any]:
    if count < 1 or count > 5:
        raise ValueError("demonstration count must be between 1 and 5")
    target_path = Path(data_file).resolve()
    targets = json.loads(target_path.read_text(encoding="utf-8"))
    if not isinstance(targets, dict):
        raise ValueError("Target dataset must be normalized as an object keyed by instance ID")
    output = Path(output_root).resolve()
    fingerprint = demonstration_fingerprint(demonstration_file)
    overlap_ids, overlap_questions = _target_overlap_keys(targets)

    demonstrations: List[Dict[str, Any]] = []
    source_info: Dict[str, Any] = {"source": None, "usable_record_count": 0}
    excluded_overlap = 0
    if demonstration_file:
        source_path = Path(demonstration_file).expanduser().resolve()
        if source_path == target_path:
            raise ValueError("Demonstration source cannot be the target dataset file")
        demonstrations, source_info = _normalize_source(source_path)
        safe = []
        for item in demonstrations:
            question_hash = hashlib.sha256(item["question"].lower().encode("utf-8")).hexdigest()
            if item["demo_id"].lower() in overlap_ids or question_hash in overlap_questions:
                excluded_overlap += 1
                continue
            safe.append(item)
        demonstrations = safe
        if not demonstrations:
            raise ValueError("All demonstrations overlap the target split; refusing target-label leakage")

    items = []
    for instance_id, target in sorted(targets.items()):
        selected = select_demonstrations(target, demonstrations, count) if demonstrations else []
        record = {
            "schema_version": "1.7", "instance_id": instance_id,
            "status": "ready" if selected else "disabled_no_training_source",
            "target_signature": {
                "question_sha256": hashlib.sha256(_question(target).encode("utf-8")).hexdigest(),
                "db_id": str(target.get("db_id") or target.get("db_name") or ""),
            },
            "source_fingerprint": fingerprint,
            "selected": [
                {key: value for key, value in item.items() if key != "contract"}
                for item in selected
            ],
            "prompt": _prompt(selected),
        }
        atomic_write_json(str(output / "prompt_learning" / f"{instance_id}.json"), record)
        items.append({
            "instance_id": instance_id, "status": record["status"],
            "demonstration_ids": [item["demo_id"] for item in selected],
        })
    manifest = {
        "schema_version": "1.7", "stage": "prompt_learning", "record_count": len(items),
        "demonstration_count": count, "source": source_info, "source_fingerprint": fingerprint,
        "excluded_target_overlap": excluded_overlap, "instances": items,
    }
    atomic_write_json(str(output / "prompt_learning_manifest.json"), manifest)
    return manifest


def load_prompt(output_root: str, instance_id: str) -> str:
    path = Path(output_root) / "prompt_learning" / f"{instance_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return str(payload.get("prompt") or "")
    except (OSError, ValueError, json.JSONDecodeError):
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build leakage-safe SlayQL v1.7 prompt demonstrations")
    parser.add_argument("--data_file", required=True)
    parser.add_argument("--output_root", required=True)
    parser.add_argument("--demonstration-file")
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args()
    result = build(args.data_file, args.output_root, args.demonstration_file, args.count)
    print(
        f"Prompt learning ready: {result['record_count']} instances; "
        f"source={result['source'].get('source') or 'disabled'}",
        flush=True,
    )


if __name__ == "__main__":
    main()

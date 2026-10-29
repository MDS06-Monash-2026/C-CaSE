import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


SCHEMA_VERSION = "1.0"


def load_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def atomic_write_text(path: str, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def atomic_write_json(path: str, payload: Any, indent: int = 2) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=False) + "\n",
    )


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    if path is None:
        path = str(Path(__file__).resolve().parent / "config" / "lightweight_accuracy.json")
    config = load_json(path)
    if not isinstance(config, dict):
        raise ValueError(f"Invalid lightweight configuration: {path}")
    return config


def per_instance_path(log_path: str, category: str, instance_id: str) -> str:
    return os.path.join(log_path, category, f"{instance_id}.json")


def write_instance_artifact(
    log_path: str, category: str, instance_id: str, payload: Dict[str, Any]
) -> str:
    record = dict(payload)
    record.setdefault("schema_version", SCHEMA_VERSION)
    record.setdefault("instance_id", instance_id)
    path = per_instance_path(log_path, category, instance_id)
    atomic_write_json(path, record)
    return path


def aggregate_json_records(source_dir: str) -> list:
    source = Path(source_dir)
    records = []
    if not source.exists():
        return records
    for path in sorted(source.glob("*.json"), key=lambda item: item.stem):
        record = load_json(str(path))
        if isinstance(record, dict):
            records.append(record)
    return records


def write_jsonl(path: str, records: Iterable[Dict[str, Any]]) -> None:
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=False) for record in records]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def write_csv(path: str, records: Iterable[Dict[str, Any]], fieldnames: list) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow(record)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


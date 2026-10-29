import argparse
import dataclasses
import json
import shutil
from pathlib import Path

import pandas as pd

import semantic_validator as semantic
from artifact_store import atomic_write_json, atomic_write_text
from pipeline_types import QueryContract


def _load_contract(contract_dir, instance_id):
    path = Path(contract_dir) / f"{instance_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return QueryContract.from_dict(json.load(handle))


def _validate(sql, frame, contract):
    sql_validator = getattr(semantic, "check_sql", None) or getattr(semantic, "validate_sql")
    result_validator = getattr(semantic, "check_result", None) or getattr(
        semantic, "validate_result"
    )
    return sql_validator(sql, contract) + result_validator(frame, contract)


def _value(check, name, default=None):
    if isinstance(check, dict):
        return check.get(name, default)
    return getattr(check, name, default)


def _record(check):
    if hasattr(check, "to_dict"):
        return check.to_dict()
    if dataclasses.is_dataclass(check):
        return dataclasses.asdict(check)
    return dict(check)


def prepare(sql_root, execution_root, contract_dir, output_root):
    output_root = Path(output_root)
    manifest = []
    for sql_path in Path(sql_root).glob("task_sql_*/*.sql"):
        instance_id = sql_path.stem
        candidate_dir = sql_path.parent.name
        csv_path = Path(execution_root) / candidate_dir / f"{instance_id}.csv"
        if not csv_path.exists():
            continue
        contract = _load_contract(contract_dir, instance_id)
        if contract is None:
            continue
        try:
            frame = pd.read_csv(csv_path)
        except Exception:
            continue
        sql = sql_path.read_text(encoding="utf-8")
        checks = _validate(sql, frame, contract)
        failures = [
            check
            for check in checks
            if not _value(check, "passed", False)
            and _value(check, "severity", "hard") == "hard"
        ]
        if not failures:
            continue

        queue_dir = output_root / candidate_dir
        queued_sql = queue_dir / f"{instance_id}.sql"
        queued_error = queue_dir / f"{instance_id}.error"
        queued_sql.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sql_path, queued_sql)
        reason = {
            "kind": "semantic_validation_failure",
            "instruction": "Repair only the listed contract violations; preserve valid logic.",
            "failures": [_record(check) for check in failures],
        }
        atomic_write_text(queued_error, json.dumps(reason, ensure_ascii=True, indent=2))
        manifest.append(
            {
                "instance_id": instance_id,
                "candidate_dir": candidate_dir,
                "sql_path": str(queued_sql),
                "error_path": str(queued_error),
                "repair_attempt_limit": 1,
                "failures": reason["failures"],
            }
        )
    atomic_write_json(output_root / "semantic_repair_manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql_root", required=True)
    parser.add_argument("--execution_root", required=True)
    parser.add_argument("--contract_dir", required=True)
    parser.add_argument("--output_root", required=True)
    args = parser.parse_args()
    prepare(**vars(args))


if __name__ == "__main__":
    main()

import argparse
import dataclasses
import json
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd

from artifact_store import atomic_write_json, load_config, write_instance_artifact
from pipeline_types import QueryContract
import semantic_validator as semantic


def _sql_checks(sql, contract):
    validator = getattr(semantic, "check_sql", None) or getattr(semantic, "validate_sql")
    return validator(sql, contract)


def _result_checks(frame, contract):
    validator = getattr(semantic, "check_result", None) or getattr(semantic, "validate_result")
    return validator(frame, contract)


def _check_score(checks):
    scorer = getattr(semantic, "check_score", None) or getattr(semantic, "score_checks")
    return scorer(checks)


def _load_contract(contract_dir, instance_id):
    path = Path(contract_dir) / f"{instance_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return QueryContract.from_dict(json.load(handle))


def _read_frame(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _candidate_id(path):
    name = path.parent.name
    digits = "".join(char for char in name if char.isdigit())
    return int(digits or 0)


def _check_value(check, name, default=None):
    if isinstance(check, dict):
        return check.get(name, default)
    return getattr(check, name, default)


def _check_record(check):
    if hasattr(check, "to_dict"):
        return check.to_dict()
    if dataclasses.is_dataclass(check):
        return dataclasses.asdict(check)
    if isinstance(check, dict):
        return check
    return {"name": "unknown", "passed": False, "detail": str(check)}


def _has_hard_failure(checks):
    return any(
        not _check_value(check, "passed", False)
        and _check_value(check, "severity", "hard") == "hard"
        for check in checks
    )


def collect_candidates(sql_root, execution_root, contract_dir):
    grouped = defaultdict(list)
    for sql_path in Path(sql_root).glob("task_sql_*/*.sql"):
        instance_id = sql_path.stem
        candidate_id = _candidate_id(sql_path)
        csv_path = Path(execution_root) / sql_path.parent.name / f"{instance_id}.csv"
        error_path = Path(execution_root) / sql_path.parent.name / f"{instance_id}.error"
        contract = _load_contract(contract_dir, instance_id)
        sql = sql_path.read_text(encoding="utf-8").strip()
        frame = _read_frame(csv_path) if csv_path.exists() else None
        sql_checks = _sql_checks(sql, contract) if contract else []
        result_checks = _result_checks(frame, contract) if contract and frame is not None else []
        validated_draft = False
        if contract:
            draft = getattr(contract, "validated_draft", None)
            validated_draft = bool(draft) and candidate_id == 0
        grouped[instance_id].append(
            {
                "candidate_id": candidate_id,
                "sql_path": sql_path,
                "csv_path": csv_path,
                "error_path": error_path,
                "sql": sql,
                "frame": frame,
                "executed": csv_path.exists() and not error_path.exists(),
                "checks": sql_checks + result_checks,
                "validated_draft": validated_draft,
            }
        )
    return grouped


def _clusters(candidates):
    clusters = []
    for candidate in candidates:
        if candidate["frame"] is None:
            continue
        for cluster in clusters:
            if semantic.results_equivalent(candidate["frame"], cluster[0]["frame"]):
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    return clusters


def _simplicity(sql):
    normalized = sql.lower()
    joins = normalized.count(" join ")
    nesting = normalized.count("select") - 1
    return 1.0 / (1.0 + joins + max(0, nesting) + len(sql) / 2000.0)


def select(candidates, weights):
    clusters = _clusters(candidates)
    largest = max((len(cluster) for cluster in clusters), default=1)
    cluster_size = {
        id(candidate): len(cluster) for cluster in clusters for candidate in cluster
    }
    for candidate in candidates:
        semantic_score = _check_score(candidate["checks"])
        consistency = cluster_size.get(id(candidate), 0) / largest
        candidate["score_parts"] = {
            "execution": float(candidate["executed"]),
            "semantic": semantic_score,
            "contract": semantic_score,
            "evidence": float(candidate["validated_draft"]),
            "consistency": consistency,
            "simplicity": _simplicity(candidate["sql"]),
        }
        candidate["score"] = sum(
            candidate["score_parts"].get(name, 0.0) * float(weight)
            for name, weight in weights.items()
        )
    eligible = [
        candidate
        for candidate in candidates
        if candidate["executed"] and not _has_hard_failure(candidate["checks"])
    ]
    pool = eligible or [candidate for candidate in candidates if candidate["executed"]] or candidates
    return max(pool, key=lambda candidate: (candidate["score"], -candidate["candidate_id"]))


def run(sql_root, execution_root, contract_dir, output_dir, artifact_root):
    config = load_config()
    groups = collect_candidates(sql_root, execution_root, contract_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    manifest = []
    for instance_id, candidates in sorted(groups.items()):
        selected = select(candidates, config["selection"]["weights"])
        destination = Path(output_dir) / f"{instance_id}.sql"
        shutil.copyfile(selected["sql_path"], destination)
        record = {
            "instance_id": instance_id,
            "selected_candidate": selected["candidate_id"],
            "selected_sql_path": str(destination),
            "candidates": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "executed": candidate["executed"],
                    "score": candidate["score"],
                    "score_parts": candidate["score_parts"],
                    "checks": [_check_record(check) for check in candidate["checks"]],
                }
                for candidate in candidates
            ],
        }
        write_instance_artifact(artifact_root, "selection", instance_id, record)
        manifest.append(record)
    atomic_write_json(Path(output_dir) / "selection_manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql_root", required=True)
    parser.add_argument("--execution_root", required=True)
    parser.add_argument("--contract_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--artifact_root", required=True)
    args = parser.parse_args()
    run(**vars(args))


if __name__ == "__main__":
    main()

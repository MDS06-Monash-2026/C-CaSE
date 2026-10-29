import argparse
import csv
import json
from pathlib import Path

from artifact_store import atomic_write_json, atomic_write_text


def _read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _index_rows(rows):
    return {
        row.get("instance_id") or row.get("id"): row
        for row in rows
        if row.get("instance_id") or row.get("id")
    }


def _artifact(directory, instance_id):
    return _read_json(Path(directory) / f"{instance_id}.json", {})


def _failure_category(record):
    if record["correctness"] is True:
        return None
    if record["missing_prediction"]:
        return "missing_prediction"
    checks = [
        check
        for candidate in record.get("selection", {}).get("candidates", [])
        for check in candidate.get("checks", [])
        if not check.get("passed", True)
    ]
    names = " ".join(check.get("name", "") for check in checks).lower()
    if "dialect" in names or "parse" in names:
        return "dialect_or_syntax"
    if "table" in names or "column" in names or "schema" in names:
        return "schema_grounding"
    if "filter" in names or "forbidden" in names or "invariant" in names:
        return "semantic_constraint"
    if "shape" in names or "row" in names or "null" in names:
        return "result_shape"
    if record.get("evaluation_error"):
        return "execution_or_evaluation"
    return "logical_mismatch"


def build(dataset_path, evaluation_path, prediction_dir, artifact_root, output_jsonl, output_csv):
    dataset = _read_json(dataset_path, [])
    evaluations = _read_json(evaluation_path, [])
    if isinstance(evaluations, dict):
        evaluations = evaluations.get("results", evaluations.get("records", []))
    evaluation_by_id = _index_rows(evaluations)
    records = []
    for item in dataset:
        instance_id = item.get("instance_id") or item.get("id")
        evaluation = evaluation_by_id.get(instance_id, {})
        prediction_path = Path(prediction_dir) / f"{instance_id}.sql"
        correctness = evaluation.get("correct")
        if correctness is None and "score" in evaluation:
            correctness = bool(evaluation["score"])
        record = {
            "instance_id": instance_id,
            "question": item.get("question"),
            "correctness": correctness,
            "missing_prediction": not prediction_path.exists(),
            "prediction_path": str(prediction_path) if prediction_path.exists() else None,
            "evaluation_error": evaluation.get("error"),
            "retrieval": _artifact(Path(artifact_root) / "retrieval", instance_id),
            "contract": _artifact(Path(artifact_root) / "contracts", instance_id),
            "selection": _artifact(Path(artifact_root) / "selection", instance_id),
        }
        record["failure_category"] = _failure_category(record)
        records.append(record)

    jsonl = "".join(json.dumps(record, ensure_ascii=True) + "\n" for record in records)
    atomic_write_text(output_jsonl, jsonl)
    fieldnames = (
        "instance_id",
        "correctness",
        "missing_prediction",
        "failure_category",
        "evaluation_error",
        "prediction_path",
        "question",
    )
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({key: record.get(key) for key in fieldnames})
    atomic_write_text(output_csv, buffer.getvalue())
    summary = {
        "total": len(records),
        "correct": sum(record["correctness"] is True for record in records),
        "incorrect": sum(record["correctness"] is False for record in records),
        "unknown": sum(record["correctness"] is None for record in records),
        "missing_predictions": sum(record["missing_prediction"] for record in records),
    }
    atomic_write_json(Path(output_jsonl).with_suffix(".summary.json"), summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--prediction_dir", required=True)
    parser.add_argument("--artifact_root", required=True)
    parser.add_argument("--output_jsonl", required=True)
    parser.add_argument("--output_csv", required=True)
    args = parser.parse_args()
    build(
        args.dataset,
        args.evaluation,
        args.prediction_dir,
        args.artifact_root,
        args.output_jsonl,
        args.output_csv,
    )


if __name__ == "__main__":
    main()

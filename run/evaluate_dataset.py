"""Gold-isolated evaluation and metric aggregation for dataset pipeline runs."""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    import sqlglot
except ImportError:  # pragma: no cover
    sqlglot = None

from artifact_store import atomic_write_json, write_csv, write_jsonl


REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD_ROOT = REPO_ROOT / "evaluation_suite" / "gold"
LARGE_RESULT_ROW_THRESHOLD = 10_000


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dialect(instance_id: str) -> str:
    if instance_id.startswith(("bq", "ga")):
        return "bigquery"
    if instance_id.startswith("sf"):
        return "snowflake"
    return "sqlite"


def _sql_refs(sql: str, instance_id: str = "local") -> Dict[str, set]:
    result = {"tables": set(), "columns": set(), "joins": set()}
    if not sql or sqlglot is None:
        return result
    try:
        expressions = sqlglot.parse(sql, read=_dialect(instance_id))
    except Exception:
        return result
    for expression in expressions:
        result["tables"].update(
            str(item.name).split(".")[-1].lower()
            for item in expression.find_all(sqlglot.exp.Table) if item.name
        )
        result["columns"].update(
            str(item.name).lower()
            for item in expression.find_all(sqlglot.exp.Column) if item.name
        )
        for equality in expression.find_all(sqlglot.exp.EQ):
            left, right = equality.left, equality.right
            if isinstance(left, sqlglot.exp.Column) and isinstance(right, sqlglot.exp.Column):
                pair = sorted((left.sql().lower(), right.sql().lower()))
                result["joins"].add("=".join(pair))
    return result


def _metric_sets(predicted: set, gold: set) -> Dict[str, float]:
    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "true_positive": true_positive, "predicted": len(predicted), "gold": len(gold),
        "strict_recall": 1.0 if gold and gold.issubset(predicted) else 0.0,
        "noise_rate": (len(predicted - gold) / len(predicted)) if predicted else 0.0,
    }


def _aggregate_set_metric(items: List[Dict[str, Any]], key: str) -> Dict[str, float]:
    values = [item["metrics"][key] for item in items]
    if not values:
        return {"macro_precision": 0.0, "macro_recall": 0.0, "macro_f1": 0.0,
                "micro_precision": 0.0, "micro_recall": 0.0, "micro_f1": 0.0}
    true_positive = sum(value["true_positive"] for value in values)
    predicted = sum(value["predicted"] for value in values)
    gold = sum(value["gold"] for value in values)
    micro_precision = true_positive / predicted if predicted else 0.0
    micro_recall = true_positive / gold if gold else 0.0
    micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if micro_precision + micro_recall else 0.0
    return {
        "macro_precision": sum(value["precision"] for value in values) / len(values),
        "macro_recall": sum(value["recall"] for value in values) / len(values),
        "macro_f1": sum(value["f1"] for value in values) / len(values),
        "micro_precision": micro_precision, "micro_recall": micro_recall, "micro_f1": micro_f1,
        "strict_recall_rate": sum(value["strict_recall"] for value in values) / len(values),
        "macro_noise_rate": sum(value["noise_rate"] for value in values) / len(values),
    }


def _local_result(sql: str, db_path: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    try:
        with sqlite3.connect(db_path) as connection:
            return pd.read_sql_query(sql, connection), None
    except Exception as exc:
        return None, str(exc)


def _value_match(left: Any, right: Any, tolerance: float = 1e-2) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    try:
        return math.isclose(float(left), float(right), abs_tol=tolerance)
    except (TypeError, ValueError):
        return str(left).strip().lower() == str(right).strip().lower()


def _comparison_columns(frame: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, pd.Series], Dict[str, pd.Series]]:
    """Build sortable keys and normalized values for scalable unordered matching."""
    sort_keys: Dict[str, pd.Series] = {}
    normalized: Dict[str, pd.Series] = {}
    numeric: Dict[str, pd.Series] = {}
    for column in frame.columns:
        values = frame[column]
        converted = pd.to_numeric(values, errors="coerce")
        non_null = values.notna()
        is_numeric = bool(non_null.any() and converted[non_null].notna().all())
        if is_numeric:
            numeric_values = converted.astype(float)
            numeric[column] = numeric_values
            normalized[column] = numeric_values
            sort_keys[column] = numeric_values.fillna(float("inf"))
        else:
            text_values = values.astype("string").str.strip().str.lower().fillna("<null>")
            normalized[column] = text_values
            sort_keys[column] = text_values
    return pd.DataFrame(sort_keys, index=frame.index), normalized, numeric


def _large_unordered_match(predicted: pd.DataFrame, gold: pd.DataFrame) -> bool:
    """Compare large unordered result sets without quadratic row-by-row scans."""
    # Local result matching has always been positional; SQL aliases can differ
    # between the prediction and gold query. Use stable positional keys here too.
    column_count = predicted.shape[1]
    predicted = predicted.copy(deep=False)
    gold = gold.copy(deep=False)
    positional_columns = list(range(column_count))
    predicted.columns = positional_columns
    gold.columns = positional_columns
    predicted_hashes = pd.util.hash_pandas_object(predicted, index=False).sort_values(ignore_index=True)
    gold_hashes = pd.util.hash_pandas_object(gold, index=False).sort_values(ignore_index=True)
    if predicted_hashes.equals(gold_hashes):
        return True

    predicted_sort, predicted_values, predicted_numeric = _comparison_columns(predicted)
    gold_sort, gold_values, gold_numeric = _comparison_columns(gold)
    predicted_order = predicted_sort.sort_values(positional_columns, kind="mergesort").index
    gold_order = gold_sort.sort_values(positional_columns, kind="mergesort").index
    for column in positional_columns:
        left_numeric = predicted_numeric.get(column)
        right_numeric = gold_numeric.get(column)
        if left_numeric is not None and right_numeric is not None:
            left = left_numeric.loc[predicted_order].reset_index(drop=True)
            right = right_numeric.loc[gold_order].reset_index(drop=True)
            both_null = left.isna() & right.isna()
            close = (left - right).abs().le(1e-2)
            if not bool((both_null | close).all()):
                return False
        else:
            left = predicted_values[column].loc[predicted_order].reset_index(drop=True)
            right = gold_values[column].loc[gold_order].reset_index(drop=True)
            if not bool(left.eq(right).all()):
                return False
    return True


def _local_frames_match(predicted: pd.DataFrame, gold: pd.DataFrame, ignore_order: bool = True) -> bool:
    if predicted.shape != gold.shape:
        return False
    if ignore_order and len(predicted) >= LARGE_RESULT_ROW_THRESHOLD:
        return _large_unordered_match(predicted, gold)
    pred_rows = [tuple(row) for row in predicted.itertuples(index=False, name=None)]
    gold_rows = [tuple(row) for row in gold.itertuples(index=False, name=None)]
    if not ignore_order:
        return all(all(_value_match(a, b) for a, b in zip(pred_row, gold_row))
                   for pred_row, gold_row in zip(pred_rows, gold_rows))
    used = set()
    for gold_row in gold_rows:
        match = next((index for index, row in enumerate(pred_rows)
                      if index not in used and all(_value_match(a, b) for a, b in zip(row, gold_row))), None)
        if match is None:
            return False
        used.add(match)
    return True


def _spider2_frames_match(predicted: pd.DataFrame, gold: pd.DataFrame, condition_cols: Any, ignore_order: bool) -> bool:
    def vector_match(left: List[Any], right: List[Any]) -> bool:
        if ignore_order:
            left = sorted(left, key=lambda value: (value is None, str(value), isinstance(value, (int, float))))
            right = sorted(right, key=lambda value: (value is None, str(value), isinstance(value, (int, float))))
        return len(left) == len(right) and all(_value_match(a, b) for a, b in zip(left, right))

    gold_columns = gold.iloc[:, condition_cols] if condition_cols else gold
    predicted_vectors = predicted.transpose().values.tolist()
    return all(any(vector_match(gold_vector, predicted_vector) for predicted_vector in predicted_vectors)
               for gold_vector in gold_columns.transpose().values.tolist())


def _spider2_standard() -> Dict[str, Dict[str, Any]]:
    path = GOLD_ROOT / "spider2lite_eval.jsonl"
    if not path.exists():
        return {}
    return {item["instance_id"]: item for item in
            (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def _official_spider2_results(instance_id: str) -> List[pd.DataFrame]:
    paths = sorted((GOLD_ROOT / "exec_result").glob(f"{instance_id}.csv"))
    paths += sorted((GOLD_ROOT / "exec_result").glob(f"{instance_id}_*.csv"))
    results = []
    for path in paths:
        try:
            results.append(pd.read_csv(path))
        except Exception:
            continue
    return results


def _official_spider2_sql(instance_id: str) -> Optional[str]:
    path = GOLD_ROOT / "sql" / f"{instance_id}.sql"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def _linked_refs(run_root: Path, instance_id: str) -> Dict[str, set]:
    for name in ("unfilled_schema.json", "initial_candidates.json"):
        path = run_root / name
        if not path.exists():
            continue
        payload = _read_json(path).get(instance_id, {})
        return {
            "tables": {str(value).split(".")[-1].lower() for value in payload.get("table_candidates", [])},
            "columns": {str(value).split(".")[-1].lower() for value in payload.get("column_candidates", [])},
        }
    return {"tables": set(), "columns": set()}


def _candidate_frames(run_root: Path, instance_id: str) -> List[Tuple[int, pd.DataFrame]]:
    frames: Dict[int, pd.DataFrame] = {}
    for path in sorted((run_root / "sql_gen").glob(f"r1_lite_execution_result_*/{instance_id}.csv")):
        match = re.search(r"result_(\d+)", path.parent.name)
        try:
            frames[int(match.group(1)) if match else 0] = pd.read_csv(path)
        except Exception:
            continue
    for path in sorted((run_root / "sql_revise").glob(f"r1_lite_sql_*/{instance_id}.csv")):
        match = re.search(r"sql_(\d+)", path.parent.name)
        try:
            frames[int(match.group(1)) if match else 0] = pd.read_csv(path)
        except Exception:
            continue
    for path in sorted((run_root / "semantic_revise").glob(f"r1_lite_sql_*/{instance_id}.csv")):
        match = re.search(r"sql_(\d+)", path.parent.name)
        try:
            frames[int(match.group(1)) if match else len(frames)] = pd.read_csv(path)
        except Exception:
            continue
    return sorted(frames.items())


def _usage_summary(run_root: Path) -> Dict[str, Any]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
              "reasoning_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0,
              "cost": 0.0, "upstream_inference_cost": 0.0, "calls": 0, "missing_usage": 0,
              "latency_ms_p50": 0.0, "latency_ms_p95": 0.0, "by_stage": {}}
    latencies = []
    for path in (run_root / "usage").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            usage = record.get("usage") or {}
            totals["calls"] += 1
            stage = record.get("stage") or "unknown"
            stage_totals = totals["by_stage"].setdefault(stage, {"calls": 0, "total_tokens": 0, "cost": 0.0})
            stage_totals["calls"] += 1
            if record.get("latency_ms") is not None:
                latencies.append(float(record["latency_ms"]))
            if not usage:
                totals["missing_usage"] += 1
                continue
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                totals[key] += int(usage.get(key) or 0)
            totals["cost"] += float(usage.get("cost") or 0.0)
            stage_totals["total_tokens"] += int(usage.get("total_tokens") or 0)
            stage_totals["cost"] += float(usage.get("cost") or 0.0)
            totals["reasoning_tokens"] += int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
            details = usage.get("prompt_tokens_details") or {}
            totals["cached_tokens"] += int(details.get("cached_tokens") or 0)
            totals["cache_write_tokens"] += int(details.get("cache_write_tokens") or 0)
            totals["upstream_inference_cost"] += float((usage.get("cost_details") or {}).get("upstream_inference_cost") or 0.0)
    if latencies:
        ordered = sorted(latencies)
        totals["latency_ms_p50"] = statistics.median(ordered)
        totals["latency_ms_p95"] = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
    return totals


def _selection_summary(run_root: Path, expected: int) -> Dict[str, Any]:
    statuses: Dict[str, int] = {}
    margins = []
    for path in (run_root / "selection").glob("*.json"):
        try:
            record = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        status = (record.get("verification") or {}).get("status", "not_invoked")
        statuses[status] = statuses.get(status, 0) + 1
        margin = (record.get("selection") or {}).get("margin")
        if margin is not None:
            margins.append(float(margin))
    verification_calls = statuses.get("selected", 0) + statuses.get("invalid_response", 0) + statuses.get("error", 0)
    deterministic = statuses.get("not_invoked", 0) + statuses.get("disabled", 0) + statuses.get("unavailable_no_api_key", 0)
    return {
        "decisions": sum(statuses.values()), "status_counts": statuses,
        "deterministic_rate": deterministic / expected if expected else 0.0,
        "verification_call_rate": verification_calls / expected if expected else 0.0,
        "fallback_rate": (statuses.get("invalid_response", 0) + statuses.get("error", 0)) / expected if expected else 0.0,
        "mean_margin": sum(margins) / len(margins) if margins else 0.0,
    }


def evaluate_instance(instance_id: str, item: Dict[str, Any], prediction_dir: Path,
                      run_root: Path, standards: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    folder = prediction_dir / instance_id
    sql_path, result_path = folder / "selected.sql", folder / "result.csv"
    predicted_sql = sql_path.read_text(encoding="utf-8", errors="replace") if sql_path.exists() else ""
    predicted_frame, execution_error = None, None
    if result_path.exists():
        try:
            predicted_frame = pd.read_csv(result_path)
        except Exception as exc:
            execution_error = str(exc)
    if predicted_frame is None and item.get("db_path") and predicted_sql:
        predicted_frame, execution_error = _local_result(predicted_sql, item["db_path"])

    gold_sql = item.get("gold_sql") or _official_spider2_sql(instance_id)
    gold_frames: List[pd.DataFrame] = []
    gold_error = None
    is_local = bool(item.get("db_path"))
    if is_local and gold_sql:
        gold_frame, gold_error = _local_result(gold_sql, item["db_path"])
        if gold_frame is not None:
            gold_frames = [gold_frame]
    elif not is_local:
        gold_frames = _official_spider2_results(instance_id)
        if not gold_frames:
            gold_error = "Official Spider-2 gold result not found"

    standard = standards.get(instance_id, {})
    condition_cols = standard.get("condition_cols")
    if len(gold_frames) > 1 and condition_cols and not all(isinstance(value, list) for value in condition_cols):
        conditions = [condition_cols] * len(gold_frames)
    elif len(gold_frames) > 1 and isinstance(condition_cols, list) and all(isinstance(value, list) for value in condition_cols):
        conditions = condition_cols
    else:
        conditions = [condition_cols or []] * len(gold_frames)

    def matches(frame: pd.DataFrame, index: int, gold: pd.DataFrame) -> bool:
        local_ignore_order = "order by" not in (gold_sql or "").lower()
        return (_local_frames_match(frame, gold, local_ignore_order) if is_local else
                _spider2_frames_match(frame, gold, conditions[index], bool(standard.get("ignore_order", False))))

    result_correct = bool(predicted_frame is not None and any(matches(predicted_frame, index, gold) for index, gold in enumerate(gold_frames)))
    linked = _linked_refs(run_root, instance_id)
    selected_refs = _sql_refs(predicted_sql, instance_id)
    gold_refs = _sql_refs(gold_sql or "", instance_id)
    table_metrics = _metric_sets(linked["tables"], gold_refs["tables"])
    column_metrics = _metric_sets(linked["columns"], gold_refs["columns"])
    join_metrics = _metric_sets(selected_refs["joins"], gold_refs["joins"])
    combined_predicted = {f"t:{value}" for value in linked["tables"]} | {f"c:{value}" for value in linked["columns"]}
    combined_gold = {f"t:{value}" for value in gold_refs["tables"]} | {f"c:{value}" for value in gold_refs["columns"]}
    schema_metrics = _metric_sets(combined_predicted, combined_gold)
    correct_candidates = [candidate_id for candidate_id, frame in _candidate_frames(run_root, instance_id)
                          if any(matches(frame, index, gold) for index, gold in enumerate(gold_frames))]
    canonical_predicted = re.sub(r"\s+", " ", predicted_sql.strip().rstrip(";")).lower()
    canonical_gold = re.sub(r"\s+", " ", (gold_sql or "").strip().rstrip(";")).lower()
    evaluable = bool(gold_frames)
    return {
        "instance_id": instance_id, "correct": result_correct,
        "evaluable": evaluable,
        "prediction_available": bool(predicted_sql), "execution_error": execution_error,
        "gold_error": gold_error, "candidate_oracle": bool(correct_candidates),
        "correct_candidate_ids": correct_candidates,
        "selection_regret": bool(correct_candidates and not result_correct),
        "metrics": {"table": table_metrics, "column": column_metrics, "join": join_metrics,
                    "schema": schema_metrics, "strict_schema_recall": schema_metrics["strict_recall"],
                    "execution_accuracy": 1.0 if result_correct else 0.0,
                    "sql_exact_match": 1.0 if canonical_gold and canonical_predicted == canonical_gold else 0.0},
    }


def run(dataset: str, data_file: Path, prediction_dir: Path, output: Path) -> Dict[str, Any]:
    data = _read_json(data_file)
    run_root = prediction_dir.resolve().parents[1]
    standards = _spider2_standard() if dataset == "spider2-lite" else {}
    ordered_data = sorted(data.items())
    expected = len(ordered_data)
    print(f"Evaluation started: {expected} instances", flush=True)
    items = []
    for index, (instance_id, item) in enumerate(ordered_data, 1):
        print(f"Evaluating {index}/{expected}: {instance_id}", flush=True)
        items.append(evaluate_instance(instance_id, item, prediction_dir, run_root, standards))
        if index % 25 == 0 or index == expected:
            print(f"Evaluation progress: {index}/{expected} ({index / expected:.1%})", flush=True)
    evaluable = sum(item["evaluable"] for item in items)
    correct = sum(item["correct"] for item in items)
    covered = sum(item["prediction_available"] for item in items)
    oracle = sum(item["candidate_oracle"] for item in items)
    summary = {
        "dataset": dataset, "expected": expected, "correct": correct,
        "evaluable": evaluable,
        "execution_accuracy": correct / evaluable if evaluable else 0.0,
        "fixed_denominator_accuracy": correct / expected if expected else 0.0,
        "covered": covered, "coverage": covered / expected if expected else 0.0,
        "execution_errors": sum(bool(item["execution_error"]) for item in items),
        "gold_errors": sum(bool(item["gold_error"]) for item in items),
        "candidate_oracle_correct": oracle,
        "candidate_oracle_accuracy": oracle / evaluable if evaluable else 0.0,
        "selection_regret": sum(item["selection_regret"] for item in items),
        "selection_accuracy_given_oracle": correct / oracle if oracle else 0.0,
        "sql_exact_match": sum(item["metrics"]["sql_exact_match"] for item in items) / expected if expected else 0.0,
        "schema_linking": {key: _aggregate_set_metric(items, key) for key in ("table", "column", "join", "schema")},
        "usage": _usage_summary(run_root),
        "selection": _selection_summary(run_root, expected),
        "formulas": {
            "precision": "TP / predicted linked elements",
            "recall": "TP / gold required elements",
            "f1": "2 * precision * recall / (precision + recall)",
            "execution_accuracy": "correct results / evaluable instances",
            "fixed_denominator_accuracy": "correct results / expected instances",
            "candidate_oracle_accuracy": "evaluable instances with any correct candidate / evaluable instances",
        },
        "instances": items,
    }
    summary["usage"]["cost_per_expected_instance"] = summary["usage"]["cost"] / expected if expected else 0.0
    for item in items:
        atomic_write_json(str(run_root / "metrics" / f"{item['instance_id']}.json"), item["metrics"])
        atomic_write_json(str(run_root / "evaluation" / f"{item['instance_id']}.json"), item)
    atomic_write_json(str(output), summary)
    write_jsonl(str(output.with_suffix(".jsonl")), items)
    write_csv(str(output.with_suffix(".csv")), ({
        "instance_id": item["instance_id"], "evaluable": item["evaluable"],
        "correct": item["correct"], "prediction_available": item["prediction_available"],
        "execution_error": item["execution_error"], "gold_error": item["gold_error"],
        "candidate_oracle": item["candidate_oracle"], "selection_regret": item["selection_regret"],
        "table_precision": item["metrics"]["table"]["precision"],
        "table_recall": item["metrics"]["table"]["recall"],
        "column_precision": item["metrics"]["column"]["precision"],
        "column_recall": item["metrics"]["column"]["recall"],
    } for item in items), [
        "instance_id", "evaluable", "correct", "prediction_available", "execution_error", "gold_error",
        "candidate_oracle", "selection_regret", "table_precision", "table_recall",
        "column_precision", "column_recall",
    ])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--data_file", required=True, type=Path)
    parser.add_argument("--prediction_dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary = run(args.dataset, args.data_file, args.prediction_dir, args.output)
    print(f"Results: {summary['correct']}/{summary['expected']} correct. Score: {summary['execution_accuracy']:.4f}")


if __name__ == "__main__":
    main()

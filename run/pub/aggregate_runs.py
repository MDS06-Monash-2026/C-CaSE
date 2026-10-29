"""Aggregate dataset-pipeline runs into per-question and per-run tables (plan: O2, T1, T2).

For every run folder this collects:
  * execution accuracy (fixed denominator), candidate oracle and selection regret;
  * linking quality of the linked set (evaluate_dataset.py) and of the schema prompt the
    generator actually sees (final_schema_prompts, after the v1.8 schema-focus cap);
  * schema size and reduction against the full database schema;
  * IT-EE budget (dynamic_t_max, entropy) and completion-agent turns;
  * tokens, calls and cost by stage group (linking, generation, revision, selection).

Usage:
  python -m pub.aggregate_runs                      # discover runs automatically
  python -m pub.aggregate_runs --runs bird_dev_v18_full bird_dev_v18_k1_ref
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from pub.common import (
    BIRD_DEV_ROOT, REPO_ROOT, RESULTS_DIR, RUN_DIR, STAGE_GROUP_NAMES, STAGE_GROUPS,
    compact_schema, count_tokens, fmt_pct, gold_refs, md_table, parse_schema_prompt, read_json,
    set_metrics, wilson_interval, write_csv, write_json,
)

DEFAULT_PATTERNS = ("bird_dev_*", "smoke_v18_*", "spider1_test_full_3cand")
SPIDER1_TABLE_FILES = (
    REPO_ROOT / "spider_data" / "spider_data" / "test_tables.json",
    REPO_ROOT / "spider_data" / "spider_data" / "tables.json",
    REPO_ROOT / "spider_data" / "test_tables.json",
    REPO_ROOT / "spider_data" / "tables.json",
)


def discover_runs(patterns=DEFAULT_PATTERNS) -> List[Path]:
    found = []
    for pattern in patterns:
        for path in sorted(RUN_DIR.glob(pattern)):
            if path.is_dir() and (path / "dataset.json").exists() and path not in found:
                found.append(path)
    return found


def variant_label(environment: Dict[str, str]) -> str:
    parts = []
    for key, label in (("ABLATION_NO_RBP", "no_rbp"), ("ABLATION_NO_ITEE", "no_itee"),
                       ("ABLATION_NO_BM25", "no_bm25"), ("ABLATION_NO_QOC", "no_qoc")):
        if environment.get(key) == "1":
            parts.append(label)
    if environment.get("SLAYQL_TOP_N"):
        parts.append(f"top_n={environment['SLAYQL_TOP_N']}")
    if environment.get("ABLATION_ITEE_THRESHOLD"):
        parts.append(f"itee_thr={environment['ABLATION_ITEE_THRESHOLD']}")
    if environment.get("ABLATION_RBP_ALPHA"):
        parts.append(f"rbp_alpha={environment['ABLATION_RBP_ALPHA']}")
    return "+".join(parts) or "reference"


def _database_schemas(dataset: str) -> Dict[str, Dict[str, List[str]]]:
    """db_id -> {table: [columns]} from the benchmark's tables file."""
    candidates = [BIRD_DEV_ROOT / "dev_tables.json"] if dataset == "bird" else list(SPIDER1_TABLE_FILES)
    for path in candidates:
        if not path.exists():
            continue
        schemas: Dict[str, Dict[str, List[str]]] = {}
        for database in read_json(path):
            tables = [str(name).lower() for name in database["table_names_original"]]
            mapping: Dict[str, List[str]] = {table: [] for table in tables}
            for table_index, column in database["column_names_original"]:
                if table_index >= 0:
                    mapping[tables[table_index]].append(str(column).lower())
            schemas[database["db_id"]] = mapping
        return schemas
    return {}


def _bird_difficulty() -> Dict[str, str]:
    path = BIRD_DEV_ROOT / "dev.json"
    if not path.exists():
        return {}
    return {str(item.get("question_id")): item.get("difficulty", "") for item in read_json(path)}


def _usage_by_group(path: Path) -> Dict[str, Any]:
    totals = {f"tokens_{group}": 0 for group in STAGE_GROUP_NAMES}
    totals.update({f"calls_{group}": 0 for group in STAGE_GROUP_NAMES})
    totals.update({"tokens_total": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "calls": 0,
                   "missing_usage": 0})
    if not path.exists():
        return totals
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        group = STAGE_GROUPS.get(record.get("stage") or "", "other")
        usage = record.get("usage") or {}
        totals["calls"] += 1
        totals[f"calls_{group}"] += 1
        if not usage:
            totals["missing_usage"] += 1
            continue
        tokens = int(usage.get("total_tokens") or 0)
        totals["tokens_total"] += tokens
        totals[f"tokens_{group}"] += tokens
        totals["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        totals["cost"] += float(usage.get("cost") or 0.0)
    return totals


def _turns(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return None
    if isinstance(payload, dict):
        return sum(1 for key in payload if str(key).startswith("turn_"))
    return None


def per_question_rows(run_root: Path) -> List[Dict[str, Any]]:
    dataset_records: Dict[str, Dict[str, Any]] = read_json(run_root / "dataset.json")
    manifest = read_json(run_root / "run_manifest.json") if (run_root / "run_manifest.json").exists() else {}
    dataset = manifest.get("dataset") or ("bird" if "bird" in run_root.name else "spider1")
    schemas = _database_schemas(dataset)
    difficulty = _bird_difficulty() if dataset == "bird" else {}
    initial = read_json(run_root / "initial_candidates.json") if (run_root / "initial_candidates.json").exists() else {}
    full_schema_tokens: Dict[str, int] = {}
    rows = []
    for instance_id, record in sorted(dataset_records.items()):
        evaluation_path = run_root / "evaluation" / f"{instance_id}.json"
        evaluation = read_json(evaluation_path) if evaluation_path.exists() else {}
        metrics = evaluation.get("metrics", {})
        prompt_path = run_root / "final_schema_prompts" / f"{instance_id}.txt"
        prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace") if prompt_path.exists() else ""
        prompt = parse_schema_prompt(prompt_text)
        db_id = record.get("db_id") or record.get("db_name")
        db_schema = schemas.get(db_id, {})
        db_columns = sum(len(columns) for columns in db_schema.values())
        gold = gold_refs(record.get("gold_sql", ""), instance_id)
        if db_schema:
            # Keep only real schema items (drops CTE/alias names the parser reports as tables or columns).
            gold["tables"] &= set(db_schema)
            gold["columns"] &= {column for columns in db_schema.values() for column in columns}
        prompt_tables = set_metrics(prompt["tables"], gold["tables"])
        prompt_columns = set_metrics(prompt["columns"], gold["columns"])
        if db_id and db_id not in full_schema_tokens and db_schema:
            full_schema_tokens[db_id] = count_tokens(compact_schema(db_schema))
        linked_compact = defaultdict(list)
        for table, column in prompt["table_columns"]:
            linked_compact[table].append(column)
        prompt_compact_tokens = count_tokens(compact_schema(linked_compact))
        full_tokens = full_schema_tokens.get(db_id)

        budget = initial.get(instance_id, {})
        usage = _usage_by_group(run_root / "usage" / f"{instance_id}.jsonl")
        row = {
            "instance_id": instance_id,
            "db_id": db_id,
            "difficulty": difficulty.get(str(record.get("source_id")), ""),
            "evaluated": bool(evaluation),
            "correct": bool(evaluation.get("correct")),
            "prediction_available": bool(evaluation.get("prediction_available")),
            "candidate_oracle": bool(evaluation.get("candidate_oracle")),
            "correct_candidate_ids": json.dumps(evaluation.get("correct_candidate_ids", [])),
            "selection_regret": bool(evaluation.get("selection_regret")),
            # Linked set (after completion and postprocess; what evaluate_dataset.py measures).
            "linked_table_precision": metrics.get("table", {}).get("precision"),
            "linked_table_recall": metrics.get("table", {}).get("recall"),
            "linked_table_f1": metrics.get("table", {}).get("f1"),
            "linked_table_strict": metrics.get("table", {}).get("strict_recall"),
            "linked_tables": metrics.get("table", {}).get("predicted"),
            "linked_column_precision": metrics.get("column", {}).get("precision"),
            "linked_column_recall": metrics.get("column", {}).get("recall"),
            "linked_column_f1": metrics.get("column", {}).get("f1"),
            "linked_column_strict": metrics.get("column", {}).get("strict_recall"),
            "linked_columns": metrics.get("column", {}).get("predicted"),
            # Schema prompt seen by the generator (after the schema-focus cap).
            "prompt_tables": prompt["n_tables"],
            "prompt_columns": prompt["n_columns"],
            "prompt_table_precision": prompt_tables["precision"],
            "prompt_table_recall": prompt_tables["recall"],
            "prompt_table_strict": prompt_tables["strict_recall"],
            "prompt_column_precision": prompt_columns["precision"],
            "prompt_column_recall": prompt_columns["recall"],
            "prompt_column_strict": prompt_columns["strict_recall"],
            "gold_tables": prompt_tables["gold"],
            "gold_columns": prompt_columns["gold"],
            "prompt_file_tokens": count_tokens(prompt_text),
            "prompt_schema_block_tokens": count_tokens(prompt["table_block_text"]),
            "prompt_compact_tokens": prompt_compact_tokens,
            "db_tables": len(db_schema) or None,
            "db_columns": db_columns or None,
            "db_compact_tokens": full_tokens,
            "schema_reduction_columns": (1 - prompt["n_columns"] / db_columns) if db_columns else None,
            "schema_reduction_tokens": (1 - prompt_compact_tokens / full_tokens) if full_tokens else None,
            "itee_entropy": budget.get("entropy"),
            "itee_budget_turns": budget.get("dynamic_t_max"),
            "retrieved_columns": budget.get("retrieved_count"),
            "completion_turns": _turns(run_root / "tool_calls" / f"{instance_id}.json"),
        }
        row.update(usage)
        rows.append(row)
    return rows


def _mean(values) -> Optional[float]:
    values = [float(value) for value in values if value is not None and value != ""]
    return sum(values) / len(values) if values else None


def run_summary(run_root: Path, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    config = read_json(run_root / "resolved_config.json") if (run_root / "resolved_config.json").exists() else {}
    summary_path = run_root / "aggregates" / "summary_metrics.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    environment = config.get("environment", {}) or {}
    total = len(rows)
    correct = sum(row["correct"] for row in rows)
    low, high = wilson_interval(correct, total)
    oracle = sum(row["candidate_oracle"] for row in rows)
    tokens = sum(row["tokens_total"] for row in rows)
    cost = sum(row["cost"] for row in rows)
    usage = summary.get("usage", {})
    result = {
        "run": run_root.name,
        "complete": bool(summary) and sum(row["evaluated"] for row in rows) == total,
        "version": config.get("schema_version") or config.get("research_version", ""),
        "model": environment.get("MODEL_NAME", "not recorded"),
        "variant": variant_label(environment),
        "k": config.get("num_candidates"),
        "questions": total,
        "correct": correct,
        "ex": correct / total if total else 0.0,
        "ex_ci_low": low, "ex_ci_high": high,
        "oracle": oracle / total if total else 0.0,
        "selection_regret": sum(row["selection_regret"] for row in rows),
        "failed_predictions": sum(not row["prediction_available"] for row in rows),
    }
    for level in ("simple", "moderate", "challenging"):
        subset = [row for row in rows if row["difficulty"] == level]
        result[f"ex_{level}"] = sum(row["correct"] for row in subset) / len(subset) if subset else None
        result[f"n_{level}"] = len(subset)
    for key in ("linked_table_precision", "linked_table_recall", "linked_table_f1", "linked_table_strict",
                "linked_column_precision", "linked_column_recall", "linked_column_f1", "linked_column_strict",
                "linked_tables", "linked_columns", "prompt_tables", "prompt_columns",
                "prompt_table_precision", "prompt_table_recall", "prompt_table_strict",
                "prompt_column_precision", "prompt_column_recall", "prompt_column_strict",
                "prompt_file_tokens", "prompt_schema_block_tokens", "prompt_compact_tokens",
                "db_columns", "schema_reduction_columns", "schema_reduction_tokens",
                "itee_entropy", "itee_budget_turns", "completion_turns", "retrieved_columns"):
        result[f"mean_{key}"] = _mean(row[key] for row in rows)
    budgets = [row["itee_budget_turns"] for row in rows if row["itee_budget_turns"] is not None]
    result["share_min_budget"] = (sum(1 for value in budgets if value is not None and value < 10) / len(budgets)) if budgets else None
    result["tokens_per_question"] = tokens / total if total else 0.0
    for group in STAGE_GROUP_NAMES:
        result[f"tokens_per_question_{group}"] = sum(row[f"tokens_{group}"] for row in rows) / total if total else 0.0
    result["calls_per_question"] = sum(row["calls"] for row in rows) / total if total else 0.0
    result["cost_total"] = cost
    result["cost_per_question"] = cost / total if total else 0.0
    result["tokens_per_correct"] = tokens / correct if correct else None
    result["missing_usage_records"] = sum(row["missing_usage"] for row in rows)
    result["latency_ms_p50"] = usage.get("latency_ms_p50")
    result["latency_ms_p95"] = usage.get("latency_ms_p95")
    result["environment"] = json.dumps(environment, sort_keys=True)
    fingerprint_path = run_root / "pub_code_fingerprint.json"
    fingerprint = read_json(fingerprint_path) if fingerprint_path.exists() else {}
    result["code_fingerprint"] = str(fingerprint.get("fingerprint", "not recorded"))[:12]
    result["code_changed_during_run"] = bool(fingerprint.get("history"))
    result["host"] = fingerprint.get("host", "")
    return result


def render_markdown(summaries: List[Dict[str, Any]]) -> str:
    rows = []
    for item in summaries:
        rows.append({
            "Run": item["run"], "Variant": item["variant"], "k": item["k"], "n": item["questions"],
            "Complete": "yes" if item["complete"] else "NO",
            "EX %": f"{fmt_pct(item['ex'])} [{fmt_pct(item['ex_ci_low'], 1)}, {fmt_pct(item['ex_ci_high'], 1)}]",
            "Oracle %": fmt_pct(item["oracle"]),
            "Tbl P/R": f"{fmt_pct(item['mean_linked_table_precision'], 1)} / {fmt_pct(item['mean_linked_table_recall'], 1)}",
            "Col P/R": f"{fmt_pct(item['mean_linked_column_precision'], 1)} / {fmt_pct(item['mean_linked_column_recall'], 1)}",
            "Prompt cols": f"{item['mean_prompt_columns']:.1f}" if item["mean_prompt_columns"] is not None else "—",
            "Col reduction %": fmt_pct(item["mean_schema_reduction_columns"], 1),
            "Tokens/q": f"{item['tokens_per_question']:,.0f}",
            "Linking tok/q": f"{item['tokens_per_question_linking']:,.0f}",
            "$/q": f"{item['cost_per_question']:.4f}",
            "Min-budget %": fmt_pct(item["share_min_budget"], 1),
            "Code": item["code_fingerprint"] + (" (changed!)" if item["code_changed_during_run"] else ""),
        })
    columns = list(rows[0].keys()) if rows else []
    return "# Run summary\n\nGenerated by `python -m pub.aggregate_runs`. EX uses a fixed denominator (all questions); " \
           "brackets are Wilson 95% intervals. Linking P/R is the linked set after completion (macro mean).\n\n" + md_table(rows, columns) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", nargs="*", help="Run folder names under run/ (default: discover)")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    run_roots = [RUN_DIR / name for name in args.runs] if args.runs else discover_runs()
    summaries = []
    for run_root in run_roots:
        if not (run_root / "dataset.json").exists():
            print(f"Skipping {run_root.name}: no dataset.json")
            continue
        print(f"Aggregating {run_root.name} ...", flush=True)
        rows = per_question_rows(run_root)
        write_csv(args.output / "per_question" / f"{run_root.name}.csv", rows)
        summary = run_summary(run_root, rows)
        summaries.append(summary)
        print(f"  EX {summary['ex']:.4f} ({summary['correct']}/{summary['questions']}), "
              f"tokens/q {summary['tokens_per_question']:,.0f}, complete={summary['complete']}")
    write_csv(args.output / "runs_summary.csv", summaries)
    write_json(args.output / "runs_summary.json", summaries)
    (args.output / "runs_summary.md").write_text(render_markdown(summaries), encoding="utf-8")
    print(f"Wrote {args.output / 'runs_summary.csv'}")


if __name__ == "__main__":
    main()

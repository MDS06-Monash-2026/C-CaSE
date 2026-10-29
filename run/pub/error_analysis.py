"""Where is accuracy lost? Automatic error labels plus a sample for manual checking (plan: O6, T4).

Every wrong answer in a run gets one automatic label, checked in this order:
  no_prediction       no SQL was produced or it failed to execute;
  linking_miss_table  a gold table is missing from the schema prompt the generator saw;
  linking_miss_column all gold tables present, but a gold column is missing;
  selection           a correct candidate was generated but not selected (runs with k > 1);
  generation          everything needed was in the prompt and no candidate was correct.

A seeded random sample is written with an empty "manual_label" column so the team can verify
the automatic labels (report the agreement rate in the paper).

Usage:
  python -m pub.error_analysis --run bird_dev_v18_k1_ref --sample 100
"""

from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from pub.aggregate_runs import _database_schemas
from pub.common import RESULTS_DIR, RUN_DIR, gold_refs, md_table, parse_schema_prompt, read_json, write_csv

LABELS = ("no_prediction", "linking_miss_table", "linking_miss_column", "selection", "generation")


def label_run(run_root: Path) -> List[Dict[str, Any]]:
    records = read_json(run_root / "dataset.json")
    manifest = read_json(run_root / "run_manifest.json") if (run_root / "run_manifest.json").exists() else {}
    schemas = _database_schemas(manifest.get("dataset", "bird"))
    difficulty = {}
    dev_path = RUN_DIR.parent / "dev" / "dev_20240627" / "dev.json"
    if dev_path.exists():
        difficulty = {str(item["question_id"]): item.get("difficulty", "") for item in read_json(dev_path)}
    rows = []
    for instance_id, record in sorted(records.items()):
        evaluation_path = run_root / "evaluation" / f"{instance_id}.json"
        if not evaluation_path.exists():
            continue
        evaluation = read_json(evaluation_path)
        if evaluation.get("correct"):
            continue
        db_schema = schemas.get(record.get("db_id") or record.get("db_name"), {})
        gold = gold_refs(record.get("gold_sql", ""), instance_id)
        if db_schema:
            gold["tables"] &= set(db_schema)
            gold["columns"] &= {column for columns in db_schema.values() for column in columns}
        prompt_path = run_root / "final_schema_prompts" / f"{instance_id}.txt"
        prompt = parse_schema_prompt(prompt_path.read_text(encoding="utf-8", errors="replace") if prompt_path.exists() else "")
        missing_tables = sorted(gold["tables"] - prompt["tables"])
        missing_columns = sorted(gold["columns"] - prompt["columns"])
        if not evaluation.get("prediction_available") or evaluation.get("execution_error"):
            label = "no_prediction"
        elif missing_tables:
            label = "linking_miss_table"
        elif missing_columns:
            label = "linking_miss_column"
        elif evaluation.get("candidate_oracle"):
            label = "selection"
        else:
            label = "generation"
        selected_path = run_root / "sql_selection_v1" / "final" / instance_id / "selected.sql"
        rows.append({
            "instance_id": instance_id, "db_id": record.get("db_id"),
            "difficulty": difficulty.get(str(record.get("source_id")), ""),
            "auto_label": label, "manual_label": "", "notes": "",
            "missing_tables": ";".join(missing_tables), "missing_columns": ";".join(missing_columns),
            "candidate_oracle": bool(evaluation.get("candidate_oracle")),
            "question": record.get("question", ""), "evidence": record.get("evidence", ""),
            "gold_sql": record.get("gold_sql", ""),
            "predicted_sql": selected_path.read_text(encoding="utf-8", errors="replace") if selected_path.exists() else "",
            "execution_error": evaluation.get("execution_error") or "",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default=None, help="Run folder (default: bird_dev_v18_k1_ref, else bird_dev_v18_full)")
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    name = args.run or ("bird_dev_v18_k1_ref" if (RUN_DIR / "bird_dev_v18_k1_ref" / "evaluation").exists() else "bird_dev_v18_full")
    run_root = RUN_DIR / name
    rows = label_run(run_root)
    total_questions = len(read_json(run_root / "dataset.json"))
    counts = Counter(row["auto_label"] for row in rows)
    write_csv(args.output / "errors" / f"{name}_all_wrong.csv", rows)
    sample = random.Random(args.seed).sample(rows, min(args.sample, len(rows)))
    write_csv(args.output / "errors" / f"{name}_sample{len(sample)}.csv", sample)
    table = [{"Label": label, "Count": counts.get(label, 0),
              "% of wrong": f"{100 * counts.get(label, 0) / len(rows):.1f}" if rows else "—",
              "% of all questions": f"{100 * counts.get(label, 0) / total_questions:.1f}" if total_questions else "—"}
             for label in LABELS]
    by_difficulty = []
    for level in ("simple", "moderate", "challenging"):
        subset = Counter(row["auto_label"] for row in rows if row["difficulty"] == level)
        entry = {"Difficulty": level, "Wrong": sum(subset.values())}
        entry.update({label: subset.get(label, 0) for label in LABELS})
        by_difficulty.append(entry)
    (args.output / "errors" / f"{name}_summary.md").write_text(
        f"# Error analysis: {name}\n\nGenerated by `python -m pub.error_analysis`. {len(rows)} wrong answers out of "
        f"{total_questions} questions. Labels are automatic (see the module docstring); verify them on the sample file "
        f"`{name}_sample{len(sample)}.csv` by filling in `manual_label`.\n\n"
        + md_table(table, list(table[0].keys())) + "\n\n## By difficulty\n\n"
        + md_table(by_difficulty, list(by_difficulty[0].keys())) + "\n", encoding="utf-8")
    print(f"{name}: {len(rows)} wrong; " + ", ".join(f"{label}={counts.get(label, 0)}" for label in LABELS))
    print(f"Wrote {args.output / 'errors'}")


if __name__ == "__main__":
    main()

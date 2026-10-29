"""Offline schema-linking evaluation on Spider 2.0-Lite (plan: O1, T1, T3).

No database access is needed: linked schemas come from existing run folders and gold
tables/columns come from the official gold SQL (evaluation_suite/gold/sql, 256 instances).

For each run and instance with parsable gold SQL it computes, for two views of the linked schema,
  * "linked": table/column candidates after completion (unfilled_schema.json), and
  * "prompt": the final schema prompt sent to the generator (final_schema_prompts),
table and column precision, recall, F1 and strict recall, plus schema size and reduction
against the full (condensed) database schema from run/documents, and linking-stage tokens
estimated from the completion agent's logged input/output (tiktoken cl100k_base).

Matching rules:
  * table names are compared on their last dotted part, lower-cased;
  * the schema documents group date-partitioned tables under one representative with
    "similar_tables"; a linked representative covers all of its similar tables;
  * gold tables written with wildcards (e.g. ga_sessions_2017*) match by fnmatch;
  * gold tables and columns that do not exist in the database schema (CTE names, aliases)
    are removed and counted.

Paired comparisons (same questions, same model) are written for SlayQL vs AutoLink on the
178-question subset, and for the SlayQL full run vs AutoLink on the same instances.

Usage:
  python -m pub.spider2_linking
"""

from __future__ import annotations

import argparse
import fnmatch
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pub.common import (
    GOLD_SQL_DIR, RESULTS_DIR, RUN_DIR, compact_schema, count_tokens, fmt_pct, gold_refs, last_part,
    md_table, paired_bootstrap_diff, parse_schema_prompt, read_json, set_metrics, write_csv,
)

DEFAULT_RUNS = {
    "slayql_full": "log_spider2_full_slayql",
    "slayql_178": "log_subset_diverse_20_evaluation_slayql_ccase",
    "autolink_178": "log_subset_diverse_20_evaluation_autolink_baseline_v2",
}
# Primary pair: AutoLink vs the full SlayQL run (same model and linking scripts; intact prompts).
# The 178-question SlayQL run has many schema prompts without any table (a broken final-schema
# step), so its comparison is secondary and only covers instances whose prompt has tables.
PAIRS = (("autolink_178", "slayql_full"), ("autolink_178", "slayql_178"))
DOCUMENT_FILES = {"bigquery": "bigquery.json", "snowflake": "snowflake.json", "sqlite": "localdb.json"}
PAIRED_METRICS = (
    "prompt_table_recall", "prompt_table_precision", "prompt_table_strict",
    "prompt_column_recall", "prompt_column_precision", "prompt_column_strict",
    "linked_table_recall", "linked_table_precision", "linked_column_recall", "linked_column_precision",
    "prompt_tables", "prompt_columns", "prompt_compact_tokens", "prompt_file_tokens",
)


def _backend(instance_id: str) -> str:
    if instance_id.startswith(("bq", "ga")):
        return "bigquery"
    if instance_id.startswith("sf"):
        return "snowflake"
    return "sqlite"


@lru_cache(maxsize=None)
def _documents(backend: str) -> Dict[str, Any]:
    path = RUN_DIR / "documents" / DOCUMENT_FILES[backend]
    return read_json(path) if path.exists() else {}


class DatabaseSchema:
    """Condensed schema of one database from the run/documents files."""

    def __init__(self, backend: str, db_name: str):
        documents = _documents(backend).get(db_name, {})
        self.families: Dict[str, Set[str]] = {}
        self.columns_by_table: Dict[str, List[str]] = {}
        for full_name, entry in documents.items():
            representative = last_part(full_name)
            family = {representative} | {last_part(name) for name in entry.get("similar_tables") or []}
            self.families[representative] = family
            columns = entry.get("columns") or {}
            names = list(columns.keys()) if isinstance(columns, dict) else [str(item) for item in columns]
            self.columns_by_table[representative] = [str(name).lower() for name in names]
        self.all_table_names = set().union(*self.families.values()) if self.families else set()
        self.all_columns = {column for columns in self.columns_by_table.values() for column in columns}

    @property
    def n_tables(self) -> int:
        return len(self.families)

    @property
    def n_columns(self) -> int:
        return sum(len(columns) for columns in self.columns_by_table.values())

    @property
    def n_tables_raw(self) -> int:
        """Tables before condensing date-partitioned siblings into one representative."""
        return sum(len(family) for family in self.families.values())

    @property
    def n_columns_raw(self) -> int:
        return sum(len(self.columns_by_table.get(table, [])) * len(family) for table, family in self.families.items())

    def family(self, table: str) -> Set[str]:
        return self.families.get(table, {table})

    def table_exists(self, gold_table: str) -> bool:
        return any(fnmatch.fnmatch(name, gold_table) for name in self.all_table_names) if self.all_table_names else True


@lru_cache(maxsize=None)
def _schema(backend: str, db_name: str) -> DatabaseSchema:
    return DatabaseSchema(backend, db_name)


@lru_cache(maxsize=None)
def _full_compact_tokens(backend: str, db_name: str) -> int:
    schema = _schema(backend, db_name)
    return count_tokens(compact_schema(schema.columns_by_table)) if schema.columns_by_table else 0


def _table_metrics(linked: Set[str], gold: Set[str], schema: DatabaseSchema) -> Dict[str, float]:
    families = {table: schema.family(table) for table in linked}
    matched_gold = {g for g in gold if any(fnmatch.fnmatch(name, g) for family in families.values() for name in family)}
    useful = {table for table, family in families.items() if any(fnmatch.fnmatch(name, g) for g in gold for name in family)}
    precision = len(useful) / len(linked) if linked else 0.0
    recall = len(matched_gold) / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "strict_recall": 1.0 if gold and len(matched_gold) == len(gold) else 0.0,
            "predicted": len(linked), "gold": len(gold), "missing": sorted(gold - matched_gold)}


def _linked_from_candidates(run_root: Path) -> Dict[str, Dict[str, Set[str]]]:
    path = run_root / "unfilled_schema.json"
    if not path.exists():
        return {}
    result = {}
    for instance_id, payload in read_json(path).items():
        result[instance_id] = {
            "tables": {last_part(value) for value in payload.get("table_candidates", [])},
            "columns": {str(value).split(".")[-1].strip("`\"").lower() for value in payload.get("column_candidates", [])},
        }
    return result


def _linking_tokens(run_root: Path, instance_id: str) -> Optional[int]:
    input_path = run_root / "input" / f"{instance_id}.txt"
    output_path = run_root / "model_output" / f"{instance_id}.txt"
    if not input_path.exists() and not output_path.exists():
        return None
    total = 0
    for path in (input_path, output_path):
        if path.exists():
            total += count_tokens(path.read_text(encoding="utf-8", errors="replace"))
    return total


def evaluate_run(label: str, run_root: Path, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    linked_all = _linked_from_candidates(run_root)
    rows = []
    for gold_path in sorted(GOLD_SQL_DIR.glob("*.sql")):
        instance_id = gold_path.stem
        prompt_path = run_root / "final_schema_prompts" / f"{instance_id}.txt"
        if instance_id not in data or not prompt_path.exists():
            continue
        backend = _backend(instance_id)
        db_name = data[instance_id]["db_name"]
        schema = _schema(backend, db_name)
        refs = gold_refs(gold_path.read_text(encoding="utf-8", errors="replace"), instance_id)
        gold_tables = {table for table in refs["tables"] if schema.table_exists(table)}
        gold_columns = refs["columns"] & schema.all_columns if schema.all_columns else refs["columns"]
        prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace")
        prompt = parse_schema_prompt(prompt_text)
        prompt_table_columns = defaultdict(list)
        for table, column in prompt["table_columns"]:
            prompt_table_columns[table].append(column)
        prompt_compact = count_tokens(compact_schema(prompt_table_columns))
        full_compact = _full_compact_tokens(backend, db_name)
        prompt_tables = _table_metrics(prompt["tables"], gold_tables, schema)
        prompt_columns = set_metrics(prompt["columns"], gold_columns)
        row: Dict[str, Any] = {
            "run": label, "run_folder": run_root.name, "instance_id": instance_id, "backend": backend,
            "db_name": db_name, "gold_parsed": refs["parsed_any"], "gold_parsed_whole": refs["parsed_whole"],
            "gold_tables": len(gold_tables), "gold_columns": len(gold_columns),
            "gold_tables_dropped": len(refs["tables"] - gold_tables),
            "gold_columns_dropped": len(refs["columns"] - gold_columns),
            "db_tables": schema.n_tables, "db_columns": schema.n_columns, "db_compact_tokens": full_compact,
            "db_tables_raw": schema.n_tables_raw, "db_columns_raw": schema.n_columns_raw,
            "schema_reduction_columns_raw": (1 - prompt["n_columns"] / schema.n_columns_raw) if schema.n_columns_raw else None,
            "prompt_tables": prompt["n_tables"], "prompt_columns": prompt["n_columns"],
            "prompt_table_precision": prompt_tables["precision"], "prompt_table_recall": prompt_tables["recall"],
            "prompt_table_f1": prompt_tables["f1"], "prompt_table_strict": prompt_tables["strict_recall"],
            "prompt_missing_tables": ";".join(prompt_tables["missing"]),
            "prompt_column_precision": prompt_columns["precision"], "prompt_column_recall": prompt_columns["recall"],
            "prompt_column_f1": prompt_columns["f1"], "prompt_column_strict": prompt_columns["strict_recall"],
            "prompt_file_tokens": count_tokens(prompt_text), "prompt_compact_tokens": prompt_compact,
            "schema_reduction_columns": (1 - prompt["n_columns"] / schema.n_columns) if schema.n_columns else None,
            "schema_reduction_tokens": (1 - prompt_compact / full_compact) if full_compact else None,
            "linking_tokens_estimated": _linking_tokens(run_root, instance_id),
        }
        linked = linked_all.get(instance_id)
        if linked is not None:
            linked_tables = _table_metrics(linked["tables"], gold_tables, schema)
            linked_columns = set_metrics(linked["columns"], gold_columns)
            row.update({
                "linked_tables": linked_tables["predicted"], "linked_columns": linked_columns["predicted"],
                "linked_table_precision": linked_tables["precision"], "linked_table_recall": linked_tables["recall"],
                "linked_table_strict": linked_tables["strict_recall"],
                "linked_column_precision": linked_columns["precision"], "linked_column_recall": linked_columns["recall"],
                "linked_column_strict": linked_columns["strict_recall"],
            })
        rows.append(row)
    return rows


def _valid(row: Dict[str, Any]) -> bool:
    """Gold SQL parsed with at least one real table, and the schema prompt contains tables."""
    return bool(row["gold_parsed"]) and row["gold_tables"] > 0 and row["prompt_tables"] > 0


def _mean(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _median(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = sorted(float(row[key]) for row in rows if row.get(key) is not None)
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def summarise(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries = []
    for label in sorted({row["run"] for row in rows}):
        subset = [row for row in rows if row["run"] == label]
        valid = [row for row in subset if _valid(row)]
        with_tokens = [row for row in valid if row.get("linking_tokens_estimated") is not None]
        summary = {"run": label, "run_folder": subset[0]["run_folder"], "instances_with_gold": len(subset),
                   "instances_evaluated": len(valid),
                   "excluded_empty_prompt": sum(1 for row in subset if row["prompt_tables"] == 0),
                   "excluded_gold_unparsed": sum(1 for row in subset if not row["gold_parsed"] or row["gold_tables"] == 0),
                   "instances_with_linking_logs": len(with_tokens)}
        for key in ("prompt_table_precision", "prompt_table_recall", "prompt_table_f1", "prompt_table_strict",
                    "prompt_column_precision", "prompt_column_recall", "prompt_column_f1", "prompt_column_strict",
                    "linked_table_precision", "linked_table_recall", "linked_table_strict",
                    "linked_column_precision", "linked_column_recall", "linked_column_strict",
                    "prompt_tables", "prompt_columns", "db_tables", "db_columns", "db_tables_raw", "db_columns_raw",
                    "prompt_compact_tokens", "db_compact_tokens", "prompt_file_tokens",
                    "schema_reduction_columns", "schema_reduction_tokens", "schema_reduction_columns_raw"):
            summary[f"mean_{key}"] = _mean(valid, key)
            summary[f"median_{key}"] = _median(valid, key)
        summary["mean_linking_tokens_estimated"] = _mean(with_tokens, "linking_tokens_estimated")
        for backend in ("bigquery", "snowflake", "sqlite"):
            part = [row for row in valid if row["backend"] == backend]
            summary[f"n_{backend}"] = len(part)
            summary[f"table_recall_{backend}"] = _mean(part, "prompt_table_recall")
        summaries.append(summary)
    return summaries


def paired(rows: List[Dict[str, Any]], base: str, variant: str) -> List[Dict[str, Any]]:
    by_run: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if _valid(row):
            by_run[row["run"]][row["instance_id"]] = row
    shared = sorted(set(by_run.get(base, {})) & set(by_run.get(variant, {})))
    results = []
    for metric in PAIRED_METRICS + ("linking_tokens_estimated",):
        pairs = [(by_run[base][key].get(metric), by_run[variant][key].get(metric)) for key in shared]
        pairs = [(float(a), float(b)) for a, b in pairs if a is not None and b is not None]
        if not pairs:
            continue
        diff, low, high = paired_bootstrap_diff([a for a, _ in pairs], [b for _, b in pairs])
        results.append({
            "base": base, "variant": variant, "metric": metric, "questions": len(pairs),
            "base_mean": sum(a for a, _ in pairs) / len(pairs),
            "variant_mean": sum(b for _, b in pairs) / len(pairs),
            "diff": diff, "diff_ci_low": low, "diff_ci_high": high,
        })
    return results


def render_markdown(summaries: List[Dict[str, Any]], comparisons: List[Dict[str, Any]]) -> str:
    table = [{
        "Run": item["run"], "n": item["instances_evaluated"],
        "Excluded (empty prompt / gold unparsed)": f"{item['excluded_empty_prompt']} / {item['excluded_gold_unparsed']}",
        "Table P / R / strict (prompt)": f"{fmt_pct(item['mean_prompt_table_precision'], 1)} / {fmt_pct(item['mean_prompt_table_recall'], 1)} / {fmt_pct(item['mean_prompt_table_strict'], 1)}",
        "Column P / R / strict (prompt)": f"{fmt_pct(item['mean_prompt_column_precision'], 1)} / {fmt_pct(item['mean_prompt_column_recall'], 1)} / {fmt_pct(item['mean_prompt_column_strict'], 1)}",
        "Tables kept / in DB": f"{item['mean_prompt_tables']:.1f} / {item['mean_db_tables']:.1f}" if item["mean_prompt_tables"] is not None else "—",
        "Columns kept / in DB (condensed / raw), median": (
            f"{item['median_prompt_columns']:.0f} / {item['median_db_columns']:.0f} / {item['median_db_columns_raw']:.0f}"
            if item["median_prompt_columns"] is not None else "—"),
        "Column reduction % vs condensed / raw (median)": (
            f"{fmt_pct(item['median_schema_reduction_columns'], 1)} / {fmt_pct(item['median_schema_reduction_columns_raw'], 1)}"),
        "Schema token reduction % (mean / median)": (
            f"{fmt_pct(item['mean_schema_reduction_tokens'], 1)} / {fmt_pct(item['median_schema_reduction_tokens'], 1)}"),
        "Linking tokens/q (est., n)": (f"{item['mean_linking_tokens_estimated']:,.0f} ({item['instances_with_linking_logs']})"
                                       if item["mean_linking_tokens_estimated"] is not None else "—"),
    } for item in summaries]
    pairs = [{
        "Comparison": f"{row['variant']} − {row['base']}", "Metric": row["metric"], "n": row["questions"],
        "Base": f"{row['base_mean']:.4f}", "Variant": f"{row['variant_mean']:.4f}",
        "Δ [95% CI]": f"{row['diff']:+.4f} [{row['diff_ci_low']:+.4f}, {row['diff_ci_high']:+.4f}]",
    } for row in comparisons]
    return ("# Spider 2.0-Lite schema linking (offline)\n\nGenerated by `python -m pub.spider2_linking`. Gold tables and "
            "columns come from the official gold SQL, restricted to items that exist in the database schema. "
            "\"Prompt\" is the schema the generator saw; \"DB\" sizes use the condensed schema documents. Linking tokens "
            "are estimated with tiktoken from the completion agent's logged input and output, only where logs exist. "
            "\"Condensed\" counts one representative per group of date-partitioned tables (as in the schema "
            "documents); \"raw\" counts every partition.\n\n"
            + md_table(table, list(table[0].keys()) if table else [])
            + "\n\n## Paired comparisons (same instances, same model)\n\n"
            + md_table(pairs, list(pairs[0].keys()) if pairs else []) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    data = read_json(RUN_DIR / "spider2_data.json")
    rows: List[Dict[str, Any]] = []
    for label, folder in DEFAULT_RUNS.items():
        run_root = RUN_DIR / folder
        if not run_root.exists():
            print(f"Skipping {label}: {folder} not found")
            continue
        print(f"Evaluating linking for {label} ({folder}) ...", flush=True)
        run_rows = evaluate_run(label, run_root, data)
        rows.extend(run_rows)
        print(f"  {len(run_rows)} instances with gold SQL, {sum(_valid(row) for row in run_rows)} evaluable")
    summaries = summarise(rows)
    comparisons = [item for base, variant in PAIRS for item in paired(rows, base, variant)]
    write_csv(args.output / "spider2_linking_per_instance.csv", rows)
    write_csv(args.output / "spider2_linking_summary.csv", summaries)
    write_csv(args.output / "spider2_linking_paired.csv", comparisons)
    (args.output / "spider2_linking.md").write_text(render_markdown(summaries, comparisons), encoding="utf-8")
    for item in summaries:
        print(f"{item['run']}: n={item['instances_evaluated']}, table R={item['mean_prompt_table_recall']}, "
              f"P={item['mean_prompt_table_precision']}, token reduction={item['mean_schema_reduction_tokens']}")
    print(f"Wrote {args.output / 'spider2_linking.md'}")


if __name__ == "__main__":
    main()

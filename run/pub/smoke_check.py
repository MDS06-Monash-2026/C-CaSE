"""Check that smoke runs worked and that every experiment switch had an effect.

For each smoke run (smoke_v18_k1_<variant>) it checks:
  * the run finished and was evaluated;
  * resolved_config.json records the expected experiment switch and the model;
  * API calls went to the configured model;
  * few-shot demonstrations match the v1.8 full run for the same questions;
  * the switch changed what it should, compared with the smoke reference run:
      no_rbp   log shows "RBP disabled"; retrieval order differs
      no_bm25  log shows "BM25 grounding disabled"
      no_qoc   generation prompt no longer contains the ```sql output-format block
      topn*    retrieved columns never exceed the top-N limit
      itee_max IT-EE budgets equal the offline simulation at threshold 1.01

Usage:
  python -m pub.smoke_check --runs smoke_v18_k1_ref smoke_v18_k1_no_rbp ...
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pub.common import RUN_DIR, md_table, read_json, read_text_any

EXPECTED_ENV = {
    "no_rbp": {"ABLATION_NO_RBP": "1"},
    "no_bm25": {"ABLATION_NO_BM25": "1"},
    "no_qoc": {"ABLATION_NO_QOC": "1"},
    "no_itee": {"ABLATION_NO_ITEE": "1"},
    "topn20": {"SLAYQL_TOP_N": "20"},
    "topn50": {"SLAYQL_TOP_N": "50"},
    "topn10000": {"SLAYQL_TOP_N": "10000"},
    "itee_max": {"ABLATION_ITEE_THRESHOLD": "1.01"},
    "ref": {},
}
V18_RUN = RUN_DIR / "bird_dev_v18_full"


def _variant(run: str) -> str:
    return run.split("_k1_", 1)[-1]


def _log(run: str) -> str:
    text = ""
    for name in (f"{run}.log", f"{run}.err.log"):
        path = RUN_DIR / "logs_pub" / name
        if path.exists():
            text += read_text_any(path)
    return text


def _generation_prompts(root: Path) -> List[str]:
    prompts = []
    for path in (root / "sql_gen").glob("r1_lite_messages_*/*.json"):
        try:
            prompts.append(json.dumps(read_json(path), ensure_ascii=False))
        except (OSError, ValueError):
            continue
    for path in (root / "sql_gen").glob("r1_lite_sql_generation_*/*.txt"):
        prompts.append(path.read_text(encoding="utf-8", errors="replace"))
    return prompts


def check_run(run: str, reference: str) -> List[Tuple[str, str, str]]:
    root, ref_root = RUN_DIR / run, RUN_DIR / reference
    variant = _variant(run)
    results: List[Tuple[str, str, str]] = []

    def add(check: str, ok: Any, detail: str = "") -> None:
        results.append((check, "PASS" if ok is True else ("INFO" if ok is None else "FAIL"), detail))

    summary_path = root / "aggregates" / "summary_metrics.json"
    add("run finished and evaluated", summary_path.exists(), str(summary_path.relative_to(RUN_DIR)) if summary_path.exists() else "missing summary_metrics.json")
    if summary_path.exists():
        summary = read_json(summary_path)
        add("predictions produced", summary.get("covered", 0) == summary.get("expected", -1),
            f"{summary.get('covered')}/{summary.get('expected')} covered, {summary.get('correct')} correct")

    config = read_json(root / "resolved_config.json") if (root / "resolved_config.json").exists() else {}
    environment = config.get("environment", {})
    expected = EXPECTED_ENV.get(variant, {})
    recorded = {key: value for key, value in environment.items() if key.startswith(("ABLATION_", "SLAYQL_TOP_N"))}
    add("switch recorded in resolved_config", recorded == expected, f"recorded {recorded or '{}'}, expected {expected or '{}'}")
    add("model recorded in resolved_config", bool(environment.get("MODEL_NAME")), environment.get("MODEL_NAME", "missing"))

    models = set()
    for path in (root / "usage").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                models.add(json.loads(line).get("model"))
            except json.JSONDecodeError:
                continue
    add("API calls used the configured model", models == {environment.get("MODEL_NAME")} if models else None,
        ", ".join(sorted(str(model) for model in models)) or "no usage records")

    # Reference selections: the v1.8 run folder if present, otherwise the exported copy in pub_inputs.
    exported = RUN_DIR / "pub_inputs" / "v18_demo_selections.json"
    reference_selections = read_json(exported) if exported.exists() else {}
    same, compared = 0, 0
    for path in (root / "prompt_learning").glob("*.json"):
        v18_path = V18_RUN / "prompt_learning" / path.name
        if v18_path.exists():
            theirs = [item["demo_id"] for item in read_json(v18_path).get("selected", [])]
        elif path.stem in reference_selections:
            theirs = reference_selections[path.stem]
        else:
            continue
        compared += 1
        mine = [item["demo_id"] for item in read_json(path).get("selected", [])]
        same += mine == theirs
    add("demonstrations match the v1.8 full run", same == compared if compared else None, f"{same}/{compared} identical")

    log = _log(run)
    initial = read_json(root / "initial_candidates.json") if (root / "initial_candidates.json").exists() else {}
    ref_initial = read_json(ref_root / "initial_candidates.json") if (ref_root / "initial_candidates.json").exists() else {}
    if variant == "no_rbp":
        add("log shows RBP disabled", "RBP disabled" in log)
        changed = sum(initial.get(key, {}).get("column_candidates") != ref_initial.get(key, {}).get("column_candidates") for key in initial)
        add("retrieval differs from reference", changed > 0 if ref_initial else None, f"{changed}/{len(initial)} questions differ")
    elif variant == "no_bm25":
        add("log shows BM25 grounding disabled", "BM25 grounding disabled" in log)
    elif variant == "no_itee":
        add("log shows IT-EE disabled", "IT-EE disabled" in log)
    elif variant == "no_qoc":
        prompts = _generation_prompts(root)
        add("generation prompts saved", bool(prompts) or None, f"{len(prompts)} prompt files")
        if prompts:
            add("output-format block removed", all("contained within ```sql```" not in text for text in prompts))
    elif variant.startswith("topn"):
        limit = int(expected["SLAYQL_TOP_N"])
        counts = [value.get("retrieved_count", 0) for value in initial.values()]
        add(f"retrieved columns <= {limit}", all(count <= limit for count in counts), f"retrieved {counts}")
        if ref_initial and limit < 100:
            ref_counts = [value.get("retrieved_count", 0) for value in ref_initial.values()]
            add("fewer columns than reference", sum(counts) < sum(ref_counts) or None, f"{sum(counts)} vs reference {sum(ref_counts)}")
    elif variant == "itee_max":
        import it_ee
        matches = 0
        detail = []
        for key, value in initial.items():
            with contextlib.redirect_stdout(io.StringIO()):
                _, simulated = it_ee.determine_budget(float(value["entropy"]), query=value.get("question", ""), base_turns=10, threshold=1.01)
            matches += simulated == value.get("dynamic_t_max")
            detail.append(f"{value.get('dynamic_t_max')} (sim {simulated})")
        add("IT-EE budgets match simulation at 1.01", matches == len(initial) if initial else None, ", ".join(detail))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--reference", default="smoke_v18_k1_ref")
    args = parser.parse_args()
    rows: List[Dict[str, Any]] = []
    for run in args.runs:
        for check, status, detail in check_run(run, args.reference):
            rows.append({"Run": run, "Check": check, "Status": status, "Detail": detail})
    report = "# Smoke check\n\nGenerated by `python -m pub.smoke_check`.\n\n" + md_table(rows, ["Run", "Check", "Status", "Detail"]) + "\n"
    output = RUN_DIR / "pub_results_smoke" / "smoke_check.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    failures = [row for row in rows if row["Status"] == "FAIL"]
    print(f"{len(failures)} failed check(s). Report: {output}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

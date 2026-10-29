"""Run every publication analysis step and assemble pub_results/REPORT.md.

Steps (each is also runnable on its own as `python -m pub.<module>`):
  1. aggregate_runs   per-question and per-run tables for BIRD / Spider 1.0 runs   (O2, T1, T2)
  2. stats            paired comparisons vs the reference run, Holm-adjusted        (O5, T2)
  3. oracle_at_k      accuracy vs number of candidates                              (O3, F3)
  4. itee_activation  when IT-EE reduces the exploration budget                     (O7)
  5. spider2_linking  offline Spider 2.0-Lite linking, SlayQL vs AutoLink           (O1, T1, T3)
  6. error_analysis   automatic error labels + manual-check sample                  (O6, T4)
  7. old_ablation     diagnosis of the old 178-question ablation                    (O4)
  8. figures          F2 and F3

Usage (from the run/ folder):
  python -m pub.run_analysis
  python -m pub.run_analysis --skip spider2_linking     # skip slow steps
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from pub.common import RESULTS_DIR, RUN_DIR, md_table

STEPS = ("aggregate_runs", "stats", "oracle_at_k", "itee_activation", "spider2_linking",
         "error_analysis", "old_ablation", "figures")

# Published numbers from the team's Comparisons.pdf. Re-check every value against the original
# paper (backbone, split, recall definition) before quoting them.
PUBLISHED_LINKING = [
    {"Method": "RSL-SQL", "Venue": "2024", "Training": "Prompting", "Backbone": "GPT-4o", "BIRD EX": "67.21", "P": "—", "R": "94.32", "Recall type": "verify"},
    {"Method": "MCS-SQL", "Venue": "COLING 2025", "Training": "Prompting", "Backbone": "GPT-4", "BIRD EX": "65.50", "P": "—", "R": "99.20", "Recall type": "verify"},
    {"Method": "LinkAlign", "Venue": "EMNLP 2025", "Training": "Prompting", "Backbone": "GPT-4 (verify)", "BIRD EX": "61.60", "P": "—", "R": "79.40", "Recall type": "verify"},
    {"Method": "JOLT-SQL", "Venue": "EMNLP 2025", "Training": "Fine-tuning", "Backbone": "Qwen2.5-Coder-14B", "BIRD EX": "64.90", "P": "75.12", "R": "96.68", "Recall type": "verify"},
    {"Method": "GenLink", "Venue": "EMNLP 2025", "Training": "Fine-tuning", "Backbone": "7-8B models", "BIRD EX": "67.34", "P": "—", "R": "94.56-97.22", "Recall type": "count-based"},
    {"Method": "AutoLink", "Venue": "AAAI 2026", "Training": "Prompting", "Backbone": "DeepSeek", "BIRD EX": "68.71", "P": "—", "R": "97.40", "Recall type": "strict"},
    {"Method": "BiSchemaLink", "Venue": "EACL 2026", "Training": "Prompting", "Backbone": "Gemini 2.0-Flash", "BIRD EX": "57.80", "P": "—", "R": "90.60", "Recall type": "verify"},
    {"Method": "SchemaGraphSQL", "Venue": "EACL 2026", "Training": "Prompting", "Backbone": "Gemini 2.5-Flash", "BIRD EX": "62.91", "P": "86.21", "R": "95.71", "Recall type": "verify"},
    {"Method": "LiteSQL", "Venue": "EACL 2026", "Training": "Fine-tuning + RL", "Backbone": "Qwen2.5-Coder", "BIRD EX": "72.10", "P": "—", "R": "82.31", "Recall type": "verify"},
    {"Method": "Graph-Link", "Venue": "ICML 2026", "Training": "Prompting", "Backbone": "Qwen3-max", "BIRD EX": "68.50", "P": "70.40", "R": "95.90", "Recall type": "verify"},
]
PUBLISHED_SPIDER2_EX = [
    {"Method": "AST-SQL", "Venue": "ICML 2026", "Training": "RL", "Backbone": "Qwen2.5-Coder / OmniSQL-7B", "EX": "8.90 / 14.10"},
    {"Method": "Arctic-Text2SQL-R1-32B", "Venue": "ACL 2026", "Training": "RL", "Backbone": "32B", "EX": "16.30"},
    {"Method": "LinkAlign", "Venue": "EMNLP 2025", "Training": "Prompting", "Backbone": "DeepSeek", "EX": "33.09"},
    {"Method": "AutoLink", "Venue": "AAAI 2026", "Training": "Prompting", "Backbone": "DeepSeek", "EX": "34.92"},
    {"Method": "VET", "Venue": "ACL 2026", "Training": "Prompting", "Backbone": "DeepSeek-Chat", "EX": "37.04"},
    {"Method": "SlayQL (ours)", "Venue": "—", "Training": "Prompting", "Backbone": "deepseek-v4-flash", "EX": "45.89 (251/547)"},
    {"Method": "PExA", "Venue": "ACL 2026", "Training": "Prompting", "Backbone": "verify", "EX": "46.60"},
    {"Method": "SquRL", "Venue": "ICML 2026", "Training": "RL", "Backbone": "verify", "EX": "49.18"},
]


def run_step(name: str) -> bool:
    module = __import__(f"pub.{name}", fromlist=["main"])
    argv = sys.argv
    sys.argv = [f"pub.{name}"]
    if name == "stats":
        sys.argv += ["--pairs", "bird_dev_full:bird_dev_v18_full"]
    try:
        started = time.time()
        print(f"\n=== {name} ===", flush=True)
        module.main()
        print(f"=== {name} done in {time.time() - started:.0f}s ===", flush=True)
        return True
    except Exception:
        traceback.print_exc()
        print(f"=== {name} FAILED (continuing) ===", flush=True)
        return False
    finally:
        sys.argv = argv


def _section(title: str, path: Path) -> str:
    if not path.exists():
        return f"## {title}\n\n_Not available: `{path.relative_to(RUN_DIR)}` was not produced._\n"
    body = path.read_text(encoding="utf-8").split("\n", 1)[-1]
    return f"## {title}\n\n_Source: `{path.relative_to(RUN_DIR)}`_\n{body}\n"


def _code_consistency(results: Path) -> str:
    """Warn if the new k=1 runs were produced by different pipeline code."""
    import json
    path = results / "runs_summary.json"
    if not path.exists():
        return ""
    runs = [row for row in json.loads(path.read_text(encoding="utf-8")) if row["run"].startswith("bird_dev_v18_k1_")]
    fingerprints = {row.get("code_fingerprint") for row in runs}
    changed = [row["run"] for row in runs if row.get("code_changed_during_run")]
    if not runs:
        return ""
    if len(fingerprints) == 1 and not changed:
        return f"**Code consistency:** all {len(runs)} new runs used the same pipeline code ({fingerprints.pop()}).\n"
    lines = ["**WARNING - code consistency:** the new runs were not all produced by the same pipeline code. "
             "Check `pub_code_fingerprint.json` in each run folder before comparing them."]
    for row in runs:
        lines.append(f"- {row['run']}: {row.get('code_fingerprint')} on {row.get('host') or 'unknown host'}"
                     + (" (code changed during the run)" if row.get("code_changed_during_run") else ""))
    return "\n".join(lines) + "\n"


def build_report(results: Path, outcomes: dict) -> None:
    error_summaries = sorted((results / "errors").glob("*_summary.md")) if (results / "errors").exists() else []
    parts = [
        "# SlayQL publication results\n",
        f"Generated by `python -m pub.run_analysis` on {time.strftime('%Y-%m-%d %H:%M')}. Every number here is "
        "computed from run folders under `run/`; published numbers (last sections) are copied from "
        "`Comparisons.pdf` and must be verified before quoting.\n",
        md_table([{"Step": step, "Status": "ok" if ok else "FAILED or skipped"} for step, ok in outcomes.items()], ["Step", "Status"]) + "\n",
        _code_consistency(results),
        _section("All runs (T1/T2 source)", results / "runs_summary.md"),
        _section("Paired comparisons vs reference (T2)", results / "comparisons.md"),
        _section("Spider 2.0-Lite linking (T1, T3)", results / "spider2_linking.md"),
        _section("Candidate budget (F3)", results / "oracle_at_k.md"),
        _section("IT-EE activation (budget analysis)", results / "itee_activation.md"),
    ]
    for path in error_summaries:
        parts.append(_section(f"Error analysis ({path.stem.replace('_summary', '')})", path))
    parts.append(_section("Old 178-question ablation diagnosis", results / "old_ablation_diagnosis.md"))
    parts.append("## Figures\n\n" + "\n".join(f"- `{path.relative_to(RUN_DIR)}`" for path in sorted((results / "figures").glob("*.png"))) + "\n"
                 if (results / "figures").exists() else "## Figures\n\n_None yet._\n")
    parts.append("## Published schema-linking results (context only; verify)\n\n"
                 + md_table(PUBLISHED_LINKING, list(PUBLISHED_LINKING[0].keys())) + "\n")
    parts.append("## Published Spider 2.0-Lite EX (context only; verify)\n\n"
                 + md_table(PUBLISHED_SPIDER2_EX, list(PUBLISHED_SPIDER2_EX[0].keys())) + "\n")
    (results / "REPORT.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"\nReport: {results / 'REPORT.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip", nargs="*", default=[], choices=STEPS)
    parser.add_argument("--only", nargs="*", choices=STEPS)
    args = parser.parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    steps = args.only or [step for step in STEPS if step not in args.skip]
    outcomes = {step: (run_step(step) if step in steps else False) for step in STEPS}
    build_report(RESULTS_DIR, outcomes)


if __name__ == "__main__":
    main()

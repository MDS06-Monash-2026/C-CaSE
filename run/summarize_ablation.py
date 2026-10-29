"""Create machine-readable and Markdown comparisons from completed ablation runs."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List

from artifact_store import atomic_write_json, atomic_write_text


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _paired_interval(values: List[float], seed: int = 20260813, samples: int = 2000) -> List[float]:
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        means.append(sum(rng.choice(values) for _ in values) / len(values))
    means.sort()
    return [means[int(0.025 * samples)], means[min(samples - 1, int(0.975 * samples))]]


def summarize(run_root: Path, dataset: str, study: str, mode: str) -> Dict[str, Any]:
    prefix = f"ablation_{dataset}_{study}_"
    rows = []
    for directory in sorted(path for path in run_root.iterdir() if path.is_dir() and path.name.startswith(prefix) and path.name.endswith(f"_{mode}")):
        summary_path = directory / "aggregates" / "summary_metrics.json"
        manifest_path = directory / "ablation_manifest.json"
        if not summary_path.exists() or not manifest_path.exists():
            continue
        summary, manifest = _read(summary_path), _read(manifest_path)
        correctness = {item["instance_id"]: int(bool(item["correct"])) for item in summary.get("instances", [])}
        rows.append({
            "label": manifest["label"], "run_id": directory.name,
            "execution_accuracy": summary.get("execution_accuracy", 0.0),
            "coverage": summary.get("coverage", 0.0),
            "candidate_oracle_accuracy": summary.get("candidate_oracle_accuracy", 0.0),
            "selection_regret": summary.get("selection_regret", 0),
            "total_tokens": summary.get("usage", {}).get("total_tokens", 0),
            "cost": summary.get("usage", {}).get("cost", 0.0),
            "correctness": correctness,
        })
    if not rows:
        raise RuntimeError(f"No completed ablation summaries found for {dataset}/{study}/{mode}")
    baseline = next((row for row in rows if row["label"] in {"bm25_raw_5_0", "topn_100", "candidates_5", "rbp_0_7", "itee_0_4", "selector_0_10", "hintcap_3"}), rows[0])
    for row in rows:
        shared = sorted(set(row["correctness"]) & set(baseline["correctness"]))
        deltas = [row["correctness"][key] - baseline["correctness"][key] for key in shared]
        row["paired_delta"] = sum(deltas) / len(deltas) if deltas else 0.0
        row["paired_delta_95ci"] = _paired_interval(deltas)
        row["paired_wins"] = sum(value > 0 for value in deltas)
        row["paired_losses"] = sum(value < 0 for value in deltas)
        del row["correctness"]
    result = {"schema_version": "1.0", "dataset": dataset, "study": study, "mode": mode,
              "baseline": baseline["label"], "variants": rows}
    output_dir = run_root / "ablation_reports"
    atomic_write_json(str(output_dir / f"{dataset}_{study}_{mode}.json"), result)
    lines = [f"# {dataset} {study} ablation ({mode})", "",
             f"Paired baseline: `{baseline['label']}`", "",
             "| Variant | EX | Coverage | Oracle | Regret | Tokens | Cost | Paired delta (95% CI) | Wins/Losses |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        interval = row["paired_delta_95ci"]
        lines.append(f"| {row['label']} | {row['execution_accuracy']:.4f} | {row['coverage']:.4f} | "
                     f"{row['candidate_oracle_accuracy']:.4f} | {row['selection_regret']} | {row['total_tokens']} | "
                     f"{row['cost']:.6f} | {row['paired_delta']:+.4f} [{interval[0]:+.4f}, {interval[1]:+.4f}] | "
                     f"{row['paired_wins']}/{row['paired_losses']} |")
    atomic_write_text(str(output_dir / f"{dataset}_{study}_{mode}.md"), "\n".join(lines) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--study", required=True)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    result = summarize(args.run_root, args.dataset, args.study, args.mode)
    print(f"Wrote ablation report for {len(result['variants'])} variants")


if __name__ == "__main__":
    main()

"""Figures for the paper (plan: F2, F3).

F2  EX and prompt column recall against tokens per question for the k=1 BIRD runs, with
    Wilson 95% intervals and the accuracy-cost Pareto frontier.
F3  oracle@k and vote@k against the number of candidates, with the selected EX of each run.

Usage:
  python -m pub.figures
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from pub.common import RESULTS_DIR, read_csv, read_json

K1_PREFIX = "bird_dev_v18_k1_"


def _pareto(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    frontier, best = [], -1.0
    for point in sorted(points, key=lambda item: item["tokens_per_question"]):
        if point["ex"] > best:
            frontier.append(point)
            best = point["ex"]
    return frontier


def figure_budget(results: Path, output: Path, prefix: str = K1_PREFIX) -> bool:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = results / "runs_summary.json"
    if not path.exists():
        return False
    points = [row for row in read_json(path) if row["run"].startswith(prefix) and row["questions"]]
    if not points:
        print(f"F2 skipped: no {prefix}* runs aggregated yet")
        return False
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for point in points:
        x = point["tokens_per_question"] / 1000
        axes[0].errorbar(x, 100 * point["ex"], yerr=[[100 * (point["ex"] - point["ex_ci_low"])], [100 * (point["ex_ci_high"] - point["ex"])]],
                         fmt="o", capsize=3)
        axes[0].annotate(point["variant"], (x, 100 * point["ex"]), textcoords="offset points", xytext=(4, 4), fontsize=7)
        if point.get("mean_prompt_column_recall") is not None:
            axes[1].plot(x, 100 * point["mean_prompt_column_recall"], "o")
            axes[1].annotate(point["variant"], (x, 100 * point["mean_prompt_column_recall"]), textcoords="offset points",
                             xytext=(4, 4), fontsize=7)
    frontier = _pareto(points)
    axes[0].plot([p["tokens_per_question"] / 1000 for p in frontier], [100 * p["ex"] for p in frontier], "--", linewidth=1)
    axes[0].set(xlabel="Tokens per question (thousands)", ylabel="Execution accuracy (%)", title="Accuracy vs budget (BIRD dev, k=1)")
    axes[1].set(xlabel="Tokens per question (thousands)", ylabel="Prompt column recall (%)", title="Linking recall vs budget")
    for axis in axes:
        axis.grid(alpha=0.3)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output / f"F2_accuracy_vs_tokens.{suffix}", dpi=200)
    plt.close(fig)
    return True


def figure_candidates(results: Path, output: Path) -> bool:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = results / "oracle_at_k.csv"
    if not path.exists():
        return False
    rows = read_csv(path)
    if not rows:
        return False
    fig, axis = plt.subplots(figsize=(5, 4))
    for run in sorted({row["run"] for row in rows}):
        subset = [row for row in rows if row["run"] == run]
        ks = [int(row["j"]) for row in subset]
        line = axis.plot(ks, [100 * float(row["oracle_at_j"]) for row in subset], "o-", label=f"{run} oracle@k")[0]
        axis.plot(ks, [100 * float(row["vote_at_j"]) for row in subset], "s--", color=line.get_color(), label=f"{run} vote@k")
        axis.axhline(100 * float(subset[0]["selected_ex_all_k"]), color=line.get_color(), linestyle=":", linewidth=1)
    axis.set(xlabel="Number of candidates k", ylabel="Accuracy (%)", title="Candidate budget (dotted: selected EX)")
    axis.grid(alpha=0.3)
    axis.legend(fontsize=6)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output / f"F3_candidates.{suffix}", dpi=200)
    plt.close(fig)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=RESULTS_DIR)
    parser.add_argument("--prefix", default=K1_PREFIX, help="Run-name prefix of the k=1 runs to plot in F2")
    args = parser.parse_args()
    output = args.results / "figures"
    output.mkdir(parents=True, exist_ok=True)
    print("F2 written" if figure_budget(args.results, output, args.prefix) else "F2 not written")
    print("F3 written" if figure_candidates(args.results, output) else "F3 not written")


if __name__ == "__main__":
    main()

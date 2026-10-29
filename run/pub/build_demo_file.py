"""Rebuild the few-shot demonstration file used by the v1.8 BIRD run.

The v1.8 full run (bird_dev_v18_full) drew 2 demonstrations per question from the BIRD train
set (train.json, 9,428 examples), which is not on this machine. Its per-question selections are
saved in bird_dev_v18_full/prompt_learning/. This script writes the union of the selected
examples as a training-only demonstration file.

Because prompt_learning.select_demonstrations ranks deterministically (score, then demo_id), a
source containing every example that was selected reproduces the same selections: any example
that would outrank a selected one in this subset would also have outranked it in the full train
set. The smoke test checks this by comparing selections with the v1.8 run.

Usage:
  python -m pub.build_demo_file
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pub.common import RUN_DIR, read_json, write_json

DEFAULT_SOURCE = RUN_DIR / "bird_dev_v18_full" / "prompt_learning"
DEFAULT_OUTPUT = RUN_DIR / "pub_inputs" / "bird_train_demos_from_v18.json"


def build(source: Path, output: Path) -> int:
    demos = {}
    for path in sorted(source.glob("*.json")):
        payload = read_json(path)
        for demo in payload.get("selected", []):
            demos.setdefault(demo["demo_id"], {
                "db_id": demo["db_id"],
                # question_id reproduces the original demo_id "<db_id>:<index in train.json>".
                "question_id": demo["demo_id"].split(":", 1)[1],
                "question": demo["question"],
                "evidence": demo.get("evidence", ""),
                "SQL": demo["sql"],
                "split": "train",
            })
    records = [demos[key] for key in sorted(demos)]
    write_json(output, records)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    count = build(args.source, args.output)
    print(f"Wrote {count} training demonstrations to {args.output}")


if __name__ == "__main__":
    main()

"""Package finished (or partly finished) runs so they can be analysed on another machine.

Only what the analysis needs is included: per-question evaluations, linked schemas and schema
prompts, usage logs, IT-EE budgets, selections and manifests. Large rebuildable caches (schema
documents, embeddings, BM25 indexes, agent caches) are left out, so a full run packs into
tens of megabytes instead of gigabytes.

Unzip the package inside the run/ folder of the analysis machine, then run
`python -m pub.run_analysis` there.

Usage:
  python -m pub.package_results                         # all bird_dev_v18_k1_* runs + logs_pub
  python -m pub.package_results --runs bird_dev_v18_k1_ref bird_dev_v18_k1_topn20
  python -m pub.package_results --include-smoke
"""

from __future__ import annotations

import argparse
import json
import socket
import time
import zipfile
from pathlib import Path
from typing import List

from pub.common import RUN_DIR
from pub.fingerprint import read as read_fingerprint

INCLUDE_FILES = (
    "dataset.json", "dataset_manifest.json", "run_manifest.json", "resolved_config.json", "research_summary.json",
    "pub_code_fingerprint.json", "initial_candidates.json", "unfilled_schema.json", "schema_focus_manifest.json",
    "subset_manifest.json", "reproducibility_manifest.json", "prompt_learning_manifest.json",
    "semantic_revise_manifest.json", "selection_failures.json", "uncompleted_instances.txt",
)
INCLUDE_DIRS = (
    "aggregates", "evaluation", "metrics", "final_schema_prompts", "usage", "tool_calls", "prompt_learning",
    "sql_selection_v1", "selection", "sql_gen", "sql_revise", "semantic_revise", "error", "status",
)


def default_runs(include_smoke: bool) -> List[str]:
    patterns = ["bird_dev_v18_k1_*"] + (["smoke_v18_k1_*"] if include_smoke else [])
    names = []
    for pattern in patterns:
        names.extend(path.name for path in sorted(RUN_DIR.glob(pattern))
                     if path.is_dir() and "_backup_" not in path.name)
    return names


def package(runs: List[str], output: Path) -> Path:
    manifest = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "host": socket.gethostname(), "runs": []}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in runs:
            root = RUN_DIR / name
            if not root.is_dir():
                print(f"Skipping {name}: not found")
                continue
            count = 0
            for file_name in INCLUDE_FILES:
                path = root / file_name
                if path.exists():
                    archive.write(path, f"{name}/{file_name}")
                    count += 1
            for dir_name in INCLUDE_DIRS:
                for path in (root / dir_name).rglob("*") if (root / dir_name).exists() else []:
                    if path.is_file():
                        archive.write(path, path.relative_to(RUN_DIR).as_posix())
                        count += 1
            fingerprint = read_fingerprint(root)
            manifest["runs"].append({
                "run": name, "files": count,
                "complete": (root / "aggregates" / "summary_metrics.json").exists() and (root / "research_summary.json").exists(),
                "code_fingerprint": fingerprint.get("fingerprint"),
            })
            print(f"Added {name}: {count} files")
        logs = RUN_DIR / "logs_pub"
        if logs.exists():
            for path in logs.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(RUN_DIR).as_posix())
        archive.writestr("pub_package_manifest.json", json.dumps(manifest, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", nargs="*")
    parser.add_argument("--include-smoke", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runs = args.runs or default_runs(args.include_smoke)
    if not runs:
        raise SystemExit("No runs found to package")
    output = args.output or RUN_DIR / f"pub_results_package_{socket.gethostname()}_{time.strftime('%Y%m%d_%H%M')}.zip"
    package(runs, output)
    print(f"Wrote {output} ({output.stat().st_size / 1024 ** 2:.1f} MB). Unzip it inside run/ on the analysis machine.")


if __name__ == "__main__":
    main()

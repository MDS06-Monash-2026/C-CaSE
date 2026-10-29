"""Fingerprint of the pipeline code, so results from different machines can be checked for drift.

The fingerprint covers every pipeline script (run/*.py) and pipeline config (run/config/*.json).
Analysis code in run/pub/ is excluded because it never affects a run's outputs. Line endings
are normalised so that Windows and macOS/Linux checkouts give the same fingerprint.

Usage:
  python -m pub.fingerprint                      # print the current fingerprint
  python -m pub.fingerprint --write RUN_FOLDER   # save it into a run folder (done by pub_run_all.ps1)
  python -m pub.fingerprint --compare RUN_FOLDER # compare a run folder with the current code
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from pathlib import Path
from typing import Dict

from pub.common import RUN_DIR

FILE_NAME = "pub_code_fingerprint.json"
REFERENCE = RUN_DIR / "pub_inputs" / "code_fingerprint_reference.json"


def pipeline_files():
    return sorted(list(RUN_DIR.glob("*.py")) + list((RUN_DIR / "config").glob("*.json")))


def compute() -> Dict[str, object]:
    files = {}
    for path in pipeline_files():
        data = path.read_bytes().replace(b"\r\n", b"\n")
        files[path.relative_to(RUN_DIR).as_posix()] = hashlib.sha256(data).hexdigest()
    combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    return {"fingerprint": combined, "files": files}


def differences(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, list]:
    return {
        "changed": sorted(name for name in set(left) & set(right) if left[name] != right[name]),
        "only_in_first": sorted(set(left) - set(right)),
        "only_in_second": sorted(set(right) - set(left)),
    }


def write(run_folder: Path) -> Dict[str, object]:
    run_folder.mkdir(parents=True, exist_ok=True)
    current = compute()
    path = run_folder / FILE_NAME
    history = []
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        history = previous.get("history", [])
        if previous.get("fingerprint") != current["fingerprint"]:
            diff = differences(previous.get("files", {}), current["files"])
            print(f"WARNING: pipeline code changed since this run started: {diff}")
            history.append({"fingerprint": previous.get("fingerprint"), "recorded_at": previous.get("recorded_at"),
                            "host": previous.get("host")})
    payload = {**current, "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "host": socket.gethostname(),
               "history": history}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def read(run_folder: Path) -> Dict[str, object]:
    path = run_folder / FILE_NAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--save-reference", action="store_true", help="Store the current fingerprint as the tested reference")
    args = parser.parse_args()
    if args.write:
        payload = write(args.write if args.write.is_absolute() else RUN_DIR / args.write)
        print(f"Code fingerprint {payload['fingerprint'][:12]} written to {args.write}")
    elif args.compare:
        recorded = read(args.compare if args.compare.is_absolute() else RUN_DIR / args.compare)
        current = compute()
        same = recorded.get("fingerprint") == current["fingerprint"]
        print(f"{'SAME' if same else 'DIFFERENT'}: run {str(recorded.get('fingerprint'))[:12]} vs current {current['fingerprint'][:12]}")
        if not same:
            print(differences(recorded.get("files", {}), current["files"]))
    elif args.save_reference:
        REFERENCE.parent.mkdir(parents=True, exist_ok=True)
        REFERENCE.write_text(json.dumps(compute(), indent=2), encoding="utf-8")
        print(f"Saved reference fingerprint to {REFERENCE}")
    else:
        print(compute()["fingerprint"])


if __name__ == "__main__":
    main()

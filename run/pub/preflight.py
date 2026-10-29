"""Check that this machine is ready to run the publication experiments.

pub_run_all.ps1 runs this automatically before any run starts and stops if a check FAILs.
Checks: Python and packages, GPU, run/.env, BIRD dev data, the few-shot demonstration file,
the pipeline code (compared with the smoke-tested version), free disk space, leftover experiment
switches, and optionally one tiny API call.

Usage:
  python -m pub.preflight           # all offline checks
  python -m pub.preflight --api     # also make one tiny API call (costs a fraction of a cent)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

from pub.common import BIRD_DEV_ROOT, RUN_DIR
from pub.fingerprint import REFERENCE, compute, differences

EXPECTED_MODEL = "deepseek/deepseek-v4-flash"
DEMO_FILE = RUN_DIR / "pub_inputs" / "bird_train_demos_from_v18.json"
DEMO_SHA256 = "ad8df1606fcaf6c2b4b0433af1434888550d9636b857b481b55604f216db7485"
DEMO_RECORDS = 1805
BIRD_DATABASES = {
    "california_schools", "card_games", "codebase_community", "debit_card_specializing", "european_football_2",
    "financial", "formula_1", "student_club", "superhero", "thrombosis_prediction", "toxicology",
}
PACKAGES = ("torch", "sentence_transformers", "faiss", "openai", "rank_bm25", "sqlglot", "tiktoken",
            "pandas", "numpy", "scipy", "matplotlib", "dotenv", "func_timeout", "tqdm")
EXPERIMENT_KEYS = ("ABLATION_NO_RBP", "ABLATION_NO_ITEE", "ABLATION_NO_BM25", "ABLATION_NO_QOC",
                   "ABLATION_ITEE_THRESHOLD", "ABLATION_RBP_ALPHA", "SLAYQL_TOP_N")
MIN_FREE_GB = 20

Result = Tuple[str, str, str]


def _read_env_file(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def run_checks(api: bool) -> List[Result]:
    results: List[Result] = []

    def add(name: str, status: str, detail: str = "") -> None:
        results.append((name, status, detail))

    version = sys.version_info
    add("Python >= 3.10", "PASS" if version >= (3, 10) else "FAIL", sys.version.split()[0])
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    add("Running inside the project .venv", "PASS" if in_venv else "WARN", sys.executable)

    missing = []
    for package in PACKAGES:
        try:
            importlib.import_module(package)
        except Exception as exc:  # noqa: BLE001 - report any import failure
            missing.append(f"{package} ({type(exc).__name__})")
    add("Required packages import", "FAIL" if missing else "PASS", ", ".join(missing) or f"{len(PACKAGES)} packages")

    try:
        import torch
        cuda = torch.cuda.is_available()
        add("GPU for embeddings", "PASS" if cuda else "WARN",
            torch.cuda.get_device_name(0) if cuda else "no CUDA GPU: embeddings run on CPU (slower, still correct)")
    except Exception as exc:  # noqa: BLE001
        add("GPU for embeddings", "WARN", f"torch unavailable: {exc}")

    env_path = RUN_DIR / ".env"
    if not env_path.exists():
        add("run/.env exists", "FAIL", "create run/.env with OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME")
        env = {}
    else:
        env = _read_env_file(env_path)
        missing_keys = [key for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL_NAME") if not env.get(key)]
        add("run/.env has the three keys", "FAIL" if missing_keys else "PASS", ", ".join(missing_keys) or "ok")
        model = env.get("MODEL_NAME", "")
        add(f"MODEL_NAME is {EXPECTED_MODEL}", "PASS" if model == EXPECTED_MODEL else "FAIL",
            f"found '{model}'; all runs must use the same model")

    dev_json = BIRD_DEV_ROOT / "dev.json"
    if dev_json.exists():
        count = len(json.loads(dev_json.read_text(encoding="utf-8")))
        add("BIRD dev.json has 1534 questions", "PASS" if count == 1534 else "FAIL", f"{count} questions")
    else:
        add("BIRD dev.json has 1534 questions", "FAIL", f"missing {dev_json}")
    add("BIRD dev_tables.json present", "PASS" if (BIRD_DEV_ROOT / "dev_tables.json").exists() else "FAIL")
    found = {path.stem for path in (BIRD_DEV_ROOT / "dev_databases").rglob("*.sqlite")} if (BIRD_DEV_ROOT / "dev_databases").exists() else set()
    missing_dbs = sorted(BIRD_DATABASES - found)
    add("BIRD dev SQLite databases (11)", "FAIL" if missing_dbs else "PASS",
        f"missing: {', '.join(missing_dbs)} (run pub_setup.ps1 to extract dev_databases.zip)" if missing_dbs else "all 11 found")

    if DEMO_FILE.exists():
        digest = hashlib.sha256(DEMO_FILE.read_bytes()).hexdigest()
        records = len(json.loads(DEMO_FILE.read_text(encoding="utf-8")))
        ok = digest == DEMO_SHA256 and records == DEMO_RECORDS
        add("Few-shot demonstration file", "PASS" if ok else "FAIL",
            f"{records} records, sha256 {digest[:12]} (expected {DEMO_RECORDS}, {DEMO_SHA256[:12]})")
    else:
        add("Few-shot demonstration file", "FAIL", f"missing {DEMO_FILE}")

    current = compute()
    if REFERENCE.exists():
        reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        if reference["fingerprint"] == current["fingerprint"]:
            add("Pipeline code matches the smoke-tested version", "PASS", current["fingerprint"][:12])
        else:
            diff = differences(reference["files"], current["files"])
            add("Pipeline code matches the smoke-tested version", "WARN",
                f"current {current['fingerprint'][:12]} vs tested {reference['fingerprint'][:12]}; changed: "
                + ", ".join(diff["changed"] + diff["only_in_second"]) or "files removed")
    else:
        add("Pipeline code matches the smoke-tested version", "WARN", f"no reference file {REFERENCE.name}")

    free_gb = shutil.disk_usage(RUN_DIR).free / 1024 ** 3
    add(f"Free disk space >= {MIN_FREE_GB} GB", "PASS" if free_gb >= MIN_FREE_GB else "WARN", f"{free_gb:.0f} GB free")

    leftover = [key for key in EXPERIMENT_KEYS if os.environ.get(key)]
    add("No leftover experiment switches in this shell", "WARN" if leftover else "PASS",
        ("set: " + ", ".join(leftover) + " (pub_run_all.ps1 clears them)") if leftover else "none")

    if api:
        if not env.get("OPENAI_API_KEY"):
            add("API reachable", "FAIL", "no key")
        else:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=env["OPENAI_API_KEY"], base_url=env.get("OPENAI_BASE_URL"), timeout=60)
                response = client.chat.completions.create(model=env.get("MODEL_NAME"), max_tokens=20,
                                                          messages=[{"role": "user", "content": "Reply OK."}])
                add("API reachable", "PASS", f"model {getattr(response, 'model', env.get('MODEL_NAME'))}")
            except Exception as exc:  # noqa: BLE001
                add("API reachable", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", action="store_true", help="Also make one tiny API call")
    args = parser.parse_args()
    results = run_checks(args.api)
    width = max(len(name) for name, _, _ in results)
    for name, status, detail in results:
        print(f"[{status:4}] {name.ljust(width)}  {detail}")
    failures = sum(status == "FAIL" for _, status, _ in results)
    warnings = sum(status == "WARN" for _, status, _ in results)
    print(f"\nPreflight: {failures} FAIL, {warnings} WARN")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

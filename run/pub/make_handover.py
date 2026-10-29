"""Build the package a teammate needs to run the publication experiments on their own machine.

Contents: the pipeline and analysis code, the runner and setup scripts, the documentation,
the few-shot demonstration file and code fingerprint reference, requirements.txt, and BIRD dev
(questions, schemas, gold SQL and the compressed databases). The API key (run/.env) is never
included; a template (run/.env.example) is added instead.

Usage:
  python -m pub.make_handover                       # writes slayql_pub_handover_<date>.zip next to the repo
"""

from __future__ import annotations

import argparse
import time
import zipfile
from pathlib import Path

from pub.common import BIRD_DEV_ROOT, REPO_ROOT, RUN_DIR

RUN_FILES = ("pub_run_all.ps1", "pub_setup.ps1", "PUBLICATION_RUNBOOK.md", "TEAMMATE_QUICKSTART.md")
REPO_FILES = ("requirements.txt", "SLAYQL_PUBLICATION_PLAN_ARR_OCT2026.md")
BIRD_FILES = ("dev.json", "dev.sql", "dev_tables.json", "dev_tied_append.json", "dev_databases.zip")
ENV_TEMPLATE = """# Copy this file to .env (same folder) and fill in the key. Never commit or share .env.
OPENAI_API_KEY=<your OpenRouter key>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=deepseek/deepseek-v4-flash
"""


def build(output: Path) -> Path:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        def add(path: Path) -> None:
            archive.write(path, path.relative_to(REPO_ROOT).as_posix())

        for path in sorted(RUN_DIR.glob("*.py")):
            add(path)
        for folder in ("pub", "config", "pub_inputs"):
            for path in sorted((RUN_DIR / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    add(path)
        for name in RUN_FILES:
            if (RUN_DIR / name).exists():
                add(RUN_DIR / name)
        for name in REPO_FILES:
            if (REPO_ROOT / name).exists():
                add(REPO_ROOT / name)
        for name in BIRD_FILES:
            path = BIRD_DEV_ROOT / name
            if path.exists():
                add(path)
            else:
                print(f"WARNING: {path} not found; the teammate will need it")
        archive.writestr("run/.env.example", ENV_TEMPLATE)
        if (RUN_DIR / "TEAMMATE_QUICKSTART.md").exists():
            archive.write(RUN_DIR / "TEAMMATE_QUICKSTART.md", "README_FIRST.md")
    names = zipfile.ZipFile(output).namelist()
    assert not any(name.endswith("/.env") or name == ".env" for name in names), "API key must not be packaged"
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=REPO_ROOT.parent / f"slayql_pub_handover_{time.strftime('%Y%m%d')}.zip")
    args = parser.parse_args()
    output = build(args.output)
    print(f"Wrote {output} ({output.stat().st_size / 1024 ** 2:.0f} MB). No API key is included.")


if __name__ == "__main__":
    main()

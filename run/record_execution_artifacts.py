import argparse
import re
from pathlib import Path

import pandas as pd

from artifact_store import write_instance_artifact


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
)


def sanitize_error(message, max_chars=2000):
    value = str(message)
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(
            lambda match: (
                re.split(r"[=:]", match.group(0), maxsplit=1)[0].strip() + "=<redacted>"
                if re.search(r"[=:]", match.group(0))
                else "Bearer <redacted>"
            ),
            value,
        )
    return value[:max_chars]


def _candidate_id(directory):
    match = re.search(r"_(\d+)$", directory.name)
    return int(match.group(1)) if match else 0


def record(execution_root, artifact_root, max_error_chars=2000):
    execution_root = Path(execution_root)
    result_dirs = list(execution_root.glob("*_execution_result_*"))
    for result_dir in result_dirs:
        candidate_id = _candidate_id(result_dir)
        error_dir = Path(str(result_dir).replace("_execution_result_", "_execution_error_"))
        instance_ids = {path.stem for path in result_dir.glob("*.csv")}
        instance_ids.update(path.stem for path in error_dir.glob("*.txt"))
        instance_ids.update(path.stem for path in error_dir.glob("*.error"))
        for instance_id in instance_ids:
            csv_path = result_dir / f"{instance_id}.csv"
            error_paths = [
                error_dir / f"{instance_id}.txt",
                error_dir / f"{instance_id}.error",
                error_dir / f"{instance_id}.err",
            ]
            error_path = next((candidate for candidate in error_paths if candidate.exists()), None)
            record_data = {
                "instance_id": instance_id,
                "candidate_id": candidate_id,
                "status": "success" if csv_path.exists() and error_path is None else "error",
                "csv_path": str(csv_path) if csv_path.exists() else None,
                "error": None,
                "result_shape": None,
            }
            if csv_path.exists():
                try:
                    frame = pd.read_csv(csv_path)
                    record_data["result_shape"] = [int(frame.shape[0]), int(frame.shape[1])]
                    record_data["columns"] = [str(column) for column in frame.columns]
                except Exception as exc:
                    record_data["status"] = "artifact_read_error"
                    record_data["error"] = sanitize_error(exc, max_error_chars)
            if error_path:
                record_data["error"] = sanitize_error(
                    error_path.read_text(encoding="utf-8", errors="replace"), max_error_chars
                )
            write_instance_artifact(
                artifact_root,
                f"execution/candidate_{candidate_id}",
                instance_id,
                record_data,
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution_root", required=True)
    parser.add_argument("--artifact_root", required=True)
    parser.add_argument("--max_error_chars", type=int, default=2000)
    args = parser.parse_args()
    record(**vars(args))


if __name__ == "__main__":
    main()

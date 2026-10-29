"""Provider-first OpenRouter usage accounting for pipeline model calls."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_LOCK = threading.Lock()


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return _plain(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return _plain(value.to_dict())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {str(key): _plain(item) for key, item in vars(value).items() if not str(key).startswith("_")}
    return str(value)


def record_response_usage(
    response: Any,
    *,
    stage: str,
    instance_id: Optional[str] = None,
    candidate_id: Optional[int] = None,
    attempt: Optional[int] = None,
    latency_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """Persist the provider usage object without storing prompts or secrets."""

    usage = _plain(getattr(response, "usage", None))
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "instance_id": instance_id,
        "candidate_id": candidate_id,
        "attempt": attempt,
        "latency_ms": latency_ms,
        "response_id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "usage": usage,
        "usage_status": "provider" if isinstance(usage, dict) and usage else "provider_usage_missing",
    }
    usage_dir = os.environ.get("SLAYQL_USAGE_DIR")
    if usage_dir:
        path = Path(usage_dir)
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"{instance_id or 'run'}.jsonl"
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with _LOCK:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
    return record

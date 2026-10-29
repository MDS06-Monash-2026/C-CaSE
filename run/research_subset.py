"""Deterministic, diverse subset construction for SlayQL v1.2 research runs."""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from artifact_store import atomic_write_json


def difficulty_score(item: Dict[str, Any]) -> float:
    question = str(item.get("question", ""))
    lowered = question.lower()
    score = min(1.0, len(question.split()) / 45.0)
    score += 0.12 * sum(bool(re.search(pattern, lowered)) for pattern in (
        r"\b(each|per|every)\b", r"\b(join|related|matching)\b",
        r"\b(top|bottom|highest|lowest|rank|percent|percentage)\b",
        r"\b(except|without|not|excluding)\b", r"\b(before|after|between|year|month)\b",
        r"\b(consecutive|streak|difference|growth|change)\b",
    ))
    sql = str(item.get("gold_sql") or "")
    score += min(0.5, 0.04 * sql.lower().count(" join "))
    score += min(0.4, 0.03 * sql.lower().count("select"))
    score += min(0.2, 0.04 * sql.lower().count("group by"))
    return min(1.0, score)


def _round_robin(candidates: Sequence[str], records: Dict[str, Dict[str, Any]], count: int, seed: int) -> List[str]:
    groups: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for instance_id in candidates:
        item = records[instance_id]
        key = (str(item.get("backend", "unknown")), str(item.get("db_name", "unknown")))
        groups[key].append(instance_id)
    rng = random.Random(seed)
    queues = []
    for key in sorted(groups):
        values = list(groups[key])
        rng.shuffle(values)
        queues.append(values)
    selected: List[str] = []
    while queues and len(selected) < count:
        next_queues = []
        for queue in queues:
            if queue and len(selected) < count:
                selected.append(queue.pop())
            if queue:
                next_queues.append(queue)
        queues = next_queues
    return selected


def select_subset(
    records: Dict[str, Dict[str, Any]],
    mode: str,
    seed: int = 20260813,
    smoke_count: int = 5,
    excluded_backends: Optional[Iterable[str]] = None,
    reference_evaluation: Optional[str] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    excluded = {str(value).lower() for value in (excluded_backends or [])}
    eligible = sorted(
        instance_id for instance_id, item in records.items()
        if str(item.get("backend", "")).lower() not in excluded
    )
    if not eligible:
        raise ValueError(f"No records remain after excluding backends: {sorted(excluded)}")
    scores = {instance_id: difficulty_score(records[instance_id]) for instance_id in eligible}
    reference = {}
    if reference_evaluation and Path(reference_evaluation).exists():
        try:
            payload = json.loads(Path(reference_evaluation).read_text(encoding="utf-8"))
            def as_bool(value: Any) -> Optional[bool]:
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return bool(value)
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "1", "yes"}:
                        return True
                    if lowered in {"false", "0", "no"}:
                        return False
                return None

            reference = {
                str(row.get("instance_id")): parsed
                for row in payload.get("instances", []) if isinstance(row, dict)
                and row.get("instance_id") is not None
                and (parsed := as_bool(row.get("correct"))) is not None
            } if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError):
            reference = {}

    if mode == "full":
        selected_ids = eligible
        policy = "all_eligible_records"
    elif mode == "smoke":
        selected_ids = _round_robin(eligible, records, min(smoke_count, len(eligible)), seed)
        policy = "backend_database_round_robin"
    elif mode == "subset20":
        target = min(len(eligible), max(1, int(round(len(eligible) * 0.2))))
        easy_target = max(1, int(round(target * 0.2))) if target > 1 else target
        hard_target = target - easy_target
        if reference:
            easy_pool = [iid for iid in eligible if reference.get(iid) is True]
            hard_pool = [iid for iid in eligible if reference.get(iid) is False]
            policy = "reference_correctness_20_hard_80"
        else:
            ranked = sorted(eligible, key=lambda iid: (scores[iid], iid))
            easy_pool = ranked
            hard_pool = list(reversed(ranked))
            policy = "difficulty_proxy_20_easy_80_hard"
        easy = _round_robin(easy_pool, records, min(easy_target, len(easy_pool)), seed)
        used = set(easy)
        hard = _round_robin([iid for iid in hard_pool if iid not in used], records, hard_target, seed + 1)
        selected_ids = easy + [iid for iid in hard if iid not in used]
        if len(selected_ids) < target:
            remainder = [iid for iid in eligible if iid not in set(selected_ids)]
            selected_ids.extend(_round_robin(remainder, records, target - len(selected_ids), seed + 2))
        selected_ids = selected_ids[:target]
    else:
        raise ValueError(f"Unknown run mode: {mode}")

    selected_ids = sorted(dict.fromkeys(selected_ids))
    known_correct = sum(reference.get(iid) is True for iid in selected_ids)
    manifest = {
        "schema_version": "1.2",
        "mode": mode,
        "seed": seed,
        "smoke_count": smoke_count,
        "excluded_backends": sorted(excluded),
        "record_count": len(selected_ids),
        "source_record_count": len(eligible),
        "instance_ids": selected_ids,
        "selection_policy": policy,
        "target_easy_or_known_correct_fraction": 0.2 if mode == "subset20" else None,
        "target_hard_or_known_incorrect_fraction": 0.8 if mode == "subset20" else None,
        "reference_evaluation": str(Path(reference_evaluation).resolve()) if reference_evaluation else None,
        "known_correct_fraction": known_correct / len(selected_ids) if selected_ids else 0.0,
        "difficulty": {
            iid: round(scores[iid], 4) for iid in selected_ids
        },
    }
    return {iid: records[iid] for iid in selected_ids}, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic SlayQL v1.2 research subset")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--mode", choices=("smoke", "subset20", "full"), default="subset20")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--smoke-count", type=int, default=5)
    parser.add_argument("--exclude-backend", action="append", default=[])
    parser.add_argument("--reference-evaluation")
    args = parser.parse_args()
    records = json.loads(Path(args.input).read_text(encoding="utf-8"))
    selected, manifest = select_subset(records, args.mode, args.seed, args.smoke_count, args.exclude_backend, args.reference_evaluation)
    atomic_write_json(args.output, selected)
    atomic_write_json(args.manifest, manifest)
    print(f"Research subset ready: {len(selected)} records ({manifest['selection_policy']})", flush=True)


if __name__ == "__main__":
    main()

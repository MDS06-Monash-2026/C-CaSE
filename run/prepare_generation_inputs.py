import argparse
import json
from pathlib import Path

from artifact_store import atomic_write_json, atomic_write_text, load_config
from pipeline_types import QueryContract


def _instance_id(item):
    return item.get("instance_id") or item.get("id")


def _load_contract(item, contract_dir):
    path = item.get("contract_path")
    if not path:
        path = Path(contract_dir) / f"{_instance_id(item)}.json"
    path = Path(path)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return QueryContract.from_dict(json.load(handle))


def _compact_contract(contract):
    payload = contract.to_dict()
    keep = (
        "required_tables",
        "required_columns",
        "required_operations",
        "required_filters",
        "forbidden_patterns",
        "output_shape",
        "invariants",
    )
    return {key: payload[key] for key in keep if payload.get(key)}


def _validated_draft(contract):
    draft = getattr(contract, "validated_draft", None)
    if not draft:
        return None
    if hasattr(draft, "to_dict"):
        draft = draft.to_dict()
    if draft.get("status") not in {"success", "validated"}:
        return None
    path = draft.get("sql_path") or draft.get("path")
    return Path(path) if path else None


def prepare(input_path, output_root, contract_dir, generation_root):
    config = load_config()
    with open(input_path, encoding="utf-8") as handle:
        rows = json.load(handle)

    partitions = {"easy": [], "medium": [], "hard": []}
    manifest = []
    for item in rows:
        instance_id = _instance_id(item)
        contract = _load_contract(item, contract_dir)
        mode = item.get("operating_mode", "medium")
        candidate_count = int(config["generation"]["candidates_by_mode"][mode])
        prepared = dict(item)
        if contract:
            prepared["query_contract"] = _compact_contract(contract)
            prepared["question"] = (
                f"{item.get('question', '')}\n"
                f"QUERY_CONTRACT={json.dumps(prepared['query_contract'], separators=(',', ':'))}"
            )
            draft_path = _validated_draft(contract)
            if draft_path and draft_path.exists():
                target = Path(generation_root) / "task_sql_0" / f"{instance_id}.sql"
                atomic_write_text(target, draft_path.read_text(encoding="utf-8"))
                prepared["validated_draft_reused"] = True
        partitions[mode].append(prepared)
        manifest.append(
            {
                "instance_id": instance_id,
                "operating_mode": mode,
                "candidate_count": candidate_count,
                "validated_draft_reused": prepared.get("validated_draft_reused", False),
            }
        )

    output_root = Path(output_root)
    for mode, items in partitions.items():
        atomic_write_json(output_root / f"{mode}.json", items)
    atomic_write_json(output_root / "generation_manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output_root", required=True)
    parser.add_argument("--contract_dir", required=True)
    parser.add_argument("--generation_root", required=True)
    args = parser.parse_args()
    prepare(**vars(args))


if __name__ == "__main__":
    main()

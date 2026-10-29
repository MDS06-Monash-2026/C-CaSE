import argparse
import json
from pathlib import Path

from artifact_store import atomic_write_text


MARKER = "\n-- SLAYQL_QUERY_CONTRACT_V1 --\n"


def _compact_contract(contract):
    keys = (
        "dialect",
        "required_tables",
        "required_columns",
        "joins",
        "filters",
        "operations",
        "grouping_grain",
        "output_columns",
        "required_invariants",
        "forbidden_assumptions",
        "forbidden_sql_patterns",
        "operating_mode",
    )
    return {key: contract[key] for key in keys if contract.get(key)}


def augment(prompt_dir, contract_dir):
    prompt_dir = Path(prompt_dir)
    contract_dir = Path(contract_dir)
    augmented = 0
    for contract_path in sorted(contract_dir.glob("*.json")):
        prompt_path = prompt_dir / f"{contract_path.stem}.txt"
        if not prompt_path.exists():
            continue
        content = prompt_path.read_text(encoding="utf-8")
        if MARKER in content:
            continue
        with contract_path.open(encoding="utf-8") as handle:
            contract = _compact_contract(json.load(handle))
        addition = (
            MARKER
            + "Treat this compact contract as required query semantics. Do not invent filters "
            + "or joins that conflict with it.\n"
            + json.dumps(contract, ensure_ascii=True, separators=(",", ":"))
            + "\n"
        )
        atomic_write_text(prompt_path, content.rstrip() + "\n" + addition)
        augmented += 1
    print(f"Augmented {augmented} schema prompts")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt_dir", required=True)
    parser.add_argument("--contract_dir", required=True)
    args = parser.parse_args()
    augment(args.prompt_dir, args.contract_dir)


if __name__ == "__main__":
    main()

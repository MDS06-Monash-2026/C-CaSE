import argparse
import json

from artifact_store import atomic_write_json, load_config, write_instance_artifact
from pipeline_types import derive_contract
from relationship_metadata import build_relationship_metadata


def _score(result):
    return float(result.get("score", result.get("similarity", -result.get("distance", 0.0))))


def focus_results(results, config):
    """Limit ranked records while keeping several columns from each relevant table."""
    limits = config["retrieval"]
    table_scores = {}
    for result in results:
        table = result.get("table") or result.get("table_name")
        if table:
            table_scores[table] = max(table_scores.get(table, float("-inf")), _score(result))
    selected_tables = {
        table
        for table, _ in sorted(table_scores.items(), key=lambda pair: pair[1], reverse=True)[
            : limits["max_tables"]
        ]
    }
    counts = {table: 0 for table in selected_tables}
    focused = []
    for result in sorted(results, key=_score, reverse=True):
        table = result.get("table") or result.get("table_name")
        if table not in selected_tables or counts[table] >= limits["max_columns_per_table"]:
            continue
        focused.append(result)
        counts[table] += 1
        if len(focused) >= limits["max_prompt_columns"]:
            break
    return focused


def _candidate_records(item):
    fields = (
        "column_candidates",
        "column_types",
        "column_values",
        "table_candidates",
        "descriptions",
    )
    values = [item.get(field, []) for field in fields]
    size = min((len(value) for value in values), default=0)
    return [
        {
            "column": values[0][index],
            "column_type": values[1][index],
            "column_value": values[2][index],
            "table": values[3][index],
            "description": values[4][index],
            "score": float(size - index),
        }
        for index in range(size)
    ]


def _apply_records(item, records):
    enriched = dict(item)
    enriched["column_candidates"] = [record["column"] for record in records]
    enriched["column_types"] = [record["column_type"] for record in records]
    enriched["column_values"] = [record["column_value"] for record in records]
    enriched["table_candidates"] = [record["table"] for record in records]
    enriched["descriptions"] = [record["description"] for record in records]
    enriched["retrieved_count"] = len(records)
    return enriched


def choose_mode(question, results, relationships):
    tables = {result.get("table") for result in results if result.get("table")}
    normalized = f" {question.lower()} "
    structural = (
        " join ", " each ", " per ", " except ", " versus ", " compared ",
        " highest ", " lowest ", " top ", " rank ", " before ", " after ",
    )
    graph_edges = relationships.get("graph_stats", {}).get("edges", 0)
    hard = (
        (len(tables) > 1 and graph_edges == 0)
        or len(tables) >= 4
        or any(term in normalized for term in structural)
    )
    if hard:
        return "hard"
    if len(tables) > 1 or len(question.split()) > 22:
        return "medium"
    return "easy"


def _turn_limit(mode, config):
    return int(config["completion"][f"{mode}_max_turns"])


def prepare(input_path, output_path, artifact_root, base_dir="."):
    config = load_config()
    with open(input_path, encoding="utf-8") as handle:
        source = json.load(handle)
    if not isinstance(source, dict):
        raise ValueError("Expected retrieval output keyed by Spider 2.0 instance ID")

    prepared = {}
    for instance_id, item in source.items():
        records = focus_results(_candidate_records(item), config)
        selected_tables = list(dict.fromkeys(record["table"] for record in records))
        relationships = build_relationship_metadata(
            instance_id=instance_id,
            db_name=item.get("db_name", ""),
            base_dir=base_dir,
            selected_tables=selected_tables,
        )
        mode = choose_mode(item.get("question", ""), records, relationships)
        turns = _turn_limit(mode, config)
        enriched = _apply_records(item, records)
        enriched["relationship_metadata"] = relationships
        enriched["operating_mode"] = mode
        enriched["dynamic_t_max"] = turns

        contract = derive_contract(
            instance_id=instance_id,
            question=item.get("question", ""),
            db_name=item.get("db_name", ""),
            retrieved_tables=selected_tables,
            retrieved_columns=list(dict.fromkeys(record["column"] for record in records)),
            operating_mode=mode,
        )
        contract.joins = [
            {"left_table": edge[0], "left_column": edge[1], "right_table": edge[2], "right_column": edge[3]}
            for edge in relationships.get("foreign_keys", [])
            if len(edge) >= 4
        ]
        contract_path = write_instance_artifact(
            artifact_root, "contracts", instance_id, contract.to_dict()
        )
        enriched["contract_path"] = contract_path
        write_instance_artifact(
            artifact_root,
            "retrieval",
            instance_id,
            {
                "operating_mode": mode,
                "dynamic_t_max": turns,
                "relationship_metadata": relationships,
                "selected_tables": selected_tables,
                "selected_columns": enriched["column_candidates"],
            },
        )
        prepared[instance_id] = enriched

    atomic_write_json(output_path, prepared)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifact_root", required=True)
    parser.add_argument("--base_dir", default=".")
    args = parser.parse_args()
    prepare(args.input, args.output, args.artifact_root, args.base_dir)


if __name__ == "__main__":
    main()

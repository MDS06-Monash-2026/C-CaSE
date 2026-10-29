import json
import sqlite3
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

import dataset_pipeline
import selector_first
from evaluate_dataset import _local_frames_match, _metric_sets, run as evaluate_run
from selector_first import (
    _candidate_structure,
    _question_contract,
    run_offline_replay,
    select_instance,
)
from usage_accounting import record_response_usage


def _records(count=20):
    return {
        f"bq{index:03d}": {"backend": "bigquery", "question": f"Question {index}"}
        for index in range(count)
    }


def test_smoke_and_subset_selection_are_deterministic():
    records = _records(50)
    assert dataset_pipeline.deterministic_ids(records, "smoke", 7) == sorted(records)[:5]
    first = dataset_pipeline.deterministic_ids(records, "subset20", 7)
    second = dataset_pipeline.deterministic_ids(records, "subset20", 7)
    assert first == second
    assert len(first) == 10


def test_smoke_count_and_backend_exclusion_are_explicit_and_deterministic():
    records = {
        "sf001": {"backend": "snowflake"},
        "sf002": {"backend": "snowflake"},
        "bq001": {"backend": "bigquery"},
        "bq002": {"backend": "bigquery"},
        "local001": {"backend": "sqlite"},
        "local002": {"backend": "sqlite"},
    }
    selected = dataset_pipeline.deterministic_ids(
        records, "smoke", 7, smoke_count=3, excluded_backends=["snowflake"]
    )
    assert selected == ["bq001", "bq002", "local001"]
    assert all(records[instance_id]["backend"] != "snowflake" for instance_id in selected)
    assert {records[instance_id]["backend"] for instance_id in selected} == {"bigquery", "sqlite"}


def test_backend_smoke_selects_three_per_available_backend():
    records = {}
    for backend, prefix in (("snowflake", "sf"), ("bigquery", "bq"), ("sqlite", "local")):
        records.update({f"{prefix}{index:03d}": {"backend": backend} for index in range(5)})
    selected = dataset_pipeline.deterministic_ids(records, "backend-smoke", 1)
    assert len(selected) == 9
    assert {records[instance_id]["backend"] for instance_id in selected} == {"snowflake", "bigquery", "sqlite"}


def test_existing_diverse_subset_is_preserved_whole(tmp_path):
    records = _records(17)
    source = {"source_files": [str(tmp_path / "subset_diverse_20_evaluation.json")]}
    manifest = dataset_pipeline.make_run_manifest(
        "spider2-lite", "dev", "subset20", records, source, tmp_path / "run", 9
    )
    assert manifest["record_count"] == len(records)
    assert set(json.loads((tmp_path / "run" / "dataset.json").read_text())) == set(records)


def test_existing_diverse_subset_honors_backend_exclusion(tmp_path):
    records = {
        "sf001": {"backend": "snowflake"},
        "bq001": {"backend": "bigquery"},
        "local001": {"backend": "sqlite"},
    }
    source = {"source_files": [str(tmp_path / "subset_diverse_20_evaluation.json")]}
    manifest = dataset_pipeline.make_run_manifest(
        "spider2-lite", "dev", "subset20", records, source, tmp_path / "run", 9,
        excluded_backends=["snowflake"],
    )
    assert manifest["instance_ids"] == ["bq001", "local001"]
    assert manifest["excluded_backends"] == ["snowflake"]


def test_bird_root_is_listed_and_confirmed(tmp_path, monkeypatch, capsys):
    (tmp_path / "train.json").write_text("[]", encoding="utf-8")
    answers = iter((str(tmp_path), "yes"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert dataset_pipeline._prompt_bird_root() == tmp_path.resolve()
    output = capsys.readouterr().out
    assert "BIRD directory listing" in output
    assert "train.json" in output


def test_bird_normalization_indexes_sqlite_paths_once(tmp_path, monkeypatch):
    database_root = tmp_path / "train_databases" / "train_databases" / "demo"
    database_root.mkdir(parents=True)
    database_path = database_root / "demo.sqlite"
    sqlite3.connect(database_path).close()
    (tmp_path / "train.json").write_text(json.dumps([
        {"question_id": 1, "db_id": "demo", "question": "First"},
        {"question_id": 2, "db_id": "demo", "question": "Second"},
    ]), encoding="utf-8")
    calls = []
    original = dataset_pipeline._index_sqlite_databases

    def counted(root):
        calls.append(root)
        return original(root)

    monkeypatch.setattr(dataset_pipeline, "_index_sqlite_databases", counted)
    records, manifest = dataset_pipeline._normalize_bird("train", tmp_path)
    assert len(calls) == 1
    assert len(records) == 2
    assert {item["db_path"] for item in records.values()} == {str(database_path.resolve())}
    assert manifest["database_root"].endswith("train_databases")


def test_spider1_test_uses_test_database_root(tmp_path, monkeypatch):
    root = tmp_path / "spider_data" / "spider_data"
    source = root / "test.json"
    database_root = root / "test_database" / "demo"
    database_root.mkdir(parents=True)
    sqlite_path = database_root / "demo.sqlite"
    sqlite3.connect(sqlite_path).close()
    source.write_text(json.dumps([{
        "db_id": "demo", "question": "How many rows?", "query": "SELECT 1"
    }]), encoding="utf-8")
    monkeypatch.setattr(dataset_pipeline, "REPO_ROOT", tmp_path)
    records, manifest = dataset_pipeline._normalize_spider1("test")
    assert records["local_spider1_test_00000"]["db_path"] == str(sqlite_path.resolve())
    assert manifest["database_root"].endswith("test_database")


def test_large_unordered_result_matching_is_scalable_and_tolerant():
    base = pd.DataFrame({"value": [1.0, 2.0, 2.0], "label": [" A ", "B", "B"]})
    predicted = pd.concat([base] * 4_000, ignore_index=True)
    gold = predicted.sample(frac=1, random_state=7).reset_index(drop=True)
    gold["value"] = gold["value"] + 0.005
    gold.columns = ["other_value", "other_label"]
    assert _local_frames_match(predicted, gold)
    gold.loc[0, "other_label"] = "different"
    assert not _local_frames_match(predicted, gold)


def test_full_gate_requires_same_config_completed_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_pipeline, "RUN_DIR", tmp_path)
    manifest = {"dataset": "spider1", "split": "dev", "mode": "full", "config_hash": "same", "source_hash": "source"}
    with pytest.raises(RuntimeError, match="smoke"):
        dataset_pipeline.enforce_run_gates(manifest)
    for mode in ("smoke", "backend-smoke", "subset20"):
        run_root = tmp_path / mode
        (run_root / "aggregates").mkdir(parents=True)
        (run_root / "aggregates" / "summary_metrics.json").write_text("{}", encoding="utf-8")
        (run_root / "run_manifest.json").write_text(json.dumps({
            "dataset": "spider1", "split": "dev", "mode": mode,
            "config_hash": "same", "source_hash": "source", "status": "complete",
        }), encoding="utf-8")
    dataset_pipeline.enforce_run_gates(manifest)


@pytest.mark.parametrize("dataset", ("bird", "spider1", "spider2-lite"))
@pytest.mark.parametrize("mode", ("smoke", "subset20", "full"))
def test_parser_accepts_all_nine_standalone_combinations(dataset, mode):
    args = dataset_pipeline.build_parser().parse_args([
        "run", "--dataset", dataset, "--mode", mode,
    ])
    assert args.dataset == dataset
    assert args.mode == mode
    assert not args.enforce_gates


def test_parser_accepts_custom_smoke_count_and_backend_exclusion():
    args = dataset_pipeline.build_parser().parse_args([
        "run", "--dataset", "spider2-lite", "--mode", "smoke",
        "--smoke-count", "3", "--exclude-backend", "snowflake",
    ])
    assert args.smoke_count == 3
    assert args.exclude_backend == ["snowflake"]


def test_standalone_run_does_not_enforce_prerequisite_gates(tmp_path, monkeypatch):
    manifest = {"dataset": "spider1", "split": "dev", "mode": "full", "status": "prepared"}
    records = {"local_1": {}}
    args = Namespace(enforce_gates=False, num_candidates=5, workers=1)
    monkeypatch.setattr(dataset_pipeline, "prepare_run", lambda _args: tmp_path)
    monkeypatch.setattr(dataset_pipeline, "load_run", lambda _root: (manifest, records))
    monkeypatch.setattr(dataset_pipeline, "enforce_run_gates", lambda _manifest: pytest.fail("gates should be optional"))
    monkeypatch.setattr(dataset_pipeline, "run_inference", lambda *_args: None)
    monkeypatch.setattr(dataset_pipeline, "write_integrity_reports", lambda *_args: None)
    dataset_pipeline.cli_run(args)
    saved = json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert saved["status"] == "complete"


def test_enforce_gates_flag_uses_strict_sequence(tmp_path, monkeypatch):
    manifest = {"dataset": "spider1", "split": "dev", "mode": "full", "status": "prepared"}
    args = Namespace(enforce_gates=True, num_candidates=5, workers=1)
    called = []
    monkeypatch.setattr(dataset_pipeline, "prepare_run", lambda _args: tmp_path)
    monkeypatch.setattr(dataset_pipeline, "load_run", lambda _root: (manifest, {}))
    monkeypatch.setattr(dataset_pipeline, "enforce_run_gates", lambda value: called.append(value))
    monkeypatch.setattr(dataset_pipeline, "run_inference", lambda *_args: None)
    monkeypatch.setattr(dataset_pipeline, "write_integrity_reports", lambda *_args: None)
    dataset_pipeline.cli_run(args)
    assert called == [manifest]


def test_corrupt_completed_stage_is_invalidated(tmp_path):
    records = {"local_1": {}}
    dataset_pipeline.mark_stage(tmp_path, "selector_first")
    assert not dataset_pipeline.stage_checkpoint_is_valid(tmp_path, "selector_first", records, 5)
    checkpoint = dataset_pipeline.load_checkpoint(tmp_path)
    assert checkpoint["stages"]["selector_first"]["status"] == "invalid"


def test_selector_deduplicates_without_dropping_unique_candidates(monkeypatch):
    monkeypatch.setenv("SLAYQL_SELECTOR_VERIFY", "0")
    frame = pd.DataFrame({"count": [2]})
    candidates = []
    for candidate_id, sql in enumerate((
        "SELECT COUNT(*) FROM people", "SELECT COUNT(*) FROM people", "SELECT name FROM people"
    )):
        candidates.append({
            "candidate_id": candidate_id, "sql": sql, "source": "generated", "frame": frame,
            "error": None, "executed": True, "parseable": True,
            "canonical_sql": sql.lower(), "references": {"tables": ["people"], "columns": []},
            "result_hash": "same" if candidate_id < 2 else "different", "value_evidence": [],
        })
    result = select_instance("local_test", candidates, "How many people are there?")
    assert result["selected"]["candidate_id"] == 0
    assert candidates[1]["duplicate_of"] == 0
    assert result["eligible_candidate_count"] == 2


def _selector_candidate(candidate_id, sql, frame, result_hash=None):
    return {
        "candidate_id": candidate_id, "sql": sql, "source": "generated", "frame": frame,
        "error": None, "executed": frame is not None, "parseable": True,
        "canonical_sql": " ".join(sql.lower().split()),
        "references": {"tables": [], "columns": []},
        "result_hash": result_hash, "value_evidence": [],
    }


def test_structural_contract_extracts_material_sql_features():
    sql = (
        "SELECT DISTINCT p.city, COUNT(DISTINCT p.id) AS people "
        "FROM people p JOIN visits v ON p.id = v.person_id "
        "WHERE v.visited_at >= '2024-01-01' GROUP BY p.city "
        "ORDER BY people DESC LIMIT 5"
    )
    structure = _candidate_structure(sql, "local_test")
    contract = _question_contract(
        "For each city, return the top 5 cities by distinct people after 2024-01-01"
    )
    assert structure["grain"] == "grouped"
    assert structure["aggregations"] == ["count"]
    assert structure["aggregate_distinct"]
    assert structure["joins"] and structure["predicates"]
    assert structure["order_by"] and structure["limit"] == 5
    assert structure["has_time_filter"]
    assert contract["expects_grouping"] and contract["expects_ranking"]
    assert contract["expected_limit"] == 5


def test_equivalent_results_receive_one_representative_vote(monkeypatch):
    monkeypatch.setenv("SLAYQL_SELECTOR_VERIFY", "0")
    same = pd.DataFrame({"name": ["Ada", "Lin"]})
    different = pd.DataFrame({"name": ["Ada"]})
    candidates = [
        _selector_candidate(0, "SELECT name FROM people ORDER BY name", same),
        _selector_candidate(1, "SELECT name FROM people ORDER BY name ASC", same.copy()),
        _selector_candidate(2, "SELECT name FROM people WHERE name = 'Ada'", different),
    ]
    result = select_instance("local_test", candidates, "List the people names")
    assert result["representative_count"] == 2
    duplicate = next(candidate for candidate in candidates if "duplicate_of" in candidate)
    assert duplicate["duplicate_reason"] == "equivalent_result"
    assert sorted(duplicate["duplicate_members"]) == [0, 1]


def test_selector_rejects_multiple_statements_and_invalid_local_table(tmp_path, monkeypatch):
    monkeypatch.setenv("SLAYQL_SELECTOR_VERIFY", "0")
    db_path = tmp_path / "people.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT)")
    frame = pd.DataFrame({"name": ["Ada"]})
    candidates = [
        _selector_candidate(0, "SELECT name FROM people; SELECT name FROM people", frame),
        _selector_candidate(1, "SELECT name FROM missing_table", frame),
        _selector_candidate(2, "SELECT name FROM people", frame),
    ]
    result = select_instance(
        "local_test", candidates, "List people names", {"db_path": str(db_path)},
    )
    assert result["selected"]["candidate_id"] == 2
    gate_status = {
        candidate["candidate_id"]: {gate["name"]: gate["passed"] for gate in candidate["hard_gates"]}
        for candidate in candidates
    }
    assert not gate_status[0]["single_statement"]
    assert not gate_status[1]["schema_tables"]
    assert gate_status[2]["single_statement"] and gate_status[2]["schema_tables"]


def test_verifier_requires_close_score_and_material_disagreement(monkeypatch):
    calls = []

    def fake_verify(instance_id, question, contract, candidates, selected, disagreement, **_kwargs):
        calls.append(disagreement)
        selected["verification"] = {"status": "selected"}
        return selected

    monkeypatch.setattr(selector_first, "_verify", fake_verify)
    monkeypatch.setenv("SLAYQL_SELECTOR_MARGIN", "1.0")
    frame = pd.DataFrame({"value": [1]})
    same_candidates = [
        _selector_candidate(0, "SELECT value FROM metrics", frame, "first"),
        _selector_candidate(1, "SELECT value FROM metrics", frame, "second"),
    ]
    select_instance("local_test", same_candidates, "Return the value")
    assert not calls

    different_candidates = [
        _selector_candidate(0, "SELECT value FROM metrics", frame, "first"),
        _selector_candidate(1, "SELECT SUM(value) FROM metrics", frame, "second"),
    ]
    result = select_instance("local_test", different_candidates, "Return the value")
    assert calls and calls[0]["material"]
    assert "aggregations" in calls[0]["reasons"]
    assert result["selected"]["selection"]["method"] == "verification"


def test_offline_replay_is_isolated_and_freezes_candidate_artifacts(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "replay"
    data_file = source / "dataset.json"
    data_file.parent.mkdir(parents=True)
    data_file.write_text(json.dumps({
        "local_test": {"question": "How many people are there?"}
    }), encoding="utf-8")
    sql_dir = source / "sql_gen" / "r1_lite_sql_0"
    result_dir = source / "sql_gen" / "r1_lite_execution_result_0"
    sql_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    (sql_dir / "local_test.sql").write_text("SELECT COUNT(*) AS count FROM people", encoding="utf-8")
    pd.DataFrame({"count": [2]}).to_csv(result_dir / "local_test.csv", index=False)
    args = Namespace(
        log_path=str(source), offline_replay_output=str(output), data_file=str(data_file),
        task="r1_lite", num_candidates=1, allow_replay_verification=False,
    )
    run_offline_replay(args)
    manifest = json.loads((output / "offline_replay_manifest.json").read_text(encoding="utf-8"))
    selection = json.loads((output / "selection" / "local_test.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["configuration"]["verification_enabled"] is False
    assert manifest["configuration"]["candidate_artifacts"]["file_count"] == 2
    assert selection["verification"]["status"] == "not_invoked"
    assert not (source / "selection").exists()

    (sql_dir / "local_test.sql").write_text("SELECT COUNT(id) AS count FROM people", encoding="utf-8")
    with pytest.raises(RuntimeError, match="source artifacts or frozen configuration changed"):
        run_offline_replay(args)


def test_provider_usage_is_persisted_without_prompt_data(tmp_path, monkeypatch):
    class Usage:
        def model_dump(self):
            return {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14, "cost": 0.001}

    class Response:
        id = "generation-1"
        model = "test-model"
        usage = Usage()

    monkeypatch.setenv("SLAYQL_USAGE_DIR", str(tmp_path))
    record = record_response_usage(Response(), stage="generation", instance_id="local_1", candidate_id=2)
    saved = json.loads((tmp_path / "local_1.jsonl").read_text(encoding="utf-8"))
    assert record["usage"]["total_tokens"] == 14
    assert saved["response_id"] == "generation-1"
    assert "prompt" not in saved


def test_local_evaluator_reports_ex_schema_and_oracle(tmp_path):
    db_path = tmp_path / "people.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany("INSERT INTO people(name) VALUES (?)", [("Ada",), ("Lin",)])

    run_root = tmp_path / "run"
    prediction = run_root / "sql_selection_v1" / "final" / "local_1"
    prediction.mkdir(parents=True)
    sql = "SELECT name FROM people ORDER BY name"
    (prediction / "selected.sql").write_text(sql, encoding="utf-8")
    pd.DataFrame({"name": ["Ada", "Lin"]}).to_csv(prediction / "result.csv", index=False)
    candidate_dir = run_root / "sql_gen" / "r1_lite_execution_result_0"
    candidate_dir.mkdir(parents=True)
    pd.DataFrame({"name": ["Ada", "Lin"]}).to_csv(candidate_dir / "local_1.csv", index=False)
    (run_root / "unfilled_schema.json").write_text(json.dumps({
        "local_1": {"table_candidates": ["people"], "column_candidates": ["name"]}
    }), encoding="utf-8")
    data_file = run_root / "dataset.json"
    data_file.write_text(json.dumps({
        "local_1": {"db_path": str(db_path), "gold_sql": sql, "backend": "sqlite"}
    }), encoding="utf-8")
    summary = evaluate_run("spider1", data_file, run_root / "sql_selection_v1" / "final",
                           run_root / "aggregates" / "summary_metrics.json")
    assert summary["execution_accuracy"] == 1.0
    assert summary["candidate_oracle_accuracy"] == 1.0
    assert summary["schema_linking"]["table"]["micro_recall"] == 1.0
    assert summary["schema_linking"]["column"]["micro_f1"] == 1.0


def test_metric_formula_handles_empty_sets():
    assert _metric_sets(set(), {"id"})["recall"] == 0.0
    assert _metric_sets({"id"}, {"id"})["f1"] == 1.0

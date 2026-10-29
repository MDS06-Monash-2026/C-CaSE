import json
import sqlite3
from argparse import Namespace

import research_interaction
import research_suite
import focus_schema
from sql_generation import candidate_guidance, relational_schema_view
from candidate_router import build_route_hypotheses, render_routed_schema, route_for_candidate
from semantic_contract import assess_semantic_contract, compile_semantic_contract, physical_projection_check
from selector_first import _interaction_grounding, collect_candidates
from selector_first import _result_preview
from selector_first import _candidate_structure
from selector_first import _question_contract as selector_question_contract
from prompt_learning import build as build_prompt_learning
from semantic_revise import repair_trigger
from sql_generation import _apply_v17_generation_contract
from research_subset import select_subset


def _records(count=50):
    records = {}
    for index in range(count):
        backend = "bigquery" if index % 2 else "sqlite"
        records[f"item_{index:03d}"] = {
            "backend": backend,
            "db_name": f"db_{index % 5}",
            "question": "Return the total for each customer ordered by total descending "
                        + ("with a join and date filter" if index >= 25 else ""),
            "gold_sql": "SELECT COUNT(*) FROM customers" + (" JOIN orders ON customers.id = orders.customer_id" if index >= 25 else ""),
        }
    return records


def test_subset20_is_deterministic_and_reference_stratified(tmp_path):
    records = _records()
    reference = {
        "instances": [
            {"instance_id": f"item_{index:03d}", "correct": index < 25}
            for index in range(50)
        ]
    }
    reference_path = tmp_path / "summary.json"
    reference_path.write_text(json.dumps(reference), encoding="utf-8")

    selected, manifest = select_subset(records, "subset20", seed=17, reference_evaluation=str(reference_path))
    selected_again, manifest_again = select_subset(records, "subset20", seed=17, reference_evaluation=str(reference_path))

    assert list(selected) == list(selected_again)
    assert manifest["instance_ids"] == manifest_again["instance_ids"]
    assert len(selected) == 10
    assert manifest["selection_policy"] == "reference_correctness_20_hard_80"
    assert sum(int(int(instance_id[-3:]) < 25) for instance_id in selected) == 2


def test_subset_excludes_snowflake_and_round_robins_databases():
    records = {
        "sf": {"backend": "snowflake", "db_name": "sf"},
        "bq_a": {"backend": "bigquery", "db_name": "a"},
        "bq_b": {"backend": "bigquery", "db_name": "b"},
        "local_a": {"backend": "sqlite", "db_name": "a"},
        "local_b": {"backend": "sqlite", "db_name": "b"},
    }
    selected, manifest = select_subset(records, "smoke", smoke_count=4, excluded_backends=["snowflake"])
    assert "sf" not in selected
    assert len(selected) == 4
    assert manifest["excluded_backends"] == ["snowflake"]
    assert {records[key]["db_name"] for key in selected} == {"a", "b"}


def test_interaction_evidence_caches_sqlite_relationships_and_values(tmp_path):
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT, FOREIGN KEY(customer_id) REFERENCES customers(id))")
        connection.execute("INSERT INTO customers VALUES (1, 'Ada')")
        connection.execute("INSERT INTO orders VALUES (1, 1, 'paid')")

    data_file = tmp_path / "dataset.json"
    data_file.write_text(json.dumps({
        "local_1": {
            "db_path": str(database), "db_name": "shop", "backend": "sqlite",
            "question": "Which customer had a 'paid' order status?",
        }
    }), encoding="utf-8")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "local_1.txt").write_text("Table: customers\nTable: orders\n", encoding="utf-8")

    manifest = research_interaction.build(str(data_file), str(schema_dir), str(tmp_path / "run"), max_context_chars=2000)
    evidence = json.loads((tmp_path / "run" / "interaction" / "local_1.json").read_text(encoding="utf-8"))
    context = (schema_dir / "local_1.txt").read_text(encoding="utf-8")
    assert manifest["record_count"] == 1
    assert any(edge["from_table"] == "orders" for edge in evidence["relationships"])
    assert any(edge["from_table"] == "orders" for edge in evidence["recommended_joins"])
    assert any(probe["column"] == "status" and probe["reason"] == "question_literal_match" for probe in evidence["value_probes"])
    assert "SLAYQL_INTERACTION_EVIDENCE_V12" in context
    assert "Question obligations to verify" in context

    compact_evidence = research_interaction._sqlite_catalog(
        str(database), "Which customer had a 'paid' order status?", compact=True
    )
    compact_context = research_interaction._context_text(compact_evidence, 2000, compact=True)
    assert compact_evidence["interaction_mode"] == "selective_query_linked"
    assert len(compact_evidence["value_probes"]) <= 6
    assert "SLAYQL_INTERACTION_EVIDENCE_V13" in compact_context


def test_interaction_context_can_be_reused_for_final_schema(tmp_path):
    output = tmp_path / "run"
    context_dir = output / "interaction_context"
    context_dir.mkdir(parents=True)
    (context_dir / "local_1.txt").write_text(
        "-- SLAYQL_INTERACTION_EVIDENCE_V12 --\n- verify join\n", encoding="utf-8"
    )
    (output / "interaction_manifest.json").write_text(json.dumps({"record_count": 1}), encoding="utf-8")
    final_schema = tmp_path / "final_schema_prompts"
    final_schema.mkdir()
    (final_schema / "local_1.txt").write_text("Table: orders\n", encoding="utf-8")

    result = research_interaction.append_cached(str(output), str(final_schema))
    assert result["appended"] == 1
    assert "verify join" in (final_schema / "local_1.txt").read_text(encoding="utf-8")
    assert str(final_schema.resolve()) in json.loads(
        (output / "interaction_manifest.json").read_text(encoding="utf-8")
    )["appended_schema_dirs"]


def test_cloud_interaction_looks_under_run_documents(tmp_path):
    documents = tmp_path / "run" / "documents"
    documents.mkdir(parents=True)
    (documents / "bigquery.json").write_text(json.dumps({
        "ga360": {"sessions": {"columns": {"visitorId": "STRING", "transactionRevenue": "FLOAT64"}}}
    }), encoding="utf-8")
    evidence = research_interaction._cloud_catalog(
        {"backend": "bigquery", "db_name": "ga360", "question": "visitor transaction revenue"}, tmp_path
    )
    assert evidence["dialect"] == "bigquery"
    assert evidence["tables"][0]["name"] == "sessions"
    assert evidence["lexical_matches"]


def test_research_suite_defaults_and_target_validation():
    parser = research_suite.build_parser()
    args = parser.parse_args(["prepare", "--dataset", "spider1", "--mode", "subset20"])
    assert research_suite._candidate_default("spider1") == 3
    assert research_suite.TARGETS["bird"] == 0.75
    args.target_accuracy = 1.1
    try:
        research_suite.prepare_run(args)
    except ValueError as error:
        assert "target-accuracy" in str(error)
    else:
        raise AssertionError("invalid target should be rejected before dataset access")


def test_candidate_roles_are_distinct_without_changing_candidate_count():
    prompts = [candidate_guidance(index) for index in range(5)]
    assert len(set(prompts)) == 5
    assert "join key" in prompts[1]
    assert "NULL" in prompts[2]
    assert "adversarial" in prompts[4]


def test_v13_contract_recognizes_ordinal_entity_ranking(monkeypatch):
    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.3")
    contract = selector_question_contract(
        "What is the full name of the racer who ranked 1st in the qualifying race?"
    )
    assert contract["expects_ranking"] is True
    assert contract["expects_order"] is True
    assert contract["ordinal_limit"] == 1
    assert contract["expected_grain"] is None


def test_interaction_grounding_prefers_linked_join_path():
    candidate = {
        "sql": "SELECT c.name FROM customers c JOIN orders o ON c.id = o.customer_id",
        "structure": {
            "tables": ["customers", "orders"],
            "joins": [{"table": "orders"}],
        },
    }
    evidence = {
        "lexical_matches": [{"table": "customers"}, {"table": "orders"}],
        "recommended_joins": [{
            "from_table": "orders", "from_column": "customer_id",
            "to_table": "customers", "to_column": "id",
        }],
    }
    assert _interaction_grounding(candidate, evidence) > 0.5


def test_v14_focus_preserves_linked_columns_and_adds_question_plan(monkeypatch):
    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.4")
    schema = (
        "###Table full name: customers\n"
        "[\n"
        "    id (Type: INTEGER; Sample values: ['1']; Description: id)\n"
        "    name (Type: TEXT; Sample values: ['Ada']; Description: name)\n"
        "    email (Type: TEXT; Sample values: ['a@example.com']; Description: email)\n"
        "    address (Type: TEXT; Sample values: ['x']; Description: address)\n"
        "]\n"
    )
    focused, details = focus_schema.focus_one(
        schema,
        "Which customer name had a paid order?",
        {
            "lexical_matches": [{"table": "customers", "column": "name", "score": 4}],
            "recommended_joins": [{"from_table": "orders", "from_column": "customer_id", "to_table": "customers", "to_column": "id"}],
            "question_contract": {"join_likely": True},
        },
        max_tables=1, max_columns_per_table=2, max_columns_total=2,
    )
    assert details["focused"] is True
    assert "SLAYQL_V14_QUESTION_PLAN" in focused
    assert "name (Type:" in focused
    assert "id (Type:" in focused


def test_v15_relational_closure_keeps_bridge_table():
    relationships = [
        {"from_table": "drivers", "from_column": "driverId", "to_table": "standings", "to_column": "driverId", "source": "foreign_key"},
        {"from_table": "standings", "from_column": "raceId", "to_table": "races", "to_column": "raceId", "source": "foreign_key"},
        {"from_table": "results", "from_column": "raceId", "to_table": "races", "to_column": "raceId", "source": "foreign_key"},
    ]
    closure = research_interaction._relational_closure(relationships, ["drivers", "races"])
    assert closure["tables"] == ["drivers", "races", "standings"]
    assert len(closure["edges"]) == 2
    assert any(edge["from_table"] == "standings" for edge in closure["edges"])


def test_v15_focus_and_ddl_preserve_closure_endpoints(monkeypatch):
    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.5")
    schema = "\n".join([
        "###Table full name: drivers", "[", "    driverId (Type: INTEGER; Sample values: ['1']; Description: key)", "    name (Type: TEXT; Sample values: ['Ada']; Description: name)", "]",
        "###Table full name: standings", "[", "    driverId (Type: INTEGER; Sample values: ['1']; Description: key)", "    raceId (Type: INTEGER; Sample values: ['2']; Description: key)", "    points (Type: INTEGER; Sample values: ['8']; Description: points)", "]",
        "###Table full name: races", "[", "    raceId (Type: INTEGER; Sample values: ['2']; Description: key)", "    raceName (Type: TEXT; Sample values: ['GP']; Description: name)", "]",
    ])
    edges = [
        {"from_table": "drivers", "from_column": "driverId", "to_table": "standings", "to_column": "driverId", "source": "foreign_key"},
        {"from_table": "standings", "from_column": "raceId", "to_table": "races", "to_column": "raceId", "source": "foreign_key"},
    ]
    evidence = {
        "tables": [
            {"name": "drivers", "columns": [{"name": "driverId", "type": "INTEGER"}, {"name": "name", "type": "TEXT"}]},
            {"name": "standings", "columns": [{"name": "driverId", "type": "INTEGER"}, {"name": "raceId", "type": "INTEGER"}, {"name": "points", "type": "INTEGER"}]},
            {"name": "races", "columns": [{"name": "raceId", "type": "INTEGER"}, {"name": "raceName", "type": "TEXT"}]},
        ],
        "lexical_matches": [{"table": "drivers", "column": "name", "score": 2}, {"table": "races", "column": "raceName", "score": 2}],
        "relational_closure": {"seed_tables": ["drivers", "races"], "tables": ["drivers", "races", "standings"], "edges": edges},
        "recommended_joins": edges,
        "question_contract": {"join_likely": True},
    }
    focused, details = focus_schema.focus_one(
        schema, "Which driver name belongs to the race?", evidence,
        max_tables=3, max_columns_per_table=2, max_columns_total=6, version="1.5",
    )
    ddl = relational_schema_view(evidence)
    assert "SLAYQL_SCHEMA_FOCUS_V15" in focused
    assert "SLAYQL_V15_QUESTION_PLAN" in focused
    assert "standings" in details["selected_table_names"]
    assert "standings.driverId = races.raceId" not in ddl
    assert "standings.raceId = races.raceId" in ddl


def test_v15_result_preview_exposes_values_without_full_frame():
    import pandas as pd

    frame = pd.DataFrame({"name": ["Ada", "Grace", "Linus", "Ken", "Margaret", "Edsger"]})
    preview = _result_preview({"frame": frame})
    assert preview["total_rows"] == 6
    assert [row["name"] for row in preview["rows"]] == ["Ada", "Grace", "Linus", "Ken", "Margaret"]


def test_v15_bm25_value_link_becomes_relational_seed(tmp_path, monkeypatch):
    from value_grounder import build_db_value_index

    database = tmp_path / "racing.sqlite"
    indices = tmp_path / "indices"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE drivers (driver_id INTEGER PRIMARY KEY, forename TEXT, surname TEXT)")
        connection.execute("CREATE TABLE races (race_id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE results (driver_id INTEGER, race_id INTEGER, FOREIGN KEY(driver_id) REFERENCES drivers(driver_id), FOREIGN KEY(race_id) REFERENCES races(race_id))")
        connection.execute("INSERT INTO drivers VALUES (1, 'Lewis', 'Hamilton')")
        connection.execute("INSERT INTO races VALUES (2, 'British Grand Prix')")
        connection.execute("INSERT INTO results VALUES (1, 2)")
        build_db_value_index(connection, "racing", str(indices))

    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.5")
    monkeypatch.setenv("SLAYQL_BM25_STRICT", "1")
    monkeypatch.setenv("SLAYQL_BM25_DIR", str(indices))
    question = "Which races did Lewis Hamilton participate in?"
    evidence = research_interaction._sqlite_catalog(str(database), question, compact=True)
    evidence = research_interaction._append_bm25_value_links(
        evidence, {"db_name": "racing", "question": question}, "local_racing_1", tmp_path / "run"
    )
    assert any(link["table"] == "drivers" for link in evidence["value_links"])
    assert evidence["relational_closure"]["seed_tables"][0] == "drivers"
    assert {"drivers", "races", "results"}.issubset(set(evidence["relational_closure"]["tables"]))


def test_v16_semantic_contract_preserves_formula_and_output_arity():
    contract = compile_semantic_contract({
        "raw_question": "List the loan ID, district and average salary for loans lasting 60 months.",
        "evidence": "average salary refers to AVG(A11); duration = 60",
    })
    assert contract["required_operations"] == ["avg"]
    assert contract["required_columns"] == ["A11", "duration"]
    assert contract["required_literals"] == ["60"]
    assert contract["output"]["expected_projection_count"] == 3
    assert contract["output"]["projection_confidence"] == "high"

    good_sql = "SELECT loan_id, district, AVG(A11) FROM loans WHERE duration = 60"
    bad_sql = "SELECT DISTINCT loan_id, district, salary, duration FROM loans WHERE duration = 60"
    good = assess_semantic_contract(good_sql, _candidate_structure(good_sql, "local_1"), contract)
    bad = assess_semantic_contract(bad_sql, _candidate_structure(bad_sql, "local_1"), contract)
    assert good["score"] > bad["score"]
    assert any(check["name"] == "no_unrequested_distinct" and not check["passed"] for check in bad["checks"])


def test_v16_full_name_mapping_expands_physical_output_columns():
    contract = compile_semantic_contract({
        "raw_question": "What is the full name of the racer?",
        "evidence": "full name of racer = forename, surname",
    })
    assert contract["required_columns"] == ["forename", "surname"]
    assert contract["output"]["physical_output_columns"] == ["forename", "surname"]
    assert contract["output"]["expected_projection_count"] == 2


def test_v19_physical_projection_gate_rejects_concatenated_logical_field():
    contract = compile_semantic_contract({
        "raw_question": "What is the full name of the racer?",
        "evidence": "full name of racer = forename, surname",
    })
    bad_sql = "SELECT forename || ' ' || surname FROM drivers"
    bad_structure = _candidate_structure(bad_sql, "local_1")
    check = physical_projection_check(bad_sql, bad_structure, contract)
    assert check["passed"] is False
    assert check["actual_projection_count"] == 1
    good_sql = "SELECT forename, surname FROM drivers"
    good = physical_projection_check(good_sql, _candidate_structure(good_sql, "local_1"), contract)
    assert good["passed"] is True


def test_v19_route_preserves_physical_output_tables(monkeypatch):
    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.9")
    schema = "\n".join([
        "###Table full name: drivers", "[", "    driver_id (Type: INTEGER; Description: key)", "    forename (Type: TEXT; Description: first)", "    surname (Type: TEXT; Description: last)", "]",
        "###Table full name: results", "[", "    driver_id (Type: INTEGER; Description: key)", "    race_id (Type: INTEGER; Description: key)", "]",
        "###Table full name: races", "[", "    race_id (Type: INTEGER; Description: key)", "    name (Type: TEXT; Description: race)", "]",
    ])
    evidence = {
        "semantic_contract": {"required_columns": ["forename", "surname"], "output": {"physical_output_columns": ["forename", "surname"], "expected_projection_count": 2, "projection_confidence": "high"}},
        "answer_plan": {"likely_tables": ["drivers"]},
        "lexical_matches": [{"table": "results", "column": "race_id", "score": 5}],
        "relationships": [{"from_table": "drivers", "from_column": "driver_id", "to_table": "results", "to_column": "driver_id"}],
        "question_contract": {"join_likely": True},
    }
    plan = build_route_hypotheses(schema, evidence)
    assert plan["routes"]
    assert all("drivers" in route["table_keys"] for route in plan["routes"])
    assert all("drivers" in route["mandatory_tables"] for route in plan["routes"])


def test_v16_routes_are_distinct_and_keep_full_schema_fallback():
    schema = "\n".join([
        "###Table full name: drivers", "[", "    driverId (Type: INTEGER; Description: key)", "]",
        "###Table full name: standings", "[", "    driverId (Type: INTEGER; Description: key)", "    raceId (Type: INTEGER; Description: key)", "]",
        "###Table full name: results", "[", "    driverId (Type: INTEGER; Description: key)", "    raceId (Type: INTEGER; Description: key)", "]",
        "###Table full name: races", "[", "    raceId (Type: INTEGER; Description: key)", "]",
        "-- SLAYQL_INTERACTION_EVIDENCE_V16 --", "contract",
    ])
    edges = [
        {"from_table": "drivers", "from_column": "driverId", "to_table": "standings", "to_column": "driverId"},
        {"from_table": "standings", "from_column": "raceId", "to_table": "races", "to_column": "raceId"},
        {"from_table": "drivers", "from_column": "driverId", "to_table": "results", "to_column": "driverId"},
        {"from_table": "results", "from_column": "raceId", "to_table": "races", "to_column": "raceId"},
    ]
    evidence = {
        "lexical_matches": [{"table": "drivers", "score": 4}, {"table": "races", "score": 4}],
        "relationship_catalog": edges,
        "relational_closure": {"seed_tables": ["drivers", "races"], "tables": ["drivers", "standings", "races"]},
        "question_contract": {"join_likely": True},
    }
    plan = build_route_hypotheses(schema, evidence)
    assigned = [route_for_candidate(plan, index) for index in range(5)]
    assert len({frozenset(route["table_keys"]) for route in assigned}) >= 3
    assert assigned[2]["full_schema"] is True
    assert set(assigned[2]["table_keys"]) == {"drivers", "standings", "results", "races"}
    routed = render_routed_schema(schema, assigned[0], 0)
    assert "SLAYQL_V16_ROUTE" in routed
    assert "SLAYQL_INTERACTION_EVIDENCE_V16" in routed


def test_v16_interaction_caches_semantic_contract(tmp_path, monkeypatch):
    database = tmp_path / "people.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, forename TEXT, surname TEXT)")
    data_file = tmp_path / "dataset.json"
    data_file.write_text(json.dumps({
        "local_1": {
            "db_path": str(database), "db_name": "people", "backend": "sqlite",
            "question": "What is the full name? Evidence: full name = forename, surname",
            "raw_question": "What is the full name?", "evidence": "full name = forename, surname",
        }
    }), encoding="utf-8")
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "local_1.txt").write_text("Table: people\n", encoding="utf-8")
    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.6")
    manifest = research_interaction.build(
        str(data_file), str(schema_dir), str(tmp_path / "run"), max_context_chars=3000, compact=True,
    )
    evidence = json.loads((tmp_path / "run" / "interaction" / "local_1.json").read_text(encoding="utf-8"))
    context = (tmp_path / "run" / "interaction_context" / "local_1.txt").read_text(encoding="utf-8")
    assert manifest["schema_version"] == "1.6"
    assert evidence["semantic_contract"]["output"]["expected_projection_count"] == 2
    assert evidence["interaction_mode"] == "semantic_contract_relational_routes"
    assert "SLAYQL_INTERACTION_EVIDENCE_V16" in context
    assert "SLAYQL_V16_SEMANTIC_CONTRACT" in context


def test_v17_removes_legacy_extra_projection_rules():
    legacy = (
        "When asked something without stating name or id, return both of them. e.g. Which products ...? "
        "The answer should include product_name and product_id.\n"
        "Make sure that the query content of the sql definitely includes what needs to be involved in the question, "
        "the execution result can be more than what is required by the question, but it must not be less."
    )
    revised = _apply_v17_generation_contract(legacy)
    assert "return both" not in revised
    assert "can be more" not in revised
    assert "exactly the requested answer fields" in revised


def test_v17_prompt_learning_rejects_target_overlap_and_ignores_target_gold(tmp_path):
    training = tmp_path / "train_examples.json"
    training.write_text(json.dumps([
        {"db_id": "shop", "question_id": 1, "question": "Count paid orders", "query": "SELECT COUNT(*) FROM orders WHERE status = 'paid'"},
        {"db_id": "shop", "question_id": 2, "question": "List customer names", "query": "SELECT name FROM customers"},
        {"db_id": "sales", "question_id": 3, "question": "Average sale amount", "query": "SELECT AVG(amount) FROM sales"},
    ]), encoding="utf-8")
    target = tmp_path / "dataset.json"
    target.write_text(json.dumps({
        "local_dev_1": {
            "db_id": "shop", "source_id": "9", "question": "Count paid orders",
            "gold_sql": "TARGET GOLD MUST NEVER ENTER THE PROMPT",
        }
    }), encoding="utf-8")
    manifest = build_prompt_learning(str(target), str(tmp_path / "run"), str(training), count=2)
    artifact = json.loads((tmp_path / "run" / "prompt_learning" / "local_dev_1.json").read_text(encoding="utf-8"))
    assert manifest["excluded_target_overlap"] == 1
    assert len(artifact["selected"]) == 2
    assert "TARGET GOLD" not in artifact["prompt"]
    assert "Count paid orders" not in artifact["prompt"]


def test_v17_prompt_learning_requires_training_provenance(tmp_path):
    source = tmp_path / "examples.json"
    source.write_text(json.dumps([
        {"question": "List names", "query": "SELECT name FROM people"}
    ]), encoding="utf-8")
    target = tmp_path / "dataset.json"
    target.write_text(json.dumps({"local_1": {"question": "Count people"}}), encoding="utf-8")
    try:
        build_prompt_learning(str(target), str(tmp_path / "run"), str(source), count=1)
    except ValueError as error:
        assert "training-only" in str(error) or "marked as train" in str(error)
    else:
        raise AssertionError("non-training prompt source should be rejected")


def test_v17_semantic_repair_requires_disagreement_and_material_risk():
    selected = {
        "candidate_id": 0, "executed": True, "eligible": True, "result_hash": "a",
        "selection": {"margin": 0.05},
        "semantic_contract_checks": [
            {"name": "evidence_operation:avg", "passed": False, "weight": 0.9},
            {"name": "no_unrequested_distinct", "passed": True, "weight": 0.8},
        ],
    }
    selection = {"selected": selected, "candidates": [selected, {"executed": True, "result_hash": "b"}]}
    interaction = {"semantic_contract": {"required_operations": ["avg"], "evidence_clauses": ["average = AVG(amount)"]}}
    assert repair_trigger(selection, interaction)["triggered"] is True
    selection["candidates"][1]["result_hash"] = "a"
    assert repair_trigger(selection, interaction)["triggered"] is False


def test_v17_selector_loads_semantic_repair_as_extra_candidate(tmp_path, monkeypatch):
    generated = tmp_path / "sql_gen" / "r1_lite_sql_0"
    result = tmp_path / "sql_gen" / "r1_lite_execution_result_0"
    repair = tmp_path / "semantic_revise" / "r1_lite_sql_1"
    decisions = tmp_path / "semantic_revise" / "decisions"
    for directory in (generated, result, repair, decisions):
        directory.mkdir(parents=True, exist_ok=True)
    (generated / "local_1.sql").write_text("SELECT name FROM people", encoding="utf-8")
    (result / "local_1.csv").write_text("name\nAda\n", encoding="utf-8")
    (repair / "local_1.sql").write_text("SELECT name FROM people WHERE active = 1", encoding="utf-8")
    (repair / "local_1.csv").write_text("name\nAda\n", encoding="utf-8")
    (decisions / "local_1.json").write_text(json.dumps({
        "status": "complete", "accepted": True, "output_candidate": 1, "parent_candidate": 0,
    }), encoding="utf-8")
    monkeypatch.setenv("SLAYQL_RESEARCH_VERSION", "1.7")
    candidates = collect_candidates(tmp_path, "r1_lite", "local_1", 1)
    assert len(candidates) == 2
    assert candidates[1]["candidate_id"] == 1
    assert candidates[1]["source"] == "semantic_revision"
    assert candidates[1]["parent_candidate_id"] == 0

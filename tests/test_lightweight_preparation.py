from prepare_lightweight_inputs import choose_mode, focus_results


def test_focus_results_caps_tables_and_columns():
    config = {
        "retrieval": {
            "max_tables": 2,
            "max_columns_per_table": 2,
            "max_prompt_columns": 3,
        }
    }
    results = [
        {"table": "a", "column": "a1", "score": 1.0},
        {"table": "a", "column": "a2", "score": 0.9},
        {"table": "a", "column": "a3", "score": 0.8},
        {"table": "b", "column": "b1", "score": 0.7},
        {"table": "c", "column": "c1", "score": 0.6},
    ]
    focused = focus_results(results, config)
    assert len(focused) == 3
    assert {result["table"] for result in focused} == {"a", "b"}


def test_missing_join_evidence_escalates_multi_table_question():
    results = [
        {"table": "orders", "score": 1.0},
        {"table": "customers", "score": 0.9},
    ]
    assert choose_mode("Show sales per customer", results, {"edges": []}) == "hard"

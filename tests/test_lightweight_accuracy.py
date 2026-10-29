import pandas as pd
import pytest

from dialect import resolve_dialect
from semantic_validator import extract_final_sql, results_equivalent


@pytest.mark.parametrize(
    ("instance_id", "engine"),
    [
        ("bq001", "bigquery"),
        ("ga001", "bigquery"),
        ("sf001", "snowflake"),
        ("local001", "sqlite"),
    ],
)
def test_dialect_routing(instance_id, engine):
    assert resolve_dialect(instance_id).key == engine


def test_unknown_dialect_fails_closed():
    with pytest.raises(ValueError):
        resolve_dialect("other001")


def test_final_sql_block_wins_over_longer_earlier_draft():
    response = """```sql
SELECT a, b, c FROM old_draft WHERE long_explanation = 1;
```
Final answer:
```sql
SELECT a FROM final_table;
```"""
    sql, source = extract_final_sql(response)
    assert sql == "SELECT a FROM final_table;"
    assert source == "final_fenced_block"


def test_result_equivalence_ignores_row_and_column_order():
    left = pd.DataFrame({"name": ["a", "b"], "value": [1, 2]})
    right = pd.DataFrame({"value": [2, 1], "name": ["b", "a"]})
    assert results_equivalent(left, right)


def test_result_equivalence_is_symmetric_for_different_values():
    left = pd.DataFrame({"value": [1, 2]})
    right = pd.DataFrame({"value": [1, 3]})
    assert not results_equivalent(left, right)
    assert not results_equivalent(right, left)

"""
Unit tests for the SGSA (Self-Generated Semantic Assertions) Validator.

Tests cover all four assertion types:
  - expected_row_count
  - unique_columns
  - value_bounds
  - no_nulls

Plus edge cases: empty assertions, missing columns, malformed inputs,
case-insensitive matching, and the assertion parser.
"""

import json
import pandas as pd
import pytest

from semantic_validator import (
    validate,
    parse_assertions_from_output,
    format_errors_for_llm,
    load_assertions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df():
    """A typical SQL result with 5 rows."""
    return pd.DataFrame({
        "product_name": ["Widget A", "Widget B", "Widget C", "Widget D", "Widget E"],
        "revenue": [100.0, 250.5, 75.3, 300.0, 180.2],
        "recovery_rate": [45.2, 88.1, 12.5, 99.9, 67.3],
    })


@pytest.fixture
def duplicate_df():
    """DataFrame with duplicates in product_name (JOIN explosion)."""
    return pd.DataFrame({
        "product_name": ["Widget A", "Widget A", "Widget B", "Widget C", "Widget C"],
        "revenue": [100, 100, 250, 75, 75],
    })


@pytest.fixture
def bad_math_df():
    """DataFrame with impossible percentage values."""
    return pd.DataFrame({
        "product_name": ["X", "Y", "Z"],
        "recovery_rate": [45.2, 1102.47, -5.0],
    })


@pytest.fixture
def all_null_df():
    """DataFrame with an entirely null column."""
    return pd.DataFrame({
        "product_name": ["A", "B", "C"],
        "recovery_rate": [None, None, None],
    })


# ---------------------------------------------------------------------------
# Test: expected_row_count
# ---------------------------------------------------------------------------

class TestExpectedRowCount:
    def test_exact_match(self, sample_df):
        errors = validate(sample_df, {"expected_row_count": 5})
        assert errors == []

    def test_mismatch(self, sample_df):
        errors = validate(sample_df, {"expected_row_count": 3})
        assert len(errors) == 1
        assert "[SEMANTIC ERROR]" in errors[0]
        assert "3 row(s)" in errors[0]
        assert "5 row(s)" in errors[0]

    def test_zero_rows_expected(self):
        df = pd.DataFrame(columns=["a", "b"])
        errors = validate(df, {"expected_row_count": 0})
        assert errors == []

    def test_invalid_value_skipped(self, sample_df):
        errors = validate(sample_df, {"expected_row_count": "not_a_number"})
        assert errors == []  # Should be silently skipped


# ---------------------------------------------------------------------------
# Test: unique_columns
# ---------------------------------------------------------------------------

class TestUniqueColumns:
    def test_all_unique(self, sample_df):
        errors = validate(sample_df, {"unique_columns": ["product_name"]})
        assert errors == []

    def test_duplicates_detected(self, duplicate_df):
        errors = validate(duplicate_df, {"unique_columns": ["product_name"]})
        assert len(errors) == 1
        assert "duplicate" in errors[0].lower()
        assert "Widget A" in errors[0] or "Widget C" in errors[0]

    def test_missing_column(self, sample_df):
        errors = validate(sample_df, {"unique_columns": ["nonexistent_col"]})
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_case_insensitive(self, sample_df):
        errors = validate(sample_df, {"unique_columns": ["PRODUCT_NAME"]})
        assert errors == []  # Should match case-insensitively


# ---------------------------------------------------------------------------
# Test: value_bounds
# ---------------------------------------------------------------------------

class TestValueBounds:
    def test_within_bounds(self, sample_df):
        assertions = {
            "value_bounds": {"recovery_rate": {"min": 0, "max": 100}}
        }
        errors = validate(sample_df, assertions)
        assert errors == []

    def test_exceeds_max(self, bad_math_df):
        assertions = {
            "value_bounds": {"recovery_rate": {"min": 0, "max": 100}}
        }
        errors = validate(bad_math_df, assertions)
        # Should catch both the >100 and <0 violations
        assert len(errors) == 2
        assert any("1102.47" in e for e in errors)
        assert any("-5.0" in e for e in errors)

    def test_min_only(self, sample_df):
        assertions = {
            "value_bounds": {"revenue": {"min": 0}}
        }
        errors = validate(sample_df, assertions)
        assert errors == []

    def test_max_only(self):
        df = pd.DataFrame({"pct": [50, 101]})
        errors = validate(df, {"value_bounds": {"pct": {"max": 100}}})
        assert len(errors) == 1
        assert "101" in errors[0]

    def test_missing_column(self, sample_df):
        assertions = {
            "value_bounds": {"ghost_column": {"min": 0, "max": 1}}
        }
        errors = validate(sample_df, assertions)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_case_insensitive(self, sample_df):
        assertions = {
            "value_bounds": {"RECOVERY_RATE": {"min": 0, "max": 100}}
        }
        errors = validate(sample_df, assertions)
        assert errors == []


# ---------------------------------------------------------------------------
# Test: no_nulls
# ---------------------------------------------------------------------------

class TestNoNulls:
    def test_no_nulls_pass(self, sample_df):
        errors = validate(sample_df, {"no_nulls": ["product_name"]})
        assert errors == []

    def test_all_null_fails(self, all_null_df):
        errors = validate(all_null_df, {"no_nulls": ["recovery_rate"]})
        assert len(errors) == 1
        assert "entirely NULL" in errors[0]

    def test_missing_column(self, sample_df):
        errors = validate(sample_df, {"no_nulls": ["missing_col"]})
        assert len(errors) == 1
        assert "does not exist" in errors[0]


# ---------------------------------------------------------------------------
# Test: Combined assertions
# ---------------------------------------------------------------------------

class TestCombined:
    def test_multiple_failures(self, bad_math_df):
        assertions = {
            "expected_row_count": 5,
            "unique_columns": ["product_name"],
            "value_bounds": {"recovery_rate": {"min": 0, "max": 100}},
            "no_nulls": ["product_name"],
        }
        errors = validate(bad_math_df, assertions)
        # Should have: row_count mismatch + min violation + max violation
        assert len(errors) >= 3

    def test_all_pass(self, sample_df):
        assertions = {
            "expected_row_count": 5,
            "unique_columns": ["product_name"],
            "value_bounds": {"recovery_rate": {"min": 0, "max": 100}},
            "no_nulls": ["product_name", "revenue"],
        }
        errors = validate(sample_df, assertions)
        assert errors == []


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_assertions(self, sample_df):
        assert validate(sample_df, {}) == []

    def test_none_assertions(self, sample_df):
        assert validate(sample_df, None) == []

    def test_none_df(self):
        errors = validate(None, {"expected_row_count": 5})
        assert len(errors) == 1
        assert "None" in errors[0]

    def test_empty_df(self):
        df = pd.DataFrame(columns=["a"])
        errors = validate(df, {"expected_row_count": 0})
        assert errors == []


# ---------------------------------------------------------------------------
# Test: parse_assertions_from_output
# ---------------------------------------------------------------------------

class TestParseAssertions:
    def test_valid_json_block(self):
        output = '''Here are the assertions:

```json
{
  "expected_row_count": 3,
  "value_bounds": {"rate": {"min": 0, "max": 100}}
}
```

```sql
SELECT * FROM table LIMIT 3
```'''
        result = parse_assertions_from_output(output)
        assert result["expected_row_count"] == 3
        assert "rate" in result["value_bounds"]

    def test_no_json_block(self):
        output = '''```sql
SELECT * FROM table
```'''
        result = parse_assertions_from_output(output)
        assert result == {}

    def test_invalid_json(self):
        output = '''```json
{invalid json here}
```'''
        result = parse_assertions_from_output(output)
        assert result == {}

    def test_empty_input(self):
        assert parse_assertions_from_output("") == {}
        assert parse_assertions_from_output(None) == {}

    def test_generic_block_fallback(self):
        output = '''Here is the assertion:
```
{"expected_row_count": 1}
```

```sql
SELECT COUNT(*) FROM table
```'''
        result = parse_assertions_from_output(output)
        assert result["expected_row_count"] == 1


# ---------------------------------------------------------------------------
# Test: format_errors_for_llm
# ---------------------------------------------------------------------------

class TestFormatErrors:
    def test_empty_errors(self):
        assert format_errors_for_llm([]) == ""

    def test_single_error(self):
        msg = format_errors_for_llm(["[SEMANTIC ERROR] test error"])
        assert "test error" in msg
        assert "semantic validation" in msg.lower()
        assert "Do NOT change the assertions" in msg

    def test_multiple_errors(self):
        errors = [
            "[SEMANTIC ERROR] error 1",
            "[SEMANTIC ERROR] error 2",
        ]
        msg = format_errors_for_llm(errors)
        assert "error 1" in msg
        assert "error 2" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

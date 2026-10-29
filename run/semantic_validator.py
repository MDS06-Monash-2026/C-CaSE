import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # The validator remains usable before dependency installation.
    sqlglot = None
    exp = None


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    severity: str
    message: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_PLACEHOLDER_PATTERNS = [
    r"\bYOUR_DATABASE_NAME\b",
    r"\bYOUR_SCHEMA_NAME\b",
    r"\bYOUR_TABLE_NAME\b",
    r"\bREPLACE_ME\b",
    r"<database>|<schema>|<table>",
]
_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|merge|grant|revoke|copy)\b",
    re.IGNORECASE,
)


def extract_final_sql(content: str) -> Tuple[str, str]:
    fenced = re.findall(r"```(?:sql)?\s*\n(.*?)\n\s*```", content or "", re.DOTALL | re.IGNORECASE)
    non_empty = [block.strip() for block in fenced if block.strip()]
    if non_empty:
        return non_empty[-1], "final_fenced_block"
    return (content or "").strip(), "raw_content"


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[`\"\[\]]", "", value or "").lower().strip()


def _parse_sql(sql: str, dialect: str):
    if sqlglot is None:
        return None, "sqlglot_not_installed"
    try:
        statements = sqlglot.parse(sql, read=dialect)
        return statements, None
    except Exception as exc:
        return None, str(exc)


def _referenced_schema(statements) -> Tuple[Set[str], Set[str]]:
    tables: Set[str] = set()
    columns: Set[str] = set()
    if not statements or exp is None:
        return tables, columns
    for statement in statements:
        for table in statement.find_all(exp.Table):
            parts = [getattr(table, key, None) for key in ("catalog", "db", "name")]
            full_name = ".".join(str(part) for part in parts if part)
            tables.add(_normalize_identifier(full_name or table.name))
            tables.add(_normalize_identifier(table.name))
        for column in statement.find_all(exp.Column):
            columns.add(_normalize_identifier(column.name))
            if column.table:
                columns.add(_normalize_identifier(f"{column.table}.{column.name}"))
    return tables, columns


def validate_sql(sql: str, contract: Dict[str, Any], dialect: str) -> List[CheckResult]:
    checks: List[CheckResult] = []
    stripped = (sql or "").strip()
    statements, parse_error = _parse_sql(stripped, dialect)
    checks.append(
        CheckResult(
            "SQL001",
            bool(statements) if sqlglot is not None else bool(stripped),
            "warning",
            parse_error or "SQL parsed in the expected dialect",
            1.0 if statements else 0.6,
        )
    )
    statement_count = len(statements) if statements is not None else len(
        [part for part in re.split(r";\s*(?=\S)", stripped.rstrip(";")) if part.strip()]
    )
    checks.append(CheckResult("SQL002", statement_count == 1, "error", f"statement_count={statement_count}"))
    destructive = bool(_DESTRUCTIVE_PATTERN.search(stripped))
    checks.append(CheckResult("SQL003", not destructive, "error", "destructive SQL detected" if destructive else "query-only SQL"))
    placeholder = next((pattern for pattern in _PLACEHOLDER_PATTERNS if re.search(pattern, stripped, re.IGNORECASE)), None)
    checks.append(CheckResult("SQL004", placeholder is None, "error", f"placeholder={placeholder}" if placeholder else "no placeholders"))

    tables, columns = _referenced_schema(statements)
    normalized_sql = _normalize_identifier(stripped)
    for required in contract.get("required_tables", []):
        normalized = _normalize_identifier(required)
        short = normalized.split(".")[-1]
        passed = normalized in tables or short in tables or short in normalized_sql
        checks.append(CheckResult("SEM001", passed, "error", f"required table: {required}"))
    for required in contract.get("required_columns", []):
        normalized = _normalize_identifier(required)
        short = normalized.split(".")[-1]
        passed = normalized in columns or short in columns or re.search(rf"\b{re.escape(short)}\b", normalized_sql) is not None
        checks.append(CheckResult("SEM002", passed, "error", f"required column: {required}", 0.9))
    for pattern in contract.get("forbidden_sql_patterns", []):
        matched = re.search(pattern, stripped, re.IGNORECASE | re.DOTALL) is not None
        checks.append(CheckResult("SEM004", not matched, "error", f"forbidden pattern: {pattern}", 0.9))

    lowered_question = str(contract.get("objective", "")).lower()
    if "one record per date" in lowered_question or "one row per date" in lowered_question:
        partitions_by_city = re.search(r"partition\s+by\s+[^)]*city", stripped, re.IGNORECASE | re.DOTALL)
        checks.append(CheckResult("SEM005", partitions_by_city is None, "error", "output grain must not be partitioned by city", 0.9))
    return checks


def validate_result(df: Optional[pd.DataFrame], contract: Dict[str, Any]) -> List[CheckResult]:
    if df is None:
        return [CheckResult("RES001", False, "error", "no execution result")]
    checks = [CheckResult("RES001", True, "error", "execution produced a dataframe")]
    checks.append(CheckResult("RES002", not df.empty, "warning", f"row_count={len(df)}"))
    checks.append(CheckResult("RES003", len(df.columns) > 0, "error", f"column_count={len(df.columns)}"))
    all_null = bool(len(df.columns)) and all(df[column].isna().all() for column in df.columns)
    checks.append(CheckResult("RES008", not all_null, "error", "all output columns are null" if all_null else "output contains values"))

    invariants = " ".join(contract.get("required_invariants", [])).lower()
    if "one output row per selected date" in invariants and not df.empty:
        date_columns = [column for column in df.columns if "date" in str(column).lower()]
        if date_columns:
            duplicates = bool(df[date_columns[0]].duplicated().any())
            checks.append(CheckResult("RES004", not duplicates, "error", "duplicate output dates" if duplicates else "one row per date", 0.95))
    if "state abbreviation should be populated" in invariants and not df.empty:
        state_columns = [column for column in df.columns if "state" in str(column).lower()]
        if state_columns:
            series = df[state_columns[0]].astype(str).str.strip().str.lower()
            invalid = series.isin({"", "nan", "none", "n/a", "null"}).mean()
            checks.append(CheckResult("RES005", invalid < 0.5, "error", f"invalid_state_rate={invalid:.3f}", 0.95))
    return checks


def check_score(checks: Iterable[CheckResult]) -> float:
    total = 0.0
    earned = 0.0
    weights = {"error": 1.0, "warning": 0.35, "info": 0.1}
    for check in checks:
        weight = weights.get(check.severity, 0.35) * max(0.0, min(1.0, check.confidence))
        total += weight
        if check.passed:
            earned += weight
    return earned / total if total else 0.0


def has_hard_failures(checks: Iterable[CheckResult]) -> bool:
    return any(not check.passed and check.severity == "error" and check.confidence >= 0.8 for check in checks)


def dataframe_signature(df: pd.DataFrame, ignore_order: bool = True) -> Tuple[Any, ...]:
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower() for column in normalized.columns]
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    normalized = normalized.where(pd.notna(normalized), None)
    rows = [tuple(str(value).strip().lower() if value is not None else None for value in row) for row in normalized.itertuples(index=False, name=None)]
    if ignore_order:
        rows.sort(key=lambda row: tuple("" if value is None else value for value in row))
    return tuple(normalized.columns), tuple(rows)


def results_equivalent(left: pd.DataFrame, right: pd.DataFrame, ignore_order: bool = True) -> bool:
    if left.shape != right.shape:
        return False
    return dataframe_signature(left, ignore_order) == dataframe_signature(right, ignore_order)

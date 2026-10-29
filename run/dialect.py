from dataclasses import dataclass


@dataclass(frozen=True)
class DialectInfo:
    key: str
    display_name: str
    executor: str
    sqlglot_name: str


_DIALECTS = {
    "bigquery": DialectInfo("bigquery", "BigQuery", "bigquery", "bigquery"),
    "snowflake": DialectInfo("snowflake", "Snowflake", "snowflake", "snowflake"),
    "sqlite": DialectInfo("sqlite", "SQLite", "sqlite", "sqlite"),
}


def resolve_dialect(instance_id: str) -> DialectInfo:
    """Return the single authoritative dialect mapping for a Spider instance."""
    normalized = (instance_id or "").lower()
    if normalized.startswith(("bq", "ga")):
        return _DIALECTS["bigquery"]
    if normalized.startswith("sf"):
        return _DIALECTS["snowflake"]
    if normalized.startswith("local"):
        return _DIALECTS["sqlite"]
    raise ValueError(f"Unsupported instance ID prefix: {instance_id!r}")


def dialect_key(instance_id: str) -> str:
    return resolve_dialect(instance_id).key


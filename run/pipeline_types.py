import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from dialect import resolve_dialect


CONTRACT_SCHEMA_VERSION = "1.0"


@dataclass
class ContractFilter:
    expression: str
    source: str = "question"
    required: bool = True


@dataclass
class ValidatedDraft:
    sql_path: Optional[str] = None
    execution_status: str = "not_run"
    result_shape: Optional[Dict[str, Any]] = None
    semantic_score: float = 0.0


@dataclass
class QueryContract:
    instance_id: str
    db_name: str
    dialect: str
    objective: str
    required_tables: List[str] = field(default_factory=list)
    optional_tables: List[str] = field(default_factory=list)
    required_columns: List[str] = field(default_factory=list)
    joins: List[Dict[str, Any]] = field(default_factory=list)
    filters: List[ContractFilter] = field(default_factory=list)
    grouping_grain: str = "unknown"
    operations: List[str] = field(default_factory=list)
    output_columns: List[str] = field(default_factory=list)
    ordering: List[str] = field(default_factory=list)
    required_invariants: List[str] = field(default_factory=list)
    forbidden_assumptions: List[str] = field(default_factory=list)
    forbidden_sql_patterns: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    validated_draft: ValidatedDraft = field(default_factory=ValidatedDraft)
    contract_status: str = "incomplete"
    operating_mode: str = "medium"
    schema_version: str = CONTRACT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "QueryContract":
        data = dict(payload)
        data.pop("schema_version", None)
        data["filters"] = [
            item if isinstance(item, ContractFilter) else ContractFilter(**item)
            for item in data.get("filters", [])
        ]
        draft = data.get("validated_draft") or {}
        data["validated_draft"] = (
            draft if isinstance(draft, ValidatedDraft) else ValidatedDraft(**draft)
        )
        return cls(**data)


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        normalized = value.strip().lower()
        if value and normalized not in seen:
            result.append(value)
            seen.add(normalized)
    return result


def _question_operations(question: str) -> List[str]:
    lowered = question.lower()
    patterns = [
        (r"\b(count|how many|number of)\b", "count"),
        (r"\b(sum|total)\b", "sum"),
        (r"\b(avg|average|mean)\b", "average"),
        (r"\b(rank|ranked|top|bottom|highest|lowest|second-highest)\b", "ranking"),
        (r"\b(consecutive|streak)\b", "consecutive grouping"),
        (r"\b(no|not|without|excluding|except)\b", "set exclusion"),
        (r"\b(each|per|for every|for each)\b", "per-group output"),
        (r"\b(growth|change|difference|elapsed|rate|ratio|percentage)\b", "derived metric"),
        (r"\b(json|array|nested|struct|unnest)\b", "nested data"),
    ]
    return [label for pattern, label in patterns if re.search(pattern, lowered)]


def derive_contract(
    instance_id: str,
    question: str,
    db_name: str,
    retrieved_tables: Optional[List[str]] = None,
    retrieved_columns: Optional[List[str]] = None,
    operating_mode: str = "medium",
) -> QueryContract:
    """Create a conservative contract skeleton without using gold data."""
    dialect = resolve_dialect(instance_id).key
    tables = _unique(retrieved_tables or [])
    columns = _unique(retrieved_columns or [])
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", question)
    filters = [ContractFilter(expression=f"literal: {value}") for value in quoted[:8]]
    operations = _question_operations(question)
    lowered = question.lower()
    invariants = []
    forbidden = []
    forbidden_patterns = []

    if "exactly one" in lowered or "one record per" in lowered or "one row per" in lowered:
        invariants.append("one output row per requested entity or group")
    if "consecutive" in lowered and "city" in lowered:
        forbidden.append("do not partition a global date streak by city unless requested")
        forbidden_patterns.append(r"partition\s+by\s+[^)]*city")
    if "engagement time" in lowered and "event name" not in lowered:
        forbidden.append("do not add an event_name filter unless evidence requires it")
        forbidden_patterns.append(r"event_name\s*=|event_name\s+in")
    if "state abbreviation" in lowered:
        invariants.append("state abbreviation should be populated for returned rows")

    status = "complete" if tables and columns else "incomplete"
    return QueryContract(
        instance_id=instance_id,
        db_name=db_name,
        dialect=dialect,
        objective=" ".join(question.split()),
        required_tables=tables,
        required_columns=columns,
        filters=filters,
        operations=operations,
        required_invariants=invariants,
        forbidden_assumptions=forbidden,
        forbidden_sql_patterns=forbidden_patterns,
        contract_status=status,
        operating_mode=operating_mode,
    )


def validate_contract(contract: QueryContract) -> List[str]:
    missing = []
    if not contract.instance_id:
        missing.append("instance_id")
    if not contract.db_name:
        missing.append("db_name")
    if not contract.objective:
        missing.append("objective")
    if not contract.dialect:
        missing.append("dialect")
    if contract.contract_status == "complete" and not contract.required_tables:
        missing.append("required_tables")
    if contract.contract_status == "complete" and not contract.required_columns:
        missing.append("required_columns")
    return missing


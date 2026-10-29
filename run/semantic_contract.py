"""Deterministic question/evidence contracts for SlayQL v1.6+.

The contract does not attempt to solve SQL. It preserves benchmark-provided
semantics so generation and selection cannot silently replace them with a more
plausible interpretation, extra output columns, or unrequested deduplication.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Tuple


_FUNCTIONS = {
    "avg", "average", "count", "datetime", "distinct", "divide", "group_concat",
    "julianday", "max", "min", "multiply", "round", "strftime", "substr",
    "subtract", "sum", "year",
}
_FUNCTION_PATTERN = "|".join(sorted((re.escape(name) for name in _FUNCTIONS), key=len, reverse=True))
_OPERATION_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("group_concat", r"\bgroup_concat\s*\("),
    ("distinct", r"\bdistinct\b"),
    ("count", r"\bcount\s*\("),
    ("sum", r"\bsum\s*\("),
    ("avg", r"\b(?:avg|average)\s*\("),
    ("max", r"\bmax\s*\("),
    ("min", r"\bmin\s*\("),
    ("divide", r"\bdivide\s*\("),
    ("subtract", r"\bsubtract\s*\("),
    ("multiply", r"\bmultiply\s*\("),
    ("union", r"\bunion\b"),
    ("except", r"\bexcept\b"),
    ("intersect", r"\bintersect\b"),
)
_IDENTIFIER_STOPWORDS = {
    "and", "as", "between", "by", "case", "date", "else", "end", "false",
    "for", "from", "in", "is", "not", "normal", "null", "of", "on", "or",
    "range", "refers", "then", "to", "true", "when", "where", "within",
}
_OUTPUT_BOUNDARIES = re.compile(
    r"\b(?:for|whose|with|where|that|who|having|when|among|between|after|before|if|in|"
    r"has|have|had|is|are|was|were|uses?|used|attended|paid|from which)\b",
    re.IGNORECASE,
)


def _unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def _split_question_evidence(item: Dict[str, Any]) -> Tuple[str, str]:
    question = str(item.get("question", "") or "")
    raw_question = str(item.get("raw_question", "") or "").strip()
    evidence = str(item.get("evidence", "") or "").strip()
    if not raw_question and "\nEvidence:" in question:
        raw_question, embedded = question.split("\nEvidence:", 1)
        evidence = evidence or embedded.strip()
    return (raw_question or question).strip(), evidence


def _evidence_clauses(evidence: str) -> List[str]:
    return [
        re.sub(r"\s+", " ", clause).strip(" .")
        for clause in re.split(r"[;\n]+", evidence or "")
        if clause.strip(" .")
    ]


def _expression_identifiers(evidence: str) -> List[str]:
    identifiers: List[str] = []
    identifiers.extend(re.findall(r"`([^`]{1,80})`", evidence or ""))
    parse_evidence = re.sub(r"`[^`]+`", "", evidence or "")

    for argument in re.findall(rf"\b(?:{_FUNCTION_PATTERN})\s*\(([^()]*)\)", parse_evidence, re.IGNORECASE):
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", argument):
            token = token.strip()
            if token and token.lower() not in _FUNCTIONS and token.lower() not in _IDENTIFIER_STOPWORDS:
                identifiers.append(token)

    for raw_clause in _evidence_clauses(evidence):
        clause = re.sub(r"`[^`]+`", "", raw_clause)
        expression = re.split(r"refers?\s+to", clause, maxsplit=1, flags=re.IGNORECASE)[-1].strip()
        for left in re.findall(
            r"(?:^|\bAND\b|\bOR\b|,)\s*[`\"]?([A-Za-z_][A-Za-z0-9_ -]{0,50}?)[`\"]?\s*(?=>=|<=|<>|!=|=|>|<)",
            expression,
            flags=re.IGNORECASE,
        ):
            value = left.strip()
            if value and " " not in value and value.lower() not in _IDENTIFIER_STOPWORDS:
                identifiers.append(value)
        if "+" in expression and "refers to" in clause.lower():
            identifiers.extend(
                token.strip(" `\"")
                for token in expression.split("+")
                if re.fullmatch(r"\s*[`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?\s*", token)
            )
        mapping = re.search(
            r"(?:refers?\s+to|=)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\+|,|\band\b)\s*([A-Za-z_][A-Za-z0-9_]*)\s*$",
            clause,
            flags=re.IGNORECASE,
        )
        if mapping:
            identifiers.extend(mapping.groups())
    return _unique(re.sub(r"\s+", " ", value).strip() for value in identifiers)


def _evidence_literals(evidence: str) -> List[str]:
    quoted = [
        value.strip() for value in re.findall(r"['\"]([^'\"]{1,100})['\"]", evidence or "")
        if value.strip() and not value.strip().startswith("%")
    ]
    numbers = re.findall(r"(?<![A-Za-z_])(?:19|20)\d{2}(?:[-/]\d{1,2}){0,2}|(?<=[<>=])\s*-?\d+(?:\.\d+)?", evidence or "")
    return _unique(quoted + [value.strip() for value in numbers])[:16]


def _requested_segments(question: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", question.strip()).strip(" ?.")
    segments: List[str] = []
    patterns = (
        r"^(?:please\s+)?(?:list|show|provide|give|return|write|state)\s+(?:me\s+)?(.+)$",
        r"\bwhat\s+(?:is|are|was|were)\s+(.+)$",
        r"^which\s+(?:is|are|was|were)\s+(.+)$",
    )
    only_segments: List[str] = []
    for sentence in re.split(r"[?.]+", normalized):
        sentence = sentence.strip()
        if not sentence:
            continue
        initial_entity = re.match(r"^(?:which|who)\s+(.+)$", sentence, re.IGNORECASE)
        if initial_entity:
            value = _OUTPUT_BOUNDARIES.split(initial_entity.group(1), maxsplit=1)[0].strip(" ,")
            if value:
                segments.append(value)
        for pattern in patterns:
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if not match:
                continue
            captured = match.group(1)
            captured = _OUTPUT_BOUNDARIES.split(captured, maxsplit=1)[0].strip(" ,")
            if captured:
                segments.append(captured)
            break
        if re.search(r"\bhow much\b", sentence, re.IGNORECASE):
            segments.append("amount")
        if re.search(r"\bhow many\b", sentence, re.IGNORECASE):
            segments.append("count")
        calculation = re.search(
            r"^(?:please\s+)?(?:calculate|compute)\s+(.+)$", sentence, re.IGNORECASE,
        )
        if calculation:
            value = _OUTPUT_BOUNDARIES.split(calculation.group(1), maxsplit=1)[0].strip(" ,")
            if value:
                segments.append(value)
        for match in re.finditer(
            r"\b(only\s+)?(?:indicate|give|provide|show|include|list)\s+(.+)$",
            sentence, re.IGNORECASE,
        ):
            value = _OUTPUT_BOUNDARIES.split(match.group(2), maxsplit=1)[0].strip(" ,")
            if value:
                segments.append(value)
                if match.group(1):
                    only_segments.append(value)
    if only_segments:
        return _unique(only_segments)
    return _unique(segments)


def _split_output_terms(segment: str) -> List[str]:
    cleaned = re.sub(r"^(?:the|all|out of)\s+", "", segment.strip(), flags=re.IGNORECASE)
    separator = r"\s+and\s+" if re.search(r"\bor\b", cleaned, re.IGNORECASE) else r"\s*,\s*|\s+and\s+"
    parts = [part.strip(" ,") for part in re.split(separator, cleaned, flags=re.IGNORECASE)]
    merged: List[str] = []
    for part in (part for part in parts if part):
        if merged:
            previous_word = re.findall(r"[A-Za-z]+", merged[-1])[-1:]
            next_word = re.findall(r"[A-Za-z]+", part)[:1]
            if previous_word and next_word and previous_word[0][:1].isupper() and next_word[0][:1].isupper():
                merged[-1] += " and " + part
                continue
        merged.append(part)
    return merged


def _output_contract(question: str, evidence: str) -> Dict[str, Any]:
    lowered = question.lower()
    segments = _requested_segments(question)
    terms = _unique(term for segment in segments for term in _split_output_terms(segment))
    if len(segments) >= 2 and len(terms) >= 2:
        first = terms[0]
        later = terms[1:]
        first_has_attribute = bool(re.search(
            r"\b(id|name|title|code|number|date|time|amount|count|percentage|percent|average|sum|total|rate)\b",
            first, re.IGNORECASE,
        ))
        later_identifies_entity = any(
            re.search(r"\b(id|name|title|code)\b", term, re.IGNORECASE) for term in later
        )
        if len(first.split()) <= 4 and not first_has_attribute and later_identifies_entity:
            terms = later
    scalar_signal = bool(re.search(
        r"\b(how many|number of|count of|percentage|percent|total number|difference in)\b",
        lowered,
    )) or bool(re.search(
        r"\b(?:what is|what was|calculate|compute|find|give|provide)\s+(?:the\s+)?"
        r"(?:average|mean|sum|total|maximum|minimum|max|min|difference)\b",
        lowered,
    ))
    scalar = scalar_signal and len(terms) <= 1
    expected = 1 if scalar else len(terms) if terms else None
    confidence = "high" if scalar or len(terms) >= 2 else "medium" if expected == 1 else "low"

    full_name = re.search(
        r"full name(?:\s+of\s+[A-Za-z_][A-Za-z0-9_ ]*)?\s*(?:refers?\s+to|=)\s*"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\+|,|\band\b)\s*([A-Za-z_][A-Za-z0-9_]*)",
        evidence or "", flags=re.IGNORECASE,
    )
    physical_columns: List[str] = []
    if full_name and "full name" in lowered:
        physical_columns = [full_name.group(1), full_name.group(2)]
        if expected is None:
            expected = 2
        else:
            expected += 1  # one logical "full name" term expands to two columns
        confidence = "high"

    if expected is None and re.match(r"\s*(?:who|which|what)\b", lowered):
        expected, confidence = 1, "medium"
    return {
        "minimal_projection": True,
        "requested_segments": segments,
        "requested_terms": terms,
        "physical_output_columns": physical_columns,
        "expected_projection_count": expected,
        "projection_confidence": confidence,
        "scalar": scalar,
    }


def compile_semantic_contract(item: Dict[str, Any]) -> Dict[str, Any]:
    question, evidence = _split_question_evidence(item)
    operations = [name for name, pattern in _OPERATION_PATTERNS if re.search(pattern, evidence, re.IGNORECASE)]
    output = _output_contract(question, evidence)
    return {
        "schema_version": "1.0",
        "raw_question": question,
        "evidence": evidence,
        "evidence_clauses": _evidence_clauses(evidence),
        "required_columns": _expression_identifiers(evidence),
        "required_literals": _evidence_literals(evidence),
        "required_operations": operations,
        "output": output,
        "rules": [
            "Use evidence formulas and comparison boundaries literally.",
            "Return only requested output fields; filter/order/helper fields are not output fields.",
            "Do not add DISTINCT, latest-row logic, deduplication, or extra grouping unless requested.",
            "Keep physical output columns separate when evidence expands a logical phrase into multiple fields.",
        ],
    }


def semantic_contract_prompt(contract: Dict[str, Any]) -> str:
    output = contract.get("output", {})
    marker = (
        "SLAYQL_V19_SEMANTIC_CONTRACT" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else
        "SLAYQL_V18_SEMANTIC_CONTRACT" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.8" else
        "SLAYQL_V17_SEMANTIC_CONTRACT" if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.7" else
        "SLAYQL_V16_SEMANTIC_CONTRACT"
    )
    lines = [
        f"-- {marker} --",
        f"Evidence clauses: {contract.get('evidence_clauses') or ['none']}",
        f"Required mapped columns: {contract.get('required_columns') or ['none']}",
        f"Required literals: {contract.get('required_literals') or ['none']}",
        f"Required formula operations: {contract.get('required_operations') or ['none']}",
        f"Requested output terms: {output.get('requested_terms') or output.get('requested_segments') or ['minimal direct answer']}",
        f"Expected outer projection count: {output.get('expected_projection_count')} ({output.get('projection_confidence', 'low')} confidence)",
        f"Physical output columns: {output.get('physical_output_columns') or ['none']}",
    ]
    lines.extend(f"- {rule}" for rule in contract.get("rules", []))
    return "\n".join(lines)


def physical_projection_check(
    sql: str, structure: Dict[str, Any], contract: Dict[str, Any],
) -> Dict[str, Any]:
    """Hard v1.9 gate for high-confidence physical output slots.

    A logical label such as ``full name`` is sometimes represented by several
    benchmark columns.  Execution success alone cannot distinguish a
    concatenated/under-projected answer, so v1.9 rejects it before selection.
    Contracts without physical expansion remain neutral.
    """
    output = contract.get("output", {}) or {}
    columns = [str(value) for value in output.get("physical_output_columns", []) if str(value).strip()]
    expected = output.get("expected_projection_count")
    if not columns or output.get("projection_confidence") != "high" or expected is None:
        return {"passed": None, "reason": "no high-confidence physical output expansion"}
    normalized_sql = _normalized(sql)
    missing = [column for column in columns if _normalized(column) not in normalized_sql]
    actual = int(structure.get("projection_count", 0) or 0)
    passed = actual == int(expected) and not missing
    return {
        "passed": passed,
        "expected_projection_count": int(expected),
        "actual_projection_count": actual,
        "required_columns": columns,
        "missing_columns": missing,
        "reason": "all physical output slots are present" if passed else "physical output slots/count do not match the contract",
    }


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def assess_semantic_contract(
    sql: str, structure: Dict[str, Any], contract: Dict[str, Any],
) -> Dict[str, Any]:
    sql_lower = str(sql or "").lower()
    sql_normalized = _normalized(sql)
    checks: List[Dict[str, Any]] = []

    for column in contract.get("required_columns", []):
        passed = bool(_normalized(column)) and _normalized(column) in sql_normalized
        checks.append({"name": f"evidence_column:{column}", "passed": passed, "weight": 0.7})
    for literal in contract.get("required_literals", []):
        passed = _normalized(literal) in sql_normalized
        checks.append({"name": f"evidence_literal:{literal}", "passed": passed, "weight": 0.8})

    aggregations = set(structure.get("aggregations", []))
    order_by = structure.get("order_by", [])
    limit = structure.get("limit")
    for operation in contract.get("required_operations", []):
        if operation in {"count", "sum", "avg", "group_concat"}:
            passed = operation in aggregations or operation in sql_lower
        elif operation == "max":
            passed = "max" in aggregations or (bool(order_by) and bool(order_by[0].get("descending")) and limit is not None)
        elif operation == "min":
            passed = "min" in aggregations or (bool(order_by) and not bool(order_by[0].get("descending")) and limit is not None)
        elif operation == "divide":
            passed = "/" in sql_lower
        elif operation == "subtract":
            passed = "-" in sql_lower
        elif operation == "multiply":
            passed = "*" in sql_lower
        elif operation == "distinct":
            passed = bool(structure.get("select_distinct") or structure.get("aggregate_distinct"))
        else:
            passed = operation in set(structure.get("set_operations", [])) or operation in sql_lower
        checks.append({"name": f"evidence_operation:{operation}", "passed": bool(passed), "weight": 0.9})

    output = contract.get("output", {})
    expected = output.get("expected_projection_count")
    confidence = output.get("projection_confidence")
    if expected is not None and confidence == "high":
        checks.append({
            "name": "minimal_output_projection",
            "passed": int(structure.get("projection_count", 0)) == int(expected),
            "weight": 1.3,
            "detail": f"expected={expected}; actual={structure.get('projection_count', 0)}",
        })
    distinct_requested = "distinct" in contract.get("required_operations", []) or "distinct" in contract.get("raw_question", "").lower()
    if not distinct_requested:
        checks.append({
            "name": "no_unrequested_distinct",
            "passed": not bool(structure.get("select_distinct") or structure.get("aggregate_distinct")),
            "weight": 0.8,
        })

    total = sum(float(check["weight"]) for check in checks)
    passed = sum(float(check["weight"]) for check in checks if check["passed"])
    failed = sum(float(check["weight"]) for check in checks if not check["passed"])
    return {
        "score": passed / total if total else 0.5,
        "penalty": failed / total if total else 0.0,
        "checks": checks,
    }

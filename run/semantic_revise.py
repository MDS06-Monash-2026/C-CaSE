"""Selective execution-grounded semantic candidate generation for SlayQL v1.7-v1.9.

Unlike the legacy revision stage, this stage targets executable candidates that
remain semantically uncertain.  It never overwrites a generated candidate: one
accepted repair is exposed to the selector as an additional candidate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

from artifact_store import atomic_write_json, atomic_write_text
from prompt_learning import load_prompt
from semantic_contract import assess_semantic_contract, compile_semantic_contract, physical_projection_check
from selector_first import (
    _candidate_structure,
    _compact_interaction_evidence,
    _interaction_grounding,
    _result_preview,
    collect_candidates,
    select_instance,
)
from sql_revise import thread_safe_sql_execution
from semantic_validator import dataframe_signature
from usage_accounting import record_response_usage


_write_lock = threading.Lock()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def _extract_sql(content: str) -> str:
    blocks = re.findall(r"```sql\s*(.*?)\s*```", content or "", flags=re.IGNORECASE | re.DOTALL)
    if not blocks:
        blocks = re.findall(r"```\s*(.*?)\s*```", content or "", flags=re.DOTALL)
    if blocks:
        return max((block.strip() for block in blocks if block.strip()), key=len, default="")
    match = re.search(r"\b(?:WITH|SELECT)\b.*", content or "", flags=re.IGNORECASE | re.DOTALL)
    return match.group(0).strip().rstrip("`").strip() if match else ""


def _semantic_failures(candidate: Dict[str, Any]) -> Tuple[float, List[str]]:
    checks = candidate.get("semantic_contract_checks", [])
    total = sum(float(check.get("weight", 0.0)) for check in checks)
    failed = [check for check in checks if check.get("passed") is False]
    failed_weight = sum(float(check.get("weight", 0.0)) for check in failed)
    return failed_weight / total if total else 0.0, [str(check.get("name")) for check in failed]


def repair_trigger(
    selection: Dict[str, Any], interaction: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a target-label-free repair decision for one instance."""
    selected = selection["selected"]
    candidates = selection["candidates"]
    version = os.environ.get("SLAYQL_RESEARCH_VERSION")
    semantic = (interaction or {}).get("semantic_contract", {}) or {}
    physical = physical_projection_check(selected.get("sql", ""), selected.get("structure", {}), semantic)
    physical_failure = version == "1.9" and physical.get("passed") is False
    if not selected.get("executed") or (not selected.get("eligible") and not physical_failure):
        return {"triggered": False, "reasons": ["selected_candidate_not_executable_and_eligible"]}
    hashes = [candidate.get("result_hash") for candidate in candidates if candidate.get("executed")]
    unique_hashes = {value for value in hashes if value}
    if len(unique_hashes) <= 1 and not physical_failure:
        return {"triggered": False, "reasons": ["executed_candidates_agree"]}

    selected_hash = selected.get("result_hash")
    support = sum(value == selected_hash for value in hashes) if selected_hash else 0
    penalty, failures = _semantic_failures(selected)
    evidence_backed = bool(
        semantic.get("evidence_clauses")
        or semantic.get("required_columns")
        or semantic.get("required_literals")
        or semantic.get("required_operations")
    )
    margin = float(selected.get("selection", {}).get("margin", 1.0))
    material_failures = {
        failure for failure in failures
        if failure.startswith(("evidence_", "minimal_output_projection"))
    }
    reasons = []
    if physical_failure:
        reasons.append("physical_output_projection_failure")
    if penalty >= 0.20 and material_failures:
        reasons.append("material_semantic_contract_failure")
    if evidence_backed and support <= 1 and margin < 0.18:
        reasons.append("unsupported_result_under_evidence_disagreement")
    return {
        "triggered": bool(reasons), "reasons": reasons or ["uncertainty_below_repair_threshold"],
        "selected_candidate": selected.get("candidate_id"), "result_support": support,
        "executed_candidate_count": len(hashes), "unique_result_count": len(unique_hashes),
        "score_margin": margin, "semantic_penalty": penalty, "semantic_failures": failures,
    }


def _dialect(instance_id: str) -> str:
    if instance_id.startswith(("bq", "ga")):
        return "BigQuery"
    if instance_id.startswith("sf"):
        return "Snowflake"
    return "SQLite"


def _repair_prompt(
    instance_id: str, item: Dict[str, Any], schema: str, selection: Dict[str, Any],
    interaction: Dict[str, Any], trigger: Dict[str, Any], demonstrations: str,
) -> str:
    selected = selection["selected"]
    alternatives = []
    for candidate in selection["candidates"]:
        alternatives.append({
            "candidate_id": candidate.get("candidate_id"), "sql": candidate.get("sql"),
            "score": candidate.get("score"), "semantic_checks": candidate.get("semantic_contract_checks", []),
            "result": _result_preview(candidate),
        })
    demonstration_block = f"\n{demonstrations}\n" if demonstrations else ""
    return (
        f"You are the SlayQL v{os.environ.get('SLAYQL_RESEARCH_VERSION', '1.7')} execution-grounded SQL agent. Produce one corrected SQL query only. "
        "The current query executes, but independent candidates disagree and deterministic checks found a semantic risk. "
        "Use the actual result shape and values as observations, not as proof of correctness. Re-ground the user intent, "
        "evidence formula, relation path, filters, row grain, and exact requested projection in the schema. Preserve all "
        "explicit comparison boundaries and literals. Do not invent DISTINCT, deduplication, latest-row logic, helper "
        "output columns, or an alternative business metric. Return exactly one fenced SQL block and no explanation.\n"
        f"Dialect: {_dialect(instance_id)}\n"
        f"Question: {item.get('question', '')}\n"
        f"Semantic evidence: {json.dumps(_compact_interaction_evidence(interaction), default=str)}\n"
        f"Repair trigger: {json.dumps(trigger, default=str)}\n"
        f"Current selected SQL: {selected.get('sql', '')}\n"
        f"Executed candidates: {json.dumps(alternatives, default=str)}\n"
        f"Schema:\n{schema[:160000]}\n"
        f"{demonstration_block}"
        + ("v1.9 repair rule: satisfy every physical output slot separately; never collapse multiple required columns into one expression.\n"
           if os.environ.get("SLAYQL_RESEARCH_VERSION") == "1.9" else "")
        + "Now repair the current question. Return exactly one fenced SQL block using only current-schema identifiers."
    )


def _atomic_write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    os.close(descriptor)
    try:
        frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


class SemanticReviser:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1",
            # Per-request timeout in seconds; 600 is the OpenAI SDK default.
            timeout=float(os.environ.get("SLAYQL_API_TIMEOUT", "600")),
        )
        self.model = os.environ.get("MODEL_NAME")

    def request(self, instance_id: str, prompt: str, response_path: Path) -> Dict[str, Any]:
        cached = _read_json(response_path)
        if isinstance(cached, dict) and cached.get("sql"):
            return cached
        last_error = "unknown API error"
        for attempt in range(1, 4):
            response = None
            try:
                started = time.monotonic()
                response = self.client.chat.completions.create(
                    model=self.model, messages=[{"role": "user", "content": prompt}],
                )
                record_response_usage(
                    response, stage="semantic_revision", instance_id=instance_id,
                    candidate_id="repair", attempt=attempt,
                    latency_ms=(time.monotonic() - started) * 1000,
                )
                content = response.choices[0].message.content or ""
                sql = _extract_sql(content)
                if not sql:
                    raise ValueError("semantic repair returned no SQL")
                payload = {"schema_version": os.environ.get("SLAYQL_RESEARCH_VERSION", "1.7"), "instance_id": instance_id, "sql": sql, "content": content}
                atomic_write_json(str(response_path), payload)
                return payload
            except Exception as error:
                if response is None:
                    record_response_usage(
                        None, stage="semantic_revision", instance_id=instance_id,
                        candidate_id="repair", attempt=attempt,
                    )
                last_error = str(error)
                if attempt < 3:
                    time.sleep(min(2 ** (attempt - 1), 4))
        raise RuntimeError(f"Semantic repair API failed for {instance_id}: {last_error}")


def _evaluate_repair(
    instance_id: str, sql: str, frame: pd.DataFrame, parent: Dict[str, Any],
    interaction: Dict[str, Any], base_candidates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    structure = _candidate_structure(sql, instance_id)
    contract = interaction.get("semantic_contract") or compile_semantic_contract({
        "question": interaction.get("question", "")
    })
    parent_assessment = assess_semantic_contract(parent.get("sql", ""), parent["structure"], contract)
    assessment = assess_semantic_contract(sql, structure, contract)
    candidate = {"sql": sql, "structure": structure, "frame": frame}
    parent_grounding = float(parent.get("score_parts", {}).get("evidence", 0.0))
    grounding = _interaction_grounding(candidate, interaction)
    query_safe = (
        structure.get("statement_count") == 1 and structure.get("query_only")
        and bool(structure.get("tables"))
    )
    semantic_delta = float(assessment["score"]) - float(parent_assessment["score"])
    semantic_non_regression = assessment["score"] + 0.05 >= parent_assessment["score"]
    grounding_non_regression = grounding + 0.15 >= parent_grounding
    repair_signature = dataframe_signature(frame)
    existing_signatures = {
        dataframe_signature(candidate["frame"])
        for candidate in (base_candidates or [])
        if candidate.get("frame") is not None
    }
    repair_result_novel = repair_signature not in existing_signatures
    version = os.environ.get("SLAYQL_RESEARCH_VERSION")
    strict_v18 = version == "1.8"
    strict_v19 = version == "1.9"
    # v1.7 accepted too many duplicate or weak repairs.  v1.8 only exposes a
    # repair when it is a genuinely new result and strictly improves the
    # semantic contract, leaving the original candidate set untouched.
    parent_physical = physical_projection_check(parent.get("sql", ""), parent["structure"], contract)
    repair_physical = physical_projection_check(sql, structure, contract)
    if strict_v19:
        accepted = bool(
            query_safe and repair_result_novel and grounding >= parent_grounding
            and assessment["score"] >= 0.50
            and (repair_physical.get("passed") is True or (
                parent_physical.get("passed") is not False and semantic_delta >= 0.05
            ))
        )
    elif strict_v18:
        accepted = bool(
            query_safe and repair_result_novel and semantic_delta >= 0.10
            and grounding >= parent_grounding
            and assessment["score"] >= 0.55
        )
    else:
        accepted = bool(query_safe and semantic_non_regression and grounding_non_regression)
    return {
        "accepted": accepted, "query_safe": query_safe,
        "parent_semantic_score": parent_assessment["score"],
        "repair_semantic_score": assessment["score"],
        "semantic_delta": semantic_delta,
        "parent_grounding_score": parent_grounding, "repair_grounding_score": grounding,
        "repair_result_novel": repair_result_novel,
        "strict_v18_gate": strict_v18,
        "strict_v19_gate": strict_v19,
        "parent_physical_projection": parent_physical,
        "repair_physical_projection": repair_physical,
        "repair_semantic_checks": assessment["checks"],
        "result_shape": {"rows": int(len(frame)), "columns": int(len(frame.columns))},
    }


def process_instance(
    reviser: SemanticReviser, data: Dict[str, Dict[str, Any]], log_path: Path,
    schema_dir: Path, task: str, count: int, instance_id: str,
) -> Dict[str, Any]:
    decision_path = log_path / "semantic_revise" / "decisions" / f"{instance_id}.json"
    existing = _read_json(decision_path)
    if isinstance(existing, dict) and existing.get("status") == "complete":
        return existing
    item = data[instance_id]
    if instance_id.startswith("sf"):
        decision = {
            "schema_version": os.environ.get("SLAYQL_RESEARCH_VERSION", "1.7"), "instance_id": instance_id, "status": "complete",
            "triggered": False, "accepted": False, "reasons": ["snowflake_excluded_or_credentials_unavailable"],
        }
        atomic_write_json(str(decision_path), decision)
        return decision

    interaction = _read_json(log_path / "interaction" / f"{instance_id}.json", {}) or {}
    candidates = collect_candidates(log_path, task, instance_id, count)
    selection = select_instance(instance_id, candidates, item.get("question", ""), item, allow_verification=False)
    trigger = repair_trigger(selection, interaction)
    if not trigger["triggered"]:
        decision = {
            "schema_version": os.environ.get("SLAYQL_RESEARCH_VERSION", "1.7"), "instance_id": instance_id, "status": "complete",
            "accepted": False, **trigger,
        }
        atomic_write_json(str(decision_path), decision)
        return decision

    schema_path = schema_dir / f"{instance_id}.txt"
    schema = schema_path.read_text(encoding="utf-8", errors="replace")
    prompt = _repair_prompt(
        instance_id, item, schema, selection, interaction, trigger,
        load_prompt(str(log_path), instance_id),
    )
    response_path = log_path / "semantic_revise" / "responses" / f"{instance_id}.json"
    response = reviser.request(instance_id, prompt, response_path)
    sql = response["sql"]
    state, execution = thread_safe_sql_execution(instance_id, sql, item.get("db_name"))
    accepted = False
    validation: Dict[str, Any] = {"execution_status": state}
    output_candidate = count
    if state == "success" and isinstance(execution, pd.DataFrame):
        validation.update(_evaluate_repair(
            instance_id, sql, execution, selection["selected"], interaction,
            selection.get("candidates", []),
        ))
        accepted = bool(validation["accepted"])
        if accepted:
            output_dir = log_path / "semantic_revise" / f"{task}_sql_{output_candidate}"
            atomic_write_text(str(output_dir / f"{instance_id}.sql"), sql)
            _atomic_write_frame(output_dir / f"{instance_id}.csv", execution)
    else:
        validation["execution_error"] = str(execution)[:1000]
    decision = {
        "schema_version": os.environ.get("SLAYQL_RESEARCH_VERSION", "1.7"), "instance_id": instance_id, "status": "complete",
        **trigger, "accepted": accepted,
        "parent_candidate": selection["selected"].get("candidate_id"),
        "output_candidate": output_candidate if accepted else None,
        "response_path": str(response_path.resolve()), "validation": validation,
    }
    atomic_write_json(str(decision_path), decision)
    return decision


def run(
    data_file: str, schema_dir: str, log_path: str, task: str = "r1_lite",
    count: int = 5, workers: int = 4,
) -> Dict[str, Any]:
    data = json.loads(Path(data_file).read_text(encoding="utf-8"))
    root, schemas = Path(log_path).resolve(), Path(schema_dir).resolve()
    pending = []
    for instance_id in sorted(data):
        decision = _read_json(root / "semantic_revise" / "decisions" / f"{instance_id}.json", {})
        if not isinstance(decision, dict) or decision.get("status") != "complete":
            pending.append(instance_id)
    print(f"Semantic revision pending instances: {len(pending)}", flush=True)
    reviser = SemanticReviser()
    errors = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(process_instance, reviser, data, root, schemas, task, count, instance_id): instance_id
            for instance_id in pending
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Semantic revision", dynamic_ncols=True):
            instance_id = futures[future]
            try:
                future.result()
            except Exception as error:
                errors.append({"instance_id": instance_id, "error": str(error)})
    if errors:
        atomic_write_json(str(root / "semantic_revise" / "failed.json"), errors)
        raise RuntimeError(f"Semantic revision failed for {len(errors)} instance(s): {errors[:3]}")
    decisions = [
        _read_json(path, {}) for path in sorted((root / "semantic_revise" / "decisions").glob("*.json"))
    ]
    manifest = {
        "schema_version": os.environ.get("SLAYQL_RESEARCH_VERSION", "1.7"), "stage": "semantic_revision", "record_count": len(decisions),
        "triggered": sum(bool(item.get("triggered")) for item in decisions),
        "accepted": sum(bool(item.get("accepted")) for item in decisions),
        "max_repairs_per_instance": 1,
    }
    atomic_write_json(str(root / "semantic_revise_manifest.json"), manifest)
    print(
        f"Semantic revision finished: triggered={manifest['triggered']}, accepted={manifest['accepted']}",
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="SlayQL v1.7-v1.9 selective semantic revision")
    parser.add_argument("--data_file", required=True)
    parser.add_argument("--schema_dir", required=True)
    parser.add_argument("--log_path", required=True)
    parser.add_argument("--task", default="r1_lite")
    parser.add_argument("--num_candidates", type=int, default=5)
    parser.add_argument("--num_workers", type=int, default=4)
    args = parser.parse_args()
    run(args.data_file, args.schema_dir, args.log_path, args.task, args.num_candidates, args.num_workers)


if __name__ == "__main__":
    main()

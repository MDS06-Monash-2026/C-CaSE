import os
import json
import re
import time
import random
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from config import *
from tqdm import tqdm
from dotenv import load_dotenv
from artifact_store import atomic_write_json, atomic_write_text
from candidate_router import build_route_hypotheses, render_routed_schema, route_for_candidate
from prompt_learning import load_prompt

load_dotenv()


class Config:
    INITIAL_RETRY_DELAY = 1
    MAX_RETRY_DELAY = 30
    MAX_RETRIES = 5


class TaskGenerationError(Exception):
    def __init__(self, instance_id: str, candidate_idx: int, reason: str):
        self.instance_id = instance_id
        self.candidate_idx = candidate_idx
        self.reason = reason
        super().__init__(f"{instance_id} (candidate {candidate_idx}): {reason}")


def candidate_guidance(candidate_idx: int) -> str:
    """Give same-budget candidates distinct reasoning priorities to reduce correlated errors."""
    version = os.environ.get("SLAYQL_RESEARCH_VERSION")
    if version == "1.9":
        roles = (
            "Build the query from the explicit output slots first, then connect their source tables using the smallest supported relation path.",
            "Audit every requested output column against the assigned schema route; keep physical columns separate even when the question uses a logical phrase such as full name.",
            "Use the full-schema recall fallback and semantic contract. Resolve ambiguous identifiers from observed values and return the exact requested grain.",
            "Test join cardinality and filter scope before aggregation. Use EXISTS or pre-aggregation only when it preserves the requested row semantics.",
            "Act as an adversarial contract reviewer: check output arity, relation endpoints, literals, grouping, ordering, and tie semantics before emitting SQL.",
        )
        return (
            "\n\n[SLAYQL_V19_CANDIDATE_ROLE]\n"
            f"Candidate {candidate_idx}: {roles[candidate_idx % len(roles)]}\n"
            "v1.9 uses an adaptive schema view. The semantic contract and database observations are authoritative. "
            "Never hide a required output-bearing table, concatenate separate requested fields, or expose join/filter helper fields."
        )
    if version == "1.8":
        roles = (
            "Use the measured primary relation route and make the answer-plan grain explicit before writing SQL.",
            "Independently test the measured alternative join route; preserve predicates on the table where the question defines them.",
            "Use the full-schema recall fallback plus the answer plan. Resolve ambiguous fields from observed values and return only requested columns.",
            "Audit aggregation grain and join fan-out. Prefer pre-aggregation or EXISTS when the measured route shows many-to-many risk.",
            "Act as an adversarial plan reviewer: challenge table choice, join direction, literal boundaries, grouping, ordering, and tie semantics.",
        )
        return (
            "\n\n[SLAYQL_V18_CANDIDATE_ROLE]\n"
            f"Candidate {candidate_idx}: {roles[candidate_idx % len(roles)]}\n"
            "The v1.8 answer plan, semantic contract, and database observations constrain this candidate. "
            "Do not expose helper fields or invent DISTINCT, deduplication, latest-row logic, grouping, or formula substitutions."
        )
    if version == "1.7":
        roles = (
            "Apply the retrieved training structures only after re-grounding every identifier; implement the primary relation route literally.",
            "Independently validate the alternative relation route, join direction, filter scope, and evidence formula.",
            "Use the full-schema recall fallback plus training structures, but return only the explicitly requested projection.",
            "Challenge aggregation grain, predicate placement, set behavior, ranking direction, and tie semantics on the counterfactual route.",
            "Audit all relation endpoints, evidence literals, formula operations, and requested output fields without copying another candidate.",
        )
        return (
            "\n\n[SLAYQL_V17_CANDIDATE_ROLE]\n"
            f"Candidate {candidate_idx}: {roles[candidate_idx % len(roles)]}\n"
            "The semantic contract and current database evidence are authoritative. Training examples teach reusable structure only. "
            "Do not add identity/helper fields, DISTINCT, latest-row logic, deduplication, grouping, or formula substitutions unless requested."
        )
    if version == "1.6":
        roles = (
            "Use the assigned primary relation route and implement the evidence formula literally.",
            "Use the assigned alternative route; verify its join keys without drifting back to the primary route.",
            "Use the full-schema recall fallback, but choose the smallest supported path and minimal requested projection.",
            "Use the assigned counterfactual route and check aggregation grain, grouping, ordering, and set behavior.",
            "Audit the assigned route against evidence literals, formula operations, and exact requested output fields.",
        )
        return (
            "\n\n[SLAYQL_V16_CANDIDATE_ROLE]\n"
            f"Candidate {candidate_idx}: {roles[candidate_idx % len(roles)]}\n"
            "The semantic contract is authoritative. Do not substitute a more plausible metric, add DISTINCT, "
            "invent latest-row logic, deduplicate rows, or expose helper columns unless explicitly requested."
        )
    if version == "1.5":
        roles = (
            "Lock the requested output columns and row grain, then build the most direct evidence-grounded query.",
            "Use the relational DDL view. Trace a complete join path, including bridge tables, and verify every join key.",
            "Plan in execution order: row source, joins, filters, aggregation, then projection/order/limit. Preserve literal operators exactly.",
            "Construct a counterfactual relation path. Challenge the most obvious table or metric and use a genuinely different valid path when one exists.",
            "Act as an adversarial semantic reviewer. Reject unrequested DISTINCT, deduplication, latest-row logic, concatenation, and output columns.",
        )
        return (
            "\n\n[SLAYQL_V15_CANDIDATE_ROLE]\n"
            f"Candidate {candidate_idx}: {roles[candidate_idx % len(roles)]}\n"
            "This candidate must independently map every requested output to a schema field. "
            "Database evidence is authoritative; a merely plausible business interpretation is not."
        )
    roles = (
        "Build the most direct schema-grounded query. Verify the requested output grain before writing SQL.",
        "Trace the complete relationship path first. Verify every join key and avoid accidental row multiplication.",
        "Validate filters, literals, dates, NULL behavior, and DISTINCT semantics against the observed database evidence.",
        "Use an independent CTE or aggregation formulation and check grouping, ranking, ordering, and limits.",
        "Act as an adversarial semantic reviewer before finalizing: look for plausible-but-wrong tables, joins, and metrics.",
    )
    marker = (
        "SLAYQL_V14_CANDIDATE_ROLE" if version == "1.4" else
        "SLAYQL_V13_CANDIDATE_ROLE" if version == "1.3" else
        "SLAYQL_V12_CANDIDATE_ROLE"
    )
    version_checklist = (
        " Before final SQL, explicitly reconcile the requested entity, output columns, and ordinal/ranking semantics."
        if version in {"1.3", "1.4"} else ""
    )
    if version == "1.4":
        version_checklist += (
            " Treat the question plan and linked join endpoints as constraints; do not use a merely similar table or value."
        )
    return (
        f"\n\n[{marker}]\n"
        f"Candidate {candidate_idx}: {roles[candidate_idx % len(roles)]}\n"
        "This is an independent candidate. Do not copy a presumed answer; use the schema, interaction evidence, and tool results."
        + version_checklist
    )


def relational_schema_view(evidence: Dict, schema_tables: Optional[List[str]] = None) -> str:
    """Build a bounded DDL-style view that emphasizes alternative join paths."""
    closure = evidence.get("relational_closure", {}) if isinstance(evidence, dict) else {}
    table_order = [link.get("table") for link in evidence.get("value_links", []) if link.get("table")]
    table_order.extend(closure.get("seed_tables", []))
    table_order.extend(schema_tables or [])
    table_order.extend(closure.get("tables", []))
    table_order.extend(
        entry.get("table") for entry in evidence.get("lexical_matches", []) if entry.get("table")
    )
    table_order = list(dict.fromkeys(str(table) for table in table_order if table))[:8]
    selected_table_keys = {table.lower().split(".")[-1] for table in table_order}
    edge_candidates = list(closure.get("edges", [])) + list(evidence.get("relationship_catalog", []))
    edges = []
    seen_edges = set()
    for edge in edge_candidates:
        edge_key = (
            str(edge.get("from_table", "")).lower(), str(edge.get("from_column", "")).lower(),
            str(edge.get("to_table", "")).lower(), str(edge.get("to_column", "")).lower(),
        )
        endpoints = {edge_key[0].split(".")[-1], edge_key[2].split(".")[-1]}
        if not endpoints.issubset(selected_table_keys) or edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append(edge)
        if len(edges) >= 16:
            break
    tables = {
        str(table.get("name", "")).lower().split(".")[-1]: table
        for table in evidence.get("tables", []) if isinstance(table, dict) and table.get("name")
    }
    linked_columns: Dict[str, set] = {}
    for entry in evidence.get("lexical_matches", []):
        table, column = entry.get("table"), entry.get("column")
        if table and column:
            linked_columns.setdefault(str(table).lower().split(".")[-1], set()).add(str(column).lower())
    for edge in edges:
        for table_key, column_key in (("from_table", "from_column"), ("to_table", "to_column")):
            table, column = edge.get(table_key), edge.get(column_key)
            if table and column:
                linked_columns.setdefault(str(table).lower().split(".")[-1], set()).add(str(column).lower())

    lines = [
        "-- SLAYQL_V15_RELATIONAL_DDL_VIEW --",
        "-- Complementary view: reason over these relation paths, then verify against the full schema above.",
    ]
    for requested_table in table_order:
        table_key = requested_table.lower().split(".")[-1]
        table = tables.get(table_key)
        if not table:
            continue
        columns = table.get("columns", [])
        normalized = []
        for column in columns:
            if isinstance(column, dict):
                normalized.append((str(column.get("name", "")), str(column.get("type", "UNKNOWN")), bool(column.get("primary_key"))))
            else:
                normalized.append((str(column), "UNKNOWN", False))
        priorities = linked_columns.get(table_key, set())
        normalized.sort(key=lambda item: (item[0].lower() not in priorities, not item[2]))
        definitions = [
            f"  {name} {column_type or 'UNKNOWN'}" + (" PRIMARY KEY" if primary_key else "")
            for name, column_type, primary_key in normalized[:12] if name
        ]
        if definitions:
            lines.extend([f"CREATE TABLE {table.get('name')} (", ",\n".join(definitions), ");"])
    if edges:
        lines.append("-- RELATIONSHIPS")
        lines.extend(
            f"-- {edge.get('from_table')}.{edge.get('from_column')} = "
            f"{edge.get('to_table')}.{edge.get('to_column')}"
            for edge in edges[:16]
        )
    return "\n".join(lines)[:7000]


def _candidate_schema_view(schema: str, instance_id: str, candidate_idx: int) -> str:
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"}:
        run_root = os.environ.get("SLAYQL_RUN_ROOT")
        if not run_root:
            return schema
        try:
            evidence_path = os.path.join(run_root, "interaction", f"{instance_id}.json")
            with open(evidence_path, "r", encoding="utf-8") as handle:
                evidence = json.load(handle)
            plan = build_route_hypotheses(schema, evidence)
            route = route_for_candidate(plan, candidate_idx)
            trace = {
                "schema_version": "1.0", "instance_id": instance_id,
                "candidate_id": candidate_idx, "selected_route": route,
                "route_plan": plan,
            }
            atomic_write_json(
                os.path.join(run_root, "candidate_routes", f"{instance_id}_{candidate_idx}.json"),
                trace,
            )
            return render_routed_schema(schema, route, candidate_idx)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return schema
    if os.environ.get("SLAYQL_RESEARCH_VERSION") != "1.5" or candidate_idx % 5 not in {1, 3}:
        return schema
    run_root = os.environ.get("SLAYQL_RUN_ROOT")
    if not run_root:
        return schema
    try:
        evidence_path = os.path.join(run_root, "interaction", f"{instance_id}.json")
        with open(evidence_path, "r", encoding="utf-8") as handle:
            evidence = json.load(handle)
        schema_tables = re.findall(r"^###Table full name:\s*(.*?)\s*$", schema, re.MULTILINE)
        view = relational_schema_view(evidence, schema_tables=schema_tables)
        return schema.rstrip() + "\n\n" + view + "\n" if view else schema
    except (OSError, ValueError, TypeError):
        return schema


class DataLoader:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.data = None
        return cls._instance

    def load(self, data_file: str) -> Dict:
        if self.data is None:
            with open(data_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        return self.data


def retry_delay(attempt: int) -> float:
    base = min(Config.INITIAL_RETRY_DELAY * (2 ** (attempt - 1)), Config.MAX_RETRY_DELAY)
    return base + random.uniform(0, 1)


def _apply_v17_generation_contract(prompt: str) -> str:
    """Remove two legacy output rules that contradict the v1.6+ contract."""
    prompt = prompt.replace(
        "When asked something without stating name or id, return both of them. e.g. Which products ...? The answer should include product_name and product_id.",
        "Return identity fields such as name or id only when the question explicitly requests them or dataset evidence defines them as the requested logical output.",
    )
    prompt = prompt.replace(
        "Make sure that the query content of the sql definitely includes what needs to be involved in the question, the execution result can be more than what is required by the question, but it must not be less.",
        "The execution result must contain exactly the requested answer fields. Join keys, filters, ordering expressions, and helper calculations may be used internally but must not be exposed unless requested.",
    )
    return prompt


def _apply_v18_generation_contract(prompt: str) -> str:
    """Add the measured-plan and fan-out guardrails used by v1.8."""
    return prompt + (
        "\n\n[SLAYQL_V18_ANSWER_PLAN_RULES]\n"
        "Before finalizing SQL, reconcile the natural-language output grain with the measured answer plan. "
        "Use measured join cardinalities to avoid accidental row multiplication. For a many-to-many or high-fanout "
        "route, pre-aggregate or use EXISTS when that preserves the requested semantics. Keep filters on the correct "
        "entity, honor all explicit boundaries and literals, and expose only requested output columns. "
        "The answer plan is evidence for validation, not permission to change the question."
    )


def _apply_v19_generation_contract(prompt: str) -> str:
    """Add hard output-slot and adaptive-schema guardrails for v1.9."""
    return prompt + (
        "\n\n[SLAYQL_V19_PROJECTION_AND_SCHEMA_RULES]\n"
        "Treat the semantic contract's physical output columns as mandatory slots. If a logical phrase expands to "
        "multiple physical columns (for example, full name -> forename and surname), project each requested "
        "expression separately; do not concatenate, replace, or omit them unless the question explicitly asks for "
        "one combined value. Before writing SQL, verify that every output-bearing table and join endpoint appears in "
        "the current schema view. Use the full-schema fallback or a supported bridge when the assigned route cannot "
        "satisfy all slots. Keep helper fields internal and emit one executable query only."
    )


class SQLGenerator:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1",
            # Per-request timeout in seconds; 600 is the OpenAI SDK default.
            timeout=float(os.environ.get("SLAYQL_API_TIMEOUT", "600")),
        )
        self.loader = DataLoader()
        self.model = os.environ.get("MODEL_NAME")

    def generate(
        self,
        instance_id: str,
        info: Dict,
        schema: str,
        candidate_idx: int,
        no_qoc: bool = False,
        max_retries: int = Config.MAX_RETRIES,
    ) -> Dict:
        question = info["question"]

        if instance_id.startswith("bq"):
            sql_type = BIGQUERY_DIALECT_OPTIMIZATION_SQL_GEN
            dialect = "BigQuery"
        elif instance_id.startswith("sf"):
            sql_type = SNOWFLAKE_DIALECT_OPTIMIZATION_SQL_GEN
            dialect = "SnowFlake"
        elif instance_id.startswith("local"):
            sql_type = SQLITE_DIALECT_OPTIMIZATION_SQL_GEN
            dialect = "SQLite"
        else:
            sql_type = ""
            dialect = "Unknown"

        prompt = SQL_GENERATION.replace("{PROMPT}", schema)
        prompt = prompt.replace("{QUESTION}", question)
        prompt = prompt.replace("{SQL_DIALECT_OPTIMIZATION}", sql_type)
        prompt = prompt.replace("{SQL_TYPE}", dialect)
        version = os.environ.get("SLAYQL_RESEARCH_VERSION")
        if version == "1.9":
            prompt = _apply_v17_generation_contract(prompt)
            prompt = _apply_v18_generation_contract(prompt)
            prompt = _apply_v19_generation_contract(prompt)
            run_root = os.environ.get("SLAYQL_RUN_ROOT")
            if run_root and candidate_idx % 5 in {0, 2}:
                demonstrations = load_prompt(run_root, instance_id)
                if demonstrations:
                    prompt += "\n\n" + demonstrations
        elif version == "1.8":
            prompt = _apply_v17_generation_contract(prompt)
            prompt = _apply_v18_generation_contract(prompt)
            run_root = os.environ.get("SLAYQL_RUN_ROOT")
            if run_root and candidate_idx % 5 in {0, 2}:
                demonstrations = load_prompt(run_root, instance_id)
                if demonstrations:
                    prompt += "\n\n" + demonstrations
        elif version == "1.7":
            prompt = _apply_v17_generation_contract(prompt)
            run_root = os.environ.get("SLAYQL_RUN_ROOT")
            if run_root and candidate_idx % 5 in {0, 2}:
                demonstrations = load_prompt(run_root, instance_id)
                if demonstrations:
                    prompt += "\n\n" + demonstrations
        if version in {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
            prompt += candidate_guidance(candidate_idx)

        if no_qoc:
            prompt = prompt.replace(
                "📤 Output Format\nIn addition to outputting other information, you also need to return the generated SQL query in the following format:\n```sql\nYour sql query\n```\nMake sure that all the sqls is contained within ```sql``` and the last ```sql``` contains the final complete SQL in your output.",
                "📤 Output Format\nReturn the SQL query that answers the question. Make sure to output valid SQL.",
            )

        messages = [{"role": "user", "content": prompt}]
        last_error = "unknown error"

        for attempt in range(1, max_retries + 1):
            response = None
            try:
                request_started = time.monotonic()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                from usage_accounting import record_response_usage
                record_response_usage(
                    response,
                    stage="sql_generation",
                    instance_id=instance_id,
                    candidate_id=candidate_idx,
                    attempt=attempt,
                    latency_ms=(time.monotonic() - request_started) * 1000,
                )
                message = response.choices[0].message
                reasoning_content = getattr(message, "reasoning_content", "") or ""
                model_output = message.content

                if model_output is None or not str(model_output).strip():
                    raise ValueError("Model returned empty or None content")

                return {
                    "output": model_output,
                    "think": reasoning_content,
                }

            except Exception as e:
                if response is None:
                    from usage_accounting import record_response_usage
                    record_response_usage(
                        None, stage="sql_generation", instance_id=instance_id,
                        candidate_id=candidate_idx, attempt=attempt,
                    )
                last_error = str(e)
                if attempt >= max_retries:
                    break
                delay = retry_delay(attempt)
                print(
                    f"[Retry {attempt}/{max_retries}] {instance_id}: {last_error} "
                    f"— retrying in {delay:.1f}s"
                )
                time.sleep(delay)

        raise TaskGenerationError(instance_id, -1, last_error)


def collect_tasks(
    schema_dir: str,
    log_path: str,
    task: str,
    num_candidates: int,
    only: Optional[List[Tuple[str, int]]] = None,
) -> List[Tuple[str, int]]:
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.6", "1.7", "1.8", "1.9"} and only is None:
        # Route traces are deterministic checkpoint artifacts. Rebuild them
        # without a model call before deciding which SQL tasks remain.
        for filename in sorted(name for name in os.listdir(schema_dir) if name.endswith(".txt")):
            instance_id = filename[:-4]
            try:
                with open(os.path.join(schema_dir, filename), "r", encoding="utf-8") as handle:
                    schema = handle.read()
                for candidate_idx in range(num_candidates):
                    _candidate_schema_view(schema, instance_id, candidate_idx)
            except OSError:
                continue
    if only is not None:
        pending = []
        for iid, cid in only:
            out_file = f"{log_path}/sql_gen/{task}_sql_generation_{cid}/{iid}.txt"
            if not os.path.exists(out_file):
                pending.append((iid, cid))
        return pending

    instance_ids = [f[:-4] for f in os.listdir(schema_dir) if f.endswith(".txt")]
    tasks = []
    for cid in range(num_candidates):
        for iid in instance_ids:
            out_file = f"{log_path}/sql_gen/{task}_sql_generation_{cid}/{iid}.txt"
            if not os.path.exists(out_file):
                tasks.append((iid, cid))
    return tasks


def run_task(
    generator: SQLGenerator,
    data: Dict,
    schema_dir: str,
    log_path: str,
    task: str,
    instance_id: str,
    candidate_idx: int,
    max_retries: int = Config.MAX_RETRIES,
) -> Optional[str]:
    """Run one SQL generation task. Returns error message on failure, None on success."""
    try:
        schema_path = f"{schema_dir}/{instance_id}.txt"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()
        schema = _candidate_schema_view(schema, instance_id, candidate_idx)

        no_bm25 = os.environ.get("ABLATION_NO_BM25", "0") == "1"
        no_qoc = os.environ.get("ABLATION_NO_QOC", "0") == "1"

        if not no_bm25:
            from value_grounder import get_value_hints

            db_name = data[instance_id].get("db_name", "")
            question = data[instance_id].get("question", "")
            try:
                value_hints_block = get_value_hints(
                    query=question,
                    db_id=db_name,
                    indices_dir=os.environ.get("SLAYQL_BM25_DIR", "bm25_indices"),
                    threshold=float(os.environ.get("SLAYQL_BM25_THRESHOLD", "5.0")),
                    normalized=os.environ.get("SLAYQL_BM25_NORMALIZED", "0") == "1",
                    max_hints=int(os.environ.get("SLAYQL_VALUE_HINT_CAP", "3")),
                    trace_id=f"{instance_id}_generation_{candidate_idx}",
                    trace_dir=os.environ.get("SLAYQL_BM25_TRACE_DIR"),
                )
                if value_hints_block:
                    schema += f"\n{value_hints_block}\n"
            except Exception:
                pass

        result = generator.generate(
            instance_id,
            data[instance_id],
            schema,
            candidate_idx,
            no_qoc=no_qoc,
            max_retries=max_retries,
        )

        os.makedirs(f"{log_path}/sql_gen/{task}_sql_generation_{candidate_idx}", exist_ok=True)
        os.makedirs(f"{log_path}/sql_gen/{task}_reasoning_{candidate_idx}", exist_ok=True)

        atomic_write_text(
            f"{log_path}/sql_gen/{task}_sql_generation_{candidate_idx}/{instance_id}.txt",
            result["output"],
        )
        atomic_write_text(
            f"{log_path}/sql_gen/{task}_reasoning_{candidate_idx}/{instance_id}.txt",
            result.get("think") or "",
        )

        return None

    except Exception as e:
        return str(e)


def run_batch(
    tasks: List[Tuple[str, int]],
    generator: SQLGenerator,
    data: Dict,
    schema_dir: str,
    log_path: str,
    task: str,
    num_workers: int,
    max_retries: int,
    desc: str,
) -> List[Dict]:
    """Run a batch of tasks; continue on failure and return failed task records."""
    if not tasks:
        return []

    failed: List[Dict] = []
    failed_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_map = {
            executor.submit(
                run_task,
                generator,
                data,
                schema_dir,
                log_path,
                task,
                iid,
                cid,
                max_retries,
            ): (iid, cid)
            for iid, cid in tasks
        }

        for future in tqdm(
            as_completed(future_map),
            total=len(future_map),
            desc=desc,
            dynamic_ncols=True,
        ):
            iid, cid = future_map[future]
            err = future.result()
            if err:
                record = {
                    "instance_id": iid,
                    "candidate_idx": cid,
                    "error": err,
                }
                with failed_lock:
                    failed.append(record)
                print(f"[FAIL] {iid} (candidate {cid}): {err}")

    return failed


def save_failed_tasks(log_path: str, failed: List[Dict]) -> str:
    path = os.path.join(log_path, "sql_gen_failed_tasks.json")
    atomic_write_json(path, failed)
    return path


def sql_clean(log_path: str, task: str, candidate_idx: int):
    in_dir = f"{log_path}/sql_gen/{task}_sql_generation_{candidate_idx}"
    out_dir = f"{log_path}/sql_gen/{task}_sql_{candidate_idx}"

    os.makedirs(out_dir, exist_ok=True)

    import re

    if not os.path.exists(in_dir):
        print(f"[sql_clean] Skip candidate {candidate_idx}: missing {in_dir}")
        return

    for name in os.listdir(in_dir):
        if not name.endswith(".txt"):
            continue
        iid = name[:-4]
        with open(f"{in_dir}/{name}", "r", encoding="utf-8") as f:
            content = f.read()

        blocks = re.findall(r"```sql\s*\n(.*?)\n\s*```", content, re.DOTALL)
        if not blocks:
            blocks = re.findall(r"```\s*\n(.*?)\n\s*```", content, re.DOTALL)
        if blocks:
            non_empty_blocks = [b.strip() for b in blocks if b.strip()]
            sql = max(non_empty_blocks, key=len) if non_empty_blocks else ""
        else:
            end = content.rfind("```")
            start = content.rfind("```sql", 0, end)
            if start != -1 and end != -1 and end > start:
                sql = content[start + 6 : end].strip()
            else:
                sql = content.strip()

        atomic_write_text(f"{out_dir}/{iid}.sql", sql)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_workers", type=int, default=8)
    parser.add_argument("--num_candidates", type=int, default=5)
    parser.add_argument("--data_file", type=str, required=True)
    parser.add_argument("--schema_dir", type=str, required=True)
    parser.add_argument("--log_path", type=str, required=True)
    parser.add_argument("--task", type=str, default="r1_lite")
    parser.add_argument(
        "--max_retries",
        type=int,
        default=Config.MAX_RETRIES,
        help="Retries per task with exponential backoff + jitter (default: 5)",
    )
    parser.add_argument(
        "--no_rerun_failed",
        action="store_true",
        help="Skip the final dedicated rerun pass for failed task IDs",
    )
    parser.add_argument(
        "--no_qoc",
        action="store_true",
        help="[Ablation 1] Disable strict SQL output contracts (QOC).",
    )
    parser.add_argument(
        "--no_bm25",
        action="store_true",
        help="[Ablation 1] Disable BM25 value hints in SQL generation.",
    )
    args = parser.parse_args()

    Config.MAX_RETRIES = args.max_retries

    if args.no_qoc:
        os.environ["ABLATION_NO_QOC"] = "1"
    if args.no_bm25:
        os.environ["ABLATION_NO_BM25"] = "1"

    os.makedirs(args.log_path, exist_ok=True)

    loader = DataLoader()
    data = loader.load(args.data_file)
    generator = SQLGenerator()

    tasks = collect_tasks(
        args.schema_dir, args.log_path, args.task, args.num_candidates
    )
    print(f"Total pending tasks: {len(tasks)}")

    failed = run_batch(
        tasks,
        generator,
        data,
        args.schema_dir,
        args.log_path,
        args.task,
        args.num_workers,
        args.max_retries,
        desc="SQL Generation",
    )

    if failed and not args.no_rerun_failed:
        rerun_tasks = [(f["instance_id"], f["candidate_idx"]) for f in failed]
        print(f"\n=== Rerun pass: {len(rerun_tasks)} failed task(s) ===")
        still_failed = run_batch(
            rerun_tasks,
            generator,
            data,
            args.schema_dir,
            args.log_path,
            args.task,
            max(1, min(args.num_workers, 4)),
            args.max_retries,
            desc="SQL Generation (rerun)",
        )
        failed = still_failed

    if failed:
        path = save_failed_tasks(args.log_path, failed)
        print(f"\n[WARN] {len(failed)} task(s) still failed after rerun. Saved to: {path}")
    else:
        failed_path = os.path.join(args.log_path, "sql_gen_failed_tasks.json")
        if os.path.exists(failed_path):
            os.remove(failed_path)
        print("\nAll SQL generation tasks succeeded.")

    print("SQL generation finished")

    with ThreadPoolExecutor(max_workers=args.num_candidates) as executor:
        futures = [
            executor.submit(sql_clean, args.log_path, args.task, cid)
            for cid in range(args.num_candidates)
        ]
        for f in as_completed(futures):
            f.result()

    print("SQL cleaning finished")


if __name__ == "__main__":
    main()

import os
import json
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


class SQLGenerator:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        self.loader = DataLoader()
        self.model = os.environ.get("MODEL_NAME")

    def generate(
        self,
        instance_id: str,
        info: Dict,
        schema: str,
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

        if no_qoc:
            prompt = prompt.replace(
                "📤 Output Format\nIn addition to outputting other information, you also need to return the generated SQL query in the following format:\n```sql\nYour sql query\n```\nMake sure that all the sqls is contained within ```sql``` and the last ```sql``` contains the final complete SQL in your output.",
                "📤 Output Format\nReturn the SQL query that answers the question. Make sure to output valid SQL.",
            )

        messages = [{"role": "user", "content": prompt}]
        last_error = "unknown error"

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
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

        no_bm25 = os.environ.get("ABLATION_NO_BM25", "0") == "1"
        no_qoc = os.environ.get("ABLATION_NO_QOC", "0") == "1"

        if not no_bm25:
            from value_grounder import get_value_hints

            db_name = data[instance_id].get("db_name", "")
            question = data[instance_id].get("question", "")
            try:
                value_hints_block = get_value_hints(
                    query=question, db_id=db_name, indices_dir="bm25_indices"
                )
                if value_hints_block:
                    schema += f"\n{value_hints_block}\n"
            except Exception:
                pass

        result = generator.generate(
            instance_id,
            data[instance_id],
            schema,
            no_qoc=no_qoc,
            max_retries=max_retries,
        )

        os.makedirs(f"{log_path}/sql_gen/{task}_sql_generation_{candidate_idx}", exist_ok=True)
        os.makedirs(f"{log_path}/sql_gen/{task}_reasoning_{candidate_idx}", exist_ok=True)

        with open(
            f"{log_path}/sql_gen/{task}_sql_generation_{candidate_idx}/{instance_id}.txt",
            "w",
            encoding="utf-8",
        ) as f:
            f.write(result["output"])

        with open(
            f"{log_path}/sql_gen/{task}_reasoning_{candidate_idx}/{instance_id}.txt",
            "w",
            encoding="utf-8",
        ) as f:
            f.write(result.get("think") or "")

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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=2, ensure_ascii=False)
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

        with open(f"{out_dir}/{iid}.sql", "w", encoding="utf-8") as f:
            f.write(sql)


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

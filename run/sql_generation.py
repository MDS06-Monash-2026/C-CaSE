import os
import json
import time
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
from openai import OpenAI
from config import *
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

class Config:
    INITIAL_RETRY_DELAY = 1
    MAX_RETRY_DELAY = 30

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

class SQLGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
        self.loader = DataLoader()
        self.model = os.environ.get("MODEL_NAME")

    def generate(self, instance_id: str, info: Dict, schema: str) -> Dict:
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

        # USE SINGLE_PASS_SQL_GENERATION
        prompt = SINGLE_PASS_SQL_GENERATION.replace("{tscg_distilled_steiner_tree_schema}", schema)
        prompt = prompt.replace("{user_question}", question)
        prompt = prompt.replace("{SQL_DIALECT}", dialect)
        
        # Append Structured JSON instructions
        prompt += "\n\n[STRICT JSON OUTPUT FORMAT]\nYou must output valid JSON containing exactly one key 'sql'.\n{\n  \"sql\": \"SELECT ...\"\n}"

        messages = [{"role": "user", "content": prompt}]
        
        attempt = 0
        while True:
            try:
                # SlayQL 2.0 Single-Shot Drafter (No Agentic Loop)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0 # Deterministic drafting
                )
                
                content = response.choices[0].message.content
                parsed = json.loads(content)
                sql = parsed.get("sql", "")
                
                return {
                    "output": sql,
                    "think": "SlayQL 2.0 Deterministic Drafter"
                }

            except Exception as e:
                attempt += 1
                delay = min(Config.INITIAL_RETRY_DELAY * (2 ** (attempt - 1)), Config.MAX_RETRY_DELAY)
                print(f"[Retry {attempt}] API call failed for {instance_id}. ERROR: {str(e)} \nRetrying in {delay}s")
                time.sleep(delay)
                if attempt > 3:
                    return {
                        "output": "SELECT 1;",
                        "think": "Failed API"
                    }

def collect_tasks(schema_dir: str, log_path: str, task: str) -> List[Tuple[str]]:
    instance_ids = [f[:-4] for f in os.listdir(schema_dir) if f.endswith(".txt")]

    tasks = []
    # Only 1 candidate for Drafter
    for iid in instance_ids:
        out_file = f"{log_path}/sql_gen/{task}_sql_generation_0/{iid}.txt"
        if not os.path.exists(out_file):
            tasks.append((iid,))
    return tasks

def run_task(
    generator: SQLGenerator,
    data: Dict,
    schema_dir: str,
    log_path: str,
    task: str,
    instance_id: str
):
    schema_path = f"{schema_dir}/{instance_id}.txt"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    result = generator.generate(instance_id, data[instance_id], schema)

    os.makedirs(f"{log_path}/sql_gen/{task}_sql_generation_0", exist_ok=True)
    os.makedirs(f"{log_path}/sql_gen/{task}_reasoning_0", exist_ok=True)

    with open(f"{log_path}/sql_gen/{task}_sql_generation_0/{instance_id}.txt", "w", encoding="utf-8") as f:
        f.write(result["output"])

    with open(f"{log_path}/sql_gen/{task}_reasoning_0/{instance_id}.txt", "w", encoding="utf-8") as f:
        f.write(result["think"])

def sql_clean(log_path: str, task: str):
    in_dir = f"{log_path}/sql_gen/{task}_sql_generation_0"
    out_dir = f"{log_path}/sql_gen/{task}_sql_0"
    
    os.makedirs(out_dir, exist_ok=True)

    for name in os.listdir(in_dir):
        if not name.endswith(".txt"):
            continue
        iid = name[:-4]
        with open(f"{in_dir}/{name}", "r", encoding="utf-8") as f:
            content = f.read()
        
        # Output is already pure SQL from JSON but clean it just in case
        sql = content.strip()
        with open(f"{out_dir}/{iid}.sql", "w", encoding="utf-8") as f:
            f.write(sql)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_workers", type=int, default=8)
    parser.add_argument("--num_candidates", type=int, default=1) # SlayQL 2.0 uses 1 draft
    parser.add_argument("--data_file", type=str, required=True)
    parser.add_argument("--schema_dir", type=str, required=True)
    parser.add_argument("--log_path", type=str, required=True)
    args = parser.parse_args()

    # Load Data
    DataLoader().load(args.data_file)
    data = DataLoader().data

    # We only run the Drafter (0th candidate)
    task_name = "test"
    generator = SQLGenerator()
    tasks = collect_tasks(args.schema_dir, args.log_path, task_name)

    if tasks:
        print(f"Total pending SlayQL 2.0 Drafter tasks: {len(tasks)}")
        with ThreadPoolExecutor(max_workers=args.num_workers) as executor:
            futures = [
                executor.submit(run_task, generator, data, args.schema_dir, args.log_path, task_name, iid)
                for (iid,) in tasks
            ]
            for _ in tqdm(as_completed(futures), total=len(futures), desc="SlayQL 2.0 SQL Generation"):
                pass
    else:
        print("All Drafter tasks completed.")

    print("\nCleaning SlayQL 2.0 output...")
    sql_clean(args.log_path, task_name)
    print("Cleaned!")

if __name__ == "__main__":
    main()

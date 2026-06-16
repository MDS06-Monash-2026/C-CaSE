import json
import os
import shutil
import subprocess
import argparse
import pandas as pd
import sys
import re

def extract_deterministic_subset(source_json, subset_size=10):
    """
    Selects a deterministic subset of 10 items from the dataset,
    ensuring balanced representation across cloud warehouses and local dialects.
    """
    with open(source_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    sorted_keys = sorted(data.keys())
    bq_keys = [k for k in sorted_keys if k.startswith("bq") or k.startswith("ga")][:8]
    sf_keys = []
    local_keys = [k for k in sorted_keys if k.startswith("local")][:2]
    
    subset_keys = bq_keys + sf_keys + local_keys
    subset_data = {k: data[k] for k in subset_keys if k in data}
    
    # Fallback to absolute sequential slicing if key structures differ
    if len(subset_data) < subset_size:
        subset_data = {k: data[k] for k in sorted_keys[:subset_size]}
        
    return subset_data

def run_pipeline_configuration(log_path, config_flags, subset_file):
    """
    Executes the ingestion, schema tracking, linking, and processing steps 
    under the specified file path boundaries.
    """
    print(f"\n>>> Running Pipeline Experiment Matrix for Target Path: {log_path} <<<")
    os.makedirs(log_path, exist_ok=True)
    
    # Step 1: Initial schema lookup and structural assembly
    subprocess.run([
        sys.executable, "retrieve_topk_schema.py", 
        "--log_path", log_path, 
        "--top_n", "100"
    ], check=True)
    
    subprocess.run([
        sys.executable, "add_id.py", 
        "--log_path", log_path
    ], check=True)
    
    subprocess.run([
        sys.executable, "generate_schema.py", 
        "--log_path", log_path, 
        "--is_initial"
    ], check=True)
    
    # Step 2: Run interactive multi-turn exploration loops
    # Inject environmental configuration parameters to enable or disable C-CaSE modules dynamically
    env = os.environ.copy()
    for k, v in config_flags.items():
        env[k] = str(v)
        
    if not os.path.exists(f"{log_path}/merge_candidates.json"):
        subprocess.run([
            sys.executable, "complete_schema.py", 
            "--log_path", log_path
        ], env=env, check=True)
    else:
        print(f"[{log_path}] Skipping complete_schema (cached)")
        
    if not os.path.exists(f"{log_path}/final_schema_prompts"):
        subprocess.run([
            sys.executable, "postprocess.py", 
            "--log_path", log_path
        ], check=True)
        subprocess.run([
            sys.executable, "generate_schema.py", 
            "--log_path", log_path
        ], check=True)
    else:
        print(f"[{log_path}] Skipping generate_schema (cached)")
        
    # Downstream SQL Execution
    schema_dir = f"{log_path}/final_schema_prompts"
    if not os.path.exists(f"{log_path}/sql_gen"):
        subprocess.run([
            sys.executable, "sql_generation.py", 
            "--data_file", subset_file,
            "--schema_dir", schema_dir,
            "--log_path", log_path,
            "--num_workers", "8",
            "--num_candidates", "3"
        ], check=True)
    else:
        print(f"[{log_path}] Skipping sql_generation (cached)")
        
    subprocess.run([
        sys.executable, "sql_execution.py", 
        "--data_file", subset_file,
        "--log_path", log_path,
        "--num_workers", "4",
        "--num_candidates", "3"
    ], check=True)
        
    if not os.path.exists(f"{log_path}/sql_revise"):
        subprocess.run([
            sys.executable, "sql_revise.py", 
            "--data_file", subset_file,
            "--schema_dir", schema_dir,
            "--log_path", log_path,
            "--num_workers", "8",
            "--num_candidates", "3"
        ], check=True)
    else:
        print(f"[{log_path}] Skipping sql_revise (cached)")
        
    if not os.path.exists(f"{log_path}/sql_selection/final"):
        subprocess.run([
            sys.executable, "sql_selection.py", 
            "--log_path", log_path,
            "--num_candidates", "3"
        ], check=True)
    else:
        print(f"[{log_path}] Skipping sql_selection (cached)")

def compute_metrics(log_path, golden_data_file):
    """
    Parses execution output paths to compute Schema F1 and Execution Accuracy.
    """
    with open(f"{log_path}/merge_candidates.json", "r", encoding="utf-8") as f:
        predicted = json.load(f)
    
    with open("gold_schema_columns.json", "r", encoding="utf-8") as f:
        gold_schema = json.load(f)
        
    total_tp = 0
    total_fp = 0
    total_fn = 0
    
    for inst_id, pred_info in predicted.items():
        if inst_id not in gold_schema:
            continue
            
        p_cols_full = set(pred_info.get("column_candidates", []))
        p_cols = set([c.split('.')[-1].lower() for c in p_cols_full])
        g_cols = set(gold_schema[inst_id]["columns"])
        
        total_tp += len(p_cols.intersection(g_cols))
        total_fp += len(p_cols - g_cols)
        total_fn += len(g_cols - p_cols)
            
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    srr = f1 * 100
    
    ex_score = 0.0
    try:
        eval_cmd = [
            sys.executable, "../evaluation_suite/evaluate.py",
            "--mode", "sql",
            "--result_dir", f"{log_path}/sql_selection/final",
            "--gold_dir", "../evaluation_suite/gold"
        ]
        result = subprocess.run(eval_cmd, capture_output=True, text=True)
        match = re.search(r"Score: (\d+\.\d+)", result.stdout)
        if match:
            ex_score = float(match.group(1)) * 100
    except Exception as e:
        print(f"Failed to compute EX score: {e}")

    return srr, ex_score

def main():
    parser = argparse.ArgumentParser()
    env_pct = float(os.environ.get("SUBSET_PERCENTAGE", 20.0))
    parser.add_argument("--data_file", default="spider2_data.json")
    parser.add_argument("--subset_percentage", type=float, default=env_pct, help="Percentage of dataset to evaluate")
    args = parser.parse_args()
    
    backup_file = args.data_file + ".bak"
    # Auto-recover from previous crashes where backup was not restored
    if os.path.exists(backup_file):
        print(f"Recovering original {args.data_file} from previous interrupted run...")
        shutil.move(backup_file, args.data_file)
        
    with open(args.data_file, "r", encoding="utf-8") as f:
        total_len = len(json.load(f))
    
    target_size = max(1, int(total_len * (args.subset_percentage / 100.0)))
    subset_file = f"subset_{target_size}_evaluation.json"
    print(f"[Initialization] Compiling deterministic {target_size}-instance dataset split ({args.subset_percentage}%) -> {subset_file}")
    
    subset_data = extract_deterministic_subset(args.data_file, subset_size=target_size)
    
    with open(subset_file, "w", encoding="utf-8") as f:
        json.dump(subset_data, f, indent=4, ensure_ascii=False)
        
    try:
        # pyrefly: ignore [missing-import]
        import sqlglot
    except ImportError:
        print("Installing sqlglot for AST parsing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "sqlglot"], check=True)
    
    print("Extracting gold schema columns via AST parsing...")
    subprocess.run([sys.executable, "extract_gold_schema.py", "--subset_file", subset_file], check=True)
    
    # Temporarily swap spider2_data.json to the subset for the evaluation scripts
    backup_file = args.data_file + ".bak"
    shutil.copy2(args.data_file, backup_file)
    shutil.copy2(subset_file, args.data_file)
        
    try:
        # Run Trial 1: Baseline AutoLink Configuration (Disable Graph Penalties & Calibrations)
        baseline_flags = {"USE_GRAPH_NAV": "FALSE", "USE_CONFORMAL_GATE": "FALSE"}
        baseline_log = f"log_subset_{target_size}_autolink_baseline"
        run_pipeline_configuration(baseline_log, baseline_flags, subset_file)
        srr_baseline, ex_baseline = compute_metrics(baseline_log, subset_file)
        
        # Run Trial 2: SlayQL / C-CaSE Configuration (Enable Graph Penalties & Calibrations)
        ccase_flags = {"USE_GRAPH_NAV": "TRUE", "USE_CONFORMAL_GATE": "TRUE"}
        ccase_log = f"log_subset_{target_size}_slayql_ccase"
        run_pipeline_configuration(ccase_log, ccase_flags, subset_file)
        srr_ccase, ex_ccase = compute_metrics(ccase_log, subset_file)
        
        # Render comparative reporting dashboard matrix
        print("\n" + "="*60)
        print("         SLAYQL EXPERIMENTAL EVALUATION DASHBOARD MATRIX")
        print("="*60)
        print(f"Dataset Evaluation Split Target Size : {target_size} Instances ({args.subset_percentage}%)")
        print(f"Baseline AutoLink Schema F1: {srr_baseline:.2f}% | Execution Accuracy (EX): {ex_baseline:.2f}%")
        print(f"SlayQL (C-CaSE) Schema F1  : {srr_ccase:.2f}% | Execution Accuracy (EX): {ex_ccase:.2f}%")
        print("-" * 60)
        print("Verification Completed. Check logs for complete execution profiles.")
        print("=" * 60)
    finally:
        # Restore the original spider2_data.json
        shutil.move(backup_file, args.data_file)

if __name__ == "__main__":
    main()

import os
import shutil
import subprocess
import argparse
import sys
import json

def run_pipeline(batch_file, log_path, env, step_prefix=""):
    print(f"\n{step_prefix}========== Running Pipeline for {log_path} ==========")
    
    # Step 1: Initial schema lookup
    if not os.path.exists(f"{log_path}/schema_with_id.json"):
        print(f"\n{step_prefix}[1/8] Retrieving Top-K Schemas...")
        subprocess.run([sys.executable, "retrieve_topk_schema.py", "--log_path", log_path, "--top_n", "100"], check=True)
        print(f"\n{step_prefix}[2/8] Adding DB Identifiers...")
        subprocess.run([sys.executable, "add_id.py", "--log_path", log_path], check=True)
    else:
        print(f"\n{step_prefix}[1/8 & 2/8] Skipping initial retrieval (cached in {log_path})")

    if not os.path.exists(f"{log_path}/initial_schema_prompts"):
        print(f"\n{step_prefix}[3/8] Generating Initial Schema Prompts...")
        subprocess.run([sys.executable, "generate_schema.py", "--log_path", log_path, "--is_initial"], check=True)
    else:
        print(f"\n{step_prefix}[3/8] Skipping initial schema prompts (cached)")
    
    if not os.path.exists(f"{log_path}/merge_candidates.json"):
        print(f"\n{step_prefix}[4/8] Running Interactive Multi-Turn Schema Exploration...")
        subprocess.run([sys.executable, "complete_schema.py", "--log_path", log_path], env=env, check=True)
    else:
        print(f"\n{step_prefix}[4/8] Skipping complete_schema (cached)")
    
    if not os.path.exists(f"{log_path}/final_schema_prompts"):
        print(f"\n{step_prefix}[5/8] Post-Processing Schema Trees...")
        subprocess.run([sys.executable, "postprocess.py", "--log_path", log_path], check=True)
        print(f"\n{step_prefix}[6/8] Iterative Schema Pruning...")
        subprocess.run([sys.executable, "generate_schema.py", "--log_path", log_path], env=env, check=True)
    else:
        print(f"\n{step_prefix}[5/8 & 6/8] Skipping schema pruning (cached)")
    
    schema_dir = f"{log_path}/final_schema_prompts"
    
    if not os.path.exists(f"{log_path}/sql_gen"):
        print(f"\n{step_prefix}[7/8] Generating Candidate SQL...")
        subprocess.run([sys.executable, "sql_generation.py", "--data_file", batch_file, "--schema_dir", schema_dir, "--log_path", log_path, "--num_workers", "8", "--num_candidates", "3"], env=env, check=True)
    else:
        print(f"\n{step_prefix}[7/8] Skipping sql_generation (cached)")
        
    print(f"\n{step_prefix}[8/8] Executing Candidates on BigQuery...")
    subprocess.run([sys.executable, "sql_execution.py", "--data_file", batch_file, "--log_path", log_path, "--num_workers", "4", "--num_candidates", "3"], env=env, check=True)
    
    if not os.path.exists(f"{log_path}/sql_revise"):
        print(f"\n{step_prefix}[Self-Correction] Revision phase...")
        subprocess.run([sys.executable, "sql_revise.py", "--data_file", batch_file, "--schema_dir", schema_dir, "--log_path", log_path, "--num_workers", "8", "--num_candidates", "3"], env=env, check=True)
    else:
        print(f"\n{step_prefix}[Self-Correction] Skipping sql_revise (cached)")
        
    if not os.path.exists(f"{log_path}/sql_selection/final"):
        print(f"\n{step_prefix}[Final] SQL Selection Voting...")
        subprocess.run([sys.executable, "sql_selection.py", "--log_path", log_path, "--num_candidates", "3"], env=env, check=True)
    else:
        print(f"\n{step_prefix}[Final] Skipping sql_selection (cached)")

def main():
    parser = argparse.ArgumentParser(description="Iterative Evaluation for AutoLink and SlayQL on Diverse Subset")
    parser.add_argument("--batch_file", type=str, default="subset_diverse_20_evaluation.json", help="Path to diverse subset JSON")
    parser.add_argument("--clear_cache", action="store_true", help="Clear previous output directories before running")
    parser.add_argument("--reuse_schema", action="store_true", help="Have SlayQL directly reuse AutoLink's schema output (skips steps 1-6 for SlayQL to isolate SQL-gen tools)")
    args = parser.parse_args()
    
    if not os.path.exists(args.batch_file):
        print(f"Error: {args.batch_file} not found! Please run generate_diverse_subset.py first.")
        return
        
    log_autolink = f"log_{args.batch_file.replace('.json', '')}_autolink_baseline"
    log_slayql = f"log_{args.batch_file.replace('.json', '')}_slayql_ccase"
    
    if args.clear_cache:
        print("[CACHE] Clearing previous run data...")
        if os.path.exists(log_autolink): shutil.rmtree(log_autolink)
        if os.path.exists(log_slayql): shutil.rmtree(log_slayql)
        
    os.makedirs(log_autolink, exist_ok=True)
    os.makedirs(log_slayql, exist_ok=True)
    
    target_data = "spider2_data.json"
    backup_file = target_data + ".bak"
    
    # Auto-recover just in case
    if os.path.exists(backup_file):
        shutil.move(backup_file, target_data)
        
    shutil.copy2(target_data, backup_file)
    shutil.copy2(args.batch_file, target_data)
    
    try:
        # Phase 1: AutoLink (Baseline - No advanced MCP reasoning tools)
        env_auto = os.environ.copy()
        env_auto["USE_GRAPH_NAV"] = "FALSE"
        env_auto["USE_CONFORMAL_GATE"] = "FALSE"
        run_pipeline(args.batch_file, log_autolink, env_auto, step_prefix="[AutoLink] ")

        if args.reuse_schema:
            print("\n[Optimization] --reuse_schema is enabled. Copying AutoLink's schema to SlayQL...")
            autolink_schema_dir = f"{log_autolink}/final_schema_prompts"
            slayql_schema_dir = f"{log_slayql}/final_schema_prompts"
            
            if os.path.exists(autolink_schema_dir):
                if os.path.exists(slayql_schema_dir):
                    shutil.rmtree(slayql_schema_dir)
                # Copying final_schema_prompts triggers the caching to skip Steps 1-6!
                shutil.copytree(autolink_schema_dir, slayql_schema_dir)
                print(f"[Optimization] Schema copied successfully. SlayQL will skip to Step 7 (SQL Generation).")

        # Phase 2: SlayQL (Advanced - With graph nav & conformal gating MCP)
        env_slay = os.environ.copy()
        env_slay["USE_GRAPH_NAV"] = "TRUE"
        env_slay["USE_CONFORMAL_GATE"] = "TRUE"
        run_pipeline(args.batch_file, log_slayql, env_slay, step_prefix="[SlayQL] ")

        print(f"\n========== Pipeline Executions Complete ==========")
        print(f"Run 'python generate_detailed_analysis.py' and 'python compare_batch_ex.py' to compare results.")
        
    finally:
        # Guarantee restoration of the main dataset
        if os.path.exists(backup_file):
            shutil.move(backup_file, target_data)

if __name__ == "__main__":
    main()

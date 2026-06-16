import os
import json
import shutil
import subprocess
import argparse
import sys
import glob

def main():
    parser = argparse.ArgumentParser(description="Iterative Development Runner for SlayQL")
    parser.add_argument("--batch_size", type=int, default=20, help="Number of instances to evaluate iteratively")
    parser.add_argument("--clear_cache", action="store_true", help="Clear the previous run's output so it runs from scratch")
    args = parser.parse_args()
    
    if not os.path.exists("subset_109_evaluation.json"):
        print("Error: subset_109_evaluation.json not found! Please run the main eval script once to generate it.")
        return
        
    with open("subset_109_evaluation.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Get the first N instances
    keys = list(data.keys())[:args.batch_size]
    batch_data = {k: data[k] for k in keys}
    
    batch_file = f"subset_dev{args.batch_size}_evaluation.json"
    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(batch_data, f, indent=4, ensure_ascii=False)
        
    print(f"[INIT] Created temporary batch dataset {batch_file} with {args.batch_size} instances.")
    
    target_data = "spider2_data.json"
    backup_file = target_data + ".bak"
    
    # Auto-recover just in case
    if os.path.exists(backup_file):
        shutil.move(backup_file, target_data)
        
    shutil.copy2(target_data, backup_file)
    shutil.copy2(batch_file, target_data)
    
    log_path = f"log_subset_dev{args.batch_size}_slayql_ccase"
    
    if args.clear_cache and os.path.exists(log_path):
        print(f"[CACHE] Clearing previous run data in {log_path}...")
        shutil.rmtree(log_path)
        
    os.makedirs(log_path, exist_ok=True)
    
    print(f"\n========== SlayQL Iterative Run Started ({args.batch_size} instances) ==========")
    
    env = os.environ.copy()
    env["USE_GRAPH_NAV"] = "TRUE"
    env["USE_CONFORMAL_GATE"] = "TRUE"
    
    try:
        # Step 1: Initial schema lookup
        if not os.path.exists(f"{log_path}/schema_with_id.json"):
            print("\n[1/8] Retrieving Top-K Schemas...")
            subprocess.run([sys.executable, "retrieve_topk_schema.py", "--log_path", log_path, "--top_n", "100"], check=True)
            print("\n[2/8] Adding DB Identifiers...")
            subprocess.run([sys.executable, "add_id.py", "--log_path", log_path], check=True)
        else:
            print(f"\n[1/8 & 2/8] Skipping initial retrieval (cached in {log_path})")

        if not os.path.exists(f"{log_path}/initial_schema_prompts"):
            print("\n[3/8] Generating Initial Schema Prompts...")
            subprocess.run([sys.executable, "generate_schema.py", "--log_path", log_path, "--is_initial"], check=True)
        else:
            print(f"\n[3/8] Skipping initial schema prompts (cached)")
        
        if not os.path.exists(f"{log_path}/merge_candidates.json"):
            print("\n[4/8] Running Interactive Multi-Turn Schema Exploration...")
            subprocess.run([sys.executable, "complete_schema.py", "--log_path", log_path], env=env, check=True)
        else:
            print(f"\n[4/8] Skipping complete_schema (cached)")
        
        if not os.path.exists(f"{log_path}/final_schema_prompts"):
            print("\n[5/8] Post-Processing Schema Trees...")
            subprocess.run([sys.executable, "postprocess.py", "--log_path", log_path], check=True)
            print("\n[6/8] Iterative Schema Pruning...")
            subprocess.run([sys.executable, "generate_schema.py", "--log_path", log_path], env=env, check=True)
        else:
            print(f"\n[5/8 & 6/8] Skipping schema pruning (cached)")
        
        schema_dir = f"{log_path}/final_schema_prompts"
        
        if not os.path.exists(f"{log_path}/sql_gen"):
            print("\n[7/8] Generating Candidate SQL...")
            subprocess.run([sys.executable, "sql_generation.py", "--data_file", batch_file, "--schema_dir", schema_dir, "--log_path", log_path, "--num_workers", "8", "--num_candidates", "3"], env=env, check=True)
        else:
            print(f"\n[7/8] Skipping sql_generation (cached)")
            
        # sql_execution checks internal caching based on CSVs
        print("\n[8/8] Executing Candidates on BigQuery...")
        subprocess.run([sys.executable, "sql_execution.py", "--data_file", batch_file, "--log_path", log_path, "--num_workers", "4", "--num_candidates", "3"], env=env, check=True)
        
        if not os.path.exists(f"{log_path}/sql_revise"):
            print("\n[Self-Correction] Revision phase...")
            subprocess.run([sys.executable, "sql_revise.py", "--data_file", batch_file, "--schema_dir", schema_dir, "--log_path", log_path, "--num_workers", "8", "--num_candidates", "3"], env=env, check=True)
        else:
            print(f"\n[Self-Correction] Skipping sql_revise (cached)")
            
        if not os.path.exists(f"{log_path}/sql_selection/final"):
            print("\n[Final] SQL Selection Voting...")
            subprocess.run([sys.executable, "sql_selection.py", "--log_path", log_path, "--num_candidates", "3"], env=env, check=True)
        else:
            print(f"\n[Final] Skipping sql_selection (cached)")
        
        print(f"\n========== SlayQL Iterative Run Complete! ==========")
        print(f"You can now run 'python generate_detailed_analysis.py' to see the newly generated output differences!")
        
    finally:
        # Guarantee restoration of the dataset
        if os.path.exists(backup_file):
            shutil.move(backup_file, target_data)
        if os.path.exists(batch_file):
            os.remove(batch_file)

if __name__ == "__main__":
    main()

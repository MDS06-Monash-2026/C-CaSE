import os
import json
import glob
import argparse

def main():
    parser = argparse.ArgumentParser(description="Compare SQL Pipeline Executions")
    parser.add_argument("-i", "--instance", type=str, help="Specific instance ID to inspect (e.g. bq001)")
    args = parser.parse_args()

    # Discover existing log folders to infer the target size
    dirs = glob.glob("log_subset_*_slayql_ccase")
    if not dirs:
        print("No evaluation logs found in the current directory.")
        return
        
    # Get the highest subset size if multiple exist
    dirs.sort(key=lambda x: int(x.split("_")[2]), reverse=True)
    target_dir = dirs[0]
    target_size = target_dir.split("_")[2]
    
    baseline_dir = f"log_subset_{target_size}_autolink_baseline"
    ccase_dir = f"log_subset_{target_size}_slayql_ccase"
    
    print(f"Loading data from subset size {target_size}...")
    
    try:
        with open("spider2_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Could not find spider2_data.json!")
        return
        
    final_dir = os.path.join(ccase_dir, "sql_selection", "final")
    if not os.path.exists(final_dir):
        print(f"Could not find final SQL generation output at {final_dir}.")
        print("Has the SlayQL evaluation fully completed?")
        return
        
    instances = [d for d in os.listdir(final_dir) if os.path.isdir(os.path.join(final_dir, d))]
    
    if args.instance:
        if args.instance not in instances:
            print(f"Error: Instance '{args.instance}' not found in the evaluation results.")
            return
        instances = [args.instance]
    
    output_lines = []
    if not args.instance:
        output_lines.append(f"# 🔍 SQL Pipeline Execution Comparison\n")
        output_lines.append(f"> AutoLink vs SlayQL (C-CaSE) vs Gold Reference\n\n")
    
    import csv
    
    def format_csv_as_markdown(filepath, max_rows=5):
        if not os.path.exists(filepath):
            return "*(No execution results found or query failed)*\n"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
                if not reader:
                    return "*(Empty result set)*\n"
                
                headers = reader[0]
                rows = reader[1:max_rows+1]
                
                md_table = f"| {' | '.join(headers)} |\n"
                md_table += f"|{'|'.join(['---'] * len(headers))}|\n"
                for row in rows:
                    md_table += f"| {' | '.join(row)} |\n"
                
                if len(reader) > max_rows + 1:
                    md_table += f"\n*...and {len(reader) - max_rows - 1} more rows.*\n"
                    
                return md_table
        except Exception as e:
            return f"*(Error reading results: {e})*\n"

    for i, iid in enumerate(sorted(instances)):
        if not args.instance:
            output_lines.append(f"## {i+1}. Instance: `{iid}`\n")
        else:
            output_lines.append(f"# 🔍 Inspection Report: `{iid}`\n")
        
        # User Natural Language Question
        question = data.get(iid, {}).get("question", "Question not found in spider2_data.json")
        output_lines.append(f"**Question:**\n> {question}\n\n")
        
        # Gold Answer
        gold_path = f"../evaluation_suite/gold/sql/{iid}.sql"
        gold_sql = open(gold_path, "r", encoding="utf-8").read().strip() if os.path.exists(gold_path) else "N/A"
        output_lines.append(f"### 🏆 Gold Reference Answer\n```sql\n{gold_sql}\n```\n")
        gold_csv = glob.glob(f"../evaluation_suite/gold/exec_result/{iid}*.csv")
        gold_csv_path = gold_csv[0] if gold_csv else ""
        output_lines.append(f"**Execution Output:**\n{format_csv_as_markdown(gold_csv_path)}\n\n")
        
        # Baseline (AutoLink)
        base_path = f"{baseline_dir}/sql_selection/final/{iid}/selected.sql"
        base_sql = open(base_path, "r", encoding="utf-8").read().strip() if os.path.exists(base_path) else "N/A"
        output_lines.append(f"### 🤖 AutoLink Baseline Prediction\n```sql\n{base_sql}\n```\n")
        base_csv = f"{baseline_dir}/sql_selection/final/{iid}/result.csv"
        output_lines.append(f"**Execution Output:**\n{format_csv_as_markdown(base_csv)}\n\n")
        
        # C-CaSE (SlayQL)
        ccase_path = f"{ccase_dir}/sql_selection/final/{iid}/selected.sql"
        ccase_sql = open(ccase_path, "r", encoding="utf-8").read().strip() if os.path.exists(ccase_path) else "N/A"
        output_lines.append(f"### 🚀 SlayQL (C-CaSE) Prediction\n```sql\n{ccase_sql}\n```\n")
        ccase_csv = f"{ccase_dir}/sql_selection/final/{iid}/result.csv"
        output_lines.append(f"**Execution Output:**\n{format_csv_as_markdown(ccase_csv)}\n\n")
        
        output_lines.append("---\n\n")
        
    if args.instance:
        print("\n".join(output_lines))
    else:
        report_file = "comparison_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.writelines(output_lines)
            
        print(f"\n[SUCCESS] Generated comparison report for {len(instances)} instances!")
        print(f"You can now open the '{report_file}' file to visually compare the SQL outputs.")

if __name__ == "__main__":
    main()

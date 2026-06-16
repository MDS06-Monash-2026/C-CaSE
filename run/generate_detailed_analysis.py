import os
import json
import glob
import csv
import shutil
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

def get_csv_rows(filepath):
    """Safely extracts all rows from a CSV as normalized string tuples for set comparison"""
    if not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            if len(reader) <= 1: # Empty or just headers
                return set()
            
            rows = set()
            for row in reader[1:]:
                # Normalize values: lowercased and stripped to prevent minor format mismatches
                clean_row = tuple(str(x).strip().lower() for x in row)
                rows.add(clean_row)
            return rows
    except:
        return set()

def main():
    dirs = glob.glob("log_subset_*_slayql_ccase")
    if not dirs:
        print("No evaluation logs found.")
        return
        
    # Sort by the most recently modified directory to automatically pick up the newest run
    dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    target_dir = dirs[0]
    target_size = target_dir.split("_")[2]
    
    baseline_dir = f"log_subset_{target_size}_autolink_baseline"
    if not os.path.exists(baseline_dir):
        # Fallback to the master baseline so dev iterative scripts can still compare against it
        baseline_dir = "log_subset_109_autolink_baseline"
        
    ccase_dir = target_dir
    
    try:
        with open("spider2_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("spider2_data.json not found!")
        return

    final_dir = os.path.join(ccase_dir, "sql_selection", "final")
    if not os.path.exists(final_dir):
        print(f"Could not find final SQL directory: {final_dir}")
        return
        
    instances = [d for d in os.listdir(final_dir) if os.path.isdir(os.path.join(final_dir, d))]
    
    base_out_dir = "detailed_analysis"
    os.makedirs(base_out_dir, exist_ok=True)
    
    print(f"Generating deep analysis for {len(instances)} instances...")
    
    for iid in sorted(instances):
        iid_dir = os.path.join(base_out_dir, iid)
        os.makedirs(iid_dir, exist_ok=True)
        
        question = data.get(iid, {}).get("question", "Unknown question")
        
        # Gather File Paths
        gold_path = f"../evaluation_suite/gold/sql/{iid}.sql"
        gold_csv = glob.glob(f"../evaluation_suite/gold/exec_result/{iid}*.csv")
        gold_csv_path = gold_csv[0] if gold_csv else ""
        
        base_path = f"{baseline_dir}/sql_selection/final/{iid}/selected.sql"
        base_csv = f"{baseline_dir}/sql_selection/final/{iid}/result.csv"
        
        ccase_path = f"{ccase_dir}/sql_selection/final/{iid}/selected.sql"
        ccase_csv = f"{ccase_dir}/sql_selection/final/{iid}/result.csv"
        
        # Copy the raw CSVs into the instance folder for the user's manual inspection
        if gold_csv_path: shutil.copy2(gold_csv_path, os.path.join(iid_dir, "gold.csv"))
        if os.path.exists(base_csv): shutil.copy2(base_csv, os.path.join(iid_dir, "autolink.csv"))
        if os.path.exists(ccase_csv): shutil.copy2(ccase_csv, os.path.join(iid_dir, "slayql.csv"))
        
        # Read the raw SQL text
        gold_sql = open(gold_path, encoding="utf-8").read().strip() if os.path.exists(gold_path) else "N/A"
        base_sql = open(base_path, encoding="utf-8").read().strip() if os.path.exists(base_path) else "N/A"
        ccase_sql = open(ccase_path, encoding="utf-8").read().strip() if os.path.exists(ccase_path) else "N/A"
        
        # Compute exact tabular diffs using set operations
        gold_rows = get_csv_rows(gold_csv_path)
        base_rows = get_csv_rows(base_csv)
        ccase_rows = get_csv_rows(ccase_csv)
        
        base_missing = gold_rows - base_rows
        base_extra = base_rows - gold_rows
        
        ccase_missing = gold_rows - ccase_rows
        ccase_extra = ccase_rows - gold_rows
        
        # Build the Markdown Report
        lines = [
            f"# Detailed Tabular & SQL Analysis: `{iid}`\n",
            f"**Question:** {question}\n\n",
            "---\n\n",
            "## 1. Execution Output Exact Differences\n\n",
            "This section compares the actual data rows returned by the database.\n\n"
        ]
        
        # AutoLink Tabular Diff
        lines.append("### 🤖 AutoLink vs 🏆 Gold\n")
        lines.append(f"- **Execution Match:** {'✅ Perfect Match' if not base_missing and not base_extra and len(gold_rows) > 0 else '❌ Failed/Mismatched'}\n")
        lines.append(f"- **Total Rows Generated:** {len(base_rows)} (Gold has {len(gold_rows)})\n")
        lines.append(f"- **Missing Rows (in Gold, not in AutoLink):** {len(base_missing)}\n")
        lines.append(f"- **Extra Rows (in AutoLink, not in Gold):** {len(base_extra)}\n\n")
        
        if base_missing:
            lines.append("#### Example Missing Rows (Failed to fetch)\n```text\n")
            for r in list(base_missing)[:5]: lines.append(str(r) + "\n")
            lines.append("```\n\n")
        if base_extra:
            lines.append("#### Example Extra Rows (Hallucinated or wrong filter)\n```text\n")
            for r in list(base_extra)[:5]: lines.append(str(r) + "\n")
            lines.append("```\n\n")
            
        # SlayQL Tabular Diff
        lines.append("### 🚀 SlayQL (C-CaSE) vs 🏆 Gold\n")
        lines.append(f"- **Execution Match:** {'✅ Perfect Match' if not ccase_missing and not ccase_extra and len(gold_rows) > 0 else '❌ Failed/Mismatched'}\n")
        lines.append(f"- **Total Rows Generated:** {len(ccase_rows)} (Gold has {len(gold_rows)})\n")
        lines.append(f"- **Missing Rows (in Gold, not in SlayQL):** {len(ccase_missing)}\n")
        lines.append(f"- **Extra Rows (in SlayQL, not in Gold):** {len(ccase_extra)}\n\n")
        
        if ccase_missing:
            lines.append("#### Example Missing Rows (Failed to fetch)\n```text\n")
            for r in list(ccase_missing)[:5]: lines.append(str(r) + "\n")
            lines.append("```\n\n")
        if ccase_extra:
            lines.append("#### Example Extra Rows (Hallucinated or wrong filter)\n```text\n")
            for r in list(ccase_extra)[:5]: lines.append(str(r) + "\n")
            lines.append("```\n\n")
            
        lines.append("---\n\n")
        lines.append("## 2. SQL Source Code Comparison\n\n")
        lines.append("### 🏆 Gold Reference Answer\n```sql\n" + gold_sql + "\n```\n\n")
        lines.append("### 🤖 AutoLink Baseline Prediction\n```sql\n" + base_sql + "\n```\n\n")
        lines.append("### 🚀 SlayQL (C-CaSE) Prediction\n```sql\n" + ccase_sql + "\n```\n\n")
            
        with open(os.path.join(iid_dir, "analysis_report.md"), "w", encoding="utf-8") as f:
            f.writelines(lines)
            
    print(f"\n[SUCCESS] Detailed analysis fully generated at 'd:\\C-CaSE\\run\\detailed_analysis\\' for {len(instances)} instances!")
    print(f"Check the 'detailed_analysis' folder. Every test case has its own folder containing the raw CSVs and an 'analysis_report.md' file.")

if __name__ == "__main__":
    main()

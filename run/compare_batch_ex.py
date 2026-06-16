import os
import glob
import csv
import argparse
import json

def get_csv_rows(filepath):
    if not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            if len(reader) <= 1:
                return set()
            
            rows = set()
            for row in reader[1:]:
                # Sort the values in the row so column order does not matter
                clean_row = tuple(sorted([str(x).strip().lower() for x in row]))
                rows.add(clean_row)
            return rows
    except:
        return set()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slayql_dir", default="log_subset_dev20_slayql_ccase", help="Path to SlayQL logs")
    parser.add_argument("--autolink_dir", default="log_subset_dev20_autolink_baseline", help="Path to AutoLink logs")
    args = parser.parse_args()

    baseline_dir = args.autolink_dir
    ccase_dir = args.slayql_dir
    
    final_dir = os.path.join(ccase_dir, "sql_selection", "final")
    if not os.path.exists(final_dir):
        print(f"Could not find final SQL directory: {final_dir}")
        return
        
    instances = [d for d in os.listdir(final_dir) if os.path.isdir(os.path.join(final_dir, d))]
    
    print(f"============================================================")
    print(f"          BATCH EXECUTION ACCURACY (EX) DASHBOARD           ")
    print(f"============================================================")
    print(f"Evaluating Directory : {ccase_dir}")
    print(f"Baseline Directory   : {baseline_dir}")
    print(f"Total Instances      : {len(instances)}")
    print(f"------------------------------------------------------------")
    
    autolink_correct = 0
    slayql_correct = 0
    
    autolink_passed_cases = []
    slayql_passed_cases = []
    
    for iid in instances:
        gold_csv = glob.glob(f"../evaluation_suite/gold/exec_result/{iid}*.csv")
        gold_csv_path = gold_csv[0] if gold_csv else ""
        
        base_csv = f"{baseline_dir}/sql_selection/final/{iid}/result.csv"
        ccase_csv = f"{ccase_dir}/sql_selection/final/{iid}/result.csv"
        
        gold_rows = get_csv_rows(gold_csv_path)
        base_rows = get_csv_rows(base_csv)
        ccase_rows = get_csv_rows(ccase_csv)
        
        # Determine if execution exactly matches gold output
        base_match = (len(gold_rows) > 0) and (gold_rows == base_rows)
        ccase_match = (len(gold_rows) > 0) and (gold_rows == ccase_rows)
        
        if base_match: 
            autolink_correct += 1
            autolink_passed_cases.append(iid)
        if ccase_match: 
            slayql_correct += 1
            slayql_passed_cases.append(iid)
        
    auto_ex = (autolink_correct / len(instances)) * 100 if instances else 0.0
    slay_ex = (slayql_correct / len(instances)) * 100 if instances else 0.0
    
    print(f"Baseline AutoLink EX : {autolink_correct} / {len(instances)} ({auto_ex:.2f}%)")
    print(f"SlayQL (MCP) EX      : {slayql_correct} / {len(instances)} ({slay_ex:.2f}%)")
    
    # Calculate performance difference
    diff = slay_ex - auto_ex
    diff_sign = "+" if diff >= 0 else ""
    print(f"------------------------------------------------------------")
    print(f"SlayQL Improvement   : {diff_sign}{diff:.2f}%")
    print(f"============================================================")
    
    # Print the specific cases
    print(f"\n[AutoLink Correct Cases]: {', '.join(autolink_passed_cases) if autolink_passed_cases else 'None'}")
    print(f"[SlayQL Correct Cases]: {', '.join(slayql_passed_cases) if slayql_passed_cases else 'None'}")
    
    # ---------------------------------------------------------
    # Generate LLM Analysis Context File
    # ---------------------------------------------------------
    slayql_improvements = set(slayql_passed_cases) - set(autolink_passed_cases)
    slayql_regressions = set(autolink_passed_cases) - set(slayql_passed_cases)
    both_failed = set(instances) - set(autolink_passed_cases) - set(slayql_passed_cases)
    
    llm_report = [
        f"# LLM Evaluation Context: AutoLink vs SlayQL (MCP) Batch Run",
        f"**Target Batch Size**: {len(instances)}",
        f"**Baseline AutoLink EX**: {autolink_correct} / {len(instances)} ({auto_ex:.2f}%)",
        f"**SlayQL (MCP) EX**: {slayql_correct} / {len(instances)} ({slay_ex:.2f}%)\n",
    ]
    
    import json
    questions_map = {}
    try:
        with open("spider2_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in data.items():
                questions_map[k] = v.get("question", "")
    except Exception as e:
        print(f"Error loading questions: {e}")
    
    # Helper to pull the detailed report
    def get_detailed_report(iid):
        report_path = os.path.join("detailed_analysis", iid, "analysis_report.md")
        question = questions_map.get(iid, "*(Question not found)*")
        header = f"**Question**: {question}\n\n"
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                return header + f.read()
        return header + f"*(Detailed report for {iid} not found)*"

    llm_report.append(f"## 1. SlayQL Improvements (Upgrades)")
    llm_report.append(f"These are instances where the Baseline FAILED, but the new SlayQL MCP agent PASSED:\n")
    if slayql_improvements:
        for iid in slayql_improvements:
            llm_report.append(f"### Improvement: {iid}")
            llm_report.append(get_detailed_report(iid))
            llm_report.append("\n---\n")
    else:
        llm_report.append("- None\n")
        
    llm_report.append(f"## 2. SlayQL Regressions (Downgrades)")
    llm_report.append(f"These are instances where the Baseline PASSED, but the new SlayQL MCP agent FAILED (Look at these to fix regressions!):\n")
    if slayql_regressions:
        for iid in slayql_regressions:
            llm_report.append(f"### Regression: {iid}")
            llm_report.append(get_detailed_report(iid))
            llm_report.append("\n---\n")
    else:
        llm_report.append("- None\n")
        
    llm_report.append(f"## 3. Persistently Failing Cases")
    llm_report.append(f"These instances failed in BOTH models. The schema or the problem might be too complex:\n")
    if both_failed:
        for iid in both_failed:
            llm_report.append(f"### Persistently Failing: {iid}")
            llm_report.append(get_detailed_report(iid))
            llm_report.append("\n---\n")
    else:
        llm_report.append("- None\n")
        
    with open("llm_analysis_context.md", "w", encoding="utf-8") as f:
        f.write("\n".join(llm_report))
        
    print(f"\n[INFO] Generated 'llm_analysis_context.md' with FULL details embedded for easy copy-pasting.")

if __name__ == "__main__":
    main()

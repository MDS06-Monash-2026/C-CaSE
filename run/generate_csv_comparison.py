import os
import json
import argparse
import pandas as pd

def load_correct_ids(csv_path):
    if not csv_path or not os.path.exists(csv_path):
        return set()
    try:
        df = pd.read_csv(csv_path)
        ids = set()
        for val in df["instance_id"].dropna():
            val = str(val)
            if val.startswith("sf_"):
                ids.add(val[3:])
            ids.add(val)
        return ids
    except Exception as e:
        print(f"Error loading {csv_path}: {e}")
        return set()

def read_result_csv(base_dir, instance_id, is_baseline=False):
    paths = []
    if is_baseline:
        parent_dir = os.path.dirname(base_dir)
        paths.append(os.path.join(parent_dir, "final_csv", f"{instance_id}.csv"))
        paths.append(os.path.join(parent_dir, "final_csv", f"sf_{instance_id}.csv"))
        paths.append(os.path.join(base_dir, instance_id, "result.csv"))
        paths.append(os.path.join(base_dir, f"sf_{instance_id}", "result.csv"))
    else:
        csv_dir = base_dir + "_csv"
        paths.append(os.path.join(csv_dir, f"{instance_id}.csv"))
        paths.append(os.path.join(csv_dir, f"sf_{instance_id}.csv"))
        paths.append(os.path.join(base_dir, instance_id, "result.csv"))
        paths.append(os.path.join(base_dir, f"sf_{instance_id}", "result.csv"))

    for path in paths:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                if df.empty:
                    return "Empty Result (0 rows)"
                if len(df.columns) > 10:
                    df = df.iloc[:, :10]
                    col_truncated = True
                else:
                    col_truncated = False
                
                markdown_table = df.head(5).to_markdown(index=False)
                total_rows = len(df)
                suffix = ""
                if total_rows > 5:
                    suffix += f"\n\n*... and {total_rows - 5} more rows.*"
                if col_truncated:
                    suffix += f"\n\n*... truncated to first 10 columns.*"
                return markdown_table + suffix
            except Exception as e:
                return f"Error reading CSV: {e}"
    return "N/A"

def read_gold_csv(instance_id):
    gold_dirs = [
        "../evaluation_suite/gold/exec_result",
        "evaluation_suite/gold/exec_result",
        "d:/C-CaSE/evaluation_suite/gold/exec_result"
    ]
    gold_dir = None
    for gd in gold_dirs:
        if os.path.exists(gd):
            gold_dir = gd
            break
            
    if not gold_dir:
        return "N/A"
        
    import re
    pattern = re.compile(rf"^{re.escape(instance_id)}(_[a-z])?\.csv$")
    files = sorted(f for f in os.listdir(gold_dir) if pattern.match(f))
    
    if not files:
        pattern_sf = re.compile(rf"^sf_{re.escape(instance_id)}(_[a-z])?\.csv$")
        files = sorted(f for f in os.listdir(gold_dir) if pattern_sf.match(f))
        
    if not files:
        return "N/A"
        
    results = []
    for file in files:
        path = os.path.join(gold_dir, file)
        try:
            df = pd.read_csv(path)
            if df.empty:
                results.append("Empty Gold Result")
                continue
            if len(df.columns) > 10:
                df = df.iloc[:, :10]
            markdown_table = df.head(5).to_markdown(index=False)
            total_rows = len(df)
            if total_rows > 5:
                markdown_table += f"\n\n*... and {total_rows - 5} more rows.*"
            results.append(markdown_table)
        except Exception as e:
            results.append(f"Error reading Gold CSV: {e}")
            
    return "\n\n**OR**\n\n".join(results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_file', type=str, default="subset_diverse_20_evaluation.json")
    parser.add_argument('--slayql_dir', type=str, default="log_subset_diverse_20_evaluation_slayql_ccase/sql_gen/r1_lite_sql_0")
    parser.add_argument('--baseline_dir', type=str, default="log_subset_diverse_20_evaluation_autolink_baseline/sql_selection/final")
    parser.add_argument('--output_path', type=str, default="csv_only_comparison_report.md")
    args = parser.parse_args()

    # Load data file
    with open(args.data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load correct IDs
    slayql_correct_path = f"{args.slayql_dir}_csv-ids.csv"
    if not os.path.exists(slayql_correct_path):
        slayql_correct_path = f"{args.slayql_dir}-ids.csv"
        
    baseline_correct_path = f"{args.baseline_dir}-ids.csv"

    slayql_correct = load_correct_ids(slayql_correct_path)
    baseline_correct = load_correct_ids(baseline_correct_path)

    improved = []
    degraded = []
    both_correct = []
    both_incorrect = []

    for instance_id, info in data.items():
        question = info.get("question", "N/A")
        db_name = info.get("db_name", "N/A")
        
        slayql_result = read_result_csv(args.slayql_dir, instance_id, is_baseline=False)
        baseline_result = read_result_csv(args.baseline_dir, instance_id, is_baseline=True)
        gold_result = read_gold_csv(instance_id)

        is_slayql_ok = instance_id in slayql_correct
        is_baseline_ok = instance_id in baseline_correct

        item = {
            "id": instance_id,
            "db": db_name,
            "question": question,
            "slayql_result": slayql_result,
            "baseline_result": baseline_result,
            "gold_result": gold_result,
            "slayql_ok": is_slayql_ok,
            "baseline_ok": is_baseline_ok
        }

        if is_slayql_ok and not is_baseline_ok:
            improved.append(item)
        elif not is_slayql_ok and is_baseline_ok:
            degraded.append(item)
        elif is_slayql_ok and is_baseline_ok:
            both_correct.append(item)
        else:
            both_incorrect.append(item)

    # Generate Markdown Report
    total = len(data)
    num_slayql_ok = len(improved) + len(both_correct)
    num_baseline_ok = len(degraded) + len(both_correct)

    md = []
    md.append("# SlayQL vs Baseline CSV Execution Results Comparison (True Offline Evaluation)")
    md.append("")
    md.append("## Summary Metrics")
    md.append("")
    md.append(f"| Metric | Baseline | SlayQL (Enhanced) | Change |")
    md.append(f"|---|---|---|---|")
    if total > 0:
        md.append(f"| **Correct Instances** | {num_baseline_ok} / {total} ({num_baseline_ok/total*100:.1f}%) | {num_slayql_ok} / {total} ({num_slayql_ok/total*100:.1f}%) | {num_slayql_ok - num_baseline_ok:+} |")
    else:
        md.append(f"| **Correct Instances** | 0 / 0 | 0 / 0 | +0 |")
    md.append("")
    md.append("### Category Breakdown")
    md.append(f"- **Improved** (❌ Baseline -> ✅ SlayQL): **{len(improved)}**")
    md.append(f"- **Degraded** (✅ Baseline -> ❌ SlayQL): **{len(degraded)}**")
    md.append(f"- **Both Correct**: **{len(both_correct)}**")
    md.append(f"- **Both Incorrect**: **{len(both_incorrect)}**")
    md.append("")
    md.append("---")
    md.append("")

    def append_group(title, items, emoji_baseline, emoji_slayql):
        md.append(f"## {title} ({len(items)})")
        md.append("")
        if not items:
            md.append("No instances in this category.")
            md.append("")
            return

        for idx, item in enumerate(items, 1):
            md.append(f"### {idx}. {item['id']} (DB: `{item['db']}`)")
            md.append(f"**Question**: {item['question']}")
            md.append("")
            md.append(f"**Status**: Baseline {emoji_baseline} | SlayQL {emoji_slayql}")
            md.append("")
            
            md.append("#### 📊 Execution Results Comparison")
            md.append("")
            
            md.append("<details open>")
            md.append(f"<summary><b>Gold Standard Result (Expected)</b></summary>")
            md.append("")
            md.append(item['gold_result'])
            md.append("")
            md.append("</details>")
            md.append("")
            
            md.append("<details open>")
            md.append(f"<summary><b>SlayQL Execution Result ({emoji_slayql})</b></summary>")
            md.append("")
            md.append(item['slayql_result'])
            md.append("")
            md.append("</details>")
            md.append("")
            
            md.append("<details open>")
            md.append(f"<summary><b>Baseline Execution Result ({emoji_baseline})</b></summary>")
            md.append("")
            md.append(item['baseline_result'])
            md.append("")
            md.append("</details>")
            md.append("")
            md.append("---")
            md.append("")

    append_group("📈 Improved Instances (Baseline ❌ -> SlayQL ✅)", improved, "❌", "✅")
    append_group("📉 Degraded Instances (Baseline ✅ -> SlayQL ❌)", degraded, "✅", "❌")
    append_group("🤝 Both Correct (Baseline ✅ -> SlayQL ✅)", both_correct, "✅", "✅")
    append_group("❌ Both Incorrect (Baseline ❌ -> SlayQL ❌)", both_incorrect, "❌", "❌")

    # Save output
    output_dir = os.path.dirname(args.output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    with open(args.output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"CSV Comparison report written successfully to {args.output_path}")

if __name__ == "__main__":
    main()

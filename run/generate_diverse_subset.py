import json
import random
import argparse
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="Generate a uniform and diverse subset of Spider2")
    parser.add_argument("--input", default="spider2_data.json", help="Original dataset")
    parser.add_argument("--output", default="subset_diverse_20_evaluation.json", help="Output subset file")
    parser.add_argument("--fraction", type=float, default=0.2, help="Fraction of the dataset to sample (default 20%)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for high reproducibility")
    args = parser.parse_args()

    # Highly reproducible
    random.seed(args.seed)

    print(f"Loading data from {args.input}...")
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Stratify the data
    # We will group by (engine, db_name) to ensure diversity
    groups = defaultdict(list)
    
    for instance_id, info in data.items():
        # Determine engine from prefix
        if instance_id.startswith("bq") or instance_id.startswith("ga"):
            engine = "bigquery"
        elif instance_id.startswith("sf"):
            engine = "snowflake"
        elif instance_id.startswith("local"):
            engine = "sqlite"
        else:
            engine = "unknown"
            
        db_name = info.get("db_name", "unknown")
        groups[(engine, db_name)].append((instance_id, info))

    sampled_data = {}
    engine_stats = defaultdict(int)
    
    print(f"Stratifying into {len(groups)} distinct database groups...")
    
    for (engine, db_name), items in groups.items():
        # Sort to guarantee determinism before random sampling
        items.sort(key=lambda x: x[0])
        
        # Calculate sample size for this group
        sample_size = max(1, int(len(items) * args.fraction))
        # If the fraction is exactly 0.2 but group is e.g. 2, size is 1.
        
        sampled_items = random.sample(items, min(sample_size, len(items)))
        
        for inst_id, info in sampled_items:
            sampled_data[inst_id] = info
            engine_stats[engine] += 1

    # Save to new JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(sampled_data, f, indent=4, ensure_ascii=False)

    print("\n" + "="*40)
    print("✨ Diverse Subset Generation Complete ✨")
    print("="*40)
    print(f"Original Dataset Size: {len(data)}")
    print(f"Target Fraction:       {args.fraction * 100:.0f}%")
    print(f"New Dataset Size:      {len(sampled_data)}")
    print("\nBreakdown by Engine:")
    for engine, count in engine_stats.items():
        print(f"  - {engine.capitalize().ljust(12)} : {count} instances")
    print(f"\nHighly reproducible dataset saved to: {args.output}")

if __name__ == "__main__":
    main()

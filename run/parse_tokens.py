import os
import argparse

try:
    import tiktoken
except ImportError:
    tiktoken = None

def count_tokens(text, model="gpt-4"):
    if tiktoken:
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception:
            pass
    # Fallback to word approximation
    return len(text.split()) * 1.3

def parse_tokens(log_path, data_file=None):
    import json
    
    subset_ids = None
    if data_file and os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            subset_data = json.load(f)
            subset_ids = set(subset_data.keys())

    input_dir = os.path.join(log_path, "input") # Note: directory is 'input', not 'inputs' based on listing
    if not os.path.exists(input_dir):
        # try 'inputs' as fallback
        input_dir = os.path.join(log_path, "inputs")
        
    output_dir = os.path.join(log_path, "model_output")
    
    if not os.path.exists(input_dir) or not os.path.exists(output_dir):
        print(f"Missing log directories for token parsing in {log_path}.")
        return

    total_input_tokens = 0
    total_output_tokens = 0
    total_queries = 0

    for file in os.listdir(input_dir):
        if file.endswith(".txt"):
            instance_id = file[:-4]
            if subset_ids is not None and instance_id not in subset_ids:
                continue
                
            total_queries += 1
            with open(os.path.join(input_dir, file), "r", encoding="utf-8") as f:
                content = f.read()
                total_input_tokens += count_tokens(content)

    for file in os.listdir(output_dir):
        if file.endswith(".txt"):
            instance_id = file[:-4]
            if subset_ids is not None and instance_id not in subset_ids:
                continue
                
            with open(os.path.join(output_dir, file), "r", encoding="utf-8") as f:
                content = f.read()
                total_output_tokens += count_tokens(content)

    total_tokens = total_input_tokens + total_output_tokens
    avg_tokens = total_tokens / max(1, total_queries)

    print("\n" + "="*50)
    print(f"TOKEN CONSUMPTION METRICS ({log_path})")
    print("="*50)
    print(f"Total Queries Evaluated: {total_queries}")
    print(f"Total Input Tokens:      {int(total_input_tokens)}")
    print(f"Total Output Tokens:     {int(total_output_tokens)}")
    print(f"Total Tokens Used:       {int(total_tokens)}")
    print(f"Average Tokens/Query:    {int(avg_tokens)}")
    print("="*50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', type=str, required=True)
    parser.add_argument('--data_file', type=str, default="subset_diverse_20_evaluation.json")
    args = parser.parse_args()
    parse_tokens(args.log_path, args.data_file)

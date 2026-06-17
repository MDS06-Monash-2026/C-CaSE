import os
import json
import concurrent.futures
import networkx as nx
from networkx.algorithms.approximation import steiner_tree
from openai import OpenAI
from utils import *
import argparse
from config import *
import threading

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
model = os.environ.get("MODEL_NAME")

_GRAPH_CACHE = {}
_GRAPH_LOCK = threading.Lock()

def get_db_graph(db_name, embed_path):
    with _GRAPH_LOCK:
        if db_name in _GRAPH_CACHE:
            return _GRAPH_CACHE[db_name]
        
        G = nx.Graph()
        metadata_path = os.path.join(embed_path, db_name, "metadata.json")
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except:
            metadata = []
            
        tables = set(meta["table"] for meta in metadata)
        for t in tables:
            G.add_node(t)
            
        table_columns = {}
        for meta in metadata:
            t = meta["table"]
            c = meta["column"].lower()
            if t not in table_columns:
                table_columns[t] = set()
            table_columns[t].add(c)
            
        table_list = list(tables)
        for i in range(len(table_list)):
            for j in range(i + 1, len(table_list)):
                t1, t2 = table_list[i], table_list[j]
                shared_cols = table_columns[t1].intersection(table_columns[t2])
                if any("id" in col or "name" in col or "code" in col or "key" in col for col in shared_cols):
                    # Edge weight = 1.0 (Uniform for basic Steiner tree, can be tuned)
                    G.add_edge(t1, t2, weight=1.0)
                    
        _GRAPH_CACHE[db_name] = G
        return G, metadata

def tscg_compress(schema_metadata):
    """
    Tool-Schema Compression Grammar (TSCG) Implementation.
    1. Constraint-First Layout (CFL)
    2. Abbreviated Type Annotations (ATA)
    3. Structural Compression Operators (SCO)
    """
    compressed = []
    
    # Group by table
    tables = {}
    for meta in schema_metadata:
        t = meta["table"]
        if t not in tables:
            tables[t] = []
        tables[t].append(meta)
        
    for t, cols in tables.items():
        compressed.append(f"T[{t}]:")
        for c in cols:
            col_name = c["column"]
            col_type = c.get("column_type", "").upper()
            
            # ATA: Abbreviate common types
            if "VARCHAR" in col_type or "TEXT" in col_type or "STRING" in col_type: col_type = "str"
            elif "INT" in col_type or "NUM" in col_type or "FLOAT" in col_type: col_type = "num"
            elif "DATE" in col_type or "TIME" in col_type: col_type = "time"
            else: col_type = "any"
            
            # CFL: Constraints first (primary key, foreign key inference)
            prefix = ""
            if "id" in col_name.lower(): prefix = "[PK/FK]"
            
            # RKE: Remove redundant descriptions if they just repeat column name
            desc = c.get("description", "").strip()
            if desc.lower() == col_name.lower() or not desc:
                desc_str = ""
            else:
                # Strip excessive whitespace
                desc = " ".join(desc.split())
                desc_str = f" | {desc}"
                
            compressed.append(f"  - {prefix}{col_name}({col_type}){desc_str}")
            
    return "\n".join(compressed)

def process_instance(instance_id, info, log_path, embed_path):
    print(f"Processing {instance_id} via SlayQL 2.0 Deterministic Steiner Routing...")
    db_name = info["db_name"]
    question = info["question"]
    
    # 1. Build Graph & get metadata
    G, metadata = get_db_graph(db_name, embed_path)
    
    # 2. Extract Table Summaries
    tables = list(G.nodes)
    if not tables:
        # Fallback
        return
        
    table_summaries = ", ".join(tables)
    
    # 3. Prompt 1: Semantic Anchoring
    prompt = SEMANTIC_ANCHORING.replace("{list_of_all_tables_with_one_line_summaries}", table_summaries)
    prompt = prompt.replace("{user_question}", question)
    
    max_retries = 3
    terminal_nodes = set()
    for _ in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            terminal_nodes.update(parsed.get("source_tables", []))
            terminal_nodes.update(parsed.get("destination_tables", []))
            break
        except Exception as e:
            print(f"Anchoring error on {instance_id}: {e}")
            continue
            
    # Filter valid tables
    valid_terminals = [t for t in terminal_nodes if t in G.nodes]
    
    if not valid_terminals:
        # If no valid terminals found, fallback to all tables (or top 1)
        valid_terminals = tables[:1]
        
    # 4. Steiner Tree Optimization (KMB algorithm)
    try:
        # We need at least 2 nodes for steiner_tree
        if len(valid_terminals) > 1:
            # networkx steiner_tree requires weight='weight'
            steiner_subgraph = steiner_tree(G, valid_terminals, weight='weight')
            required_tables = set(steiner_subgraph.nodes)
        else:
            required_tables = set(valid_terminals)
    except Exception as e:
        print(f"Steiner tree error on {instance_id}: {e}")
        required_tables = set(valid_terminals)
        
    # 5. Extract specific metadata for required tables
    required_metadata = [m for m in metadata if m["table"] in required_tables]
    
    # 6. TSCG Compression
    distilled_schema = tscg_compress(required_metadata)
    
    # 7. Save output for SQL Gen
    out_dir = os.path.join(log_path, "final_schema_prompts")
    os.makedirs(out_dir, exist_ok=True)
    
    with open(os.path.join(out_dir, f"{instance_id}.txt"), "w", encoding="utf-8") as f:
        f.write(distilled_schema)

def complete_schema(log_path, embed_path, batch_file, num_threads=8):
    os.makedirs(os.path.join(log_path, "final_schema_prompts"), exist_ok=True)
    
    with open(batch_file, "r", encoding="utf-8") as f:
        spider2_data = json.load(f)
        
    instance_ids = []
    for k in spider2_data.keys():
        if not os.path.exists(os.path.join(log_path, "final_schema_prompts", f"{k}.txt")):
            instance_ids.append(k)
            
    if not instance_ids:
        print("All schemas already processed!")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for iid in instance_ids:
            futures.append(executor.submit(process_instance, iid, spider2_data[iid], log_path, embed_path))
            
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Thread failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', type=str, default="log_v3_topn100")
    parser.add_argument('--embed_path', type=str, default="../evaluation_suite/embeddings")
    parser.add_argument('--data_file', type=str, default="spider2_data.json")
    args = parser.parse_args()
    print("Starting SlayQL 2.0 Deterministic Schema Discovery...")
    complete_schema(args.log_path, args.embed_path, args.data_file, num_threads=8)
    print("Finished.")

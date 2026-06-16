import os
import json
import multiprocessing as mp
from tqdm import tqdm
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from utils import *
import argparse
import networkx as nx
import math

# Global tuning constants
ALPHA = 1.0
BETA = 0.5

import threading
_GRAPH_CACHE = {}
_GRAPH_LOCK = threading.Lock()

def get_or_build_schema_graph(db_name, embed_path):
    """
    Builds an undirected schema graph G where nodes are tables and edges are 
    formal or inferred primary-foreign key relationships.
    """
    with _GRAPH_LOCK:
        cache_key = f"{db_name}"
        if cache_key in _GRAPH_CACHE:
            return _GRAPH_CACHE[cache_key]
            
        import re
        G = nx.Graph()
        metadata_path = os.path.join(embed_path, db_name, "metadata.json")
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata_mapping = json.load(f)
            
        # Step 1: Register all unique tables as graph vertices
        # Sanitize wildcard tables (e.g., ga_sessions_20170701 -> ga_sessions_*)
        tables = set(re.sub(r'_\d+$', '_*', meta["table"]) for meta in metadata_mapping)
        for t in tables:
            G.add_node(t)
            
        # Step 2: Build inferred and explicit structural relationships
        table_columns = {}
        for meta in metadata_mapping:
            t = re.sub(r'_\d+$', '_*', meta["table"])
            c = meta["column"].lower()
            if t not in table_columns:
                table_columns[t] = set()
            table_columns[t].add(c)
            
        # Find overlapping columns with structural implications across tables
        table_list = list(tables)
        for i in range(len(table_list)):
            for j in range(i + 1, len(table_list)):
                t1, t2 = table_list[i], table_list[j]
                shared_cols = table_columns[t1].intersection(table_columns[t2])
                # Connect if they share index, identification, or key codes
                if any("id" in col or "name" in col or "code" in col for col in shared_cols):
                    G.add_edge(t1, t2)
                    
        _GRAPH_CACHE[cache_key] = G
        return G

def compute_graph_penalized_score(sim_score, candidate_table, active_tables, G):
    """
    Applies Dijkstra shortest-path penalties to the raw semantic similarity score.
    """
    if not active_tables:
        return sim_score
        
    min_hop = float('inf')
    for active_t in active_tables:
        try:
            hop_distance = nx.shortest_path_length(G, source=candidate_table, target=active_t)
            if hop_distance < min_hop:
                min_hop = hop_distance
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
            
    if min_hop == float('inf'):
        # Assign an unreachable topological penalty boundary
        return -100.0 
        
    # Score(c) = alpha * Sim(q,c) - beta * min Dijkstra(tc, t)
    return (ALPHA * sim_score) - (BETA * min_hop)


def sliding_window_table_match(metadata_table: str, target_table: str) -> bool:
    metadata_parts = metadata_table.lower().split('.')
    target_parts = target_table.lower().split('.')
    
    if len(target_parts) > len(metadata_parts):
        return False
    
    window_size = len(target_parts)
    
    for i in range(len(metadata_parts) - window_size + 1):
        window = metadata_parts[i:i + window_size]
        if window == target_parts:
            return True
    
    return False

def find_with_name(column_name: str, table_name: str, db_name: str, embed_path: str):
    metadata_path = os.path.join(embed_path, db_name, "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata_mapping = json.load(f)
    
    is_find = False
    result = []
    
    for idx, metadata in enumerate(metadata_mapping):
        if (metadata["column"].lower() == column_name.lower() and 
            sliding_window_table_match(metadata["table"], table_name)):
            is_find = True
            print("Exact match found:", metadata["column"], metadata["table"])
            result.append({
                "index": int(idx),
                "metadata": metadata
            })
    
    if not is_find:
        for idx, metadata in enumerate(metadata_mapping):
            if (metadata["column"].lower() == column_name.lower() and 
                sliding_window_table_match(mask_digits(metadata["table"]), mask_digits(table_name))):
                is_find = True
                print("Partial match found:", metadata["column"], metadata["table"])
                result.append({
                    "index": int(idx),
                    "metadata": metadata
                })
    
    if not is_find:
        max_count=5
        for idx, metadata in enumerate(metadata_mapping):
            if metadata["column"].lower() == column_name.lower():
                is_find = True
                print("Column match found:", metadata["column"], metadata["table"])
                result.append({
                    "index": int(idx),
                    "metadata": metadata
                })
                max_count -= 1
                if max_count <= 0:
                    break
    
    if not is_find:
        return "No matching column found. Please check the column name and table name."
    else:
        return result

def _retrieve_with_device_filtered(question: str, db_name: str, embed_path: str, 
                                 excluded_indices: set, top_k: int = 5, device: str = "cuda:0", active_tables=None):
    from model_manager import model_manager
    index_path = os.path.join(embed_path, db_name, "index.faiss")
    index = faiss.read_index(index_path)
    metadata_path = os.path.join(embed_path, db_name, "metadata.json")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata_mapping = json.load(f)
    model_manager.load_model(device=device)
    question_embedding = model_manager.encode(question)
    distances, indices = index.search(question_embedding.reshape(1, -1), len(metadata_mapping))
    filtered_results = []
    
    use_graph_nav = os.environ.get("USE_GRAPH_NAV") == "TRUE"
    if use_graph_nav and active_tables:
        G = get_or_build_schema_graph(db_name, embed_path)
    
    all_candidates = []
    for i in range(len(indices[0])):
        idx = int(indices[0][i])
        if 0 <= idx < len(metadata_mapping) and idx not in excluded_indices:
            metadata = metadata_mapping[idx]
            sim_score = float(distances[0][i])
            
            if use_graph_nav and active_tables:
                final_score = compute_graph_penalized_score(sim_score, metadata["table"], active_tables, G)
            else:
                final_score = sim_score
                
            all_candidates.append({
                "index": idx,
                "distance": final_score,
                "metadata": metadata
            })
            
    if use_graph_nav and active_tables:
        # Sort descending because score = alpha * sim - beta * penalty implies higher is better.
        all_candidates.sort(key=lambda x: x["distance"], reverse=True)
        filtered_results = all_candidates[:top_k]
    else:
        filtered_results = all_candidates[:top_k]
    
    return filtered_results, len(metadata_mapping)


def load_instance_cache(instance_id: str, cache_dir: str):
    cache_file = os.path.join(cache_dir, f"{instance_id}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"used_indices": []}


def save_instance_cache(instance_id: str, cache_dir: str, cache_data: dict):
    os.makedirs(cache_dir, exist_ok=True)
    if "used_indices" in cache_data:
        cache_data["used_indices"] = [int(idx) for idx in cache_data["used_indices"]]
    
    cache_file = os.path.join(cache_dir, f"{instance_id}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def load_instance_status(instance_id: str, status_dir: str):
    status_file = os.path.join(status_dir, f"{instance_id}.json")
    if os.path.exists(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "is_complete": False,
        "total_available": 0,
        "used_count": 0,
        "remaining_count": 0
    }


def save_instance_status(instance_id: str, status_dir: str, status_data: dict):
    os.makedirs(status_dir, exist_ok=True)

    cleaned_status = {}
    for key, value in status_data.items():
        if isinstance(value, (np.integer, np.int64, np.int32)):
            cleaned_status[key] = int(value)
        elif isinstance(value, (np.floating, np.float64, np.float32)):
            cleaned_status[key] = float(value)
        else:
            cleaned_status[key] = value
    
    status_file = os.path.join(status_dir, f"{instance_id}.json")
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_status, f, ensure_ascii=False, indent=2)


def get_next_k_results(instance_id: str, question: str, db_name: str, embed_path: str, 
                      top_k: int, cache_dir: str, status_dir: str, device: str, active_tables=None):
    cache = load_instance_cache(instance_id, cache_dir)
    status = load_instance_status(instance_id, status_dir)
    
    used_indices = set(cache.get("used_indices", []))
    
    if status.get("is_complete", False):
        print(f"Instance {instance_id} retrieve all completed.")
        return [], {}, "All columns in this databases are retrieved. There is no need to retrieve again."
    
    results, total_available = _retrieve_with_device_filtered(
        question=question,
        db_name=db_name, 
        embed_path=embed_path,
        excluded_indices=used_indices,
        top_k=top_k,
        device=device,
        active_tables=active_tables
    )
    
    if status.get("total_available", 0) == 0:
        status["total_available"] = total_available
    
    new_used_indices = [int(result["index"]) for result in results]
    all_used_indices = list(used_indices) + new_used_indices
    
    cache["used_indices"] = all_used_indices
    save_instance_cache(instance_id, cache_dir, cache)
    
    used_count = len(all_used_indices)
    remaining_count = total_available - used_count
    is_complete = len(results) < top_k or remaining_count <= 0
    
    status = {
        "is_complete": is_complete,
        "total_available": int(total_available), 
        "used_count": int(used_count),
        "remaining_count": int(remaining_count)
    }
    save_instance_status(instance_id, status_dir, status)
    
    metadata_mapping = {}
    for result in results:
        metadata_mapping[result["index"]] = result["metadata"]
    
    if is_complete:
        return results, metadata_mapping, "All columns in this databases are retrieved. There is no need to retrieve again."
    else:
        return results, metadata_mapping, ""


def process_batch_with_device(batch_items, device_id, top_k, log_dir):
    print(f"process {os.getpid()} - GPU {device_id}: loading model...")
    try:
        from model_manager import model_manager
        model_manager.load_model(device=f"cuda:{device_id}")
        memory_info = model_manager.get_memory_usage()
        if memory_info:
            print(f"process {os.getpid()} - GPU {device_id}: model has load to {memory_info['device']}")
        else:
            print(f"process {os.getpid()} - GPU {device_id}: model has load to CPU")
    except Exception as e:
        print(f"process {os.getpid()} - GPU {device_id}: model load failed: {e}")
        print(f"process {os.getpid()} - GPU {device_id}: will use CPU mode")
        model_manager.load_model(device="cpu")
    
    batch_results = {}
    
    cache_dir = os.path.join(log_dir, "cache")
    status_dir = os.path.join(log_dir, "status")
    
    device = f"cuda:{device_id}"
    
    import time
    pbar = tqdm(batch_items.items(), desc=f"GPU {device_id}")
    for instance_id, item in pbar:
        tqdm.write(f"[{time.strftime('%H:%M:%S')}] [PID {os.getpid()}] Processing instance {instance_id}...")
        pbar.set_description(f"GPU {device_id} - {instance_id}")
        question = item["question"]
        db_name = item["db_name"]

        embed_path = determine_embedding_path(instance_id)

        results, metadata_mapping, completion_message = get_next_k_results(
            instance_id=instance_id,
            question=question,
            db_name=db_name,
            embed_path=embed_path,
            top_k=top_k,
            cache_dir=cache_dir,
            status_dir=status_dir,
            device=device
        )

        table_candidates = []
        column_candidates = []
        column_types = []
        descriptions = []
        column_values = []

        for result in results:
            metadata = result["metadata"]

            table = metadata["table"]
            table_candidates.append(table)

            column = metadata["column"]
            column_candidates.append(column)

            column_type = metadata["column_type"]
            column_types.append(column_type)

            column_value = metadata["column_value"]
            column_values.append(column_value)

            description = metadata["description"]
            descriptions.append(description)

        batch_results[instance_id] = {
            "question": question,
            "db_name": db_name,
            "column_candidates": column_candidates,
            "column_types": column_types,
            "column_values": column_values,
            "table_candidates": table_candidates,
            "descriptions": descriptions,
            "retrieved_count": len(results)
        }

    return batch_results


def retrieve_additional(instance_id: str, question: str, additional_k: int, log_dir: str, device: str = "cuda:0"):
    cache_dir = os.path.join(log_dir, "cache")
    status_dir = os.path.join(log_dir, "status")
    
    with open("spider2_data.json", "r", encoding="utf-8") as f:
        spider2_data = json.load(f)
    
    if instance_id not in spider2_data:
        raise ValueError(f"Instance {instance_id} does not exist")
    
    db_name = spider2_data[instance_id]["db_name"]
    embed_path = determine_embedding_path(instance_id)
    
    results, metadata_mapping, completion_message = get_next_k_results(
        instance_id=instance_id,
        question=question,
        db_name=db_name,
        embed_path=embed_path,
        top_k=additional_k,
        cache_dir=cache_dir,
        status_dir=status_dir,
        device=device
    )
    
    formatted_results = []
    for result in results:
        metadata = result["metadata"]
        formatted_results.append({
            "table": metadata["table"],
            "column": metadata["column"],
            "column_type": metadata["column_type"],
            "column_value": metadata["column_value"],
            "description": metadata["description"],
            "distance": result["distance"]
        })
    
    return formatted_results, completion_message


def retrieve(log_dir: str, top_n: int = 50):
    os.makedirs(log_dir, exist_ok=True)

    with open("spider2_data.json", "r", encoding="utf-8") as f:
        spider2_data = json.load(f)

    instance_ids = list(spider2_data.keys())

    visible_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "0").split(",")
    num_gpus = len(visible_devices)
    
    batch_size = len(instance_ids) // num_gpus
    if batch_size == 0:
        batch_size = 1

    batches = []
    for i in range(num_gpus):
        start_idx = i * batch_size
        if i == num_gpus - 1: 
            end_idx = len(instance_ids)
        else:
            end_idx = (i + 1) * batch_size
        
        if start_idx < len(instance_ids):
            batch = {instance_id: spider2_data[instance_id] for instance_id in instance_ids[start_idx:end_idx]}
            batches.append((batch, i, top_n, log_dir))

    mp.set_start_method('spawn', force=True)
    
    with mp.Pool(processes=len(batches)) as pool:
        batch_results = pool.starmap(process_batch_with_device, batches)

    all_candidates = {}
    for instance_id in instance_ids:
        for batch_result in batch_results:
            if instance_id in batch_result:
                all_candidates[instance_id] = batch_result[instance_id]
                break

    with open(os.path.join(f"{log_dir}", "initial_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(all_candidates, f, ensure_ascii=False, indent=2)
        
    print(f"Retrieval completed, results saved to {log_dir}/")
    print(f"Cache saved to {log_dir}/cache/")
    print(f"Status saved to {log_dir}/status/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', type=str, default="log_v3_topn100")
    parser.add_argument('--top_n', type=int, default=100)
    args = parser.parse_args()

    retrieve(args.log_path, top_n=args.top_n)
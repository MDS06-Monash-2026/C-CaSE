import os
import json
import multiprocessing as mp
from tqdm import tqdm
import faiss
import numpy as np
from artifact_store import load_config, write_instance_artifact
from relationship_metadata import build_relationship_metadata
from sentence_transformers import SentenceTransformer
from utils import *
import argparse
from artifact_store import atomic_write_json

from rbp_graph import propagate_relevance
from it_ee import calculate_retrieval_entropy, determine_budget


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
                                 excluded_indices: set, top_k: int = 5, device: str = "cuda:0"):
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
    
    for i in range(len(indices[0])):
        idx = int(indices[0][i])
        if 0 <= idx < len(metadata_mapping) and idx not in excluded_indices:
            metadata = metadata_mapping[idx]
            filtered_results.append({
                "index": idx,
                "distance": float(distances[0][i]),
                "metadata": metadata
            })
            if len(filtered_results) >= top_k:
                break
    
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
                      top_k: int, cache_dir: str, status_dir: str, device: str):
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
        device=device
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


def _focus_retrieval_results(results, config):
    """Keep a compact, table-balanced schema context for downstream stages."""
    limits = dict(config["retrieval"])
    if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.5", "1.6", "1.7"}:
        # v1.4's focus had sub-perfect table recall and generated candidates
        # often omitted gold tables. Preserve alternatives for v1.5 paths.
        limits.update({"max_tables": 8, "max_columns_per_table": 12, "max_columns_total": 72})
    max_tables = int(limits.get("max_tables", 5))
    max_columns_per_table = int(limits.get("max_columns_per_table", 6))
    max_columns_total = int(limits.get("max_columns_total", limits.get("max_prompt_columns", 30)))

    def score_of(result):
        if result.get("propagated_score") is not None:
            return float(result["propagated_score"])
        if result.get("score") is not None:
            return float(result["score"])
        if result.get("similarity") is not None:
            return float(result["similarity"])
        if result.get("distance") is not None:
            return 1.0 / (1.0 + max(0.0, float(result["distance"])))
        return 0.0

    table_scores = {}
    for result in results:
        metadata = result.get("metadata", {})
        table = result.get("table") or result.get("table_name") or metadata.get("table")
        if not table:
            continue
        score = score_of(result)
        table_scores[table] = max(table_scores.get(table, float("-inf")), score)

    selected_tables = {
        table
        for table, _ in sorted(table_scores.items(), key=lambda item: item[1], reverse=True)[
            : max_tables
        ]
    }
    per_table = {table: 0 for table in selected_tables}
    focused = []
    for result in sorted(
        results,
        key=score_of,
        reverse=True,
    ):
        metadata = result.get("metadata", {})
        table = result.get("table") or result.get("table_name") or metadata.get("table")
        if table not in selected_tables:
            continue
        if per_table[table] >= max_columns_per_table:
            continue
        focused.append(result)
        per_table[table] += 1
        if len(focused) >= max_columns_total:
            break
    return focused


def _choose_operating_mode(question, results, relationship_metadata, config):
    tables = {
        result.get("table") or result.get("table_name")
        for result in results
        if result.get("table") or result.get("table_name")
    }
    normalized = f" {question.lower()} "
    structural_terms = (
        " join ", " each ", " per ", " except ", " versus ", " compared ",
        " highest ", " lowest ", " top ", " rank ", " before ", " after ",
    )
    graph_missing = len(tables) > 1 and not relationship_metadata.get("edges")
    hard = graph_missing or len(tables) >= 4 or any(term in normalized for term in structural_terms)
    medium = len(tables) > 1 or len(question.split()) > 22
    mode = "hard" if hard else "medium" if medium else "easy"
    return mode, int(config["completion"]["turns_by_mode"][mode])


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
    
    for instance_id, item in tqdm(batch_items.items(), desc=f"GPU {device_id} - 进程 {os.getpid()}"):
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

        try:
            with open("documents/bigquery.json", "r", encoding="utf-8") as bf: bq_docs = json.load(bf)
            with open("documents/snowflake.json", "r", encoding="utf-8") as sf: sf_docs = json.load(sf)
            with open("documents/localdb.json", "r", encoding="utf-8") as lf: local_docs = json.load(lf)
            if instance_id.startswith("bq") or instance_id.startswith("ga"):
                db_metadata = {"tables": list(bq_docs.get(db_name, {}).keys())}
            elif instance_id.startswith("sf"):
                db_metadata = {"tables": list(sf_docs.get(db_name, {}).keys())}
            else:
                db_metadata = {"tables": list(local_docs.get(db_name, {}).keys())}
        except:
            db_metadata = {"tables": []}

        initial_similarities = {}
        for res in results:
            sim = 1.0 / (1.0 + float(res["distance"]))
            col_path = f"{res['metadata']['table']}.{res['metadata']['column']}"
            initial_similarities[col_path] = sim

        # ------------------------------------------------------------------
        # Compute entropy BEFORE propagation so RBP can use it to set
        # a dynamic alpha (high confidence → minimal propagation).
        # ------------------------------------------------------------------
        top_n_scores_raw = [1.0 / (1.0 + float(res["distance"])) for res in results[:top_k]]
        entropy = calculate_retrieval_entropy(top_n_scores_raw, temp=0.1)

        # ------------------------------------------------------------------
        # ABLATION FLAGS  (set by ablation scripts via environment variables)
        #   ABLATION_NO_RBP=1        → skip graph propagation entirely
        #   ABLATION_RBP_ALPHA=0.7   → override static alpha (bypasses dynamic)
        #   ABLATION_NO_ITEE=1       → force full-turn budget (max tokens)
        #   ABLATION_ITEE_THRESHOLD=0.4 → override IT-EE threshold
        # ------------------------------------------------------------------
        no_rbp       = os.environ.get("ABLATION_NO_RBP", "0") == "1"
        rbp_alpha_ov = os.environ.get("ABLATION_RBP_ALPHA", None)
        no_itee      = os.environ.get("ABLATION_NO_ITEE", "0") == "1"
        itee_thresh  = float(os.environ.get("ABLATION_ITEE_THRESHOLD", "0.4"))

        if no_rbp:
            # w/o RBP: use raw cosine similarity ordering (no graph propagation)
            print(f"[ABLATION] RBP disabled — using raw cosine similarity ordering.")
            S_propagated = initial_similarities
        elif rbp_alpha_ov is not None:
            # Hyperparameter sweep: override alpha with a fixed static value
            static_alpha = float(rbp_alpha_ov)
            print(f"[ABLATION] RBP static alpha override = {static_alpha}")
            S_propagated = propagate_relevance(
                initial_similarities,
                db_metadata,
                alpha=static_alpha,
                entropy=None,   # suppress dynamic alpha when sweeping
                query=question,
            )
        else:
            # Normal SlayQL: RBP with dynamic alpha derived from entropy
            S_propagated = propagate_relevance(
                initial_similarities,
                db_metadata,
                entropy=entropy,
                query=question,
            )

        for res in results:
            col_path = f"{res['metadata']['table']}.{res['metadata']['column']}"
            res["propagated_score"] = S_propagated.get(col_path, 0.0)

        results = sorted(results, key=lambda x: x["propagated_score"], reverse=True)

        # v1.4 keeps the candidate pool table-balanced after graph propagation.
        # The completion agent can still request more schema evidence when the
        # bounded pool is insufficient, so this is a precision pass, not a hard
        # database restriction.
        if os.environ.get("SLAYQL_RESEARCH_VERSION") in {"1.4", "1.5", "1.6", "1.7"}:
            results = _focus_retrieval_results(results, load_config())

        if no_itee:
            # w/o IT-EE: always allocate the full 10-turn budget (never exits early)
            print(f"[ABLATION] IT-EE disabled — forcing full 10-turn budget.")
            should_early_exit, dynamic_t_max = False, 10
        else:
            # Normal SlayQL: entropy-based budget with optional threshold override
            should_early_exit, dynamic_t_max = determine_budget(
                entropy,
                query=question,
                base_turns=10,
                threshold=itee_thresh,
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
            "retrieved_count": len(results),
            "should_early_exit": should_early_exit,
            "dynamic_t_max": dynamic_t_max,
            "entropy": entropy
        }

    return batch_results


def retrieve_additional(instance_id: str, question: str, additional_k: int, log_dir: str, device: str = "cuda:0", data_file="spider2_data.json"):
    cache_dir = os.path.join(log_dir, "cache")
    status_dir = os.path.join(log_dir, "status")
    
    with open(data_file, "r", encoding="utf-8") as f:
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


def retrieve(log_dir: str, top_n: int = 50, data_file="spider2_data.json"):
    output_file = os.path.join(log_dir, "initial_candidates.json")
    if os.path.exists(output_file):
        print(f"Output file {output_file} already exists. Skipping retrieval phase.")
        return
    os.makedirs(log_dir, exist_ok=True)

    with open(data_file, "r", encoding="utf-8") as f:
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

    atomic_write_json(os.path.join(log_dir, "initial_candidates.json"), all_candidates)
        
    print(f"Retrieval completed, results saved to {log_dir}/")
    print(f"Cache saved to {log_dir}/cache/")
    print(f"Status saved to {log_dir}/status/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_path', type=str, default="log_v3_topn100")
    parser.add_argument('--top_n', type=int, default=100)
    parser.add_argument('--data_file', type=str, default="spider2_data.json")

    # -----------------------------------------------------------------------
    # Ablation study flags — passed via environment variables to sub-processes.
    # These args set the corresponding env vars so process_batch_with_device
    # inherits them automatically via os.environ.
    # -----------------------------------------------------------------------
    parser.add_argument('--no_itee', action='store_true',
                        help="[Ablation 1] Disable IT-EE — always use max turns.")
    parser.add_argument('--no_rbp', action='store_true',
                        help="[Ablation 1] Disable RBP — use raw cosine similarity.")
    parser.add_argument('--itee_threshold', type=float, default=None,
                        help="[Ablation 3] Override IT-EE entropy threshold (θ).")
    parser.add_argument('--rbp_alpha', type=float, default=None,
                        help="[Ablation 3] Override RBP static damping factor (α).")
    args = parser.parse_args()

    # Wire ablation flags into environment before spawning child processes
    if args.no_itee:
        os.environ["ABLATION_NO_ITEE"] = "1"
    if args.no_rbp:
        os.environ["ABLATION_NO_RBP"] = "1"
    if args.itee_threshold is not None:
        os.environ["ABLATION_ITEE_THRESHOLD"] = str(args.itee_threshold)
    if args.rbp_alpha is not None:
        os.environ["ABLATION_RBP_ALPHA"] = str(args.rbp_alpha)

    retrieve(args.log_path, top_n=args.top_n, data_file=args.data_file)

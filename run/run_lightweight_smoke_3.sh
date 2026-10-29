#!/usr/bin/env bash
# End-to-end SlayQL smoke test over three representative Spider 2.0 questions.
# Run from Git Bash/WSL: bash run_lightweight_smoke_3.sh [--fresh] [--skip-eval]

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_DATA="spider2_data.json"
DATA_FILE="smoke_lightweight_3.json"
LOG_DIR="log_smoke_lightweight_3"
ARTIFACT_ROOT="${LOG_DIR}/artifacts"
TASK="r1_lite"
TOP_N=40
NUM_CANDIDATES=3
IDS=("bq011" "sf_bq029" "local002")
FRESH=0
SKIP_EVAL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fresh) FRESH=1; shift ;;
        --skip-eval) SKIP_EVAL=1; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ "$FRESH" -eq 1 ]]; then
    case "$LOG_DIR" in
        log_smoke_lightweight_3) rm -rf -- "$LOG_DIR" ;;
        *) echo "Refusing to remove unexpected directory: $LOG_DIR" >&2; exit 2 ;;
    esac
    rm -f -- "$DATA_FILE"
fi

command -v python >/dev/null 2>&1 || { echo "python is required" >&2; exit 1; }
[[ -f "$SOURCE_DATA" ]] || { echo "Missing $SCRIPT_DIR/$SOURCE_DATA" >&2; exit 1; }
[[ -d documents ]] || { echo "Missing run/documents; generate schema documents first" >&2; exit 1; }
[[ -d embeddings ]] || { echo "Missing run/embeddings; generate embeddings first" >&2; exit 1; }

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

python - "$SOURCE_DATA" "$DATA_FILE" "${IDS[@]}" <<'PY'
import json
import sys

source_path, output_path, *ids = sys.argv[1:]
with open(source_path, encoding="utf-8") as handle:
    source = json.load(handle)
missing = [instance_id for instance_id in ids if instance_id not in source]
if missing:
    raise SystemExit(f"Missing smoke-test IDs: {missing}")
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump({instance_id: source[instance_id] for instance_id in ids}, handle, indent=2)
    handle.write("\n")
print("Smoke questions:")
for instance_id in ids:
    print(f"  {instance_id}: {source[instance_id]['question']}")
PY

mkdir -p "$LOG_DIR"
CKPT_FILE="${LOG_DIR}/.pipeline_ckpt"
touch "$CKPT_FILE"

done_stage() { grep -q "^STAGE_$1=done$" "$CKPT_FILE" 2>/dev/null; }
mark_done() { done_stage "$1" || echo "STAGE_$1=done" >> "$CKPT_FILE"; }
count_files() {
    if [[ ! -d "$1" ]]; then
        echo 0
        return
    fi
    find "$1" -type f -name "$2" | wc -l | tr -d ' '
}

echo "=== [1/13] BM25 value indices ==="
if ! done_stage 1; then
    python build_value_indices.py --data_file "$DATA_FILE"
    mark_done 1
fi

echo "=== [2/13] Retrieval (pool=$TOP_N) ==="
if [[ ! -f "${LOG_DIR}/initial_candidates.json" ]]; then
    python retrieve_topk_schema.py --log_path "$LOG_DIR" --top_n "$TOP_N" --data_file "$DATA_FILE"
fi
mark_done 2

echo "=== [3/13] Focus retrieval, relationships, contracts, adaptive turns ==="
if [[ ! -f "${LOG_DIR}/.lightweight_retrieval_done" ]]; then
    cp "${LOG_DIR}/initial_candidates.json" "${LOG_DIR}/initial_candidates.raw.json"
    python prepare_lightweight_inputs.py \
        --input "${LOG_DIR}/initial_candidates.raw.json" \
        --output "${LOG_DIR}/initial_candidates.prepared.json" \
        --artifact_root "$ARTIFACT_ROOT" \
        --base_dir "$SCRIPT_DIR"
    mv "${LOG_DIR}/initial_candidates.prepared.json" "${LOG_DIR}/initial_candidates.json"
    touch "${LOG_DIR}/.lightweight_retrieval_done"
fi
mark_done 3

echo "=== [4/13] Inject schema IDs ==="
if [[ ! -f "${LOG_DIR}/filled_pre_rule.json" ]]; then
    python add_id.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
fi
mark_done 4

echo "=== [5/13] Initial schema prompts ==="
if [[ "$(count_files "${LOG_DIR}/schema_prompts" '*.txt')" -lt 3 ]]; then
    python generate_schema.py --log_path "$LOG_DIR" --is_initial --data_file "$DATA_FILE"
fi
mark_done 5

echo "=== [6/13] Adaptive schema completion ==="
if ! done_stage 6; then
    python complete_schema.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
    mark_done 6
fi

echo "=== [7/13] Schema postprocess ==="
if [[ ! -f "${LOG_DIR}/filled_schema.json" ]]; then
    python postprocess.py --log_path "$LOG_DIR"
fi
mark_done 7

echo "=== [8/13] Final schema prompts and contract handoff ==="
if [[ "$(count_files "${LOG_DIR}/final_schema_prompts" '*.txt')" -lt 3 ]]; then
    python generate_schema.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
fi
python augment_schema_prompts.py \
    --prompt_dir "${LOG_DIR}/final_schema_prompts" \
    --contract_dir "${ARTIFACT_ROOT}/contracts"
mark_done 8

echo "=== [9/13] SQL generation (${NUM_CANDIDATES} candidates maximum) ==="
if ! done_stage 9; then
    python sql_generation.py --num_workers 3 --num_candidates "$NUM_CANDIDATES" \
        --data_file "$DATA_FILE" --schema_dir "${LOG_DIR}/final_schema_prompts" \
        --log_path "$LOG_DIR" --task "$TASK"
    mark_done 9
fi
GENERATED=$(count_files "${LOG_DIR}/sql_gen" '*.sql')
[[ "$GENERATED" -ge 3 ]] || { echo "Only $GENERATED SQL files were generated" >&2; exit 1; }

echo "=== [10/13] SQL execution ==="
if ! done_stage 10; then
    python sql_execution.py --num_workers 3 --num_candidates "$NUM_CANDIDATES" \
        --data_file "$DATA_FILE" --log_path "$LOG_DIR" --task "$TASK"
    mark_done 10
fi
python record_execution_artifacts.py \
    --execution_root "${LOG_DIR}/sql_gen" --artifact_root "$ARTIFACT_ROOT"
EXECUTED=$(find "${LOG_DIR}/sql_gen" -type f \( -path '*execution_result*/*.csv' -o -path '*execution_error*/*.txt' \) 2>/dev/null | wc -l | tr -d ' ')
[[ "$EXECUTED" -ge 3 ]] || { echo "Only $EXECUTED SQL executions were accounted for" >&2; exit 1; }

echo "=== [11/13] SQL revision ==="
if ! done_stage 11; then
    python sql_revise.py --num_workers 3 --num_candidates "$NUM_CANDIDATES" \
        --data_file "$DATA_FILE" --schema_dir "${LOG_DIR}/final_schema_prompts" \
        --log_path "$LOG_DIR" --task "$TASK"
    mark_done 11
fi

echo "=== [12/13] SQL selection ==="
SELECTED=$(count_files "${LOG_DIR}/sql_selection/final" 'selected.sql')
if [[ "$SELECTED" -lt 3 ]]; then
    python sql_selection.py --log_path "$LOG_DIR" --num_candidates "$NUM_CANDIDATES" \
        --workers 3 --task "$TASK" --data_file "$DATA_FILE"
fi
SELECTED=$(count_files "${LOG_DIR}/sql_selection/final" 'selected.sql')
[[ "$SELECTED" -ge 3 ]] || { echo "Only $SELECTED/3 instances completed selection" >&2; exit 1; }
mark_done 12

if [[ "$SKIP_EVAL" -eq 0 ]]; then
    echo "=== [13/13] Official evaluation ==="
    if [[ -d "${LOG_DIR}/sql_selection_v1/final" ]]; then
        RESULT_DIR="../run/${LOG_DIR}/sql_selection_v1/final"
    else
        RESULT_DIR="../run/${LOG_DIR}/sql_selection/final"
    fi
    (
        cd ../evaluation_suite
        python evaluate.py --mode exec_result --result_dir "$RESULT_DIR" \
            --gold_dir gold --data_file "../run/$DATA_FILE" --max_workers 3 \
            2>&1 | tee "../run/${LOG_DIR}/eval_result.txt"
    )
    mark_done 13
else
    echo "=== [13/13] Evaluation skipped by request ==="
fi

echo "Smoke pipeline completed."
echo "Questions: ${IDS[*]}"
echo "Generated SQL files: $GENERATED"
echo "Execution artifacts: $EXECUTED"
echo "Outputs: $SCRIPT_DIR/$LOG_DIR"

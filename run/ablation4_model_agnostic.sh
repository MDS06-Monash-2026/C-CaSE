#!/bin/bash
# =============================================================================
# ablation4_model_agnostic.sh — LLM Agnosticism / Model Swap Ablation
# =============================================================================
# AAAI Ablation Study 4: Proves SlayQL's framework is universally robust and
# does NOT succeed only because a strong LLM (DeepSeek-V3 / GPT-4o) is smart.
#
# ► RESUME-SAFE: Checkpoint files at <LOG_DIR>/.pipeline_ckpt track completed
#   stages for each model × system combination. Re-running the script
#   after an interruption skips all fully-completed stages automatically.
#
# Usage:
#   bash ablation4_model_agnostic.sh
#   bash ablation4_model_agnostic.sh --weak_model gpt-4o-mini
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------
DATA_FILE="subset_diverse_20_evaluation.json"    # Subset of ~20-50 queries for speed
TOP_N=100
NUM_CANDIDATES=3                         # Reduced for cost efficiency
TASK="r1_lite"
NUM_GEN_WORKERS=16
NUM_EXEC_WORKERS=4
NUM_REVISE_WORKERS=4
NUM_SELECTION_WORKERS=16

# The weak/cheaper model to test. Override via --weak_model.
WEAK_MODEL="openai/gpt-4o-mini"

# Run modes: "all" | "weak_only" | "strong_only"
RUN_MODE="all"

while [[ $# -gt 0 ]]; do
    case $1 in
        --data_file) DATA_FILE="$2"; shift 2 ;;
        --weak_model) WEAK_MODEL="$2"; shift 2 ;;
        --top_n) TOP_N="$2"; shift 2 ;;
        --num_candidates) NUM_CANDIDATES="$2"; shift 2 ;;
        --task) TASK="$2"; shift 2 ;;
        --run_mode) RUN_MODE="$2"; shift 2 ;;
        *) echo "[WARN] Unknown argument: $1"; shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi
export PYTHONPATH="."

# Capture the primary (strong) model name
STRONG_MODEL="${MODEL_NAME}"
STRONG_LABEL=$(echo "$STRONG_MODEL" | tr '/' '_' | tr '-' '_')
WEAK_LABEL=$(echo "$WEAK_MODEL" | tr '/' '_' | tr '-' '_')

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     ABLATION STUDY 4: LLM Agnosticism / Model Swap Test        ║"
echo "║                                                                  ║"
echo "║  Strong Model : ${STRONG_MODEL}"
echo "║  Weak Model   : ${WEAK_MODEL}"
echo "║  Data File    : ${DATA_FILE}"
echo "║  Run Mode     : ${RUN_MODE}"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ===========================================================================
# Checkpoint helpers
# ===========================================================================
CKPT_FILE=""

mark_done() {
    local stage="$1"
    grep -q "^STAGE_${stage}=done" "$CKPT_FILE" 2>/dev/null || \
        echo "STAGE_${stage}=done" >> "$CKPT_FILE"
}

should_skip() {
    local stage="$1"
    grep -q "^STAGE_${stage}=done" "$CKPT_FILE" 2>/dev/null
}

output_exists() { [ -e "$1" ]; }

# ---------------------------------------------------------------------------
# Helper: Run Pipeline with a specific model
# ---------------------------------------------------------------------------
run_pipeline() {
    local SYSTEM="$1"               # "slayql" or "autolink"
    local MODEL_NAME_OVERRIDE="$2"  # Full model string
    local MODEL_LABEL="$3"          # Escaped string for dir name
    
    local LOG_DIR="ablation4_${SYSTEM}_${MODEL_LABEL}"
    local SCHEMA_DIR="${LOG_DIR}/final_schema_prompts"

    CKPT_FILE="${LOG_DIR}/.pipeline_ckpt"
    mkdir -p "$LOG_DIR"
    touch "$CKPT_FILE"

    echo ""
    echo "── ${SYSTEM^^} + ${MODEL_LABEL} ─────────────────────────────"
    echo "   Log: ${LOG_DIR}   Ckpt: ${CKPT_FILE}"

    export MODEL_NAME="$MODEL_NAME_OVERRIDE"

    if [ "$SYSTEM" = "slayql" ]; then
        # ── SlayQL pipeline ────────────────────────────────────────────────
        if should_skip 1; then
            echo "  [1] BM25 index          ✅ skip"
        else
            python build_value_indices.py --data_file "$DATA_FILE" 2>/dev/null || true
            mark_done 1
        fi

        if output_exists "${LOG_DIR}/initial_candidates.json"; then
            echo "  [2] Schema retrieval    ✅ skip"
            mark_done 2
        else
            python retrieve_topk_schema.py --log_path "$LOG_DIR" --top_n "$TOP_N" --data_file "$DATA_FILE"
            mark_done 2
        fi

        if output_exists "${LOG_DIR}/filled_pre_rule.json"; then
            echo "  [3] ID injection        ✅ skip"
            mark_done 3
        else
            python add_id.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
            mark_done 3
        fi

        ICOUNT=$(ls "${LOG_DIR}/schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$ICOUNT" -gt 0 ]; then
            echo "  [4] Initial prompts     ✅ skip"
            mark_done 4
        else
            python generate_schema.py --log_path "$LOG_DIR" --is_initial --data_file "$DATA_FILE"
            mark_done 4
        fi

        echo "  [5] Schema completion   ♻  resuming..."
        python complete_schema.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
        mark_done 5

        if output_exists "${LOG_DIR}/filled_schema.json"; then
            echo "  [6] Postprocess         ✅ skip"
            mark_done 6
        else
            python postprocess.py --log_path "$LOG_DIR"
            mark_done 6
        fi

        FCOUNT=$(ls "${LOG_DIR}/final_schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$FCOUNT" -gt 0 ]; then
            echo "  [7] Final prompts       ✅ skip"
            mark_done 7
        else
            python generate_schema.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
            mark_done 7
        fi

        if should_skip 8; then
            echo "  [8] SQL generation      ✅ skip"
        else
            python sql_generation.py --num_workers "$NUM_GEN_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$DATA_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 8
        fi

        if should_skip 9; then
            echo "  [9] SQL execution       ✅ skip"
        else
            python sql_execution.py --num_workers "$NUM_EXEC_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$DATA_FILE" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 9
        fi

        if should_skip 10; then
            echo "  [10] SQL revision       ✅ skip"
        else
            python sql_revise.py --num_workers "$NUM_REVISE_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$DATA_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 10
        fi

        if output_exists "${LOG_DIR}/sql_selection_v1/final" || output_exists "${LOG_DIR}/sql_selection/final"; then
            echo "  [11] SQL selection      ✅ skip"
            mark_done 11
        else
            python sql_selection.py --log_path "$LOG_DIR" --num_candidates "$NUM_CANDIDATES" \
                --workers "$NUM_SELECTION_WORKERS" --task "$TASK" --data_file "$DATA_FILE"
            mark_done 11
        fi
    else
        # ── AutoLink baseline pipeline ─────────────────────────────────────
        if output_exists "${LOG_DIR}/filled_pre_rule.json"; then
            echo "  [3] ID injection        ✅ skip"
            mark_done 3
        else
            python _baseline/add_id.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
            mark_done 3
        fi

        ICOUNT=$(ls "${LOG_DIR}/schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$ICOUNT" -gt 0 ]; then
            echo "  [4] Initial prompts     ✅ skip"
            mark_done 4
        else
            python _baseline/generate_schema.py --log_path "$LOG_DIR" --is_initial --data_file "$DATA_FILE"
            mark_done 4
        fi

        echo "  [5] Schema completion   ♻  resuming..."
        python _baseline/complete_schema.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
        mark_done 5

        if output_exists "${LOG_DIR}/filled_schema.json"; then
            echo "  [6] Postprocess         ✅ skip"
            mark_done 6
        else
            python postprocess.py --log_path "$LOG_DIR"
            mark_done 6
        fi

        FCOUNT=$(ls "${LOG_DIR}/final_schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$FCOUNT" -gt 0 ]; then
            echo "  [7] Final prompts       ✅ skip"
            mark_done 7
        else
            python _baseline/generate_schema.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
            mark_done 7
        fi

        if should_skip 8; then
            echo "  [8] SQL generation      ✅ skip"
        else
            python _baseline/sql_generation.py --num_workers "$NUM_GEN_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$DATA_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 8
        fi

        if should_skip 9; then
            echo "  [9] SQL execution       ✅ skip"
        else
            python sql_execution.py --num_workers "$NUM_EXEC_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$DATA_FILE" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 9
        fi

        if should_skip 10; then
            echo "  [10] SQL revision       ✅ skip"
        else
            python sql_revise.py --num_workers "$NUM_REVISE_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$DATA_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 10
        fi

        if output_exists "${LOG_DIR}/sql_selection_v1/final" || output_exists "${LOG_DIR}/sql_selection/final"; then
            echo "  [11] SQL selection      ✅ skip"
            mark_done 11
        else
            python sql_selection.py --log_path "$LOG_DIR" --num_candidates "$NUM_CANDIDATES" \
                --workers "$NUM_SELECTION_WORKERS" --task "$TASK" --data_file "$DATA_FILE"
            mark_done 11
        fi
    fi

    # ── Evaluate ──────────────────────────────────────────────────────────
    if output_exists "${LOG_DIR}/eval_result.txt"; then
        echo "  [12] Evaluate           ✅ skip (eval_result.txt exists)"
        mark_done 12
    else
        cd ../evaluation_suite
        if [ -d "../run/${LOG_DIR}/sql_selection_v1/final" ]; then
            RESULT_DIR="../run/${LOG_DIR}/sql_selection_v1/final"
        else
            RESULT_DIR="../run/${LOG_DIR}/sql_selection/final"
        fi
        
        if [ -d "$RESULT_DIR" ]; then
            python evaluate.py --mode exec_result --result_dir "$RESULT_DIR" \
                --gold_dir gold --data_file "../run/$DATA_FILE" \
                2>&1 | tee "../run/${LOG_DIR}/eval_result.txt"
        else
            python evaluate.py --mode sql --result_dir "../run/${LOG_DIR}/sql_gen/${TASK}_sql_0" \
                --data_file "../run/$DATA_FILE" \
                2>&1 | tee "../run/${LOG_DIR}/eval_result.txt"
        fi
        cd ../run

        python parse_tokens.py --log_path "$LOG_DIR" --data_file "$DATA_FILE" \
            2>&1 | tee -a "${LOG_DIR}/eval_result.txt"
        mark_done 12
    fi

    echo "model=${MODEL_NAME_OVERRIDE}" > "${LOG_DIR}/model_info.txt"
    echo "framework=${SYSTEM}" >> "${LOG_DIR}/model_info.txt"

    export MODEL_NAME="$STRONG_MODEL"

    DONE=$(grep -c "=done" "${LOG_DIR}/.pipeline_ckpt" 2>/dev/null || echo 0)
    echo "  ✅ ${SYSTEM^^} + ${MODEL_LABEL} complete (${DONE}/12 stages done)"
}

# ===========================================================================
# Run the 4-cell matrix
# ===========================================================================
if [[ "$RUN_MODE" == "all" || "$RUN_MODE" == "strong_only" ]]; then
    run_pipeline "slayql"   "$STRONG_MODEL" "$STRONG_LABEL"
    run_pipeline "autolink" "$STRONG_MODEL" "$STRONG_LABEL"
fi

if [[ "$RUN_MODE" == "all" || "$RUN_MODE" == "weak_only" ]]; then
    run_pipeline "slayql"   "$WEAK_MODEL" "$WEAK_LABEL"
    run_pipeline "autolink" "$WEAK_MODEL" "$WEAK_LABEL"
fi

# ===========================================================================
# Generate Ablation 4 Report
# ===========================================================================
echo ""
echo "=== Generating Ablation 4 Report ==="
python generate_ablation_report.py \
    --ablation_type model_agnostic \
    --data_file "$DATA_FILE" \
    --task "$TASK" \
    --strong_model "$STRONG_MODEL" \
    --weak_model "$WEAK_MODEL" \
    --variants \
        "SlayQL + ${STRONG_MODEL}:ablation4_slayql_${STRONG_LABEL}" \
        "AutoLink + ${STRONG_MODEL}:ablation4_autolink_${STRONG_LABEL}" \
        "SlayQL + ${WEAK_MODEL}:ablation4_slayql_${WEAK_LABEL}" \
        "AutoLink + ${WEAK_MODEL}:ablation4_autolink_${WEAK_LABEL}" \
    --output_path "ablation4_model_agnostic_report.md"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Ablation Study 4 Complete!                                      ║"
echo "║  Report: ablation4_model_agnostic_report.md                     ║"
echo "║  Re-run this script to resume safely if interrupted.             ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

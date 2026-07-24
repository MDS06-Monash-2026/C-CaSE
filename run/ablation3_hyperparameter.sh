#!/bin/bash
# =============================================================================
# ablation3_hyperparameter.sh — Hyperparameter Sensitivity Ablation
# =============================================================================
# AAAI Ablation Study 3: Proves SlayQL's hyperparameter choices are not
# "magic numbers" but rather well-calibrated sweet spots.
#
# ► RESUME-SAFE: Checkpoint files at <LOG_DIR>/.pipeline_ckpt track completed
#   stages for each hyperparameter configuration. Re-running the script
#   after an interruption skips all fully-completed stages automatically.
#
# Usage:
#   bash ablation3_hyperparameter.sh
#   bash ablation3_hyperparameter.sh --data_file subset_21_evaluation.json
#   bash ablation3_hyperparameter.sh --sweep itee   # only run θ sweep
#   bash ablation3_hyperparameter.sh --sweep rbp    # only run α sweep
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------
# Use a smaller subset by default for the hyperparameter sweep to reduce cost.
DATA_FILE="subset_diverse_20_evaluation.json"    # Subset of ~20-50 queries for speed
TOP_N=100
NUM_CANDIDATES=3          # Reduced candidates for speed
TASK="r1_lite"
NUM_GEN_WORKERS=16
NUM_EXEC_WORKERS=4
NUM_REVISE_WORKERS=4
NUM_SELECTION_WORKERS=16
SWEEP="both"              # "itee" | "rbp" | "both"

# θ sweep values (IT-EE entropy threshold)
ITEE_THRESHOLDS="0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9"

# α sweep values (RBP damping factor) — note: these are STATIC alpha overrides
RBP_ALPHAS="0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0"

while [[ $# -gt 0 ]]; do
    case $1 in
        --data_file) DATA_FILE="$2"; shift 2 ;;
        --top_n) TOP_N="$2"; shift 2 ;;
        --num_candidates) NUM_CANDIDATES="$2"; shift 2 ;;
        --task) TASK="$2"; shift 2 ;;
        --sweep) SWEEP="$2"; shift 2 ;;
        --itee_thresholds) ITEE_THRESHOLDS="$2"; shift 2 ;;
        --rbp_alphas) RBP_ALPHAS="$2"; shift 2 ;;
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

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║    ABLATION STUDY 3: Hyperparameter Sensitivity Analysis        ║"
echo "║    Data file : ${DATA_FILE}"
echo "║    Sweep     : ${SWEEP}"
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
# Helper: Run one sweep point (one hyperparameter value)
# ---------------------------------------------------------------------------
# Args:
#   $1 = SWEEP_TYPE      ("itee" | "rbp")
#   $2 = PARAM_VALUE     (e.g. "0.4" or "0.7")
#   $3 = EXTRA_RETRIEVE  (extra args for retrieve_topk_schema.py)
# ---------------------------------------------------------------------------
run_sweep_point() {
    local SWEEP_TYPE="$1"
    local PARAM_VALUE="$2"
    local EXTRA_RETRIEVE="$3"
    local PARAM_LABEL="${PARAM_VALUE//./_}"    # 0.4 → 0_4
    local LOG_DIR="ablation3_${SWEEP_TYPE}_${PARAM_LABEL}"
    local SCHEMA_DIR="${LOG_DIR}/final_schema_prompts"

    CKPT_FILE="${LOG_DIR}/.pipeline_ckpt"
    mkdir -p "$LOG_DIR"
    touch "$CKPT_FILE"

    echo ""
    echo "  ┌─ Sweep: ${SWEEP_TYPE} = ${PARAM_VALUE} ─────────────────────"
    echo "  │  Log dir : ${LOG_DIR}"
    echo "  └──────────────────────────────────────────────────────────────"

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
        python retrieve_topk_schema.py --log_path "$LOG_DIR" --top_n "$TOP_N" \
            --data_file "$DATA_FILE" $EXTRA_RETRIEVE
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

    echo "${SWEEP_TYPE}=${PARAM_VALUE}" >> "${LOG_DIR}/hyperparameter.txt"
    DONE=$(grep -c "=done" "${LOG_DIR}/.pipeline_ckpt" 2>/dev/null || echo 0)
    echo "  ✅ ${SWEEP_TYPE}=${PARAM_VALUE} complete (${DONE}/12 stages done)"
}

# ===========================================================================
# Sweep A: IT-EE Entropy Threshold (θ)
# ===========================================================================
if [[ "$SWEEP" == "itee" || "$SWEEP" == "both" ]]; then
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "  SWEEP A: IT-EE Entropy Threshold θ"
    echo "  Values: ${ITEE_THRESHOLDS}"
    echo "════════════════════════════════════════════════════════════════"

    ITEE_VARIANT_LIST=""
    for THETA in $ITEE_THRESHOLDS; do
        LABEL="${THETA//./_}"
        LOG="ablation3_itee_${LABEL}"

        run_sweep_point "itee" "$THETA" "--itee_threshold ${THETA}"

        if [ -z "$ITEE_VARIANT_LIST" ]; then
            ITEE_VARIANT_LIST="θ=${THETA}:${LOG}"
        else
            ITEE_VARIANT_LIST="${ITEE_VARIANT_LIST} θ=${THETA}:${LOG}"
        fi
    done

    python generate_ablation_report.py \
        --ablation_type hyperparameter_itee \
        --data_file "$DATA_FILE" \
        --task "$TASK" \
        --param_name "IT-EE Threshold (θ)" \
        --param_values $ITEE_THRESHOLDS \
        --chosen_value 0.4 \
        --variants $ITEE_VARIANT_LIST \
        --output_path "ablation3_itee_sensitivity.md"

    echo "✅ IT-EE Sweep report → ablation3_itee_sensitivity.md"
fi

# ===========================================================================
# Sweep B: RBP Damping Factor (α)
# ===========================================================================
if [[ "$SWEEP" == "rbp" || "$SWEEP" == "both" ]]; then
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "  SWEEP B: RBP Static Damping Factor α"
    echo "  Values: ${RBP_ALPHAS}"
    echo "════════════════════════════════════════════════════════════════"

    RBP_VARIANT_LIST=""
    for ALPHA in $RBP_ALPHAS; do
        LABEL="${ALPHA//./_}"
        LOG="ablation3_rbp_${LABEL}"

        run_sweep_point "rbp" "$ALPHA" "--rbp_alpha ${ALPHA}"

        if [ -z "$RBP_VARIANT_LIST" ]; then
            RBP_VARIANT_LIST="α=${ALPHA}:${LOG}"
        else
            RBP_VARIANT_LIST="${RBP_VARIANT_LIST} α=${ALPHA}:${LOG}"
        fi
    done

    python generate_ablation_report.py \
        --ablation_type hyperparameter_rbp \
        --data_file "$DATA_FILE" \
        --task "$TASK" \
        --param_name "RBP Damping Factor (α)" \
        --param_values $RBP_ALPHAS \
        --chosen_value 0.7 \
        --variants $RBP_VARIANT_LIST \
        --output_path "ablation3_rbp_sensitivity.md"

    echo "✅ RBP Alpha Sweep report → ablation3_rbp_sensitivity.md"
fi

# ===========================================================================
# Merge both sensitivity reports into one unified file
# ===========================================================================
if [[ "$SWEEP" == "both" ]]; then
    echo ""
    echo "=== Merging hyperparameter sensitivity reports ==="
    python generate_ablation_report.py \
        --ablation_type hyperparameter_combined \
        --data_file "$DATA_FILE" \
        --task "$TASK" \
        --itee_thresholds $ITEE_THRESHOLDS \
        --rbp_alphas $RBP_ALPHAS \
        --itee_chosen 0.4 \
        --rbp_chosen 0.7 \
        --output_path "ablation3_hyperparameter_report.md"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Ablation Study 3 Complete!                                      ║"
echo "║  Re-run this script to resume safely if interrupted.             ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

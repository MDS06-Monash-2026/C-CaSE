#!/bin/bash
# =============================================================================
# ablation1_component_dropout.sh — Leave-One-Out Component Ablation
# =============================================================================
# AAAI Ablation Study 1: Systematically removes each SlayQL innovation to prove
# the exact contribution of IT-EE, RBP, BM25 Value Grounding, and QOC.
#
# ► RESUME-SAFE: Each pipeline stage is guarded by a checkpoint file stored at
#   <LOG_DIR>/.pipeline_ckpt. If the script is interrupted and re-run, it skips
#   any stage already marked complete and picks up from where it left off.
#   Python stages that have their own per-instance caching (sql_generation,
#   sql_execution, sql_revise, complete_schema) automatically skip already-done
#   instances without needing a shell-level guard.
#
# Usage:
#   bash ablation1_component_dropout.sh
#   bash ablation1_component_dropout.sh --data_file subset_109_evaluation.json
#   bash ablation1_component_dropout.sh --force_stage 5  # re-run from stage 5
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------
DATA_FILE="subset_diverse_20_evaluation.json"
TOP_N=100
NUM_CANDIDATES=5
TASK="r1_lite"
NUM_GEN_WORKERS=32
NUM_EXEC_WORKERS=4
NUM_REVISE_WORKERS=8
NUM_SELECTION_WORKERS=32
FORCE_STAGE=0   # If > 0, re-run from this stage number for ALL variants

while [[ $# -gt 0 ]]; do
    case $1 in
        --data_file) DATA_FILE="$2"; shift 2 ;;
        --top_n) TOP_N="$2"; shift 2 ;;
        --num_candidates) NUM_CANDIDATES="$2"; shift 2 ;;
        --task) TASK="$2"; shift 2 ;;
        --force_stage) FORCE_STAGE="$2"; shift 2 ;;
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

# ===========================================================================
# Checkpoint helpers
# ===========================================================================
CKPT_FILE=""   # set per variant inside run_variant()

# Mark a stage as complete in the checkpoint file.
mark_done() {
    local stage="$1"
    echo "STAGE_${stage}=done" >> "$CKPT_FILE"
}

# Return 0 (true) if a stage should be SKIPPED (already done & not forced).
should_skip() {
    local stage="$1"
    if [ "$FORCE_STAGE" -gt 0 ] && [ "$stage" -ge "$FORCE_STAGE" ]; then
        return 1   # not skipping — force re-run from this stage
    fi
    grep -q "^STAGE_${stage}=done" "$CKPT_FILE" 2>/dev/null
}

# Check if a file or directory exists; helper for sentinel-based guards.
output_exists() {
    local path="$1"
    [ -e "$path" ]
}

# ===========================================================================
# Core helper: run one full pipeline variant with checkpoint resume
# ===========================================================================
run_variant() {
    local VARIANT_NAME="$1"
    local LOG_DIR="$2"
    local EXTRA_RETRIEVE_ARGS="$3"
    local EXTRA_COMPLETE_ARGS="$4"
    local EXTRA_SQLGEN_ARGS="$5"
    local SCHEMA_DIR="${LOG_DIR}/final_schema_prompts"

    # Checkpoint file lives inside the log dir so it survives re-runs
    CKPT_FILE="${LOG_DIR}/.pipeline_ckpt"
    mkdir -p "$LOG_DIR"
    touch "$CKPT_FILE"

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ABLATION 1 — Variant : ${VARIANT_NAME}"
    echo "║  Log dir              : ${LOG_DIR}"
    echo "║  Checkpoint file      : ${CKPT_FILE}"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # ── Stage 1: BM25 Index ────────────────────────────────────────────────
    if should_skip 1; then
        echo "=== [1/12] BM25 index — ✅ SKIPPED (checkpoint)"
    else
        echo "=== [1/12] Building BM25 Value Indices ==="
        python build_value_indices.py --data_file "$DATA_FILE"
        mark_done 1
    fi

    # ── Stage 2: Schema Retrieval ──────────────────────────────────────────
    # Sentinel file ONLY — a stale checkpoint must NOT skip if file is missing.
    if output_exists "${LOG_DIR}/initial_candidates.json"; then
        echo "=== [2/12] Schema Retrieval — ✅ SKIPPED (initial_candidates.json exists)"
        mark_done 2
    else
        echo "=== [2/12] Dense Retrieval + RBP + IT-EE (variant: ${VARIANT_NAME}) ==="
        python retrieve_topk_schema.py \
            --log_path "$LOG_DIR" \
            --top_n "$TOP_N" \
            --data_file "$DATA_FILE" \
            $EXTRA_RETRIEVE_ARGS
        mark_done 2
    fi

    # ── Stage 3: Inject IDs ────────────────────────────────────────────────
    # Sentinel: filled_pre_rule.json (output of add_id.py)
    if output_exists "${LOG_DIR}/filled_pre_rule.json"; then
        echo "=== [3/12] ID Injection — ✅ SKIPPED (filled_pre_rule.json exists)"
        mark_done 3
    else
        echo "=== [3/12] Injecting instance IDs ==="
        python add_id.py --log_path "$LOG_DIR" --data_file "$DATA_FILE"
        mark_done 3
    fi

    # ── Stage 4: Initial Schema Prompts ───────────────────────────────────
    # Sentinel dir ONLY.
    INIT_SCHEMA_COUNT=$(ls "${LOG_DIR}/schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$INIT_SCHEMA_COUNT" -gt 0 ]; then
        echo "=== [4/12] Initial schema prompts — ✅ SKIPPED (${INIT_SCHEMA_COUNT} prompts exist)"
        mark_done 4
    else
        echo "=== [4/12] Generating initial schema prompts ==="
        python generate_schema.py \
            --log_path "$LOG_DIR" \
            --is_initial \
            --data_file "$DATA_FILE"
        mark_done 4
    fi

    # ── Stage 5: Agentic Schema Completion ────────────────────────────────
    # Always call — complete_schema.py is internally resume-safe per-instance.
    CANDIDATES_COUNT=$(ls "${LOG_DIR}/candidates/" 2>/dev/null | wc -l | tr -d ' ')
    echo "=== [5/12] Schema completion — ♻️  RESUMING (${CANDIDATES_COUNT} instances already cached) ==="
    python complete_schema.py \
        --log_path "$LOG_DIR" \
        --data_file "$DATA_FILE" \
        $EXTRA_COMPLETE_ARGS
    mark_done 5

    # ── Stage 6: Postprocess ──────────────────────────────────────────────
    # Sentinel file ONLY.
    if output_exists "${LOG_DIR}/filled_schema.json"; then
        echo "=== [6/12] Postprocess — ✅ SKIPPED (filled_schema.json exists)"
        mark_done 6
    else
        echo "=== [6/12] Postprocessing schema candidates ==="
        python postprocess.py --log_path "$LOG_DIR"
        mark_done 6
    fi

    # ── Stage 7: Final Schema Prompts ─────────────────────────────────────
    # Sentinel dir ONLY.
    FINAL_SCHEMA_COUNT=$(ls "${LOG_DIR}/final_schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$FINAL_SCHEMA_COUNT" -gt 0 ]; then
        echo "=== [7/12] Final schema prompts — ✅ SKIPPED (${FINAL_SCHEMA_COUNT} prompts exist)"
        mark_done 7
    else
        echo "=== [7/12] Generating final schema prompts ==="
        python generate_schema.py \
            --log_path "$LOG_DIR" \
            --data_file "$DATA_FILE"
        mark_done 7
    fi

    # ── Stage 8: SQL Generation ───────────────────────────────────────────
    # sql_generation.py is internally resume-safe (skips existing .txt files).
    if should_skip 8; then
        echo "=== [8/12] SQL Generation — ✅ SKIPPED (checkpoint)"
    else
        echo "=== [8/12] Generating SQL candidates (resume-safe) ==="
        python sql_generation.py \
            --num_workers "$NUM_GEN_WORKERS" \
            --num_candidates "$NUM_CANDIDATES" \
            --data_file "$DATA_FILE" \
            --schema_dir "$SCHEMA_DIR" \
            --log_path "$LOG_DIR" \
            --task "$TASK" \
            $EXTRA_SQLGEN_ARGS
        mark_done 8
    fi

    # ── Stage 9: SQL Execution ────────────────────────────────────────────
    # sql_execution.py is internally resume-safe (skips existing .csv/.txt).
    if should_skip 9; then
        echo "=== [9/12] SQL Execution — ✅ SKIPPED (checkpoint)"
    else
        echo "=== [9/12] Executing SQL candidates (resume-safe) ==="
        python sql_execution.py \
            --num_workers "$NUM_EXEC_WORKERS" \
            --num_candidates "$NUM_CANDIDATES" \
            --data_file "$DATA_FILE" \
            --log_path "$LOG_DIR" \
            --task "$TASK"
        mark_done 9
    fi

    # ── Stage 10: SQL Revision ────────────────────────────────────────────
    # sql_revise.py is internally resume-safe (skips already-revised instances).
    if should_skip 10; then
        echo "=== [10/12] SQL Revision — ✅ SKIPPED (checkpoint)"
    else
        echo "=== [10/12] Revising failed SQL candidates (resume-safe) ==="
        python sql_revise.py \
            --num_workers "$NUM_REVISE_WORKERS" \
            --num_candidates "$NUM_CANDIDATES" \
            --data_file "$DATA_FILE" \
            --schema_dir "$SCHEMA_DIR" \
            --log_path "$LOG_DIR" \
            --task "$TASK"
        mark_done 10
    fi

    # ── Stage 11: SQL Selection ───────────────────────────────────────────
    # Sentinel dir ONLY — check both sql_selection_v1/final and sql_selection/final.
    if output_exists "${LOG_DIR}/sql_selection_v1/final" || output_exists "${LOG_DIR}/sql_selection/final"; then
        echo "=== [11/12] SQL Selection — ✅ SKIPPED (selection/final exists)"
        mark_done 11
    else
        echo "=== [11/12] Selecting final SQL via self-consistency ==="
        python sql_selection.py \
            --log_path "$LOG_DIR" \
            --num_candidates "$NUM_CANDIDATES" \
            --workers "$NUM_SELECTION_WORKERS" \
            --task "$TASK" \
            --data_file "$DATA_FILE"
        mark_done 11
    fi

    # ── Stage 12: Evaluate ────────────────────────────────────────────────
    # Sentinel file ONLY.
    if output_exists "${LOG_DIR}/eval_result.txt"; then
        echo "=== [12/12] Evaluation — ✅ SKIPPED (eval_result.txt exists)"
        mark_done 12
    else
        echo "=== [12/12] Evaluating variant: ${VARIANT_NAME} ==="
        cd ../evaluation_suite
        if [ -d "../run/${LOG_DIR}/sql_selection_v1/final" ]; then
            RESULT_DIR="../run/${LOG_DIR}/sql_selection_v1/final"
        else
            RESULT_DIR="../run/${LOG_DIR}/sql_selection/final"
        fi
        
        if [ -d "$RESULT_DIR" ]; then
            python evaluate.py \
                --mode exec_result \
                --result_dir "$RESULT_DIR" \
                --gold_dir gold \
                --data_file "../run/$DATA_FILE" \
                2>&1 | tee "../run/${LOG_DIR}/eval_result.txt"
        else
            python evaluate.py \
                --mode sql \
                --result_dir "../run/${LOG_DIR}/sql_gen/${TASK}_sql_0" \
                --data_file "../run/$DATA_FILE" \
                2>&1 | tee "../run/${LOG_DIR}/eval_result.txt"
        fi
        cd ../run

        python parse_tokens.py --log_path "$LOG_DIR" --data_file "$DATA_FILE" \
            2>&1 | tee -a "${LOG_DIR}/eval_result.txt"
        mark_done 12
    fi

    echo ""
    echo "✅ Variant '${VARIANT_NAME}' complete."
    echo "   Checkpoint : ${CKPT_FILE}"
    echo "   Results    : ${LOG_DIR}/eval_result.txt"
    echo ""
}

# ===========================================================================
# Define the 5 ablation configurations
# ===========================================================================
# Optimization: If using the default diverse subset, we already ran the 
# full pipeline via compare_models.sh, so we can just point to it.
if [[ "$DATA_FILE" == "subset_diverse_20_evaluation.json" ]]; then
    FULL_LOG="log_subset_diverse_20_evaluation_slayql_ccase"
else
    FULL_LOG="ablation1_full_slayql"
fi

NO_ITEE_LOG="ablation1_no_itee"
NO_RBP_LOG="ablation1_no_rbp"
NO_BM25_LOG="ablation1_no_bm25"
NO_QOC_LOG="ablation1_no_qoc"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║   ABLATION STUDY 1: Leave-One-Out Component Dropout             ║"
echo "║   5 variants × full pipeline — checkpoint-resume enabled        ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Full SlayQL (all components enabled — reference)
if [ -f "${FULL_LOG}/eval_result.txt" ]; then
    echo "✅ Full SlayQL already complete at: ${FULL_LOG}"
else
    run_variant "full_slayql"  "$FULL_LOG"    ""          ""          ""
fi

# ===========================================================================
# Optimization: Reuse stages from FULL_LOG for variants that only change later stages
# ===========================================================================
if [ -d "$FULL_LOG" ]; then
    # NO_BM25 disables BM25 in complete_schema (stage 5). Reuse stages 2, 3, 4.
    if [ ! -f "$NO_BM25_LOG/.pipeline_ckpt" ] && [ -f "${FULL_LOG}/filled_pre_rule.json" ]; then
        echo "♻️  Copying Stages 2-4 from ${FULL_LOG} for w/o BM25 to save time..."
        mkdir -p "$NO_BM25_LOG"
        cp -rn "${FULL_LOG}/initial_candidates.json" "$NO_BM25_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/cache"                   "$NO_BM25_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/status"                  "$NO_BM25_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/unfilled_pre_rule.json"  "$NO_BM25_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/filled_pre_rule.json"    "$NO_BM25_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/schema_prompts"          "$NO_BM25_LOG/" 2>/dev/null || true
        echo "STAGE_2=done" >> "$NO_BM25_LOG/.pipeline_ckpt"
        echo "STAGE_3=done" >> "$NO_BM25_LOG/.pipeline_ckpt"
        echo "STAGE_4=done" >> "$NO_BM25_LOG/.pipeline_ckpt"
    fi

    # NO_QOC disables strict outputs in sql_generation (stage 8). Reuse stages 2-7.
    if [ ! -f "$NO_QOC_LOG/.pipeline_ckpt" ] && [ -d "${FULL_LOG}/final_schema_prompts" ]; then
        echo "♻️  Copying Stages 2-7 from ${FULL_LOG} for w/o QOC to save time..."
        mkdir -p "$NO_QOC_LOG"
        cp -rn "${FULL_LOG}/initial_candidates.json" "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/cache"                   "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/status"                  "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/unfilled_pre_rule.json"  "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/filled_pre_rule.json"    "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/schema_prompts"          "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/candidates"              "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/unfilled_schema.json"    "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/filled_schema.json"      "$NO_QOC_LOG/" 2>/dev/null || true
        cp -rn "${FULL_LOG}/final_schema_prompts"    "$NO_QOC_LOG/" 2>/dev/null || true
        for stage in {2..7}; do
            echo "STAGE_${stage}=done" >> "$NO_QOC_LOG/.pipeline_ckpt"
        done
    fi
fi

# 2. w/o IT-EE (forces full 10-turn budget every query)
run_variant "no_itee"      "$NO_ITEE_LOG" "--no_itee" ""          ""

# 3. w/o RBP (pure dense retrieval, no graph propagation)
run_variant "no_rbp"       "$NO_RBP_LOG"  "--no_rbp"  ""          ""

# 4. w/o BM25 (no value hint injection in schema completion or SQL generation)
run_variant "no_bm25"      "$NO_BM25_LOG" ""          "--no_bm25" "--no_bm25"

# 5. w/o QOC (relaxed output format, no strict \`\`\`sql\`\`\` contract)
run_variant "no_qoc"       "$NO_QOC_LOG"  ""          ""          "--no_qoc"

# ===========================================================================
# Generate Unified Ablation 1 Report
# ===========================================================================
echo ""
echo "=== Generating Ablation 1 Report ==="
python generate_ablation_report.py \
    --ablation_type component_dropout \
    --data_file "$DATA_FILE" \
    --task "$TASK" \
    --variants \
        "Full SlayQL:${FULL_LOG}" \
        "w/o IT-EE (Always loops):${NO_ITEE_LOG}" \
        "w/o RBP (No graph joins):${NO_RBP_LOG}" \
        "w/o BM25 Grounding:${NO_BM25_LOG}" \
        "w/o QOC (Strict Outputs):${NO_QOC_LOG}" \
    --output_path "ablation1_component_dropout_report.md"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Ablation Study 1 Complete!                                      ║"
echo "║                                                                  ║"
echo "║  Variant checkpoints (resume by re-running this script):        ║"
for LOG in "$FULL_LOG" "$NO_ITEE_LOG" "$NO_RBP_LOG" "$NO_BM25_LOG" "$NO_QOC_LOG"; do
    DONE=$(grep -c "=done" "${LOG}/.pipeline_ckpt" 2>/dev/null || echo 0)
    printf "║    %-48s %2s/12 ║\n" "$LOG" "$DONE"
done
echo "║                                                                  ║"
echo "║  Unified Report: ablation1_component_dropout_report.md          ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

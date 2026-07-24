#!/bin/bash
# =============================================================================
# run_autolink_baseline.sh - AutoLink Baseline Re-run (Original Code, Current Model)
# =============================================================================
# Runs the original AutoLink baseline pipeline (git commit af6bad0) with the
# current model from .env for a fair apples-to-apples comparison vs SlayQL.
#
# Key differences from SlayQL:
#   - retrieve_topk_schema: dense retrieval ONLY (no RBP graph, no IT-EE entropy)
#   - complete_schema: fixed 10-turn loop (no dynamic_t_max, no BM25 value hints)
#   - sql_generation: no BM25 value hints appended to schema
# =============================================================================

set -e

# Add the current directory to PYTHONPATH so _baseline scripts can import utils, config, etc.
export PYTHONPATH="."

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_FILE="subset_diverse_20_evaluation.json"
BASELINE_LOG="log_subset_diverse_20_evaluation_autolink_baseline_v2"
ENHANCED_LOG="log_subset_diverse_20_evaluation_slayql_ccase"
TOP_N=100
NUM_CANDIDATES=5
TASK="r1_lite"
SCHEMA_DIR="${BASELINE_LOG}/final_schema_prompts"
BASELINE_DIR="_baseline"

echo ""
echo "============================================================"
echo "  AutoLink Baseline Re-run (Original Code, Current Model)"
echo "  Data file  : $DATA_FILE"
echo "  Output dir : $BASELINE_LOG"
echo "  Candidates : $NUM_CANDIDATES"
echo "  Task       : $TASK"
echo "  Model      : $MODEL_NAME"
echo "============================================================"
echo ""

mkdir -p "$BASELINE_LOG"

# ---------------------------------------------------------------------------
# Stage 1: Dense Schema Retrieval (NO RBP, NO IT-EE)
# ---------------------------------------------------------------------------
echo "=== [1/12] Skipped Dense Retrieval (using cached log_v3_topn100) ==="
# python "$BASELINE_DIR/retrieve_topk_schema.py" \
#     --log_path "$BASELINE_LOG" \
#     --top_n $TOP_N \
#     --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 2: Inject instance IDs
# ---------------------------------------------------------------------------
echo "=== [2/12] Injecting instance IDs ==="
python "$BASELINE_DIR/add_id.py" \
    --log_path "$BASELINE_LOG" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 3: Generate initial schema prompts
# ---------------------------------------------------------------------------
echo "=== [3/12] Generating initial schema prompts ==="
python "$BASELINE_DIR/generate_schema.py" \
    --log_path "$BASELINE_LOG" \
    --is_initial \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 4: Agentic schema completion (NO BM25, fixed 10-turn loop)
# ---------------------------------------------------------------------------
echo "=== [4/12] Running agentic schema completion (AutoLink 10-turn, no BM25) ==="
python "$BASELINE_DIR/complete_schema.py" \
    --log_path "$BASELINE_LOG" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 5: Postprocess
# ---------------------------------------------------------------------------
echo "=== [5/12] Postprocessing schema candidates ==="
python postprocess.py --log_path "$BASELINE_LOG"

# ---------------------------------------------------------------------------
# Stage 6: Generate final schema prompts
# ---------------------------------------------------------------------------
echo "=== [6/12] Generating final schema prompts ==="
python "$BASELINE_DIR/generate_schema.py" \
    --log_path "$BASELINE_LOG" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 7: SQL Generation (NO BM25 value hints)
# ---------------------------------------------------------------------------
echo "=== [7/12] Generating SQL candidates (AutoLink - no BM25) ==="
python "$BASELINE_DIR/sql_generation.py" \
    --num_workers 32 \
    --num_candidates $NUM_CANDIDATES \
    --data_file "$DATA_FILE" \
    --schema_dir "$SCHEMA_DIR" \
    --log_path "$BASELINE_LOG" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 8: SQL Execution (uses current sql_execution.py - same for both)
# ---------------------------------------------------------------------------
echo "=== [8/12] Executing SQL candidates ==="
python sql_execution.py \
    --num_workers 4 \
    --num_candidates $NUM_CANDIDATES \
    --data_file "$DATA_FILE" \
    --log_path "$BASELINE_LOG" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 9: SQL Revision (uses current sql_revise.py)
# ---------------------------------------------------------------------------
echo "=== [9/12] Revising failed SQL candidates ==="
python sql_revise.py \
    --num_workers 8 \
    --num_candidates $NUM_CANDIDATES \
    --data_file "$DATA_FILE" \
    --schema_dir "$SCHEMA_DIR" \
    --log_path "$BASELINE_LOG" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 10: SQL Selection (uses current sql_selection.py)
# ---------------------------------------------------------------------------
echo "=== [10/12] Selecting final SQL via self-consistency ==="
python sql_selection.py \
    --log_path "$BASELINE_LOG" \
    --num_candidates $NUM_CANDIDATES \
    --workers 32 \
    --task "$TASK" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 11: Evaluate both models
# ---------------------------------------------------------------------------
echo ""
echo "=== [11/12] Evaluating AutoLink Baseline v2 ==="
cd ../evaluation_suite

BASELINE_RESULT_DIR="../run/$BASELINE_LOG/sql_selection/final"
if [ -d "$BASELINE_RESULT_DIR" ]; then
    python evaluate.py \
        --mode exec_result \
        --result_dir "$BASELINE_RESULT_DIR" \
        --gold_dir gold \
        --data_file "../run/$DATA_FILE"
else
    echo "[WARN] sql_selection/final not found - trying sql_gen fallback"
    python evaluate.py \
        --mode sql \
        --result_dir "../run/$BASELINE_LOG/sql_gen/${TASK}_sql_0" \
        --data_file "../run/$DATA_FILE"
fi

echo "--- SlayQL (sql_selection_v1) reference evaluation ---"
SLAYQL_RESULT_DIR="../run/$ENHANCED_LOG/sql_selection_v1/final"
if [ -d "$SLAYQL_RESULT_DIR" ]; then
    python evaluate.py \
        --mode exec_result \
        --result_dir "$SLAYQL_RESULT_DIR" \
        --gold_dir gold \
        --data_file "../run/$DATA_FILE"
fi
cd ../run

# ---------------------------------------------------------------------------
# Stage 12: Generate Comparison Report
# ---------------------------------------------------------------------------
echo ""
echo "=== [12/12] Generating Side-by-Side Comparison Report ==="

if [ -d "$BASELINE_LOG/sql_selection/final" ]; then
    BASELINE_COMPARE_DIR="$BASELINE_LOG/sql_selection/final"
else
    BASELINE_COMPARE_DIR="$BASELINE_LOG/sql_gen/${TASK}_sql_0"
fi

SLAYQL_COMPARE_DIR="$ENHANCED_LOG/sql_selection_v1/final"

python generate_comparison.py \
    --data_file "$DATA_FILE" \
    --slayql_dir "$SLAYQL_COMPARE_DIR" \
    --baseline_dir "$BASELINE_COMPARE_DIR" \
    --output_path "comparison_report.md"

if [ -f "comparison_report.md" ]; then
    echo "Comparison report saved to: comparison_report.md"
fi

echo ""
echo "============================================================"
echo "  AutoLink Baseline Re-run Complete!"
echo "  Check terminal output above for accuracy scores."
echo "  comparison_report.md has the full side-by-side analysis."
echo "============================================================"

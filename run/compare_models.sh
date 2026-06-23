#!/bin/bash
# =============================================================================
# compare_models.sh — SlayQL (C-CaSE) vs AutoLink Baseline Full Pipeline
# =============================================================================
# This script runs the complete end-to-end pipeline for the SlayQL enhanced
# system and then generates a side-by-side comparison against the AutoLink
# baseline (assumed already evaluated in BASELINE_LOG).
#
# Pipeline stages:
#   1.  Offline BM25 Value Index Building
#   2.  Schema Retrieval + IT-EE + RBP  (retrieve_topk_schema.py)
#   3.  ID Injection                    (add_id.py)
#   4.  Initial Schema Prompt Gen       (generate_schema.py --is_initial)
#   5.  Agentic Schema Completion       (complete_schema.py)
#   6.  Schema Postprocessing           (postprocess.py)
#   7.  Final Schema Prompt Gen         (generate_schema.py)
#   8.  SQL Generation (candidates)     (sql_generation.py)
#   9.  SQL Execution (candidate eval)  (sql_execution.py)
#  10.  SQL Revision (error correction) (sql_revise.py)
#  11.  SQL Selection (consistency)     (sql_selection.py)
#  12.  Evaluation — SlayQL             (evaluate.py)
#  13.  Evaluation — Baseline           (evaluate.py, if available)
#  14.  Token Metrics                   (parse_tokens.py)
#  15.  Side-by-Side SQL Comparison     (generate_comparison.py)
#  16.  CSV-only Comparison             (generate_csv_comparison.py)
#  17.  SGSA-Enhanced SQL Comparison    (generate_comparison.py → v2)
#  18.  SGSA-Enhanced CSV Comparison    (generate_csv_comparison.py → v2)
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# 0.  Load environment variables (API keys, model names, etc.)
# ---------------------------------------------------------------------------
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_FILE="subset_diverse_20_evaluation.json"
BASELINE_LOG="log_subset_diverse_20_evaluation_autolink_baseline"
ENHANCED_LOG="log_subset_diverse_20_evaluation_slayql_ccase"
ENHANCED_LOG_V2="log_subset_diverse_20_evaluation_slayql_ccase_v2"
TOP_N=100
NUM_CANDIDATES=5
TASK="r1_lite"
SCHEMA_DIR="$ENHANCED_LOG/final_schema_prompts"
NUM_GEN_WORKERS=32
NUM_EXEC_WORKERS=4
NUM_REVISE_WORKERS=8
NUM_SELECTION_WORKERS=32

echo ""
echo "============================================================"
echo "  SlayQL (C-CaSE) Full Pipeline"
echo "  Data file  : $DATA_FILE"
echo "  Output dir : $ENHANCED_LOG"
echo "  Candidates : $NUM_CANDIDATES"
echo "  Task       : $TASK"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# Stage 1: Offline BM25 Value Index Building
#   Builds per-database BM25 indices of cell values for the ValueGrounder.
#   Skips DBs that have already been indexed (idempotent).
# ---------------------------------------------------------------------------
echo "=== [1/16] Building BM25 Value Indices (Offline Phase) ==="
python build_value_indices.py --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 2: Schema Retrieval (Dense + RBP + IT-EE)
# ---------------------------------------------------------------------------
echo "=== [2/16] Running Dense Retrieval + RBP + IT-EE ==="
python retrieve_topk_schema.py \
    --log_path "$ENHANCED_LOG" \
    --top_n "$TOP_N" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 3: Inject instance IDs into schema candidates
# ---------------------------------------------------------------------------
echo "=== [3/16] Injecting instance IDs ==="
python add_id.py --log_path "$ENHANCED_LOG" --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 4: Generate initial schema prompts (before agentic expansion)
# ---------------------------------------------------------------------------
echo "=== [4/16] Generating initial schema prompts ==="
python generate_schema.py \
    --log_path "$ENHANCED_LOG" \
    --is_initial \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 5: Agentic schema completion (IT-EE safe-exit + value hints)
# ---------------------------------------------------------------------------
echo "=== [5/16] Running agentic schema completion ==="
python complete_schema.py \
    --log_path "$ENHANCED_LOG" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 6: Postprocess schema candidates (dedup, format)
# ---------------------------------------------------------------------------
echo "=== [6/16] Postprocessing schema candidates ==="
python postprocess.py --log_path "$ENHANCED_LOG"

# ---------------------------------------------------------------------------
# Stage 7: Generate final schema prompts (used for SQL generation)
# ---------------------------------------------------------------------------
echo "=== [7/16] Generating final schema prompts ==="
python generate_schema.py \
    --log_path "$ENHANCED_LOG" \
    --data_file "$DATA_FILE"

# ---------------------------------------------------------------------------
# Stage 8: SQL Generation (multi-candidate)
# ---------------------------------------------------------------------------
echo "=== [8/16] Generating SQL candidates ==="
python sql_generation.py \
    --num_workers "$NUM_GEN_WORKERS" \
    --num_candidates "$NUM_CANDIDATES" \
    --data_file "$DATA_FILE" \
    --schema_dir "$SCHEMA_DIR" \
    --log_path "$ENHANCED_LOG" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 9: SQL Execution (execute each candidate to obtain results / errors)
# ---------------------------------------------------------------------------
echo "=== [9/16] Executing SQL candidates ==="
python sql_execution.py \
    --num_workers "$NUM_EXEC_WORKERS" \
    --num_candidates "$NUM_CANDIDATES" \
    --data_file "$DATA_FILE" \
    --log_path "$ENHANCED_LOG" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 10: SQL Revision (self-correction on failed executions)
# ---------------------------------------------------------------------------
echo "=== [10/16] Revising failed SQL candidates ==="
python sql_revise.py \
    --num_workers "$NUM_REVISE_WORKERS" \
    --num_candidates "$NUM_CANDIDATES" \
    --data_file "$DATA_FILE" \
    --schema_dir "$SCHEMA_DIR" \
    --log_path "$ENHANCED_LOG" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 11: SQL Selection (self-consistency voting)
# ---------------------------------------------------------------------------
echo "=== [11/16] Selecting final SQL via self-consistency ==="
python sql_selection.py \
    --log_path "$ENHANCED_LOG" \
    --num_candidates "$NUM_CANDIDATES" \
    --workers "$NUM_SELECTION_WORKERS" \
    --task "$TASK"

# ---------------------------------------------------------------------------
# Stage 12: Evaluate SlayQL (Enhanced Pipeline)
# ---------------------------------------------------------------------------
echo ""
echo "=== [12/16] Evaluating SlayQL Pipeline ==="
cd ../evaluation_suite

SLAYQL_RESULT_DIR="../run/$ENHANCED_LOG/sql_selection/final"
if [ -d "$SLAYQL_RESULT_DIR" ]; then
    python evaluate.py \
        --mode exec_result \
        --result_dir "$SLAYQL_RESULT_DIR" \
        --gold_dir gold \
        --data_file "../run/$DATA_FILE"
else
    echo "[WARN] SlayQL sql_selection/final not found — trying sql_gen fallback."
    python evaluate.py \
        --mode sql \
        --result_dir "../run/$ENHANCED_LOG/sql_gen/${TASK}_sql_0" \
        --data_file "../run/$DATA_FILE"
fi

# ---------------------------------------------------------------------------
# Stage 13: Evaluate Baseline (AutoLink)
# ---------------------------------------------------------------------------
echo ""
echo "=== [13/16] Evaluating Baseline (AutoLink) ==="
BASELINE_RESULT_DIR="../run/$BASELINE_LOG/sql_selection/final"
if [ -d "$BASELINE_RESULT_DIR" ]; then
    python evaluate.py \
        --mode exec_result \
        --result_dir "$BASELINE_RESULT_DIR" \
        --gold_dir gold \
        --data_file "../run/$DATA_FILE"
else
    echo "[WARN] Baseline sql_selection/final not found — trying sql_gen fallback."
    if [ -d "../run/$BASELINE_LOG/sql_gen/${TASK}_sql_0" ]; then
        python evaluate.py \
            --mode sql \
            --result_dir "../run/$BASELINE_LOG/sql_gen/${TASK}_sql_0" \
            --data_file "../run/$DATA_FILE"
    else
        echo "[SKIP] Baseline results not found in $BASELINE_LOG. Skipping baseline evaluation."
    fi
fi

cd ../run

# ---------------------------------------------------------------------------
# Stage 14: Token Metrics
# ---------------------------------------------------------------------------
echo ""
echo "=== [14/16] Extracting Token Metrics ==="
python parse_tokens.py --log_path "$ENHANCED_LOG" --data_file "$DATA_FILE"
if [ -d "$BASELINE_LOG/input" ] || [ -d "$BASELINE_LOG/inputs" ]; then
    echo "--- Baseline Token Metrics ---"
    python parse_tokens.py --log_path "$BASELINE_LOG" --data_file "$DATA_FILE"
fi

# ---------------------------------------------------------------------------
# Stage 15: Side-by-side SQL + result comparison report
# ---------------------------------------------------------------------------
echo ""
echo "=== [15/16] Generating Side-by-Side SQL Comparison Report ==="

# Determine best available SlayQL result directory for comparison.
if [ -d "$ENHANCED_LOG/sql_selection/final" ]; then
    SLAYQL_COMPARE_DIR="$ENHANCED_LOG/sql_selection/final"
else
    SLAYQL_COMPARE_DIR="$ENHANCED_LOG/sql_gen/${TASK}_sql_0"
fi

if [ -d "$BASELINE_LOG/sql_selection/final" ]; then
    BASELINE_COMPARE_DIR="$BASELINE_LOG/sql_selection/final"
else
    BASELINE_COMPARE_DIR="$BASELINE_LOG/sql_gen/${TASK}_sql_0"
fi

python generate_comparison.py \
    --data_file "$DATA_FILE" \
    --slayql_dir "$SLAYQL_COMPARE_DIR" \
    --baseline_dir "$BASELINE_COMPARE_DIR" \
    --output_path "comparison_report.md"

if [ -f "comparison_report.md" ]; then
    echo "Side-by-side comparison report saved to: comparison_report.md"
fi

# ---------------------------------------------------------------------------
# Stage 16: CSV-only offline comparison (no live execution needed)
# ---------------------------------------------------------------------------
echo ""
echo "=== [16/16] Generating CSV-Only Offline Comparison Report ==="
python generate_csv_comparison.py \
    --data_file "$DATA_FILE" \
    --slayql_dir "$SLAYQL_COMPARE_DIR" \
    --baseline_dir "$BASELINE_COMPARE_DIR" \
    --output_path "csv_only_comparison_report.md"

if [ -f "csv_only_comparison_report.md" ]; then
    echo "CSV comparison report saved to: csv_only_comparison_report.md"
fi

# ---------------------------------------------------------------------------
# Stage 17: SGSA-Enhanced Side-by-Side SQL Comparison (v2 Report)
#   Uses the SGSA-enhanced log directory to generate a separate comparison
#   report reflecting the semantic validation improvement.
# ---------------------------------------------------------------------------
echo ""
echo "=== [17/18] Generating SGSA-Enhanced Comparison Report (v2) ==="

if [ -d "$ENHANCED_LOG_V2/sql_selection/final" ]; then
    SLAYQL_V2_DIR="$ENHANCED_LOG_V2/sql_selection/final"
elif [ -d "$ENHANCED_LOG_V2/sql_gen/${TASK}_sql_0" ]; then
    SLAYQL_V2_DIR="$ENHANCED_LOG_V2/sql_gen/${TASK}_sql_0"
else
    # Fall back to the standard enhanced log if v2 hasn't been populated
    SLAYQL_V2_DIR="$SLAYQL_COMPARE_DIR"
fi

python generate_comparison.py \
    --data_file "$DATA_FILE" \
    --slayql_dir "$SLAYQL_V2_DIR" \
    --baseline_dir "$BASELINE_COMPARE_DIR" \
    --output_path "comparison_report_v2.md"

if [ -f "comparison_report_v2.md" ]; then
    echo "SGSA comparison report saved to: comparison_report_v2.md"
fi

# ---------------------------------------------------------------------------
# Stage 18: SGSA-Enhanced CSV-Only Comparison (v2 Report)
# ---------------------------------------------------------------------------
echo ""
echo "=== [18/18] Generating SGSA CSV-Only Comparison Report (v2) ==="
python generate_csv_comparison.py \
    --data_file "$DATA_FILE" \
    --slayql_dir "$SLAYQL_V2_DIR" \
    --baseline_dir "$BASELINE_COMPARE_DIR" \
    --output_path "csv_only_comparison_report_v2.md"

if [ -f "csv_only_comparison_report_v2.md" ]; then
    echo "SGSA CSV comparison report saved to: csv_only_comparison_report_v2.md"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Pipeline complete!"
echo "  Check the terminal output above for Execution Accuracy."
echo "  Reports:"
echo "    comparison_report.md              (full SQL side-by-side)"
echo "    csv_only_comparison_report.md     (offline CSV comparison)"
echo "    comparison_report_v2.md           (SGSA-enhanced SQL side-by-side)"
echo "    csv_only_comparison_report_v2.md  (SGSA-enhanced CSV comparison)"
echo "============================================================"

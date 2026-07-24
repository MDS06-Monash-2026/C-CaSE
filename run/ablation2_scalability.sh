#!/bin/bash
# =============================================================================
# ablation2_scalability.sh — Efficiency vs. Query Complexity Ablation
# =============================================================================
# AAAI Ablation Study 2: Proves SlayQL is "compute-aware" — IT-EE allocates
# tokens dynamically based on query complexity.
#
# ► RESUME-SAFE: Checkpoint files at <LOG_DIR>/.pipeline_ckpt track completed
#   stages. Bucket JSON split files are cached and reused. Re-running the script
#   after an interruption skips all fully-completed stages automatically.
#   Python stages (sql_generation, sql_execution, sql_revise, complete_schema)
#   resume per-instance without needing extra shell guards.
#
# Usage:
#   bash ablation2_scalability.sh
#   bash ablation2_scalability.sh --data_file subset_109_evaluation.json
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

while [[ $# -gt 0 ]]; do
    case $1 in
        --data_file) DATA_FILE="$2"; shift 2 ;;
        --top_n) TOP_N="$2"; shift 2 ;;
        --num_candidates) NUM_CANDIDATES="$2"; shift 2 ;;
        --task) TASK="$2"; shift 2 ;;
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
# Checkpoint helpers (shared across all ablation scripts)
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

# ===========================================================================
# Step 1: Split queries into Easy / Medium / Hard buckets (cached)
# ===========================================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║   ABLATION STUDY 2: Scalability — Token vs. Complexity          ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

SPLIT_CKPT="ablation2_split.ckpt"

if grep -q "split_done" "$SPLIT_CKPT" 2>/dev/null; then
    echo "=== [PRE] Complexity split — ✅ SKIPPED (buckets already exist)"
    for B in easy medium hard; do
        N=$(python -c "import json; d=json.load(open('ablation2_${B}_queries.json')); print(len(d))" 2>/dev/null || echo "?")
        echo "       ablation2_${B}_queries.json  →  ${N} queries"
    done
else
    echo "=== [PRE] Splitting queries into Easy / Medium / Hard ==="
    python - <<PYEOF
import json, sys
sys.path.insert(0, ".")
from it_ee import analyze_complexity

data_file = "$DATA_FILE"
with open(data_file, "r", encoding="utf-8") as f:
    data = json.load(f)

easy, medium, hard = {}, {}, {}
for iid, info in data.items():
    c = analyze_complexity(info.get("question", ""))
    n = sum([c["has_temporal"], c["has_aggregation"], c["has_structural"]])
    if n == 0:
        easy[iid] = info
    elif n == 1:
        medium[iid] = info
    else:
        hard[iid] = info

print(f"Easy: {len(easy)}  Medium: {len(medium)}  Hard: {len(hard)}")
for name, bucket in [("easy", easy), ("medium", medium), ("hard", hard)]:
    with open(f"ablation2_{name}_queries.json", "w", encoding="utf-8") as f:
        json.dump(bucket, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(bucket)} queries → ablation2_{name}_queries.json")
PYEOF
    echo "split_done" >> "$SPLIT_CKPT"
fi

# ===========================================================================
# Pipeline runner for one (system, bucket) pair
# ===========================================================================
run_pipeline() {
    local SYSTEM="$1"          # "slayql" | "autolink"
    local BUCKET="$2"          # "easy" | "medium" | "hard"
    local BUCKET_FILE="ablation2_${BUCKET}_queries.json"
    local LOG_DIR="ablation2_${SYSTEM}_${BUCKET}"
    local SCHEMA_DIR="${LOG_DIR}/final_schema_prompts"

    if [ ! -f "$BUCKET_FILE" ]; then
        echo "[SKIP] $BUCKET_FILE not found — skipping ${SYSTEM}/${BUCKET}"
        return
    fi

    local N
    N=$(python -c "import json; print(len(json.load(open('$BUCKET_FILE'))))" 2>/dev/null || echo 0)
    if [ "$N" -eq 0 ]; then
        echo "[SKIP] Empty bucket ${BUCKET} for ${SYSTEM}"
        return
    fi

    CKPT_FILE="${LOG_DIR}/.pipeline_ckpt"
    mkdir -p "$LOG_DIR"
    touch "$CKPT_FILE"

    echo ""
    echo "── ${SYSTEM^^} / ${BUCKET^^} (${N} queries) ─────────────────────────────"
    echo "   Log: ${LOG_DIR}   Ckpt: ${CKPT_FILE}"

    if [ "$SYSTEM" = "slayql" ]; then
        # ── SlayQL pipeline ────────────────────────────────────────────────

        if should_skip 1; then
            echo "  [1] BM25 index          ✅ skip"
        else
            python build_value_indices.py --data_file "$BUCKET_FILE"
            mark_done 1
        fi

        if output_exists "${LOG_DIR}/initial_candidates.json"; then
            echo "  [2] Schema retrieval    ✅ skip"
            mark_done 2
        else
            python retrieve_topk_schema.py --log_path "$LOG_DIR" --top_n "$TOP_N" --data_file "$BUCKET_FILE"
            mark_done 2
        fi

        if output_exists "${LOG_DIR}/filled_pre_rule.json"; then
            echo "  [3] ID injection        ✅ skip"
            mark_done 3
        else
            python add_id.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE"
            mark_done 3
        fi

        ICOUNT=$(ls "${LOG_DIR}/schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$ICOUNT" -gt 0 ]; then
            echo "  [4] Initial prompts     ✅ skip (${ICOUNT} exist)"
            mark_done 4
        else
            python generate_schema.py --log_path "$LOG_DIR" --is_initial --data_file "$BUCKET_FILE"
            mark_done 4
        fi

        # complete_schema resumes internally — always call it
        CCOUNT=$(ls "${LOG_DIR}/candidates/" 2>/dev/null | wc -l | tr -d ' ')
        echo "  [5] Schema completion   ♻  resuming (${CCOUNT} cached)..."
        python complete_schema.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE"
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
            echo "  [7] Final prompts       ✅ skip (${FCOUNT} exist)"
            mark_done 7
        else
            python generate_schema.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE"
            mark_done 7
        fi

        if should_skip 8; then
            echo "  [8] SQL generation      ✅ skip"
        else
            python sql_generation.py --num_workers "$NUM_GEN_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$BUCKET_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 8
        fi

        if should_skip 9; then
            echo "  [9] SQL execution       ✅ skip"
        else
            python sql_execution.py --num_workers "$NUM_EXEC_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$BUCKET_FILE" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 9
        fi

        if should_skip 10; then
            echo "  [10] SQL revision       ✅ skip"
        else
            python sql_revise.py --num_workers "$NUM_REVISE_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$BUCKET_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 10
        fi

        if output_exists "${LOG_DIR}/sql_selection_v1/final" || output_exists "${LOG_DIR}/sql_selection/final"; then
            echo "  [11] SQL selection      ✅ skip"
            mark_done 11
        else
            python sql_selection.py --log_path "$LOG_DIR" --num_candidates "$NUM_CANDIDATES" \
                --workers "$NUM_SELECTION_WORKERS" --task "$TASK" --data_file "$BUCKET_FILE"
            mark_done 11
        fi

    else
        # ── AutoLink baseline pipeline ─────────────────────────────────────

        if output_exists "${LOG_DIR}/pre_rule.json"; then
            echo "  [3] ID injection        ✅ skip"
            mark_done 3
        else
            python _baseline/add_id.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE"
            mark_done 3
        fi

        ICOUNT=$(ls "${LOG_DIR}/schema_prompts/" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$ICOUNT" -gt 0 ]; then
            echo "  [4] Initial prompts     ✅ skip"
            mark_done 4
        else
            python _baseline/generate_schema.py --log_path "$LOG_DIR" --is_initial --data_file "$BUCKET_FILE"
            mark_done 4
        fi

        CCOUNT=$(ls "${LOG_DIR}/candidates/" 2>/dev/null | wc -l | tr -d ' ')
        echo "  [5] Schema completion   ♻  resuming (${CCOUNT} cached)..."
        python _baseline/complete_schema.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE"
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
            python _baseline/generate_schema.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE"
            mark_done 7
        fi

        if should_skip 8; then
            echo "  [8] SQL generation      ✅ skip"
        else
            python _baseline/sql_generation.py --num_workers "$NUM_GEN_WORKERS" \
                --num_candidates "$NUM_CANDIDATES" --data_file "$BUCKET_FILE" \
                --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 8
        fi

        if should_skip 9; then
            echo "  [9] SQL execution       ✅ skip"
        else
            python sql_execution.py --num_workers "$NUM_EXEC_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$BUCKET_FILE" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 9
        fi

        if should_skip 10; then
            echo "  [10] SQL revision       ✅ skip"
        else
            python sql_revise.py --num_workers "$NUM_REVISE_WORKERS" --num_candidates "$NUM_CANDIDATES" \
                --data_file "$BUCKET_FILE" --schema_dir "$SCHEMA_DIR" --log_path "$LOG_DIR" --task "$TASK"
            mark_done 10
        fi

        if should_skip 11 || output_exists "${LOG_DIR}/sql_selection/final"; then
            echo "  [11] SQL selection      ✅ skip"
            mark_done 11
        else
            python sql_selection.py --log_path "$LOG_DIR" --num_candidates "$NUM_CANDIDATES" \
                --workers "$NUM_SELECTION_WORKERS" --task "$TASK" --data_file "$BUCKET_FILE"
            mark_done 11
        fi
    fi

    # ── Evaluate ──────────────────────────────────────────────────────────
    if should_skip 12 || output_exists "${LOG_DIR}/eval_result.txt"; then
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
                --gold_dir gold --data_file "../run/$BUCKET_FILE" \
                2>&1 | tee "../run/${LOG_DIR}/eval_result.txt"
        fi
        cd ../run
        python parse_tokens.py --log_path "$LOG_DIR" --data_file "$BUCKET_FILE" \
            2>&1 | tee -a "${LOG_DIR}/eval_result.txt"
        mark_done 12
    fi

    DONE=$(grep -c "=done" "${LOG_DIR}/.pipeline_ckpt" 2>/dev/null || echo 0)
    echo "  ✅ ${SYSTEM^^}/${BUCKET^^} complete  (${DONE}/12 stages done)"
}

# ===========================================================================
# Run All 6 Combinations
# ===========================================================================
for BUCKET in easy medium hard; do
    run_pipeline slayql   "$BUCKET"
    run_pipeline autolink "$BUCKET"
done

# ===========================================================================
# Generate Report
# ===========================================================================
echo ""
echo "=== Generating Ablation 2 Report ==="
python generate_ablation_report.py \
    --ablation_type scalability \
    --data_file "$DATA_FILE" \
    --task "$TASK" \
    --variants \
        "SlayQL Easy:ablation2_slayql_easy" \
        "SlayQL Medium:ablation2_slayql_medium" \
        "SlayQL Hard:ablation2_slayql_hard" \
        "AutoLink Easy:ablation2_autolink_easy" \
        "AutoLink Medium:ablation2_autolink_medium" \
        "AutoLink Hard:ablation2_autolink_hard" \
    --bucket_files \
        "ablation2_easy_queries.json" \
        "ablation2_medium_queries.json" \
        "ablation2_hard_queries.json" \
    --output_path "ablation2_scalability_report.md"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Ablation Study 2 Complete!                                      ║"
echo "║  Report: ablation2_scalability_report.md                        ║"
echo "║  Re-run any time to resume from interruption point.             ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

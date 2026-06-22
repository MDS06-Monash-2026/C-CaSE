#!/bin/bash
set -e

# Configuration
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

DATA_FILE="subset_diverse_20_evaluation.json"
BASELINE_LOG="log_v3_topn100"
ENHANCED_LOG="log_subset_diverse_20_evaluation_slayql_ccase"
TOP_N=100
NUM_CANDIDATES=5
TASK="r1_lite"

echo "=== Building Value Indices for Enhanced Pipeline (Offline Phase) ==="
python build_value_indices.py

echo "=== Running Enhanced Pipeline (SlayQL) ==="
# Since the python scripts have been injected with the new module logic, 
# running this sequence automatically executes the IT-EE, RBP, and Value Grounding logic.
python retrieve_topk_schema.py --log_path $ENHANCED_LOG --top_n $TOP_N --data_file $DATA_FILE
python add_id.py --log_path $ENHANCED_LOG --data_file $DATA_FILE
python generate_schema.py --log_path $ENHANCED_LOG --is_initial --data_file $DATA_FILE
python complete_schema.py --log_path $ENHANCED_LOG --data_file $DATA_FILE
python postprocess.py --log_path $ENHANCED_LOG
python generate_schema.py --log_path $ENHANCED_LOG --data_file $DATA_FILE

python sql_generation.py \
  --num_workers 32 \
  --num_candidates $NUM_CANDIDATES \
  --data_file $DATA_FILE \
  --schema_dir $ENHANCED_LOG/final_schema_prompts \
  --log_path $ENHANCED_LOG \
  --task $TASK

echo "=== Evaluating Enhanced Pipeline ==="
cd ../evaluation_suite
python evaluate.py --mode sql --result_dir ../run/$ENHANCED_LOG/sql_gen/${TASK}_sql_0 --data_file ../run/$DATA_FILE

# Evaluate baseline if exists
if [ -d "../run/$BASELINE_LOG/sql_selection/final" ]; then
    echo "=== Evaluating Baseline Pipeline ==="
    python evaluate.py --mode sql --result_dir ../run/$BASELINE_LOG/sql_selection/final --data_file ../run/$DATA_FILE
else
    echo "Baseline SQL output not found in $BASELINE_LOG/sql_selection/final. Skipping baseline evaluation."
    echo "If you need to run the baseline, revert the python scripts to their original state and run the pipeline into $BASELINE_LOG."
fi
cd ../run

echo "=== Extracting Token Metrics ==="
python parse_tokens.py --log_path $ENHANCED_LOG --data_file $DATA_FILE
if [ -d "$BASELINE_LOG/input" ] || [ -d "$BASELINE_LOG/inputs" ]; then
    echo "Baseline Token Metrics:"
    python parse_tokens.py --log_path $BASELINE_LOG --data_file $DATA_FILE
fi

echo "=== Generating Side-by-Side Comparison Report ==="
python generate_comparison.py --data_file $DATA_FILE --slayql_dir "$ENHANCED_LOG/sql_gen/${TASK}_sql_0" --baseline_dir "$BASELINE_LOG/sql_selection/final" --output_path "comparison_report.md"
if [ -f "comparison_report.md" ]; then
    cp -f "comparison_report.md" "C:\Users\ASUS ROG\.gemini\antigravity-ide\brain\ca786be0-2761-41c0-9119-b525140ee272\comparison_report.md"
    echo "Side-by-side comparison report updated at C:\Users\ASUS ROG\.gemini\antigravity-ide\brain\ca786be0-2761-41c0-9119-b525140ee272\comparison_report.md"
fi

echo "Comparison complete! Check the terminal output above for the accuracy scores."

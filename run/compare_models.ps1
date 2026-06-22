# Load .env file
if (Test-Path ".env") {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split '=', 2
            if ($parts.Length -eq 2) {
                $name = $parts[0].Trim()
                $value = $parts[1].Trim()
                [System.Environment]::SetEnvironmentVariable($name, $value)
            }
        }
    }
}

$DATA_FILE="subset_diverse_20_evaluation.json"
$BASELINE_LOG="log_v3_topn100"
$ENHANCED_LOG="log_subset_diverse_20_evaluation_slayql_ccase"
$TOP_N=100
$NUM_CANDIDATES=5
$TASK="r1_lite"

Write-Host "=== Building Value Indices for Enhanced Pipeline (Offline Phase) ==="
python build_value_indices.py

Write-Host "=== Running Enhanced Pipeline (SlayQL) ==="
python retrieve_topk_schema.py --log_path $ENHANCED_LOG --top_n $TOP_N --data_file $DATA_FILE
python add_id.py --log_path $ENHANCED_LOG --data_file $DATA_FILE
python generate_schema.py --log_path $ENHANCED_LOG --is_initial --data_file $DATA_FILE
python complete_schema.py --log_path $ENHANCED_LOG --data_file $DATA_FILE
python postprocess.py --log_path $ENHANCED_LOG
python generate_schema.py --log_path $ENHANCED_LOG --data_file $DATA_FILE

python sql_generation.py `
  --num_workers 32 `
  --num_candidates $NUM_CANDIDATES `
  --data_file $DATA_FILE `
  --schema_dir "$ENHANCED_LOG/final_schema_prompts" `
  --log_path $ENHANCED_LOG `
  --task $TASK

Write-Host "=== Evaluating Enhanced Pipeline ==="
Push-Location ../evaluation_suite
python evaluate.py --mode sql --result_dir "../run/$ENHANCED_LOG/sql_gen/${TASK}_sql_0" --data_file "../run/$DATA_FILE"

# Evaluate baseline if exists
if (Test-Path "../run/$BASELINE_LOG/sql_selection/final") {
    Write-Host "=== Evaluating Baseline Pipeline ==="
    python evaluate.py --mode sql --result_dir "../run/$BASELINE_LOG/sql_selection/final" --data_file "../run/$DATA_FILE"
} else {
    Write-Host "Baseline SQL output not found in $BASELINE_LOG/sql_selection/final. Skipping baseline evaluation."
}
Pop-Location

Write-Host "=== Extracting Token Metrics ==="
python parse_tokens.py --log_path $ENHANCED_LOG --data_file $DATA_FILE
if (Test-Path "$BASELINE_LOG/input") {
    Write-Host "Baseline Token Metrics:"
    python parse_tokens.py --log_path $BASELINE_LOG --data_file $DATA_FILE
}

Write-Host "=== Generating Side-by-Side Comparison Report ==="
python generate_comparison.py --data_file $DATA_FILE --slayql_dir "$ENHANCED_LOG/sql_gen/${TASK}_sql_0" --baseline_dir "$BASELINE_LOG/sql_selection/final" --output_path "comparison_report.md"
if (Test-Path "comparison_report.md") {
    Copy-Item "comparison_report.md" -Destination "C:\Users\ASUS ROG\.gemini\antigravity-ide\brain\ca786be0-2761-41c0-9119-b525140ee272\comparison_report.md" -Force
    Write-Host "Side-by-side comparison report updated at C:\Users\ASUS ROG\.gemini\antigravity-ide\brain\ca786be0-2761-41c0-9119-b525140ee272\comparison_report.md"
}

Write-Host "Comparison complete! Check the terminal output above for the accuracy scores."

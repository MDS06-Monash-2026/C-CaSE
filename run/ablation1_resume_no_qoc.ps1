# Resume ablation1_no_qoc from stage 10 (revision) through eval + report.
# Stages 8-9 (SQL gen + execution) are already complete — do not rerun.
Set-StrictMode -Off
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "."

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split '=', 2
            if ($parts.Length -eq 2) {
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
            }
        }
    }
}

$DATA_FILE = "subset_diverse_20_evaluation.json"
$FULL_LOG = "log_subset_diverse_20_evaluation_slayql_ccase"
$LOG_DIR = "ablation1_no_qoc"
$TASK = "r1_lite"
$NUM_CANDIDATES = 5

Write-Host "=== Resuming ${LOG_DIR}: stages 10-12 ==="
Write-Host "Revision files before: $((Get-ChildItem "$LOG_DIR/sql_revise" -Recurse -Filter '*.sql' -File).Count)"

# Stage 10 — SQL revision (resume-safe)
python sql_revise.py --num_workers 8 --num_candidates $NUM_CANDIDATES `
    --data_file $DATA_FILE `
    --schema_dir "$LOG_DIR/final_schema_prompts" `
    --log_path $LOG_DIR --task $TASK

Write-Host "Revision files after: $((Get-ChildItem "$LOG_DIR/sql_revise" -Recurse -Filter '*.sql' -File).Count)"

# Stage 11 — SQL selection (resume-safe)
python sql_selection.py --log_path $LOG_DIR --num_candidates $NUM_CANDIDATES `
    --workers 32 --task $TASK --data_file $DATA_FILE

$selDir = "$LOG_DIR/sql_selection/final"
Write-Host "Selection dirs: $((Get-ChildItem $selDir -Directory).Count)"
Write-Host "result.csv: $((Get-ChildItem $selDir -Recurse -Filter result.csv).Count)"

# Stage 12 — Evaluation (local, no API)
Remove-Item "$LOG_DIR/eval_result.txt" -Force -ErrorAction SilentlyContinue
Push-Location ../evaluation_suite
python evaluate.py --mode exec_result `
    --result_dir "../run/$selDir" `
    --gold_dir gold --data_file "../run/$DATA_FILE" 2>&1 |
    Out-File -FilePath "../run/$LOG_DIR/eval_result.txt" -Encoding utf8
Pop-Location
python parse_tokens.py --log_path $LOG_DIR --data_file $DATA_FILE 2>&1 |
    Out-File -FilePath "$LOG_DIR/eval_result.txt" -Encoding utf8 -Append

Get-Content "$LOG_DIR/eval_result.txt" -Encoding utf8 | Select-String "Results:|Evaluating IDs"

# Regenerate ablation report (all 5 variants)
Write-Host "`n=== Regenerating ablation report ==="
python generate_ablation_report.py `
    --ablation_type component_dropout `
    --data_file $DATA_FILE `
    --task $TASK `
    --variants `
        "Full SlayQL:$FULL_LOG" `
        "w/o IT-EE (Always loops):ablation1_no_itee" `
        "w/o RBP (No graph joins):ablation1_no_rbp" `
        "w/o BM25 Grounding:ablation1_no_bm25" `
        "w/o QOC (Strict Outputs):$LOG_DIR" `
    --output_path "ablation1_component_dropout_report.md"

Write-Host "`nDone. See $LOG_DIR/eval_result.txt and ablation1_component_dropout_report.md"

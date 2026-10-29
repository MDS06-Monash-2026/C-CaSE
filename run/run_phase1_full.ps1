# =============================================================================
# run_phase1_full.ps1 - Phase 1: Baseline + SlayQL on full Spider 2.0-Lite (547)
# =============================================================================
# Uses spider2_data.json (547 instances). Does NOT touch 178-subset log dirs.
# Resume-safe via per-log .pipeline_ckpt and output existence checks.
# =============================================================================
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

$DATA_FILE = "spider2_data.json"
$SLAYQL_LOG = "log_spider2_full_slayql"
$BASELINE_LOG = "log_spider2_full_baseline"
$REPORT_OUT = "comparison_report_full.md"
$TOP_N = 100
$NUM_CANDIDATES = 5
$TASK = "r1_lite"
$NUM_GEN_WORKERS = 32
$NUM_EXEC_WORKERS = 4
$NUM_REVISE_WORKERS = 8
$NUM_SELECTION_WORKERS = 32
$BASELINE_DIR = "_baseline"

$script:CKPT_FILE = ""

function Mark-Done([int]$Stage) {
    if (-not (Select-String -Path $script:CKPT_FILE -Pattern "^STAGE_${Stage}=done" -Quiet)) {
        Add-Content -Path $script:CKPT_FILE -Value "STAGE_${Stage}=done"
    }
}

function Should-Skip([int]$Stage) {
    if (-not (Test-Path $script:CKPT_FILE)) { return $false }
    return (Select-String -Path $script:CKPT_FILE -Pattern "^STAGE_${Stage}=done" -Quiet)
}

function Run-SlayQLPipeline {
    $LogDir = $SLAYQL_LOG
    $SchemaDir = "$LogDir/final_schema_prompts"
    $script:CKPT_FILE = "$LogDir/.pipeline_ckpt"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    if (-not (Test-Path $script:CKPT_FILE)) { New-Item -ItemType File -Path $script:CKPT_FILE | Out-Null }

    Write-Host ""
    Write-Host "================================================================"
    Write-Host "  PHASE 1 - SlayQL Full (547 instances)"
    Write-Host "  Log: $LogDir"
    Write-Host "================================================================"

    if (Should-Skip 1) { Write-Host "[1/12] BM25 index - skip" }
    else { python build_value_indices.py --data_file $DATA_FILE; Mark-Done 1 }

    if (Test-Path "$LogDir/initial_candidates.json") { Write-Host "[2/12] Retrieval - skip"; Mark-Done 2 }
    else { python retrieve_topk_schema.py --log_path $LogDir --top_n $TOP_N --data_file $DATA_FILE; Mark-Done 2 }

    if (Test-Path "$LogDir/filled_pre_rule.json") { Write-Host "[3/12] add_id - skip"; Mark-Done 3 }
    else { python add_id.py --log_path $LogDir --data_file $DATA_FILE; Mark-Done 3 }

    $initCount = if (Test-Path "$LogDir/schema_prompts") { (Get-ChildItem "$LogDir/schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
    if ($initCount -gt 0) { Write-Host "[4/12] initial schema - skip ($initCount)"; Mark-Done 4 }
    else { python generate_schema.py --log_path $LogDir --is_initial --data_file $DATA_FILE; Mark-Done 4 }

    $candCount = if (Test-Path "$LogDir/candidates") { (Get-ChildItem "$LogDir/candidates" -File -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
    Write-Host "[5/12] schema completion - resuming ($candCount cached)"
    python complete_schema.py --log_path $LogDir --data_file $DATA_FILE
    Mark-Done 5

    if (Test-Path "$LogDir/filled_schema.json") { Write-Host "[6/12] postprocess - skip"; Mark-Done 6 }
    else { python postprocess.py --log_path $LogDir; Mark-Done 6 }

    $finalCount = if (Test-Path "$LogDir/final_schema_prompts") { (Get-ChildItem "$LogDir/final_schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
    if ($finalCount -gt 0) { Write-Host "[7/12] final schema - skip ($finalCount)"; Mark-Done 7 }
    else { python generate_schema.py --log_path $LogDir --data_file $DATA_FILE; Mark-Done 7 }

    if (Should-Skip 8) { Write-Host "[8/12] SQL generation - skip" }
    else {
        python sql_generation.py --num_workers $NUM_GEN_WORKERS --num_candidates $NUM_CANDIDATES `
            --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
        Mark-Done 8
    }

    if (Should-Skip 9) { Write-Host "[9/12] SQL execution - skip" }
    else {
        python sql_execution.py --num_workers $NUM_EXEC_WORKERS --num_candidates $NUM_CANDIDATES `
            --data_file $DATA_FILE --log_path $LogDir --task $TASK
        Mark-Done 9
    }

    if (Should-Skip 10) { Write-Host "[10/12] SQL revision - skip" }
    else {
        python sql_revise.py --num_workers $NUM_REVISE_WORKERS --num_candidates $NUM_CANDIDATES `
            --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
        Mark-Done 10
    }

    $sel = Test-Path "$LogDir/sql_selection/final"
    $selV1 = Test-Path "$LogDir/sql_selection_v1/final"
    if ($sel -or $selV1) { Write-Host "[11/12] SQL selection - skip"; Mark-Done 11 }
    else {
        python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES `
            --workers $NUM_SELECTION_WORKERS --task $TASK --data_file $DATA_FILE
        Mark-Done 11
    }

    if ((Should-Skip 12) -and (Test-Path "$LogDir/eval_result.txt")) { Write-Host "[12/12] eval - skip" }
    else {
        Push-Location ../evaluation_suite
        if (Test-Path "../run/$LogDir/sql_selection_v1/final") {
            $ResultDir = "../run/$LogDir/sql_selection_v1/final"
        } elseif (Test-Path "../run/$LogDir/sql_selection/final") {
            $ResultDir = "../run/$LogDir/sql_selection/final"
        } else {
            $ResultDir = "../run/$LogDir/sql_gen/${TASK}_sql_0"
        }
        python evaluate.py --mode exec_result --result_dir $ResultDir `
            --gold_dir gold --data_file "../run/$DATA_FILE" 2>&1 |
            Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
        Pop-Location
        python parse_tokens.py --log_path $LogDir --data_file $DATA_FILE 2>&1 |
            Out-File -FilePath "$LogDir/eval_result.txt" -Encoding utf8 -Append
        Mark-Done 12
    }
    Get-Content "$LogDir/eval_result.txt" -Encoding utf8 -ErrorAction SilentlyContinue | Select-String "Results:|Evaluating IDs"
}

function Run-BaselinePipeline {
    $LogDir = $BASELINE_LOG
    $SchemaDir = "$LogDir/final_schema_prompts"
    $script:CKPT_FILE = "$LogDir/.pipeline_ckpt"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    if (-not (Test-Path $script:CKPT_FILE)) { New-Item -ItemType File -Path $script:CKPT_FILE | Out-Null }

    Write-Host ""
    Write-Host "================================================================"
    Write-Host "  PHASE 1 - AutoLink Baseline Full (547 instances)"
    Write-Host "  Log: $LogDir"
    Write-Host "================================================================"

    if (Test-Path "$LogDir/initial_candidates.json") { Write-Host "[1/11] retrieval - skip"; Mark-Done 1 }
    else {
        python "$BASELINE_DIR/retrieve_topk_schema.py" --log_path $LogDir --top_n $TOP_N --data_file $DATA_FILE
        Mark-Done 1
    }

    if (Test-Path "$LogDir/filled_pre_rule.json") { Write-Host "[2/11] add_id - skip"; Mark-Done 2 }
    else { python "$BASELINE_DIR/add_id.py" --log_path $LogDir --data_file $DATA_FILE; Mark-Done 2 }

    $initCount = if (Test-Path "$LogDir/schema_prompts") { (Get-ChildItem "$LogDir/schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
    if ($initCount -gt 0) { Write-Host "[3/11] initial schema - skip"; Mark-Done 3 }
    else { python "$BASELINE_DIR/generate_schema.py" --log_path $LogDir --is_initial --data_file $DATA_FILE; Mark-Done 3 }

    Write-Host "[4/11] schema completion - resuming"
    python "$BASELINE_DIR/complete_schema.py" --log_path $LogDir --data_file $DATA_FILE
    Mark-Done 4

    if (Test-Path "$LogDir/filled_schema.json") { Write-Host "[5/11] postprocess - skip"; Mark-Done 5 }
    else { python postprocess.py --log_path $LogDir; Mark-Done 5 }

    $finalCount = if (Test-Path "$LogDir/final_schema_prompts") { (Get-ChildItem "$LogDir/final_schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
    if ($finalCount -gt 0) { Write-Host "[6/11] final schema - skip"; Mark-Done 6 }
    else { python "$BASELINE_DIR/generate_schema.py" --log_path $LogDir --data_file $DATA_FILE; Mark-Done 6 }

    if (Should-Skip 7) { Write-Host "[7/11] SQL generation - skip" }
    else {
        python "$BASELINE_DIR/sql_generation.py" --num_workers $NUM_GEN_WORKERS --num_candidates $NUM_CANDIDATES `
            --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
        Mark-Done 7
    }

    if (Should-Skip 8) { Write-Host "[8/11] SQL execution - skip" }
    else {
        python sql_execution.py --num_workers $NUM_EXEC_WORKERS --num_candidates $NUM_CANDIDATES `
            --data_file $DATA_FILE --log_path $LogDir --task $TASK
        Mark-Done 8
    }

    if (Should-Skip 9) { Write-Host "[9/11] SQL revision - skip" }
    else {
        python sql_revise.py --num_workers $NUM_REVISE_WORKERS --num_candidates $NUM_CANDIDATES `
            --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
        Mark-Done 9
    }

    if ((Should-Skip 10) -or (Test-Path "$LogDir/sql_selection/final")) { Write-Host "[10/11] SQL selection - skip"; Mark-Done 10 }
    else {
        python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES `
            --workers $NUM_SELECTION_WORKERS --task $TASK --data_file $DATA_FILE
        Mark-Done 10
    }

    if ((Should-Skip 11) -and (Test-Path "$LogDir/eval_result.txt")) { Write-Host "[11/11] eval - skip" }
    else {
        Push-Location ../evaluation_suite
        if (Test-Path "../run/$LogDir/sql_selection/final") {
            $ResultDir = "../run/$LogDir/sql_selection/final"
        } else {
            $ResultDir = "../run/$LogDir/sql_gen/${TASK}_sql_0"
        }
        python evaluate.py --mode exec_result --result_dir $ResultDir `
            --gold_dir gold --data_file "../run/$DATA_FILE" 2>&1 |
            Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
        Pop-Location
        python parse_tokens.py --log_path $LogDir --data_file $DATA_FILE 2>&1 |
            Out-File -FilePath "$LogDir/eval_result.txt" -Encoding utf8 -Append
        Mark-Done 11
    }
    Get-Content "$LogDir/eval_result.txt" -Encoding utf8 -ErrorAction SilentlyContinue | Select-String "Results:|Evaluating IDs"
}

Write-Host ""
Write-Host "PHASE 1 - Full Dataset (547 instances)"
Write-Host "Data file : $DATA_FILE"
Write-Host "SlayQL log: $SLAYQL_LOG"
Write-Host "Baseline  : $BASELINE_LOG"
Write-Host "178-subset logs are NOT modified."
Write-Host ""

Run-SlayQLPipeline
Run-BaselinePipeline

Write-Host ""
Write-Host "=== Generating full-dataset comparison report ==="
if (Test-Path "$SLAYQL_LOG/sql_selection_v1/final") {
    $SlayqlCompare = "$SLAYQL_LOG/sql_selection_v1/final"
} elseif (Test-Path "$SLAYQL_LOG/sql_selection/final") {
    $SlayqlCompare = "$SLAYQL_LOG/sql_selection/final"
} else {
    $SlayqlCompare = "$SLAYQL_LOG/sql_gen/${TASK}_sql_0"
}
if (Test-Path "$BASELINE_LOG/sql_selection/final") {
    $BaselineCompare = "$BASELINE_LOG/sql_selection/final"
} else {
    $BaselineCompare = "$BASELINE_LOG/sql_gen/${TASK}_sql_0"
}

python generate_comparison.py `
    --data_file $DATA_FILE `
    --slayql_dir $SlayqlCompare `
    --baseline_dir $BaselineCompare `
    --output_path $REPORT_OUT

Write-Host ""
Write-Host "Phase 1 complete. Report: $REPORT_OUT"

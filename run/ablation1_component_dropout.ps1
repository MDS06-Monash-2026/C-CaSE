# =============================================================================
# ablation1_component_dropout.ps1 — Leave-One-Out Component Ablation (Windows)
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

$DATA_FILE = "subset_diverse_20_evaluation.json"
$TOP_N = 100
$NUM_CANDIDATES = 5
$TASK = "r1_lite"
$NUM_GEN_WORKERS = 32
$NUM_EXEC_WORKERS = 4
$NUM_REVISE_WORKERS = 8
$NUM_SELECTION_WORKERS = 32
$FORCE_STAGE = 0

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--data_file" { $DATA_FILE = $args[++$i] }
        "--top_n" { $TOP_N = [int]$args[++$i] }
        "--num_candidates" { $NUM_CANDIDATES = [int]$args[++$i] }
        "--task" { $TASK = $args[++$i] }
        "--force_stage" { $FORCE_STAGE = [int]$args[++$i] }
        default { Write-Host "[WARN] Unknown argument: $($args[$i])" }
    }
}

$script:CKPT_FILE = ""

function Mark-Done([int]$Stage) {
    Add-Content -Path $script:CKPT_FILE -Value "STAGE_${Stage}=done"
}

function Should-Skip([int]$Stage) {
    if ($FORCE_STAGE -gt 0 -and $Stage -ge $FORCE_STAGE) { return $false }
    if (-not (Test-Path $script:CKPT_FILE)) { return $false }
    return (Select-String -Path $script:CKPT_FILE -Pattern "^STAGE_${Stage}=done" -Quiet)
}

function Run-Variant(
    [string]$VariantName,
    [string]$LogDir,
    [string]$ExtraRetrieveArgs = "",
    [string]$ExtraCompleteArgs = "",
    [string]$ExtraSqlGenArgs = ""
) {
    $SchemaDir = "$LogDir/final_schema_prompts"
    $script:CKPT_FILE = "$LogDir/.pipeline_ckpt"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    if (-not (Test-Path $script:CKPT_FILE)) { New-Item -ItemType File -Path $script:CKPT_FILE | Out-Null }

    Write-Host ""
    Write-Host "================================================================"
    Write-Host "  ABLATION 1 - Variant : $VariantName"
    Write-Host "  Log dir              : $LogDir"
    Write-Host "================================================================"
    Write-Host ""

    if (Should-Skip 1) {
        Write-Host "=== [1/12] BM25 index - SKIPPED (checkpoint)"
    } else {
        Write-Host "=== [1/12] Building BM25 Value Indices ==="
        python build_value_indices.py --data_file $DATA_FILE
        Mark-Done 1
    }

    if (Test-Path "$LogDir/initial_candidates.json") {
        Write-Host "=== [2/12] Schema Retrieval - SKIPPED (initial_candidates.json exists)"
        Mark-Done 2
    } else {
        Write-Host "=== [2/12] Dense Retrieval + RBP + IT-EE (variant: $VariantName) ==="
        if ($ExtraRetrieveArgs) {
            Invoke-Expression "python retrieve_topk_schema.py --log_path `"$LogDir`" --top_n $TOP_N --data_file `"$DATA_FILE`" $ExtraRetrieveArgs"
        } else {
            python retrieve_topk_schema.py --log_path $LogDir --top_n $TOP_N --data_file $DATA_FILE
        }
        Mark-Done 2
    }

    if (Test-Path "$LogDir/filled_pre_rule.json") {
        Write-Host "=== [3/12] ID Injection - SKIPPED (filled_pre_rule.json exists)"
        Mark-Done 3
    } else {
        Write-Host "=== [3/12] Injecting instance IDs ==="
        python add_id.py --log_path $LogDir --data_file $DATA_FILE
        Mark-Done 3
    }

    $initCount = 0
    if (Test-Path "$LogDir/schema_prompts") {
        $initCount = (Get-ChildItem "$LogDir/schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count
    }
    if ($initCount -gt 0) {
        Write-Host "=== [4/12] Initial schema prompts - SKIPPED ($initCount prompts exist)"
        Mark-Done 4
    } else {
        Write-Host "=== [4/12] Generating initial schema prompts ==="
        python generate_schema.py --log_path $LogDir --is_initial --data_file $DATA_FILE
        Mark-Done 4
    }

    $candCount = 0
    if (Test-Path "$LogDir/candidates") {
        $candCount = (Get-ChildItem "$LogDir/candidates" -File -ErrorAction SilentlyContinue | Measure-Object).Count
    }
    Write-Host "=== [5/12] Schema completion - RESUMING ($candCount instances already cached) ==="
    if ($ExtraCompleteArgs) {
        Invoke-Expression "python complete_schema.py --log_path `"$LogDir`" --data_file `"$DATA_FILE`" $ExtraCompleteArgs"
    } else {
        python complete_schema.py --log_path $LogDir --data_file $DATA_FILE
    }
    Mark-Done 5

    if (Test-Path "$LogDir/filled_schema.json") {
        Write-Host "=== [6/12] Postprocess - SKIPPED (filled_schema.json exists)"
        Mark-Done 6
    } else {
        Write-Host "=== [6/12] Postprocessing schema candidates ==="
        python postprocess.py --log_path $LogDir
        Mark-Done 6
    }

    $finalCount = 0
    if (Test-Path "$LogDir/final_schema_prompts") {
        $finalCount = (Get-ChildItem "$LogDir/final_schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count
    }
    if ($finalCount -gt 0) {
        Write-Host "=== [7/12] Final schema prompts - SKIPPED ($finalCount prompts exist)"
        Mark-Done 7
    } else {
        Write-Host "=== [7/12] Generating final schema prompts ==="
        python generate_schema.py --log_path $LogDir --data_file $DATA_FILE
        Mark-Done 7
    }

    $sql0Count = 0
    if (Test-Path "$LogDir/sql_gen/${TASK}_sql_0") {
        $sql0Count = (Get-ChildItem "$LogDir/sql_gen/${TASK}_sql_0" -File -ErrorAction SilentlyContinue | Measure-Object).Count
    }
    if ((Should-Skip 8) -and ($sql0Count -gt 0)) {
        Write-Host "=== [8/12] SQL Generation - SKIPPED (checkpoint, $sql0Count sql files)"
    } else {
        if ($sql0Count -eq 0 -and (Should-Skip 8)) {
            Write-Host "=== [8/12] SQL Generation - RE-RUNNING (checkpoint stale, 0 sql files)"
        } else {
            Write-Host "=== [8/12] Generating SQL candidates (resume-safe) ==="
        }
        if ($ExtraSqlGenArgs) {
            Invoke-Expression "python sql_generation.py --num_workers $NUM_GEN_WORKERS --num_candidates $NUM_CANDIDATES --data_file `"$DATA_FILE`" --schema_dir `"$SchemaDir`" --log_path `"$LogDir`" --task `"$TASK`" $ExtraSqlGenArgs"
        } else {
            python sql_generation.py --num_workers $NUM_GEN_WORKERS --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
        }
        Mark-Done 8
    }

    $execCsv = 0
    for ($ci = 0; $ci -lt $NUM_CANDIDATES; $ci++) {
        $ep = "$LogDir/sql_gen/${TASK}_execution_result_$ci"
        if (Test-Path $ep) {
            $execCsv += (Get-ChildItem $ep -File -ErrorAction SilentlyContinue | Measure-Object).Count
        }
    }
    if ((Should-Skip 9) -and ($execCsv -gt 0)) {
        Write-Host "=== [9/12] SQL Execution - SKIPPED (checkpoint, $execCsv csv files)"
    } else {
        if ($execCsv -eq 0 -and (Should-Skip 9)) {
            Write-Host "=== [9/12] SQL Execution - RE-RUNNING (checkpoint stale, 0 csv files)"
        } else {
            Write-Host "=== [9/12] Executing SQL candidates (resume-safe) ==="
        }
        python sql_execution.py --num_workers $NUM_EXEC_WORKERS --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --log_path $LogDir --task $TASK
        Mark-Done 9
    }

    if (Should-Skip 10) {
        Write-Host "=== [10/12] SQL Revision - SKIPPED (checkpoint)"
    } else {
        Write-Host "=== [10/12] Revising failed SQL candidates (resume-safe) ==="
        python sql_revise.py --num_workers $NUM_REVISE_WORKERS --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
        Mark-Done 10
    }

    $selV1 = Test-Path "$LogDir/sql_selection_v1/final"
    $sel = Test-Path "$LogDir/sql_selection/final"
    $selCsv = 0
    if ($selV1) {
        $selCsv = (Get-ChildItem "$LogDir/sql_selection_v1/final" -Recurse -Filter result.csv -ErrorAction SilentlyContinue | Measure-Object).Count
    } elseif ($sel) {
        $selCsv = (Get-ChildItem "$LogDir/sql_selection/final" -Recurse -Filter result.csv -ErrorAction SilentlyContinue | Measure-Object).Count
    }

    if ($selCsv -gt 0 -and (Should-Skip 11)) {
        Write-Host "=== [11/12] SQL Selection - SKIPPED (selection/final exists with $selCsv result.csv)"
    } else {
        if ($selCsv -eq 0 -and ($selV1 -or $sel)) {
            Write-Host "=== [11/12] SQL Selection - RE-RUNNING (selection dirs exist but 0 result.csv)"
        } else {
            Write-Host "=== [11/12] Selecting final SQL via self-consistency ==="
        }
        python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES --workers $NUM_SELECTION_WORKERS --task $TASK --data_file $DATA_FILE
        Mark-Done 11
    }

    if ((Test-Path "$LogDir/eval_result.txt") -and (Should-Skip 12)) {
        $evalContent = Get-Content "$LogDir/eval_result.txt" -Raw
        if ($evalContent -match "Results:\s+\d+/\d+\s+correct") {
            Write-Host "=== [12/12] Evaluation - SKIPPED (valid eval_result.txt exists)"
            Mark-Done 12
        } else {
            Write-Host "=== [12/12] Re-evaluating (previous eval invalid) ==="
            Remove-Item "$LogDir/eval_result.txt" -Force
        }
    }

    if (-not (Test-Path "$LogDir/eval_result.txt")) {
        Write-Host "=== [12/12] Evaluating variant: $VariantName ==="
        Push-Location ../evaluation_suite

        if (Test-Path "../run/$LogDir/sql_selection_v1/final") {
            $ResultDir = "../run/$LogDir/sql_selection_v1/final"
        } else {
            $ResultDir = "../run/$LogDir/sql_selection/final"
        }

        if (Test-Path $ResultDir) {
            python evaluate.py --mode exec_result --result_dir $ResultDir --gold_dir gold --data_file "../run/$DATA_FILE" 2>&1 |
                Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
        } else {
            python evaluate.py --mode sql --result_dir "../run/$LogDir/sql_gen/${TASK}_sql_0" --data_file "../run/$DATA_FILE" 2>&1 |
                Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
        }
        Pop-Location

        python parse_tokens.py --log_path $LogDir --data_file $DATA_FILE 2>&1 |
            Out-File -FilePath "$LogDir/eval_result.txt" -Encoding utf8 -Append
        Mark-Done 12
    }

    Write-Host ""
    Write-Host "Variant '$VariantName' complete."
    Write-Host "Results: $LogDir/eval_result.txt"
    Write-Host ""
}

if ($DATA_FILE -eq "subset_diverse_20_evaluation.json") {
    $FULL_LOG = "log_subset_diverse_20_evaluation_slayql_ccase"
} else {
    $FULL_LOG = "ablation1_full_slayql"
}

$NO_ITEE_LOG = "ablation1_no_itee"
$NO_RBP_LOG = "ablation1_no_rbp"
$NO_BM25_LOG = "ablation1_no_bm25"
$NO_QOC_LOG = "ablation1_no_qoc"

Write-Host ""
Write-Host "ABLATION STUDY 1: Leave-One-Out Component Dropout"
Write-Host ""

$skipFull = $false
if ((Test-Path "$FULL_LOG/eval_result.txt") -and ((Get-Content "$FULL_LOG/eval_result.txt" -Raw) -match "Results:\s+(\d+)/(\d+)\s+correct")) {
    $matches = [regex]::Match((Get-Content "$FULL_LOG/eval_result.txt" -Raw), "Evaluating IDs found:\s+(\d+)")
    $evalIds = if ($matches.Success) { [int]$matches.Groups[1].Value } else { 0 }
    if ($evalIds -ge 150) {
        Write-Host "Full SlayQL already complete at: $FULL_LOG"
        $skipFull = $true
    }
}
if (-not $skipFull) {
    Remove-Item "$FULL_LOG/eval_result.txt" -Force -ErrorAction SilentlyContinue
    Run-Variant "full_slayql" $FULL_LOG
}

if (Test-Path $FULL_LOG) {
    if (-not (Test-Path "$NO_BM25_LOG/filled_pre_rule.json") -and (Test-Path "$FULL_LOG/filled_pre_rule.json")) {
        Write-Host "Copying Stages 2-4 from $FULL_LOG for w/o BM25..."
        New-Item -ItemType Directory -Force -Path $NO_BM25_LOG | Out-Null
        Copy-Item "$FULL_LOG/initial_candidates.json" "$NO_BM25_LOG/" -Force -ErrorAction SilentlyContinue
        Copy-Item "$FULL_LOG/cache" "$NO_BM25_LOG/" -Recurse -Force -ErrorAction SilentlyContinue
        Copy-Item "$FULL_LOG/status" "$NO_BM25_LOG/" -Recurse -Force -ErrorAction SilentlyContinue
        Copy-Item "$FULL_LOG/unfilled_pre_rule.json" "$NO_BM25_LOG/" -Force -ErrorAction SilentlyContinue
        Copy-Item "$FULL_LOG/filled_pre_rule.json" "$NO_BM25_LOG/" -Force -ErrorAction SilentlyContinue
        Copy-Item "$FULL_LOG/schema_prompts" "$NO_BM25_LOG/" -Recurse -Force -ErrorAction SilentlyContinue
        $script:CKPT_FILE = "$NO_BM25_LOG/.pipeline_ckpt"
        if (-not (Test-Path $script:CKPT_FILE)) { New-Item -ItemType File -Path $script:CKPT_FILE | Out-Null }
        foreach ($s in 2..4) { Mark-Done $s }
    }

    if (-not (Test-Path "$NO_QOC_LOG/final_schema_prompts") -and (Test-Path "$FULL_LOG/final_schema_prompts")) {
        Write-Host "Copying Stages 2-7 from $FULL_LOG for w/o QOC..."
        New-Item -ItemType Directory -Force -Path $NO_QOC_LOG | Out-Null
        @("initial_candidates.json","unfilled_pre_rule.json","filled_pre_rule.json","unfilled_schema.json","filled_schema.json") | ForEach-Object {
            Copy-Item "$FULL_LOG/$_" "$NO_QOC_LOG/" -Force -ErrorAction SilentlyContinue
        }
        @("cache","status","schema_prompts","candidates","final_schema_prompts") | ForEach-Object {
            Copy-Item "$FULL_LOG/$_" "$NO_QOC_LOG/" -Recurse -Force -ErrorAction SilentlyContinue
        }
        @("initial_candidates.json","unfilled_pre_rule.json","filled_pre_rule.json","unfilled_schema.json","filled_schema.json") | ForEach-Object {
            Copy-Item "$FULL_LOG/$_" "$NO_QOC_LOG/" -Force -ErrorAction SilentlyContinue
        }
        $script:CKPT_FILE = "$NO_QOC_LOG/.pipeline_ckpt"
        foreach ($s in 2..7) { Mark-Done $s }
    }
}

Run-Variant "no_itee" $NO_ITEE_LOG "--no_itee" "" ""
Run-Variant "no_rbp" $NO_RBP_LOG "--no_rbp" "" ""
Run-Variant "no_bm25" $NO_BM25_LOG "" "--no_bm25" "--no_bm25"
Run-Variant "no_qoc" $NO_QOC_LOG "" "" "--no_qoc"

Write-Host ""
Write-Host "=== Generating Ablation 1 Report ==="
python generate_ablation_report.py `
    --ablation_type component_dropout `
    --data_file $DATA_FILE `
    --task $TASK `
    --variants `
        "Full SlayQL:$FULL_LOG" `
        "w/o IT-EE (Always loops):$NO_ITEE_LOG" `
        "w/o RBP (No graph joins):$NO_RBP_LOG" `
        "w/o BM25 Grounding:$NO_BM25_LOG" `
        "w/o QOC (Strict Outputs):$NO_QOC_LOG" `
    --output_path "ablation1_component_dropout_report.md"

Write-Host ""
Write-Host "Ablation Study 1 Complete!"
Write-Host "Report: ablation1_component_dropout_report.md"

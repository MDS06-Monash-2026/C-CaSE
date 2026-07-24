# Re-run stages 8-12 for failed ablation variants (no_itee, no_qoc)
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
$TASK = "r1_lite"
$NUM_CANDIDATES = 5

function Reset-Stages([string]$LogDir, [int[]]$FromStage) {
    $ckpt = "$LogDir/.pipeline_ckpt"
    if (Test-Path $ckpt) {
        $lines = Get-Content $ckpt | Where-Object { $_ -notmatch "^STAGE_($($FromStage -join '|'))=" }
        Set-Content $ckpt $lines -Encoding utf8
    }
    Remove-Item "$LogDir/eval_result.txt" -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir/sql_gen" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir/sql_revise" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir/sql_selection" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "$LogDir/sql_selection_v1" -Recurse -Force -ErrorAction SilentlyContinue
}

function Copy-FullStages([string]$Target, [int]$UpToStage) {
    Write-Host "Refreshing $Target from $FULL_LOG (stages 2-$UpToStage)..."
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    @("initial_candidates.json","unfilled_pre_rule.json","filled_pre_rule.json","unfilled_schema.json","filled_schema.json") | ForEach-Object {
        Copy-Item "$FULL_LOG/$_" "$Target/" -Force -ErrorAction SilentlyContinue
    }
    @("cache","status","schema_prompts","candidates","final_schema_prompts") | ForEach-Object {
        Copy-Item "$FULL_LOG/$_" "$Target/" -Recurse -Force -ErrorAction SilentlyContinue
    }
    $script:CKPT_FILE = "$Target/.pipeline_ckpt"
    Set-Content $script:CKPT_FILE "" -Encoding utf8
    for ($s = 2; $s -le $UpToStage; $s++) { Add-Content $script:CKPT_FILE "STAGE_${s}=done" }
}

function Run-Stages812([string]$LogDir, [string]$SqlGenExtra = "") {
    $SchemaDir = "$LogDir/final_schema_prompts"
    Write-Host "`n=== Running stages 8-12 for $LogDir ==="

    if ($SqlGenExtra) {
        Invoke-Expression "python sql_generation.py --num_workers 32 --num_candidates $NUM_CANDIDATES --data_file `"$DATA_FILE`" --schema_dir `"$SchemaDir`" --log_path `"$LogDir`" --task `"$TASK`" $SqlGenExtra"
    } else {
        python sql_generation.py --num_workers 32 --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
    }

    python sql_execution.py --num_workers 4 --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --log_path $LogDir --task $TASK
    python sql_revise.py --num_workers 8 --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --schema_dir $SchemaDir --log_path $LogDir --task $TASK
    python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES --workers 32 --task $TASK --data_file $DATA_FILE

    Push-Location ../evaluation_suite
    python evaluate.py --mode exec_result --result_dir "../run/$LogDir/sql_selection/final" --gold_dir gold --data_file "../run/$DATA_FILE" 2>&1 |
        Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
    Pop-Location
    python parse_tokens.py --log_path $LogDir --data_file $DATA_FILE 2>&1 |
        Out-File -FilePath "$LogDir/eval_result.txt" -Encoding utf8 -Append

    Get-Content "$LogDir/eval_result.txt" -Encoding utf8 | Select-String "Results:|Evaluating IDs"
}

Reset-Stages "ablation1_no_itee" @(8,9,10,11,12)
Run-Stages812 "ablation1_no_itee"

Copy-FullStages "ablation1_no_qoc" 7
Reset-Stages "ablation1_no_qoc" @(8,9,10,11,12)
Run-Stages812 "ablation1_no_qoc" "--no_qoc"

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
        "w/o QOC (Strict Outputs):ablation1_no_qoc" `
    --output_path "ablation1_component_dropout_report.md"

Write-Host "Done."

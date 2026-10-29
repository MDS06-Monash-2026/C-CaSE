# =============================================================================
# ablation2_scalability.ps1 — Efficiency vs. Query Complexity Ablation (Windows)
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

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--data_file" { $DATA_FILE = $args[++$i] }
        "--top_n" { $TOP_N = [int]$args[++$i] }
        "--num_candidates" { $NUM_CANDIDATES = [int]$args[++$i] }
        "--task" { $TASK = $args[++$i] }
        default { Write-Host "[WARN] Unknown argument: $($args[$i])" }
    }
}

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

function Run-Pipeline([string]$System, [string]$Bucket) {
    $BucketFile = "ablation2_${Bucket}_queries.json"
    $LogDir = "ablation2_${System}_${Bucket}"
    $SchemaDir = "$LogDir/final_schema_prompts"

    if (-not (Test-Path $BucketFile)) {
        Write-Host "[SKIP] $BucketFile not found"
        return
    }

    $bucketData = Get-Content $BucketFile -Raw | ConvertFrom-Json
    $N = ($bucketData.PSObject.Properties | Measure-Object).Count
    if ($N -eq 0) {
        Write-Host "[SKIP] Empty bucket ${Bucket} for ${System}"
        return
    }

    $script:CKPT_FILE = "$LogDir/.pipeline_ckpt"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    if (-not (Test-Path $script:CKPT_FILE)) { New-Item -ItemType File -Path $script:CKPT_FILE | Out-Null }

    Write-Host ""
    Write-Host "── $($System.ToUpper()) / $($Bucket.ToUpper()) ($N queries) ──"
    Write-Host "   Log: $LogDir"

    if ($System -eq "slayql") {
        if (Should-Skip 1) { Write-Host "  [1] BM25 index          skip" }
        else { python build_value_indices.py --data_file $BucketFile; Mark-Done 1 }

        if (Test-Path "$LogDir/initial_candidates.json") { Write-Host "  [2] Schema retrieval    skip"; Mark-Done 2 }
        else { python retrieve_topk_schema.py --log_path $LogDir --top_n $TOP_N --data_file $BucketFile; Mark-Done 2 }

        if (Test-Path "$LogDir/filled_pre_rule.json") { Write-Host "  [3] ID injection        skip"; Mark-Done 3 }
        else { python add_id.py --log_path $LogDir --data_file $BucketFile; Mark-Done 3 }

        $initCount = if (Test-Path "$LogDir/schema_prompts") { (Get-ChildItem "$LogDir/schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
        if ($initCount -gt 0) { Write-Host "  [4] Initial prompts     skip ($initCount)"; Mark-Done 4 }
        else { python generate_schema.py --log_path $LogDir --is_initial --data_file $BucketFile; Mark-Done 4 }

        $candCount = if (Test-Path "$LogDir/candidates") { (Get-ChildItem "$LogDir/candidates" -File -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
        Write-Host "  [5] Schema completion   resuming ($candCount cached)"
        python complete_schema.py --log_path $LogDir --data_file $BucketFile
        Mark-Done 5

        if (Test-Path "$LogDir/filled_schema.json") { Write-Host "  [6] Postprocess         skip"; Mark-Done 6 }
        else { python postprocess.py --log_path $LogDir; Mark-Done 6 }

        $finalCount = if (Test-Path "$LogDir/final_schema_prompts") { (Get-ChildItem "$LogDir/final_schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
        if ($finalCount -gt 0) { Write-Host "  [7] Final prompts       skip ($finalCount)"; Mark-Done 7 }
        else { python generate_schema.py --log_path $LogDir --data_file $BucketFile; Mark-Done 7 }

        if (Should-Skip 8) { Write-Host "  [8] SQL generation      skip" }
        else {
            python sql_generation.py --num_workers $NUM_GEN_WORKERS --num_candidates $NUM_CANDIDATES `
                --data_file $BucketFile --schema_dir $SchemaDir --log_path $LogDir --task $TASK
            Mark-Done 8
        }

        if (Should-Skip 9) { Write-Host "  [9] SQL execution       skip" }
        else {
            python sql_execution.py --num_workers $NUM_EXEC_WORKERS --num_candidates $NUM_CANDIDATES `
                --data_file $BucketFile --log_path $LogDir --task $TASK
            Mark-Done 9
        }

        if (Should-Skip 10) { Write-Host "  [10] SQL revision       skip" }
        else {
            python sql_revise.py --num_workers $NUM_REVISE_WORKERS --num_candidates $NUM_CANDIDATES `
                --data_file $BucketFile --schema_dir $SchemaDir --log_path $LogDir --task $TASK
            Mark-Done 10
        }

        if ((Test-Path "$LogDir/sql_selection_v1/final") -or (Test-Path "$LogDir/sql_selection/final")) {
            Write-Host "  [11] SQL selection      skip"
            Mark-Done 11
        } else {
            python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES `
                --workers $NUM_SELECTION_WORKERS --task $TASK --data_file $BucketFile
            Mark-Done 11
        }
    } else {
        if (Test-Path "$LogDir/pre_rule.json") { Write-Host "  [3] ID injection        skip"; Mark-Done 3 }
        else { python _baseline/add_id.py --log_path $LogDir --data_file $BucketFile; Mark-Done 3 }

        $initCount = if (Test-Path "$LogDir/schema_prompts") { (Get-ChildItem "$LogDir/schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
        if ($initCount -gt 0) { Write-Host "  [4] Initial prompts     skip"; Mark-Done 4 }
        else { python _baseline/generate_schema.py --log_path $LogDir --is_initial --data_file $BucketFile; Mark-Done 4 }

        $candCount = if (Test-Path "$LogDir/candidates") { (Get-ChildItem "$LogDir/candidates" -File -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
        Write-Host "  [5] Schema completion   resuming ($candCount cached)"
        python _baseline/complete_schema.py --log_path $LogDir --data_file $BucketFile
        Mark-Done 5

        if (Test-Path "$LogDir/filled_schema.json") { Write-Host "  [6] Postprocess         skip"; Mark-Done 6 }
        else { python postprocess.py --log_path $LogDir; Mark-Done 6 }

        $finalCount = if (Test-Path "$LogDir/final_schema_prompts") { (Get-ChildItem "$LogDir/final_schema_prompts" -ErrorAction SilentlyContinue | Measure-Object).Count } else { 0 }
        if ($finalCount -gt 0) { Write-Host "  [7] Final prompts       skip"; Mark-Done 7 }
        else { python _baseline/generate_schema.py --log_path $LogDir --data_file $BucketFile; Mark-Done 7 }

        if (Should-Skip 8) { Write-Host "  [8] SQL generation      skip" }
        else {
            python _baseline/sql_generation.py --num_workers $NUM_GEN_WORKERS --num_candidates $NUM_CANDIDATES `
                --data_file $BucketFile --schema_dir $SchemaDir --log_path $LogDir --task $TASK
            Mark-Done 8
        }

        if (Should-Skip 9) { Write-Host "  [9] SQL execution       skip" }
        else {
            python sql_execution.py --num_workers $NUM_EXEC_WORKERS --num_candidates $NUM_CANDIDATES `
                --data_file $BucketFile --log_path $LogDir --task $TASK
            Mark-Done 9
        }

        if (Should-Skip 10) { Write-Host "  [10] SQL revision       skip" }
        else {
            python sql_revise.py --num_workers $NUM_REVISE_WORKERS --num_candidates $NUM_CANDIDATES `
                --data_file $BucketFile --schema_dir $SchemaDir --log_path $LogDir --task $TASK
            Mark-Done 10
        }

        if ((Should-Skip 11) -or (Test-Path "$LogDir/sql_selection/final")) { Write-Host "  [11] SQL selection      skip"; Mark-Done 11 }
        else {
            python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES `
                --workers $NUM_SELECTION_WORKERS --task $TASK --data_file $BucketFile
            Mark-Done 11
        }
    }

    if ((Should-Skip 12) -and (Test-Path "$LogDir/eval_result.txt")) {
        Write-Host "  [12] Evaluate           skip"
        Mark-Done 12
    } else {
        Push-Location ../evaluation_suite
        if (Test-Path "../run/$LogDir/sql_selection_v1/final") {
            $ResultDir = "../run/$LogDir/sql_selection_v1/final"
        } else {
            $ResultDir = "../run/$LogDir/sql_selection/final"
        }
        if (Test-Path $ResultDir) {
            python evaluate.py --mode exec_result --result_dir $ResultDir `
                --gold_dir gold --data_file "../run/$BucketFile" 2>&1 |
                Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
        }
        Pop-Location
        python parse_tokens.py --log_path $LogDir --data_file $BucketFile 2>&1 |
            Out-File -FilePath "$LogDir/eval_result.txt" -Encoding utf8 -Append
        Mark-Done 12
    }

    $done = if (Test-Path $script:CKPT_FILE) { (Select-String -Path $script:CKPT_FILE -Pattern "=done").Count } else { 0 }
    Write-Host "  Done ${System}/${Bucket} ($done/12 stages)"
}

Write-Host ""
Write-Host "ABLATION STUDY 2: Scalability - Token vs. Complexity"
Write-Host ""

$SPLIT_CKPT = "ablation2_split.ckpt"
if ((Test-Path $SPLIT_CKPT) -and (Select-String -Path $SPLIT_CKPT -Pattern "split_done" -Quiet)) {
    Write-Host "=== Complexity split - SKIPPED (buckets exist) ==="
    foreach ($b in @("easy", "medium", "hard")) {
        $bf = "ablation2_${b}_queries.json"
        if (Test-Path $bf) {
            $cnt = (Get-Content $bf -Raw | ConvertFrom-Json).PSObject.Properties.Count
            Write-Host "  $bf -> $cnt queries"
        }
    }
} else {
    Write-Host "=== Splitting queries into Easy / Medium / Hard ==="
    python -c @"
import json, sys
sys.path.insert(0, '.')
from it_ee import analyze_complexity

data_file = '$DATA_FILE'
with open(data_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

easy, medium, hard = {}, {}, {}
for iid, info in data.items():
    c = analyze_complexity(info.get('question', ''))
    n = sum([c['has_temporal'], c['has_aggregation'], c['has_structural']])
    if n == 0:
        easy[iid] = info
    elif n == 1:
        medium[iid] = info
    else:
        hard[iid] = info

print(f'Easy: {len(easy)}  Medium: {len(medium)}  Hard: {len(hard)}')
for name, bucket in [('easy', easy), ('medium', medium), ('hard', hard)]:
    with open(f'ablation2_{name}_queries.json', 'w', encoding='utf-8') as f:
        json.dump(bucket, f, ensure_ascii=False, indent=2)
    print(f'Saved {len(bucket)} -> ablation2_{name}_queries.json')
"@
    Add-Content -Path $SPLIT_CKPT -Value "split_done"
}

foreach ($bucket in @("easy", "medium", "hard")) {
    Run-Pipeline "slayql" $bucket
    Run-Pipeline "autolink" $bucket
}

Write-Host ""
Write-Host "=== Generating Ablation 2 Report ==="
python generate_ablation_report.py `
    --ablation_type scalability `
    --data_file $DATA_FILE `
    --task $TASK `
    --variants `
        "SlayQL Easy:ablation2_slayql_easy" `
        "SlayQL Medium:ablation2_slayql_medium" `
        "SlayQL Hard:ablation2_slayql_hard" `
        "AutoLink Easy:ablation2_autolink_easy" `
        "AutoLink Medium:ablation2_autolink_medium" `
        "AutoLink Hard:ablation2_autolink_hard" `
    --bucket_files `
        "ablation2_easy_queries.json" `
        "ablation2_medium_queries.json" `
        "ablation2_hard_queries.json" `
    --output_path "ablation2_scalability_report.md"

Write-Host ""
Write-Host "Ablation Study 2 Complete!"
Write-Host "Report: ablation2_scalability_report.md"

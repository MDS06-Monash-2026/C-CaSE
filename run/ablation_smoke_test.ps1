# Quick smoke test for ablation SQL pipeline fix (2 local instances)
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

$DATA_FILE = "subset_4_evaluation.json"
$SOURCE = "log_subset_diverse_20_evaluation_slayql_ccase"
$INSTANCES = @("bq004", "bq008")
$TASK = "r1_lite"
$NUM_CANDIDATES = 1

function Setup-SmokeDir([string]$LogDir, [string]$ExtraSqlGenArgs) {
    if (Test-Path $LogDir) { Remove-Item $LogDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path "$LogDir/final_schema_prompts" | Out-Null
    foreach ($id in $INSTANCES) {
        Copy-Item "$SOURCE/final_schema_prompts/$id.txt" "$LogDir/final_schema_prompts/" -Force
    }

    Write-Host "`n=== Smoke test: $LogDir ($ExtraSqlGenArgs) ==="

    if ($ExtraSqlGenArgs) {
        Invoke-Expression "python sql_generation.py --num_workers 2 --num_candidates $NUM_CANDIDATES --data_file `"$DATA_FILE`" --schema_dir `"$LogDir/final_schema_prompts`" --log_path `"$LogDir`" --task `"$TASK`" $ExtraSqlGenArgs"
    } else {
        python sql_generation.py --num_workers 2 --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --schema_dir "$LogDir/final_schema_prompts" --log_path $LogDir --task $TASK
    }

    $flatSql = (Get-ChildItem "$LogDir/sql_gen/${TASK}_sql_0" -Filter "*.sql" -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "Flat .sql files: $flatSql / $($INSTANCES.Count)"
    if ($flatSql -lt $INSTANCES.Count) { throw "sql_clean fix FAILED: expected flat .sql files" }

    python sql_execution.py --num_workers 2 --num_candidates $NUM_CANDIDATES --data_file $DATA_FILE --log_path $LogDir --task $TASK

    $csv = (Get-ChildItem "$LogDir/sql_gen/${TASK}_execution_result_0" -Filter "*.csv" -File -ErrorAction SilentlyContinue | Measure-Object).Count
    $err = (Get-ChildItem "$LogDir/sql_gen/${TASK}_execution_error_0" -Filter "*.txt" -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "Execution csv=$csv errors=$err"

    python sql_selection.py --log_path $LogDir --num_candidates $NUM_CANDIDATES --workers 2 --task $TASK --data_file $DATA_FILE

    $resultCsv = (Get-ChildItem "$LogDir/sql_selection/final" -Recurse -Filter "result.csv" -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "Selection result.csv: $resultCsv"
    if ($flatSql -lt $INSTANCES.Count) { throw "sql_clean fix FAILED" }
    if ($csv + $err -lt $INSTANCES.Count) { throw "sql_execution did not process all instances" }
    Write-Host "PASS: flat sql + execution pipeline OK for $LogDir"

    Push-Location ../evaluation_suite
    python evaluate.py --mode exec_result --result_dir "../run/$LogDir/sql_selection/final" --gold_dir gold --data_file "../run/$DATA_FILE" 2>&1 |
        Out-File -FilePath "../run/$LogDir/eval_result.txt" -Encoding utf8
    Pop-Location
    Get-Content "$LogDir/eval_result.txt" -Encoding utf8 | Select-String "Results:|Evaluating IDs"
}

Setup-SmokeDir "ablation_smoke_no_itee" ""
Setup-SmokeDir "ablation_smoke_no_qoc" "--no_qoc"

Write-Host "`nSMOKE TEST PASSED"

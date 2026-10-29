param(
    [ValidateSet("bm25", "topn", "candidates", "rbp", "itee", "selector", "hintcap", "all")][string]$Study = "bm25",
    [ValidateSet("smoke", "backend-smoke", "subset20", "full")][string]$Mode = "smoke",
    [ValidateSet("spider2-lite", "spider1", "bird")][string]$Dataset = "spider2-lite",
    [ValidateSet("dev", "train", "test")][string]$Split = "dev",
    [string]$BirdRoot,
    [int]$Seed = 20260813,
    [int]$Workers = 4
)

$ErrorActionPreference = "Stop"
$RunDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModeOrder = @("smoke", "backend-smoke", "subset20", "full")
$GateModes = $ModeOrder
$TargetIndex = [Array]::IndexOf($GateModes, $Mode)
if ($TargetIndex -lt 0) { throw "Mode $Mode is not applicable to dataset $Dataset in the ablation gate chain" }

function Invoke-Variant([string]$Label, [hashtable]$Environment, [int]$NumCandidates = 5) {
    $old = @{}
    foreach ($key in $Environment.Keys) {
        $old[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], "Process")
    }
    try {
        foreach ($GateMode in $GateModes[0..$TargetIndex]) {
            $runId = "ablation_${Dataset}_${Study}_${Label}_${GateMode}"
            $common = @("--dataset", $Dataset, "--split", $Split, "--mode", $GateMode,
                        "--run-id", $runId, "--seed", $Seed, "--workers", $Workers,
                        "--num-candidates", $NumCandidates)
            if ($BirdRoot) { $common += @("--bird-root", $BirdRoot) }
            python "$RunDir/dataset_pipeline.py" run @common
            if ($LASTEXITCODE -ne 0) { throw "Ablation variant failed: $Label / $GateMode" }
            $manifest = @{
                schema_version = "1.0"; study = $Study; label = $Label; dataset = $Dataset
                split = $Split; mode = $GateMode; seed = $Seed; num_candidates = $NumCandidates
                environment = $Environment; run_id = $runId
            }
            $manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$RunDir/$runId/ablation_manifest.json"
        }
    } finally {
        foreach ($key in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $old[$key], "Process")
        }
    }
}

if ($Study -in @("bm25", "all")) {
    Invoke-Variant "bm25_raw_5_0" @{ ABLATION_NO_BM25 = "0"; SLAYQL_BM25_NORMALIZED = "0"; SLAYQL_BM25_THRESHOLD = "5.0" }
    Invoke-Variant "bm25_disabled" @{ ABLATION_NO_BM25 = "1" }
    foreach ($threshold in @("0.10", "0.20", "0.30", "0.40", "0.50")) {
        Invoke-Variant ("bm25_" + ($threshold -replace '\.', '_')) @{
            ABLATION_NO_BM25 = "0"; SLAYQL_BM25_NORMALIZED = "1"; SLAYQL_BM25_THRESHOLD = $threshold
        }
    }
}
if ($Study -in @("topn", "all")) {
    foreach ($value in @(50, 75, 100, 125)) { Invoke-Variant "topn_$value" @{ SLAYQL_TOP_N = "$value" } }
}
if ($Study -in @("candidates", "all")) {
    foreach ($value in @(3, 5, 7)) { Invoke-Variant "candidates_$value" @{} $value }
}
if ($Study -in @("rbp", "all")) {
    foreach ($value in @("0.5", "0.7", "0.9")) {
        Invoke-Variant ("rbp_" + ($value -replace '\.', '_')) @{ ABLATION_RBP_ALPHA = $value }
    }
}
if ($Study -in @("itee", "all")) {
    foreach ($value in @("0.3", "0.4", "0.5")) {
        Invoke-Variant ("itee_" + ($value -replace '\.', '_')) @{ ABLATION_ITEE_THRESHOLD = $value }
    }
}
if ($Study -in @("selector", "all")) {
    foreach ($value in @("0.00", "0.05", "0.10", "0.20", "0.30")) {
        Invoke-Variant ("selector_" + ($value -replace '\.', '_')) @{
            SLAYQL_SELECTOR_MARGIN = $value; SLAYQL_SELECTOR_VERIFY = "1"
        }
    }
}
if ($Study -in @("hintcap", "all")) {
    foreach ($value in @(1, 3, 5)) { Invoke-Variant "hintcap_$value" @{ SLAYQL_VALUE_HINT_CAP = "$value" } }
}

python "$RunDir/summarize_ablation.py" --run-root $RunDir --dataset $Dataset --study $Study --mode $Mode
if ($LASTEXITCODE -ne 0) { throw "Ablation summary generation failed" }

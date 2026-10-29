param(
    [ValidateSet("prepare", "run")][string]$Command = "run",
    [ValidateSet("bird", "spider1", "spider1.0", "spider2", "spider2-lite")][string]$Dataset,
    [ValidateSet("dev", "train", "test")][string]$Split = "dev",
    [ValidateSet("smoke", "backend-smoke", "subset20", "full")][string]$Mode = "smoke",
    [string]$BirdRoot,
    [string]$RunId,
    [int]$Seed = 20260813,
    [ValidateRange(1, 1000)][int]$SmokeCount = 5,
    [ValidateSet("snowflake", "bigquery", "sqlite")][string[]]$ExcludeBackend = @(),
    [int]$NumCandidates = 5,
    [int]$Workers = 4,
    [switch]$EnforceGates
)

$ErrorActionPreference = "Stop"
$RunDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Dataset) {
    Write-Host "Choose one standalone dataset/run-size combination:"
    Write-Host "  1. BIRD - smoke (5 instances)"
    Write-Host "  2. BIRD - subset20"
    Write-Host "  3. BIRD - full"
    Write-Host "  4. Spider 1.0 - smoke (5 instances)"
    Write-Host "  5. Spider 1.0 - subset20"
    Write-Host "  6. Spider 1.0 - full"
    Write-Host "  7. Spider 2.0-Lite - smoke (5 instances)"
    Write-Host "  8. Spider 2.0-Lite - subset20"
    Write-Host "  9. Spider 2.0-Lite - full"
    $choice = Read-Host "Selection"
    $selection = switch ($choice) {
        "1" { @("bird", "smoke") }
        "2" { @("bird", "subset20") }
        "3" { @("bird", "full") }
        "4" { @("spider1", "smoke") }
        "5" { @("spider1", "subset20") }
        "6" { @("spider1", "full") }
        "7" { @("spider2-lite", "smoke") }
        "8" { @("spider2-lite", "subset20") }
        "9" { @("spider2-lite", "full") }
        default { throw "Unknown dataset selection: $choice" }
    }
    $Dataset = $selection[0]
    $Mode = $selection[1]
}
$PipelineArgs = @("$RunDir/dataset_pipeline.py", $Command, "--dataset", $Dataset, "--split", $Split, "--mode", $Mode, "--seed", $Seed, "--smoke-count", $SmokeCount, "--num-candidates", $NumCandidates, "--workers", $Workers)
foreach ($Backend in $ExcludeBackend) { $PipelineArgs += @("--exclude-backend", $Backend) }
if ($BirdRoot) { $PipelineArgs += @("--bird-root", $BirdRoot) }
if ($RunId) { $PipelineArgs += @("--run-id", $RunId) }
if ($EnforceGates) { $PipelineArgs += "--enforce-gates" }
python @PipelineArgs

param(
    [ValidateSet("prepare", "run")][string]$Command = "run",
    [ValidateSet("bird", "spider1", "spider1.0", "spider2", "spider2-lite")][string]$Dataset,
    [ValidateSet("dev", "train", "test")][string]$Split = "dev",
    [ValidateSet("smoke", "subset20", "full")][string]$Mode = "subset20",
    [string]$BirdRoot,
    [string]$RunId,
    [int]$Seed = 20260813,
    [ValidateRange(1, 1000)][int]$SmokeCount = 5,
    [ValidateSet("snowflake", "bigquery", "sqlite")][string[]]$ExcludeBackend = @(),
    [switch]$AllowSnowflake,
    [int]$NumCandidates = 0,
    [int]$Workers = 4,
    [string]$ReferenceEvaluation,
    [ValidateRange(0.0, 1.0)][double]$TargetAccuracy = -1,
    [switch]$SkipSubsetGate,
    [ValidateRange(512, 100000)][int]$MaxInteractionChars = 12000,
    [string]$DemonstrationFile,
    [ValidateRange(1, 5)][int]$DemonstrationCount = 2
)

$ErrorActionPreference = "Stop"
$RunDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Dataset) {
    throw "-Dataset is required. Use bird, spider1, or spider2-lite."
}

$PipelineArgs = @(
    "$RunDir/research_suite_v18.py", $Command,
    "--dataset", $Dataset, "--split", $Split, "--mode", $Mode,
    "--seed", $Seed, "--smoke-count", $SmokeCount,
    "--num-candidates", $NumCandidates, "--workers", $Workers,
    "--max-interaction-chars", $MaxInteractionChars,
    "--demonstration-count", $DemonstrationCount
)
if ($BirdRoot) { $PipelineArgs += @("--bird-root", $BirdRoot) }
if ($RunId) { $PipelineArgs += @("--run-id", $RunId) }
foreach ($Backend in $ExcludeBackend) { $PipelineArgs += @("--exclude-backend", $Backend) }
if ($AllowSnowflake) { $PipelineArgs += "--allow-snowflake" }
if ($ReferenceEvaluation) { $PipelineArgs += @("--reference-evaluation", $ReferenceEvaluation) }
if ($TargetAccuracy -ge 0) { $PipelineArgs += @("--target-accuracy", $TargetAccuracy) }
if ($SkipSubsetGate) { $PipelineArgs += "--skip-subset-gate" }
if ($DemonstrationFile) { $PipelineArgs += @("--demonstration-file", $DemonstrationFile) }

python @PipelineArgs
if ($LASTEXITCODE -ne 0) { throw "SlayQL v1.8 research suite failed" }

<#
.SYNOPSIS
  Runs the SlayQL v1.8 BIRD experiments for the ARR October 2026 paper, then the analysis.

.DESCRIPTION
  Each variant is one full pipeline run of research_suite_v18.py with an experiment switch set
  through environment variables. Runs are resumable: rerunning the same command resumes
  unfinished runs from their checkpoints and skips finished ones (use -Force to rerun).

  Before anything runs, the preflight check (python -m pub.preflight) must pass. Every run
  folder records a fingerprint of the pipeline code so results from different machines can be
  checked for drift.

  Smoke mode runs a few questions per variant (a few cents) to check that every switch works.
  Full mode runs all 1,534 BIRD dev questions per variant.

  Works in Windows PowerShell 5.1 and PowerShell 7 (Windows, macOS, Linux).

.EXAMPLE
  .\pub_run_all.ps1 -Mode smoke                  # check all variants on 2 questions each
  .\pub_run_all.ps1 -Mode full -Parallel 2 -CompletionProcesses 6   # recommended full run
  .\pub_run_all.ps1 -Mode full -Variants ref,topn20                 # only some variants
  .\pub_run_all.ps1 -Mode full -DryRun           # show what would run
#>
param(
    [ValidateSet("smoke", "full")][string]$Mode = "smoke",
    [string[]]$Variants = @(),
    [switch]$IncludeOptional,
    [int]$SmokeCount = 2,
    [ValidateRange(1, 3)][int]$Parallel = 1,
    [int]$StaggerMinutes = 20,
    [int]$Workers = 4,
    [ValidateRange(1, 12)][int]$CompletionProcesses = 3,
    [ValidateRange(60, 600)][int]$ApiTimeoutSeconds = 300,
    [int]$NumCandidates = 1,
    [string]$BirdRoot = "",
    [string]$Python = "",
    [switch]$NoAnalysis,
    [switch]$SkipPreflight,
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RunDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $RunDir
$OnWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
if (-not $Python) {
    $Python = if ($OnWindows) { Join-Path $RepoRoot ".venv\Scripts\python.exe" } else { Join-Path $RepoRoot ".venv/bin/python" }
}
if (-not (Test-Path $Python)) { throw "Python environment not found at $Python. Run .\pub_setup.ps1 first (see TEAMMATE_QUICKSTART.md)." }

# Paths passed to Python are relative to run/ and use forward slashes, so folders with spaces
# (for example "C-CaSE (1)") never need quoting on any PowerShell version.
if ($BirdRoot) {
    $BirdArg = if ($BirdRoot.Contains(" ")) { if ($OnWindows) { "`"$BirdRoot`"" } else { $BirdRoot } } else { $BirdRoot }
    $BirdCheck = $BirdRoot
} else {
    $BirdArg = "../dev/dev_20240627"
    $BirdCheck = Join-Path $RepoRoot "dev/dev_20240627"
}
if (-not (Test-Path (Join-Path $BirdCheck "dev.json"))) { throw "BIRD dev not found at $BirdCheck (expected dev.json). Run .\pub_setup.ps1." }
$DemoArg = "pub_inputs/bird_train_demos_from_v18.json"
$LogDir = Join-Path $RunDir "logs_pub"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$StatusFile = Join-Path $LogDir "status.csv"

# ---------------------------------------------------------------------------
# Experiment definitions (plan section 9.4). Order = priority.
# To add an experiment: add one line here with its environment switch.
# ---------------------------------------------------------------------------
$Definitions = [ordered]@{
    "ref"       = @{ Env = @{};                                   Note = "R1 reference" }
    "topn20"    = @{ Env = @{ SLAYQL_TOP_N = "20" };              Note = "R6 retrieval budget 20 columns" }
    "no_rbp"    = @{ Env = @{ ABLATION_NO_RBP = "1" };            Note = "R2 without RBP" }
    "no_bm25"   = @{ Env = @{ ABLATION_NO_BM25 = "1" };           Note = "R4 without BM25 value grounding" }
    "itee_max"  = @{ Env = @{ ABLATION_ITEE_THRESHOLD = "1.01" }; Note = "R9 IT-EE threshold 1.01 (maximum early exit)" }
    "topn50"    = @{ Env = @{ SLAYQL_TOP_N = "50" };              Note = "R7 retrieval budget 50 columns" }
    "no_qoc"    = @{ Env = @{ ABLATION_NO_QOC = "1" };            Note = "R5 without QOC" }
    "topn10000" = @{ Env = @{ SLAYQL_TOP_N = "10000" };           Note = "R10 retrieval unpruned (optional)" }
}
$CoreVariants = @("ref", "topn20", "no_rbp", "no_bm25", "itee_max", "topn50", "no_qoc")
$OptionalVariants = @("topn10000")
$ExperimentKeys = @("ABLATION_NO_RBP", "ABLATION_NO_ITEE", "ABLATION_NO_BM25", "ABLATION_NO_QOC",
                    "ABLATION_ITEE_THRESHOLD", "ABLATION_RBP_ALPHA", "SLAYQL_TOP_N")

# Accept "a,b" as one string too (powershell -File does not split comma lists).
$Variants = @($Variants | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($Variants.Count -eq 0) {
    $Variants = $CoreVariants
    if ($IncludeOptional) { $Variants += $OptionalVariants }
}
foreach ($name in $Variants) {
    if (-not $Definitions.Contains($name)) { throw "Unknown variant '$name'. Known: $($Definitions.Keys -join ', ')" }
}

# Never inherit experiment switches from the calling shell.
foreach ($key in $ExperimentKeys) { Remove-Item "Env:$key" -ErrorAction SilentlyContinue }
$env:SLAYQL_NONINTERACTIVE = "1"
$env:SLAYQL_COMPLETION_PROCESSES = "$CompletionProcesses"   # schema-completion parallelism (speed only)
# Per-request API timeout. A dropped connection otherwise blocks a worker for up to 3 x 600 s.
# In the v1.8 full run 20 of 14,497 calls took longer than 300 s; those are retried instead.
$env:SLAYQL_API_TIMEOUT = "$ApiTimeoutSeconds"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

# The run name records the candidate count, so k=1 and k=5 runs never share a folder.
$Prefix = if ($Mode -eq "full") { "bird_dev_v18_k${NumCandidates}_" } else { "smoke_v18_k${NumCandidates}_" }

function Get-RunId([string]$name) { return "$Prefix$name" }

function Test-RunComplete([string]$runId) {
    $root = Join-Path $RunDir $runId
    return (Test-Path (Join-Path $root "aggregates/summary_metrics.json")) -and (Test-Path (Join-Path $root "research_summary.json"))
}

function Get-Arguments([string]$runId) {
    $arguments = @("research_suite_v18.py", "run", "--dataset", "bird", "--split", "dev", "--mode", $Mode,
                   "--bird-root", $BirdArg, "--run-id", $runId,
                   "--num-candidates", "$NumCandidates", "--workers", "$Workers",
                   "--demonstration-file", $DemoArg, "--demonstration-count", "2")
    if ($Mode -eq "full") { $arguments += "--skip-subset-gate" }
    if ($Mode -eq "smoke") { $arguments += @("--smoke-count", "$SmokeCount") }
    return $arguments
}

function Write-Status([string]$runId, [string]$name, [string]$started, [string]$ended, [string]$exitCode) {
    if (-not (Test-Path $StatusFile)) { "run_id,variant,mode,started,ended,exit_code,host" | Out-File -FilePath $StatusFile -Encoding utf8 }
    "$runId,$name,$Mode,$started,$ended,$exitCode,$([System.Net.Dns]::GetHostName())" | Out-File -FilePath $StatusFile -Encoding utf8 -Append
}

function Start-Variant([string]$name) {
    $runId = Get-RunId $name
    $arguments = Get-Arguments $runId
    $definition = $Definitions[$name]
    $envText = ($definition.Env.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join " "
    Write-Host ("[{0}] START {1} ({2}) {3}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $runId, $definition.Note, $envText)
    if ($DryRun) {
        Write-Host "  $Python $($arguments -join ' ')"
        return $null
    }
    & $Python -m pub.fingerprint --write $runId | Out-Host
    # The child process copies the environment at start, so set, launch, then clear.
    foreach ($entry in $definition.Env.GetEnumerator()) { Set-Item "Env:$($entry.Key)" $entry.Value }
    try {
        $process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $RunDir `
            -RedirectStandardOutput (Join-Path $LogDir "$runId.log") -RedirectStandardError (Join-Path $LogDir "$runId.err.log") `
            -NoNewWindow -PassThru
        $null = $process.Handle  # keep the handle so ExitCode is available after exit
    } finally {
        foreach ($key in $definition.Env.Keys) { Remove-Item "Env:$key" -ErrorAction SilentlyContinue }
    }
    return [pscustomobject]@{ Name = $name; RunId = $runId; Process = $process; Started = (Get-Date -Format "s") }
}

Push-Location $RunDir
try {
    # -----------------------------------------------------------------------
    # Preflight
    # -----------------------------------------------------------------------
    if (-not $SkipPreflight) {
        Write-Host "Preflight check ..."
        & $Python -m pub.preflight
        if ($LASTEXITCODE -ne 0) { throw "Preflight failed. Fix the FAIL items above (or run .\pub_setup.ps1), then rerun." }
    }

    # -----------------------------------------------------------------------
    # Queue
    # -----------------------------------------------------------------------
    $queue = [System.Collections.Generic.Queue[string]]::new()
    foreach ($name in $Variants) {
        $runId = Get-RunId $name
        if ((Test-RunComplete $runId) -and -not $Force) {
            Write-Host "SKIP $runId (already complete; use -Force to rerun)"
            continue
        }
        if ($Force -and (Test-Path (Join-Path $RunDir $runId)) -and -not $DryRun) {
            $backup = Join-Path $RunDir ("{0}_backup_{1}" -f $runId, (Get-Date -Format "yyyyMMdd_HHmmss"))
            Write-Host "Moving existing $runId to $backup"
            Move-Item (Join-Path $RunDir $runId) $backup
        }
        $queue.Enqueue($name)
    }
    Write-Host ("Mode {0}: {1} run(s) queued, parallel {2}, workers {3}, completion processes {4}, k={5}, API timeout {6}s" -f `
        $Mode, $queue.Count, $Parallel, $Workers, $CompletionProcesses, $NumCandidates, $ApiTimeoutSeconds)

    $running = [System.Collections.Generic.List[object]]::new()
    $failed = [System.Collections.Generic.List[string]]::new()
    $lastStart = [datetime]::MinValue
    while ($queue.Count -gt 0 -or $running.Count -gt 0) {
        foreach ($job in @($running)) {
            if ($job.Process.HasExited) {
                $code = $job.Process.ExitCode
                Write-Status $job.RunId $job.Name $job.Started (Get-Date -Format "s") $code
                $state = if ($code -eq 0) { "DONE" } else { "FAILED (exit $code) - see logs_pub/$($job.RunId).err.log; rerun the same command to resume" }
                Write-Host ("[{0}] {1} {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $state, $job.RunId)
                if ($code -ne 0) { $failed.Add($job.RunId) }
                $running.Remove($job) | Out-Null
            }
        }
        $staggerOk = ($running.Count -eq 0) -or (((Get-Date) - $lastStart).TotalMinutes -ge $StaggerMinutes)
        if ($queue.Count -gt 0 -and $running.Count -lt $Parallel -and $staggerOk) {
            $job = Start-Variant $queue.Dequeue()
            if ($null -ne $job) { $running.Add($job); $lastStart = Get-Date }
            continue
        }
        if ($running.Count -gt 0) { Start-Sleep -Seconds 30 }
    }

    if ($DryRun) { return }
    if ($failed.Count -gt 0) { Write-Warning "Failed runs: $($failed -join ', '). Rerun the same command to resume them." }

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------
    if (-not $NoAnalysis) {
        if ($Mode -eq "smoke") {
            $smokeRuns = @($Variants | ForEach-Object { Get-RunId $_ } | Where-Object { Test-Path (Join-Path $RunDir $_) })
            & $Python -m pub.aggregate_runs --runs @smokeRuns --output pub_results_smoke
            & $Python -m pub.stats --results pub_results_smoke --base (Get-RunId "ref") --output-name comparisons
            & $Python -m pub.smoke_check --runs @smokeRuns
        } else {
            & $Python -m pub.run_analysis
            Write-Host "`nTo send results for analysis elsewhere: $Python -m pub.package_results"
        }
    }
} finally {
    Pop-Location
}

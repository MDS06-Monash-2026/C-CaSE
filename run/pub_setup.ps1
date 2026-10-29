<#
.SYNOPSIS
  One-time setup for running the SlayQL publication experiments on a new machine.

.DESCRIPTION
  1. Creates the Python virtual environment in <repo>\.venv (Python 3.10-3.12).
  2. Installs PyTorch (CUDA 12.4 build if an NVIDIA GPU is found, otherwise the CPU build),
     requirements.txt, matplotlib and scipy.
  3. Extracts BIRD dev databases from dev\dev_20240627\dev_databases.zip if needed.
  4. Creates run\.env from run\.env.example if missing (you then add the API key).
  5. Runs the preflight check.

  Works in Windows PowerShell 5.1 and PowerShell 7 (Windows, macOS, Linux).

.EXAMPLE
  .\pub_setup.ps1
  .\pub_setup.ps1 -PythonExe "C:\Python312\python.exe"
  .\pub_setup.ps1 -Cpu            # force the CPU build of PyTorch
#>
param(
    [string]$PythonExe = "",
    [switch]$Cpu,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"
$RunDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $RunDir
$OnWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
$VenvPython = if ($OnWindows) { Join-Path $RepoRoot ".venv\Scripts\python.exe" } else { Join-Path $RepoRoot ".venv/bin/python" }

function Step([string]$text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

# 1. Python and virtual environment -------------------------------------------------------------
Step "Python environment"
if (-not (Test-Path $VenvPython)) {
    if (-not $PythonExe) {
        # Each candidate reports its real interpreter path, so launchers and shims (py.exe,
        # pyenv .bat files) are only used for discovery. No "%" in the probe: .bat shims expand it.
        $candidates = if ($OnWindows) { @("py -3.12", "py -3.11", "py -3.10", "python", "python3") } else { @("python3.12", "python3.11", "python3.10", "python3") }
        $probe = "import sys; print(sys.version_info[0], sys.version_info[1], sys.executable, sep='|')"
        $ErrorActionPreference = "Continue"   # probing commands may write to stderr
        foreach ($candidate in $candidates) {
            try {
                $parts = $candidate.Split(" ")
                $output = & $parts[0] @($parts | Select-Object -Skip 1) -c $probe 2>$null | Select-Object -Last 1
                if ($LASTEXITCODE -eq 0 -and $output -match "^3\|(10|11|12)\|(.+)$") {
                    $PythonExe = $Matches[2].Trim()
                    Write-Host "Found Python 3.$($Matches[1]) via '$candidate': $PythonExe"
                    break
                }
            } catch { }
        }
        $ErrorActionPreference = "Stop"
        if (-not $PythonExe) { throw "Python 3.10-3.12 not found. Install Python 3.12 from python.org, or pass -PythonExe <path to python.exe>." }
    }
    Write-Host "Creating .venv with: $PythonExe"
    & $PythonExe -m venv (Join-Path $RepoRoot ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) { throw "Creating the virtual environment failed" }
} else {
    Write-Host "Using existing $VenvPython"
}
& $VenvPython -m pip install --upgrade pip --quiet

# 2. Packages ----------------------------------------------------------------------------------
Step "Packages"
$hasNvidia = $false
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"   # probing commands may write to stderr
try { $null = & nvidia-smi 2>$null; $hasNvidia = ($LASTEXITCODE -eq 0) } catch { }
& $VenvPython -c "import torch" 2>$null
$torchInstalled = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $previousPreference
if (-not $torchInstalled) {
    if ($hasNvidia -and -not $Cpu) {
        Write-Host "NVIDIA GPU found: installing CUDA 12.4 build of PyTorch (about 2.5 GB)"
        & $VenvPython -m pip install torch --index-url https://download.pytorch.org/whl/cu124
    } elseif ($OnWindows -or -not $IsMacOS) {
        Write-Host "Installing CPU build of PyTorch"
        & $VenvPython -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    } else {
        & $VenvPython -m pip install torch
    }
    if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed" }
} else {
    Write-Host "PyTorch already installed"
}
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt") matplotlib scipy --quiet
if ($LASTEXITCODE -ne 0) { throw "Package installation failed" }

# 3. BIRD dev databases ------------------------------------------------------------------------
Step "BIRD dev databases"
$birdRoot = Join-Path $RepoRoot "dev/dev_20240627"
$dbRoot = Join-Path $birdRoot "dev_databases"
$sqliteCount = if (Test-Path $dbRoot) { @(Get-ChildItem $dbRoot -Recurse -Filter *.sqlite).Count } else { 0 }
if ($sqliteCount -lt 11) {
    $zip = Join-Path $birdRoot "dev_databases.zip"
    if (-not (Test-Path $zip)) { throw "Missing $zip. Copy BIRD dev (dev_20240627) into $birdRoot." }
    Write-Host "Extracting $zip (about 1.4 GB)"
    Expand-Archive -Path $zip -DestinationPath $dbRoot -Force
    $sqliteCount = @(Get-ChildItem $dbRoot -Recurse -Filter *.sqlite).Count
}
Write-Host "$sqliteCount SQLite databases found"

# 4. API key file ------------------------------------------------------------------------------
Step "API key"
$envFile = Join-Path $RunDir ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $RunDir ".env.example") $envFile
    Write-Warning "Created run\.env from the template. Open it and put the OpenRouter key in OPENAI_API_KEY, then rerun this script."
} else {
    Write-Host "run\.env exists"
}

# 5. Preflight ---------------------------------------------------------------------------------
if (-not $SkipPreflight) {
    Step "Preflight"
    Push-Location $RunDir
    try { & $VenvPython -m pub.preflight --api } finally { Pop-Location }
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nSetup complete. Next: .\pub_run_all.ps1 -Mode smoke" -ForegroundColor Green
    } else {
        Write-Warning "Preflight reported failures; fix them and rerun .\pub_setup.ps1"
    }
}

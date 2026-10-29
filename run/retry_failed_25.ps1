# Retry 25 failed instances (error.txt) on full SlayQL log with verbose logging.
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

python retry_failed_25.py `
    --log_path log_spider2_full_slayql `
    --data_file spider2_data.json `
    --task r1_lite `
    --num_workers 8 `
    --selection_workers 8

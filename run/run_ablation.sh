#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec powershell -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/run_ablation.ps1" "$@"

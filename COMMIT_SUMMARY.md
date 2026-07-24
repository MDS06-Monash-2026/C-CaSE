# Git Commit Summary — C-CaSE / SlayQL Updates

**Branch**: `slayql-1`  
**Date**: 2026-07-24  

## Summary of Changes

### 1. Core Pipeline Enhancement & Ablation Control
- **`run/sql_generation.py`**:
  - Added support for `--no_qoc` and `--no_bm25` flags for Ablation Study 1.
  - Implemented logic to strip strict ` ```sql``` ` format instructions from LLM prompts when `--no_qoc` is active.
  - Wired `--no_qoc` and `--no_bm25` into environment variables (`ABLATION_NO_QOC`, `ABLATION_NO_BM25`).
- **`run/complete_schema.py`**:
  - Added support for `--no_bm25` to bypass BM25 value hint injection into schema prompts during dynamic schema completion.
- **`run/retrieve_topk_schema.py`**:
  - Added `--no_rbp` and `--no_itee` command-line flags to enable leave-one-out ablation experiments.
- **`run/sql_selection.py`**:
  - Added `--data_file` parameter support to accept custom evaluation JSON datasets.
  - Handled OpenRouter API `None` response content safely during model voting.
  - Improved robustness in `dump_final_selection` to prevent null-reference crashes when selected SQL output is missing.

### 2. Model & Environment Configuration
- **`run/model_manager.py`**:
  - Configured custom HuggingFace model cache directory path.
- **`.gitignore`**:
  - Added rules to exclude local environment configurations (`run/.env`), log files (`*.log`), temporary ablation output folders (`run/ablation1*`), BM25 indices, and detailed log analysis caches.

### 3. Reports & Benchmark Evaluation
- **`run/comparison_report.md`**:
  - Updated comprehensive execution analysis comparing Baseline AutoLink (39.9% accuracy, 71/178) against SlayQL (40.4% accuracy, 72/178).

### 4. Added Scripts & Tools
- **`run/run_autolink_baseline.ps1` & `run/run_autolink_baseline.sh`**: Entry scripts for executing the baseline AutoLink pipeline on Windows/Linux.
- **`run/ablation2_scalability.sh`**, **`run/ablation3_hyperparameter.sh`**, **`run/ablation4_model_agnostic.sh`**: Automated shell scripts for Ablation Studies 2 (Scalability), 3 (Hyperparameter tuning), and 4 (Model agnosticism).
- **`run/generate_ablation_report.py`**: Unified parser and markdown report generator for ablation study benchmark outputs.
- **`run/_baseline/`**: Backup copies of original baseline scripts.

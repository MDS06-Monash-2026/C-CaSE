# C-CaSE / SlayQL — Project Status (Handoff)

**v1.9 release:** the adaptive-schema research suite is on `main` as tag `v1.9.0`. A local BIRD dev full run (`bird_dev_v19_full`) finished at **904/1534 (58.93% EX)**. Configure the model in `run/.env`; see README for the non-interactive v1.9 command.

**Last updated:** 2026-07-23  
**Branch:** `slayql-1`  
**Repo:** https://github.com/MDS06-Monash-2026/C-CaSE  
**Previous owner:** took over from Kian Lok Chin  
**Dataset:** Spider 2.0-Lite subset `subset_diverse_20_evaluation.json` (**178 instances** — the filename is misleading)

---

## 1. What This Project Is

Text-to-SQL FYP built on the **AutoLink** baseline, extended as **SlayQL** with four modules:

| Module | Role |
|--------|------|
| **RBP** | Graph-based schema join propagation |
| **IT-EE** | Dynamic turn budget (efficiency) |
| **BM25** | Value grounding in schema linking |
| **QOC** | Strict JSON/SQL output contracts |

**Goal:** Fair Baseline vs SlayQL comparison + AAAI-style ablation studies on the 178-instance evaluation subset.

---

## 2. Environment (Ready)

| Item | Status |
|------|--------|
| OS | Windows 11 — **use `.ps1` scripts, not `.sh`** |
| Python | 3.11.9 (system pip; conda not installed) |
| GPU | RTX 4060, CUDA PyTorch `2.6.0+cu124` |
| API | OpenRouter via `run/.env` (`deepseek/deepseek-v4-flash`) — **do not commit** |
| Resources | `run/embeddings/`, `run/documents/`, BigQuery/Snowflake credentials, `spider2-localdb` (32 SQLite DBs) |
| HF cache | Redirected to `D:\C-CaSE\hf_cache` in `model_manager.py` |
| Extra dep | `rank_bm25` installed |

Quick sanity check:
```powershell
cd d:\C-CaSE
python test.py   # BigQuery connectivity
```

---

## 3. Main Results (Baseline vs SlayQL)

| Model | EX (evaluable) | EX (178 denominator) | Report |
|-------|----------------|----------------------|--------|
| AutoLink Baseline | 71/171 (41.5%) | 71/178 (39.9%) | `run/comparison_report.md` |
| Full SlayQL | 72/163 (44.2%) | 72/178 (40.4%) | `run/log_subset_diverse_20_evaluation_slayql_ccase/` |

**Net gain:** +1 correct instance on the full 178 subset.

**Metric note:** `72/163` means only instances with a successful `result.csv` are scored. `72/178` uses all 178 questions as the denominator (failed execution counts as wrong). These are both valid — just different denominators.

---

## 4. Ablation 1 — Component Dropout (Leave-One-Out)

**Purpose:** Remove one SlayQL module at a time to quantify its contribution.  
**Report (partial):** `run/ablation1_component_dropout_report.md` — **needs regeneration after `no_qoc` is finished.**

| Variant | Log directory | EX result | Status |
|---------|---------------|-----------|--------|
| Full SlayQL | `log_subset_diverse_20_evaluation_slayql_ccase` | 72/163 (44.17%) | ✅ Done |
| w/o RBP | `ablation1_no_rbp` | 4/178 (2.25%) | ✅ Done |
| w/o BM25 | `ablation1_no_bm25` | 3/178 (1.69%) | ✅ Done |
| w/o IT-EE | `ablation1_no_itee` | **78/168 (46.43%)** | ✅ Done |
| w/o QOC | `ablation1_no_qoc` | **23/66 partial only** | ❌ **Incomplete** |

### w/o IT-EE — complete

- Stages 8–12 finished on 2026-07-23
- Selection: 178 dirs, 168 `result.csv`, 10 `error.txt`
- Slightly higher EX than Full SlayQL on a different evaluable set (168 vs 163) — consistent with IT-EE being primarily an **efficiency** win, not a large accuracy trade-off

### w/o QOC — incomplete (highest priority)

| Stage | Progress |
|-------|----------|
| 8 SQL generation | ✅ 890/890 (178 × 5 candidates) |
| 9 SQL execution | ✅ All 5 candidates finished (most SQL fails without QOC — expected) |
| 10 SQL revision | ~715/~778 (~92%) |
| 11 SQL selection | **138/178 dirs** (partial — killed mid-run) |
| 12 Evaluation | Partial eval exists (**23/66**) — **not final, discard for paper** |

**Why incomplete:** Run was stopped manually to save API credits. Stopping the Cursor terminal did **not** kill the Python child process — it kept calling the API for hours. All Python processes were manually killed on 2026-07-23 ~2:08 PM.

---

## 5. Ablation 2 / 3 / 4 — Not Started

Shell scripts exist but have **no Windows `.ps1` ports yet**:

- `run/ablation2_scalability.sh` — Easy/Medium/Hard buckets
- `run/ablation3_hyperparameter.sh` — IT-EE threshold, RBP alpha sweep
- `run/ablation4_model_agnostic.sh` — strong/weak model 2×2 matrix

---

## 6. Bugs Fixed (Important Context)

These fixes are in **local uncommitted code** — the pipeline was broken before these changes:

1. **`sql_clean` path bug** (`run/sql_generation.py`)  
   Was writing `{id}/selected.sql`; execution/selection expect flat `{id}.sql`. Root cause of earlier ablation eval failures.

2. **API `content=None` crash** (`run/sql_generation.py`)  
   OpenRouter sometimes returns empty content → batch died at ~203/890.  
   Now: retry 5× with backoff → record failed IDs → continue batch → rerun failed at end.  
   Failed IDs saved to `{log_path}/sql_gen_failed_tasks.json`.

3. **`eval_result.txt` UTF-16** from PowerShell `Tee-Object` broke report parser.  
   Fixed: UTF-8 output in `.ps1`; multi-encoding read in `generate_ablation_report.py`.

4. **`no_qoc` incomplete copy** from full log (missing `cache/`, JSON files).  
   Fixed in `ablation1_fix_failed.ps1`.

5. **`main.sh` / `sql_gen.sh`** now load `run/.env`.

---

## 7. How to Resume (Next Teammate Action)

### Do NOT rerun `no_itee` — it is finished.

### Finish `no_qoc` only (stages 10–12)

All stages are **resume-safe** (existing outputs are skipped).

```powershell
cd d:\C-CaSE\run

# Load .env manually if needed (scripts do this automatically)
# Stage 10 — finish remaining revision (~63 tasks)
python sql_revise.py --num_workers 8 --num_candidates 5 `
  --data_file subset_diverse_20_evaluation.json `
  --schema_dir ablation1_no_qoc/final_schema_prompts `
  --log_path ablation1_no_qoc --task r1_lite

# Stage 11 — finish selection (will skip 138 existing dirs)
python sql_selection.py --log_path ablation1_no_qoc --num_candidates 5 `
  --workers 32 --task r1_lite --data_file subset_diverse_20_evaluation.json

# Stage 12 — evaluation (no API cost)
Push-Location ../evaluation_suite
python evaluate.py --mode exec_result `
  --result_dir "../run/ablation1_no_qoc/sql_selection/final" `
  --gold_dir gold --data_file "../run/subset_diverse_20_evaluation.json" `
  | Out-File -FilePath "../run/ablation1_no_qoc/eval_result.txt" -Encoding utf8
Pop-Location
python parse_tokens.py --log_path ablation1_no_qoc --data_file subset_diverse_20_evaluation.json `
  | Out-File -FilePath ablation1_no_qoc/eval_result.txt -Encoding utf8 -Append

# Regenerate full ablation report
python generate_ablation_report.py --ablation_type component_dropout `
  --data_file subset_diverse_20_evaluation.json --task r1_lite `
  --variants `
    "Full SlayQL:log_subset_diverse_20_evaluation_slayql_ccase" `
    "w/o IT-EE (Always loops):ablation1_no_itee" `
    "w/o RBP (No graph joins):ablation1_no_rbp" `
    "w/o BM25 Grounding:ablation1_no_bm25" `
    "w/o QOC (Strict Outputs):ablation1_no_qoc" `
  --output_path ablation1_component_dropout_report.md
```

**Estimated remaining API cost:** ~1–2 hours of revision LLM calls (revision is the expensive stage). Selection and eval are mostly local.

### ⚠️ How to stop a run safely on Windows

Stopping the Cursor terminal **does not** kill Python child processes. Always verify:

```powershell
Get-Process python* | Select-Object Id, StartTime, @{N='Cmd';E={(Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine}}

# To stop:
Get-Process python* | Stop-Process -Force
```

---

## 8. Pipeline Overview (12 Stages)

```
 1 BM25 index        2 Retrieval         3 add_id
 4 Initial schema    5 Schema completion 6 Postprocess
 7 Final schema      8 SQL generation    9 SQL execution
10 SQL revision     11 SQL selection    12 Evaluation
```

- Checkpoint: `{log_dir}/.pipeline_ckpt` (`STAGE_N=done`)
- Full SlayQL log: `run/log_subset_diverse_20_evaluation_slayql_ccase`
- Baseline log: `run/log_subset_diverse_20_evaluation_autolink_baseline_v2` (or see `run/_baseline/`)

**Windows entry scripts:**
| Script | Purpose |
|--------|---------|
| `run/run_autolink_baseline.ps1` | Baseline full pipeline |
| `run/ablation1_component_dropout.ps1` | Full Ablation 1 (all 5 variants) |
| `run/ablation1_fix_failed.ps1` | Rerun stages 8–12 for no_itee + no_qoc only |
| `run/ablation_smoke_test.ps1` | Quick 2-instance validation (~2 min) |

---

## 9. Branch & Collaboration Warnings

- **Stay on `slayql-1`** — best EX ~40.4% on this subset.
- **Do NOT merge `slayql-2`** — SGSA regression (~15.2% vs ~40.4%).
- `main` branch uses a different SlayQL v2 architecture (Steiner tree) — not the same stack.
- **Local fixes are NOT pushed to GitHub yet.** Coordinate with Kian Lok before pushing.
- Large log/result directories are gitignored — commit scripts and reports only, not multi-GB logs.

---

## 10. Uncommitted Local Changes

Modified (not pushed):
```
run/sql_generation.py          # sql_clean fix + resilient batch/retry
run/generate_ablation_report.py
run/main.sh, run/sql_gen.sh
run/model_manager.py
run/complete_schema.py
run/retrieve_topk_schema.py
run/sql_selection.py
run/comparison_report.md
```

New (not pushed):
```
run/ablation1_component_dropout.ps1
run/ablation1_fix_failed.ps1
run/ablation_smoke_test.ps1
run/run_autolink_baseline.ps1
run/ablation1_component_dropout_report.md
run/_baseline/
memory.txt, task.txt
```

Run logs (gitignored, on disk):
```
run/ablation1_fix_run.log
run/ablation1_run.log
```

---

## 11. Task Checklist

| # | Task | Status |
|---|------|--------|
| 0 | Environment setup | ✅ Done |
| 1 | Baseline re-run + comparison report | ✅ Done |
| 2 | Ablation 1 (5 variants) | 🔄 **4/5 done** — finish `no_qoc` |
| 3 | Ablation 2 / 3 / 4 | ❌ Not started |
| 4 | Git commit + push local scripts | ❌ Not done |
| 5 | Final numbers + README/docs | ❌ Not done |

**Ablation 1 done when:** All 5 variants have final EX + token cost in `ablation1_component_dropout_report.md`.

---

## 12. Other Reference Files

| File | Purpose |
|------|---------|
| `task.txt` | Detailed todo checklist (Chinese) |
| `memory.txt` | LLM session handoff notes (may be slightly stale — prefer this file) |
| `run/comparison_report.md` | Baseline vs SlayQL side-by-side |
| `run/ablation1_fix_run.log` | Full log of the no_itee + no_qoc rerun |

**Contact:** Kian Lok Chin — embeddings, credentials, spider2-localdb if anything is missing.

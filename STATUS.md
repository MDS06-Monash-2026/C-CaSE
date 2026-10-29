# C-CaSE / SlayQL — Project Status (Handoff)

**Last updated:** 2026-07-30  
**Branch:** `slayql-1`  
**Repo:** https://github.com/MDS06-Monash-2026/C-CaSE  

> **For next LLM:** Read this file first. Deep details in `memory.txt`. Failure logs in `error_log.txt`.

---

## TL;DR — Where We Are Now

| What | Status |
|------|--------|
| **Phase 1 SlayQL (547)** | ✅ **DONE** — **251/527 (47.63%)** |
| **Phase 1 Baseline (547)** | ❌ Cancelled — user only needs SlayQL |
| **25-instance retry** | ✅ Done — 5 recovered, 20 still fail |
| **178-subset experiments** | ✅ Archived — do not delete or overwrite |
| **Next step** | **Phase 2: Ablation 1 on 547** |
| **Git** | Local fixes not committed/pushed yet |

**Paper headline number:** SlayQL **251/527 = 47.63%** on Spider 2.0-Lite full set (`spider2_data.json`, 547 instances; 527 evaluable after pipeline).

---

## 1. What This Project Is

Text-to-SQL FYP: **AutoLink baseline** vs **SlayQL** (RBP, IT-EE, BM25, QOC) on Spider 2.0-Lite.

- **Paper target:** full 547-instance evaluation (`run/spider2_data.json`)
- **Dev archive:** 178-instance subset (`run/subset_diverse_20_evaluation.json`) — keep all logs
- **User decision:** Baseline on 547 **not needed**; focus on SlayQL only going forward

---

## 2. Environment

| Item | Value |
|------|-------|
| OS | Windows 11 — **use `.ps1`, not `.sh`** |
| Python | 3.11.9 |
| GPU | RTX 4060, CUDA PyTorch 2.6.0+cu124 |
| API | OpenRouter via `run/.env` (`deepseek/deepseek-v4-flash`) — **do not commit** |
| HF cache | `D:\C-CaSE\hf_cache` |

**Windows gotcha:** Stopping Cursor terminal does **not** kill Python. Use:
```powershell
Get-Process python* | Stop-Process -Force
```

---

## 3. Dataset Strategy

| File | Instances | Role |
|------|-----------|------|
| `run/spider2_data.json` | **547** | **100% full — paper target** |
| `run/subset_diverse_20_evaluation.json` | 178 (~33%) | Dev/archive — **keep, do not overwrite** |
| `run/subset_109_evaluation.json` | 109 (~20%) | Older small subset |

---

## 4. Phase 1 Full 547 — SlayQL ✅ COMPLETE

### Main Result

| Item | Value |
|------|-------|
| **EX score** | **251/527 (47.63%)** |
| **Evaluable** | 527/547 (20 have `error.txt` only — no `result.csv`) |
| **Log dir** | `run/log_spider2_full_slayql/` |
| **Eval output** | `run/log_spider2_full_slayql/eval_result.txt` |
| **Pre-retry backup** | `run/log_spider2_full_slayql/eval_result.txt.before_retry` (250/522) |
| **Run log** | `run/phase1_full_run.log` |
| **Report** | `run/comparison_report_full.md` (Baseline column = 0%, ignore) |

### Baseline (547) — Cancelled, Ignore

User stopped mid-run. Partial log at `run/log_spider2_full_baseline/` (~13% SQL gen). **Do not rerun full `run_phase1_full.ps1`** — it would restart Baseline; SlayQL is already complete.

### 25-Instance Retry ✅ DONE (2026-07-30)

Scripts: `run/retry_failed_25.py`, `run/retry_failed_25.ps1`  
Log: `run/retry_failed_25.log`

| Outcome | Count | IDs |
|---------|-------|-----|
| **Recovered** | 5/25 | `bq430`, `sf_bq153`, `sf_bq254`, `sf_bq291`, `sf_bq426` |
| **Still failed** | 20/25 | see `error_log.txt` |

EX before retry: 250/522 (47.89%) → after retry: **251/527 (47.63%)**

### 20 Remaining Failures — Likely Not Fixable by Re-revision

Full error text: **`error_log.txt`** (numbered 1–20)  
Source files: `run/log_spider2_full_slayql/sql_selection/final/{id}/error.txt`

| Category | IDs | Root cause |
|----------|-----|------------|
| BigQuery 404/403 | `bq023`, `bq109` | Table not found / access denied |
| SQLite wrong DB | `local056`, `local096`–`local100`, `local193`–`local197`, `local199` | SQL references tables (`payment`, `Movie`, `M_Cast`, `rental`, etc.) not in assigned SQLite |
| Empty result | `local097`, `local275`, `sf_bq070`, `sf_bq131` | Query runs but no data |
| Snowflake | `sf001`, `sf009`, `sf013` | Schema/auth error, multi-statement, placeholder DB name |

**Implication:** Many `local_*` failures are **schema/DB mapping issues**, not bad SQL alone. Further revision reruns unlikely to help without fixing SQLite DB assignment.

---

## 5. Archived Results — 178-Instance Subset

Do **not** delete these logs or reports.

### Main Comparison (178)

| Model | EX (evaluable) | EX (178 denom.) | Report |
|-------|----------------|-----------------|--------|
| AutoLink Baseline | 71/171 (41.5%) | 71/178 (39.9%) | `run/comparison_report.md` |
| Full SlayQL | 72/163 (44.2%) | 72/178 (40.4%) | `log_subset_diverse_20_evaluation_slayql_ccase/` |

### Ablation 1 (178) — Complete ✅

Report: `run/ablation1_component_dropout_report.md`

| Variant | EX |
|---------|-----|
| Full SlayQL | 72/163 (44.17%) |
| w/o IT-EE | 78/168 (46.43%) |
| w/o RBP | 4/178 (2.25%) |
| w/o BM25 | 3/178 (1.69%) |
| w/o QOC | 33/100 (33.00%) |

### Ablation 2 (178) — Partial, Do Not Continue

Report: `run/ablation2_scalability_report.md` — SlayQL buckets only, AutoLink incomplete. **Rerun on 547**, not 178.

---

## 6. Roadmap — What's Next

| Phase | Task | Data | Status |
|-------|------|------|--------|
| **1** | SlayQL main experiment | 547 | ✅ **Done** — 251/527 |
| **1b** | Retry 25 error.txt instances | 547 | ✅ Done — +1 EX |
| **2** | **Ablation 1 (5 variants)** | **547** | ⏳ **NEXT** |
| **3** | Ablation 2/3/4 | 547 | ⏳ Pending |
| **4** | Reports, git commit, paper numbers | — | ⏳ Pending |

### Phase 2 Hint for Next LLM

- Reuse `run/log_spider2_full_slayql/` as **Full SlayQL** baseline for Ablation 1 — no need to rerun Full variant
- Script: `run/ablation1_component_dropout.ps1` — change `--data_file` to `spider2_data.json` (547)
- Also available: `run/ablation1_resume_no_qoc.ps1` (resume helper from 178 run)
- Ablation 2 script exists for 178 only (`run/ablation2_scalability.ps1`) — needs `.ps1` port/adaptation for 547

---

## 7. Key Files & Directories

| Purpose | Path |
|---------|------|
| Full SlayQL results (547) | `run/log_spider2_full_slayql/` |
| Full Baseline partial (ignore) | `run/log_spider2_full_baseline/` |
| SlayQL 178 archive | `run/log_subset_diverse_20_evaluation_slayql_ccase/` |
| Baseline 178 archive | `run/log_subset_diverse_20_evaluation_autolink_baseline_v2/` |
| Ablation 1 logs (178) | `run/ablation1_no_*` |
| 20 failure errors (numbered) | **`error_log.txt`** |
| LLM handoff memory | **`memory.txt`** |
| Phase 1 run log | `run/phase1_full_run.log` |
| Retry run log | `run/retry_failed_25.log` |

---

## 8. Scripts Reference

| Script | Purpose |
|--------|---------|
| `run/run_phase1_full.ps1` | Phase 1 full 547 — **SlayQL done; do not rerun fully** |
| `run/retry_failed_25.ps1` | Retry error.txt instances (done) |
| `run/ablation1_component_dropout.ps1` | Ablation 1 — **next: point to 547** |
| `run/ablation1_resume_no_qoc.ps1` | Resume no_qoc stages 10–12 |
| `run/ablation2_scalability.ps1` | Ablation 2 (178 only — adapt for 547) |
| `run/run_autolink_baseline.ps1` | 178 baseline only (legacy) |

### SlayQL Pipeline Stages

```
1 BM25 → 2 Retrieval → 3 add_id → 4 initial schema → 5 complete
→ 6 postprocess → 7 final schema → 8 SQL gen → 9 exec → 10 revise
→ 11 selection → 12 eval
```

---

## 9. Local Code Fixes (Uncommitted)

These fixes are in local working tree — still apply to future runs:

1. `sql_clean` path: flat `{id}.sql` not `{id}/selected.sql`
2. `sql_generation.py`: API `content=None` → retry + continue batch
3. UTF-8 eval output in `.ps1`; multi-encoding in `generate_ablation_report.py`
4. Windows: `Stop-Process` to kill orphaned Python

---

## 10. Branch & Git Warnings

- Stay on **`slayql-1`**. Do **not** merge **`slayql-2`** (SGSA regression).
- Local changes **not pushed** to GitHub — coordinate before push.
- **Do not commit** `run/.env` or API keys.

---

## 11. Task Checklist

| # | Task | Status |
|---|------|--------|
| 0 | Environment | ✅ |
| 1a | Main experiment (178) | ✅ Archived |
| 2a | Ablation 1 (178) | ✅ Archived |
| **1b** | **SlayQL full 547** | ✅ **251/527 (47.63%)** |
| **1c** | **Retry 25 failures** | ✅ 5 recovered, 20 documented in `error_log.txt` |
| **2b** | **Ablation 1 (547)** | ⏳ **NEXT** |
| 3 | Ablation 2/3/4 (547) | ⏳ |
| 4 | Git commit + final docs | ⏳ |

---

## 12. Docs to Read (by task)

| If you need to… | Read |
|-----------------|------|
| Understand full context | `memory.txt` |
| See 20 failure details | `error_log.txt` |
| Phase 1 numbers/report | `run/comparison_report_full.md` |
| 178 comparison | `run/comparison_report.md` |
| Ablation 1 (178) analysis | `run/ablation1_component_dropout_report.md` |
| Ablation 2 (178) partial | `run/ablation2_scalability_report.md` |
| Retry verbose log | `run/retry_failed_25.log` |
| Phase 1 stdout | `run/phase1_full_run.log` |

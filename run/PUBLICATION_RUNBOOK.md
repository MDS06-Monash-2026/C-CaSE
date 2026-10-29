# Publication Runbook: SlayQL Schema Linking and Budget Experiments

How to set up, test and run every experiment and analysis for the ARR October 2026 paper, on Windows with PowerShell. The research plan (what each experiment is for and how results are interpreted) is in [`../SLAYQL_PUBLICATION_PLAN_ARR_OCT2026.md`](../SLAYQL_PUBLICATION_PLAN_ARR_OCT2026.md).

**In short:**

```powershell
cd "C:\Users\kianl\Downloads\C-CaSE (1)\C-CaSE\run"
.\pub_run_all.ps1 -Mode smoke                                        # 1. check everything on 2 questions per variant (~$0.10, ~1 h)
.\pub_run_all.ps1 -Mode full -Parallel 2 -CompletionProcesses 6      # 2. all BIRD dev experiments, then the full analysis
# 3. read pub_results\REPORT.md
```

---

## 1. What gets run

### 1.1 New BIRD dev runs

Every run uses:
- **Pipeline:** SlayQL v1.8 (`research_suite_v18.py`).
- **Data:** all 1,534 BIRD dev questions.
- **Model:** `deepseek/deepseek-v4-flash`.
- **Candidates:** one (k=1).
- **Few-shot:** the same 2 demonstrations per question as the v1.8 full run.

Only the experiment switch differs.

| Variant | Run folder | Switch | Plan ID | Question it answers |
|---|---|---|---|---|
| `ref` | `bird_dev_v18_k1_ref` | none | R1 | Reference for every comparison |
| `topn20` | `bird_dev_v18_k1_topn20` | `SLAYQL_TOP_N=20` | R6 | Accuracy and tokens with tight schema retrieval |
| `no_rbp` | `bird_dev_v18_k1_no_rbp` | `ABLATION_NO_RBP=1` | R2 | What relevance propagation adds |
| `no_bm25` | `bird_dev_v18_k1_no_bm25` | `ABLATION_NO_BM25=1` | R4 | What value grounding adds |
| `itee_max` | `bird_dev_v18_k1_itee_max` | `ABLATION_ITEE_THRESHOLD=1.01` | R9 | Tokens saved when IT-EE's early exit is as active as it can be |
| `topn50` | `bird_dev_v18_k1_topn50` | `SLAYQL_TOP_N=50` | R7 | Medium retrieval budget |
| `no_qoc` | `bird_dev_v18_k1_no_qoc` | `ABLATION_NO_QOC=1` | R5 | What the output-format constraint adds |
| `topn10000` (optional) | `bird_dev_v18_k1_topn10000` | `SLAYQL_TOP_N=10000` | R10 | Retrieval without pruning (the 8-table / 72-column schema-focus cap still applies) |

The order in the table is the priority order: the runner runs them top to bottom.

**Dropped from the original plan (with evidence):**
- **R3 (no IT-EE), R8 (threshold 0.2) and the plan's R9 (threshold 0.7)** would be identical to R1.
- **Why:** in the existing runs, retrieval entropy is always 0.95–1.0, so at the default threshold (0.4) and at 0.2 or 0.7, IT-EE gives *every* question the full 10-turn budget. Removing IT-EE also gives 10 turns.
- **Evidence:** `python -m pub.itee_activation` shows this; see Section 7.
- **Instead:** `itee_max` sets the threshold above every entropy value, so every question IT-EE can shorten gets the reduced budget (22% of BIRD questions; the rest are forced to 10 turns by IT-EE's keyword complexity override).

### 1.2 Offline analyses (no API calls)

| Module | Plan ID | Output |
|---|---|---|
| `pub.aggregate_runs` | O2 | Per-question and per-run tables: EX, linking quality, schema size, tokens and cost by stage |
| `pub.stats` | O5 | Paired comparisons vs `ref`: ΔEX with bootstrap CI, McNemar, Holm; Δ recall, precision and tokens |
| `pub.oracle_at_k` | O3 | oracle@k and vote@k for k = 1–5 (existing k=5 runs) |
| `pub.itee_activation` | O7 | Entropy distribution and when IT-EE reduces the budget |
| `pub.spider2_linking` | O1 | Spider 2.0-Lite linking against gold SQL; paired SlayQL vs AutoLink |
| `pub.error_analysis` | O6 | Automatic error labels for every wrong answer, plus a 100-question sample for manual checking |
| `pub.old_ablation` | O4 | Diagnosis of the old 178-question ablation |
| `pub.figures` | F2, F3 | Accuracy vs tokens; accuracy vs number of candidates |
| `pub.run_analysis` | all | Runs all of the above and writes `pub_results/REPORT.md` |

---

## 2. One-time setup

### 2.0 Running on another machine (teammate handover)

1. **On this machine**, build the package: `..\.venv\Scripts\python -m pub.make_handover`. It writes `slayql_pub_handover_<date>.zip` (about 330 MB) next to the repo folder and contains:
   - the pipeline and analysis code;
   - the runner, setup script and documentation;
   - the demonstration file and the code-fingerprint reference;
   - `requirements.txt`;
   - BIRD dev (with the databases still zipped);
   - a `.env.example` template. **The API key is never included.**
2. **Send the teammate the package and the key separately.** They follow [`TEAMMATE_QUICKSTART.md`](TEAMMATE_QUICKSTART.md), which is also at the top of the package as `README_FIRST.md`:
   - `pub_setup.ps1` (environment, packages, databases, `.env`, preflight);
   - the smoke test;
   - the full runs;
   - `python -m pub.package_results` to send the results back.
3. **On this machine**, unzip their results package inside `run\`, then run `..\.venv\Scripts\python -m pub.run_analysis`.

**Safeguards for the handover:**
- **Preflight** (`python -m pub.preflight`, run automatically by `pub_run_all.ps1`) stops the runner if any of these is wrong: packages, `.env` (the model must be `deepseek/deepseek-v4-flash`), the 11 BIRD databases, or the demonstration file (checked by hash).
- It also warns if the pipeline code differs from the smoke-tested version (reference in `pub_inputs\code_fingerprint_reference.json`).
- **Code fingerprints:** every run folder gets `pub_code_fingerprint.json` (per-file hashes, host, time). `REPORT.md` warns if the new runs were not all produced by the same code, or if the code changed during a run.
- **Runs can be split across machines** with `-Variants` (for example, one machine runs `ref,topn20,no_rbp` and the other the rest). Before combining them, make sure both show the same fingerprint in `runs_summary.md`.

### 2.1 Python environment

`pub_setup.ps1` creates the environment on a new machine; see Section 2.0. On this machine it is already set up at `C-CaSE\.venv` (Python 3.12, CUDA PyTorch 2.6), with everything from `requirements.txt` plus `matplotlib` and `scipy`. To recreate it by hand:

```powershell
cd "C:\Users\kianl\Downloads\C-CaSE (1)\C-CaSE"
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
.\.venv\Scripts\python -m pip install -r requirements.txt matplotlib scipy
.\.venv\Scripts\python -c "import torch; print(torch.cuda.is_available())"   # should print True
```

The runner always uses `.venv\Scripts\python.exe`, so the environment doesn't need to be activated.

### 2.2 API key

`run\.env` must contain these three lines (it already does; never commit this file):

```text
OPENAI_API_KEY=<OpenRouter key>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=deepseek/deepseek-v4-flash
```

Set a spending limit on the OpenRouter key before the full runs.

### 2.3 Data

| Item | Location | Status |
|---|---|---|
| BIRD dev | `C-CaSE\dev\dev_20240627\` (`dev.json`, `dev_tables.json`, `dev_databases\`) | Present |
| Few-shot demonstrations | `run\pub_inputs\bird_train_demos_from_v18.json` | Built (see below) |
| Spider 2.0-Lite gold SQL | `C-CaSE\evaluation_suite\gold\sql\` | Present (256 files) |
| Spider 2.0-Lite schema documents | `run\documents\` | Present |

**About the demonstration file:**
- The v1.8 full run used 2 few-shot examples per question from the BIRD train set, which is not on this machine.
- `python -m pub.build_demo_file` rebuilds a training-only file from the examples v1.8 actually selected (1,805 examples).
- Selection is deterministic, so this reproduces the same choices. A check on 200 random questions found **200/200 identical**, and the smoke check tests it again.

### 2.4 Hardware notes

- **GPU:** GTX 1650 (4 GB). The embedding model (`BAAI/bge-large-en-v1.5`) runs on it.
  - With `-Parallel 2`, runs start 20 minutes apart so that only one is embedding at a time.
  - If you see CUDA out-of-memory errors, use `-Parallel 1`.
- **First run:** it downloads the embedding model (about 1.3 GB) and needs internet access.

---

## 3. Step 1: smoke test (do this first)

```powershell
cd "C:\Users\kianl\Downloads\C-CaSE (1)\C-CaSE\run"
.\pub_run_all.ps1 -Mode smoke
```

**What it does:**
- runs every core variant on 2 BIRD questions (`smoke_v18_k1_<variant>` folders);
- aggregates them into `pub_results_smoke\`;
- runs `pub.smoke_check`.

**Cost and time:** about $0.01–0.03 per variant and 4–10 minutes each (the first one is slower because of the model download).

**Already done on 26 September:**
- all 7 core variants passed every check (`pub_results_smoke\smoke_check.md`);
- total cost was $0.16 for 117 API calls;
- the smoke budget figure is at `pub_results_smoke\figures\F2_accuracy_vs_tokens.png`, rendered with `python -m pub.figures --results pub_results_smoke --prefix smoke_v18_k1_`.

The two `smoke_v18_k1_*_backup_*` folders are stalled first attempts, kept by `-Force`, and can be deleted.

**Pass criteria:** `pub_results_smoke\smoke_check.md` shows no `FAIL`. It checks:
- every run finished and was evaluated;
- the switch is recorded in `resolved_config.json`, together with the model;
- API calls went to `deepseek/deepseek-v4-flash`;
- demonstrations are identical to the v1.8 full run;
- each switch had its effect:
  - **no_rbp:** "RBP disabled" appears in the log, and retrieval differs from `ref`;
  - **no_bm25:** "BM25 grounding disabled" appears in the log;
  - **no_qoc:** the output-format block is gone from the generation prompts;
  - **topn:** the retrieved-column count is within the limit;
  - **itee_max:** budgets match the offline simulation.

A few checks are `INFO` rather than `PASS` or `FAIL` when 2 questions are not enough to observe the effect (for example, both smoke questions may be forced to the full IT-EE budget). That is expected.

To run a single variant: `.\pub_run_all.ps1 -Mode smoke -Variants no_rbp`.

---

## 4. Step 2: full runs

```powershell
cd "C:\Users\kianl\Downloads\C-CaSE (1)\C-CaSE\run"
.\pub_run_all.ps1 -Mode full                       # core variants one after another, then the analysis
.\pub_run_all.ps1 -Mode full -Parallel 2           # two at a time, started 20 minutes apart
.\pub_run_all.ps1 -Mode full -IncludeOptional      # also run topn10000
.\pub_run_all.ps1 -Mode full -Variants ref,topn20  # only some variants
.\pub_run_all.ps1 -Mode full -DryRun               # show the commands without running them
```

### 4.1 Time and cost

**What the estimates are based on:**
- **v1.8 full run** (k=5): 12.5k linking tokens per question and 1.25 schema-completion calls per question; per-call latency median 12 s, p95 104 s, max 614 s.
- **Smoke runs** (k=1, 2 questions): $0.014 for the reference run; 4–10 completion calls per question on the question that needed exploration.

With k=1 there is one generation call per question and no revision or tournament calls. Schema completion dominates both time and cost.

| | Per run | 7 core runs, one at a time | 7 core runs, `-Parallel 2` |
|---|---|---|---|
| Time (3 completion processes) | about 4–10 hours | about 2–3 days | about 1–1.5 days |
| Time (`-CompletionProcesses 6`) | about 3–6 hours | about 1–2 days | about 0.7–1 day |
| API cost | about $3–10 | about $20–70 | same |

**Recommendation:**

```powershell
.\pub_run_all.ps1 -Mode full -Parallel 2 -CompletionProcesses 6
```

That gives up to about 2 × (6 + 4) concurrent API calls. If `.err.log` shows `429` (rate-limited) messages, drop back to `-Parallel 1` or `-CompletionProcesses 3`.

**Tighter retrieval shifts cost into the agent.** In the smoke test, `topn20` and `topn50` needed more completion turns, because the agent fetches the columns that retrieval dropped. Expect these runs to take longer, not shorter. This is itself a budget finding for the paper.

**Slow or stuck API calls:**
- The runner sets a 300 s per-request timeout (`-ApiTimeoutSeconds`, recorded in each run's config). Without it, a dropped connection blocks a worker for up to 3 × 600 s, which happened once in the smoke test.
- In the v1.8 run, 20 of 14,497 calls took longer than 300 s; with the timeout, those are retried instead of awaited.
- The model occasionally returns empty content after a long call. The pipeline retries this automatically (`[Retry n/5] ... empty or None content` in the log).

### 4.2 Monitoring

| What | Where |
|---|---|
| Live progress of a run | `run\logs_pub\<run_id>.log` (stage names and progress counters) |
| Errors and warnings | `run\logs_pub\<run_id>.err.log` |
| Start, finish and exit code of every run | `run\logs_pub\status.csv` |
| Checkpoints per stage | `run\<run_id>\checkpoints\` and `run\<run_id>\status\` |

To follow a log: `Get-Content logs_pub\bird_dev_v18_k1_ref.log -Wait -Tail 20`.

### 4.3 Resuming and rerunning

- **Resume after a failure, crash or reboot:** run the same command again. Finished runs are skipped, and unfinished runs continue from their last completed stage.
- **Rerun a finished variant from scratch:** add `-Force`. The old folder is moved to `<run_id>_backup_<timestamp>`, not deleted.
- **"Existing run configuration differs" error:** the run folder was created with different settings (switch, model, k or workers). Use the original settings, or `-Force` to start over.

### 4.4 Stopping

Press `Ctrl+C` in the PowerShell window to stop the runner. On Windows the Python child process keeps running. Stop it with:

```powershell
Get-Process python | Where-Object { $_.Path -like "*C-CaSE*\.venv\*" } | Stop-Process
```

This only stops Python processes from this project's environment. Resume later with the same command.

---

## 5. Step 3: analysis

The full-mode runner runs the analysis automatically at the end. To run it on its own, at any time and with any subset of runs finished:

```powershell
cd "C:\Users\kianl\Downloads\C-CaSE (1)\C-CaSE\run"
..\.venv\Scripts\python -m pub.run_analysis                              # everything (about 10 minutes)
..\.venv\Scripts\python -m pub.run_analysis --skip oracle_at_k           # skip the slowest step (about 6 minutes)
..\.venv\Scripts\python -m pub.run_analysis --only aggregate_runs stats  # just the new-run tables
```

Unfinished runs are marked `Complete = NO` in the tables. Their numbers cover only the questions finished so far.

### 5.1 Where each paper table and figure comes from

| Paper item | File in `run\pub_results\` |
|---|---|
| **Everything, in one place** | `REPORT.md` |
| T1 linking quality (BIRD) | `runs_summary.md` / `.csv` (linked and prompt precision, recall, strict recall; schema size and reduction) |
| T1 and T3 linking quality (Spider 2.0-Lite), SlayQL vs AutoLink | `spider2_linking.md`, `spider2_linking_summary.csv`, `spider2_linking_paired.csv` |
| T2 ablation and budget comparisons | `comparisons.md` / `.csv` |
| T4 error analysis | `errors\<run>_summary.md`; manual-check sample `errors\<run>_sample100.csv` |
| F2 accuracy vs tokens | `figures\F2_accuracy_vs_tokens.png` / `.pdf` |
| F3 accuracy vs candidates | `figures\F3_candidates.png` / `.pdf`, data in `oracle_at_k.csv` |
| IT-EE analysis | `itee_activation.md` |
| Old ablation (appendix note) | `old_ablation_diagnosis.md` |
| Per-question data for anything else | `per_question\<run>.csv` |

### 5.2 Manual error check (team task)

Open `pub_results\errors\bird_dev_v18_k1_ref_sample100.csv` in Excel and fill in `manual_label` (one of `no_prediction`, `linking_miss_table`, `linking_miss_column`, `selection`, `generation`) after reading the question, gold SQL and predicted SQL. Report the agreement with `auto_label` in the paper.

---

## 6. Code changes made for these experiments

| File | Change | Why |
|---|---|---|
| `run/research_suite.py` | The run config now records the experiment switches, `SLAYQL_TOP_N`, `MODEL_NAME` and `OPENAI_BASE_URL` (`environment` block, part of the config hash) | Previously a run folder did not record which variant or model produced it |
| `run/dataset_pipeline.py` | `_prompt_bird_root` skips its two interactive questions when `SLAYQL_NONINTERACTIVE=1` and `--bird-root` is given; three missing switches were added to the recorded settings | Runs can start unattended with logs redirected |
| `run/complete_schema.py` | Number of completion processes read from `SLAYQL_COMPLETION_PROCESSES` (default 3, as before) | Speed only |
| `run/complete_schema.py`, `sql_generation.py`, `sql_revise.py`, `semantic_revise.py` | API client timeout read from `SLAYQL_API_TIMEOUT` (default 600 s, the SDK default, so unchanged unless set) | A dropped connection no longer blocks a worker for up to 30 minutes |
| `run/pub/` (new) | Analysis package (Section 1.2) and `build_demo_file.py`, `smoke_check.py`, `preflight.py`, `fingerprint.py`, `package_results.py`, `make_handover.py` | Offline analysis, verification and handover |
| `run/pub_run_all.ps1` (new) | Experiment runner: preflight, code fingerprint per run, PowerShell 5.1 and 7 support, space-free relative paths | One command for every run, on any machine |
| `run/pub_setup.ps1` (new) | One-time setup for a new machine | Teammate handover |
| `run/TEAMMATE_QUICKSTART.md` (new) | One-page guide for whoever runs the experiments | Teammate handover |
| `.gitignore` | Ignores `.venv/` | The environment is local |

The pipeline logic (retrieval, RBP, IT-EE, BM25, generation, selection, evaluation) is unchanged.

---

## 7. Findings from the offline analysis so far

These come from existing runs, before any new API calls. They affect how the paper is framed; see the plan's Section 10 scenarios.

1. **IT-EE never shortened the budget in the existing runs** (`itee_activation.md`).
   - Retrieval entropy is 0.953–0.9997 on BIRD and 0.961–1.000 on Spider 2.0-Lite, far above the 0.4 threshold.
   - Even with the threshold above every entropy value, the keyword complexity override keeps 78% of BIRD and 97% of Spider 2.0-Lite questions at the full 10 turns.
   - This is **Scenario C**: report it as a budget-awareness finding, and use `itee_max`, `topn20` and `topn50` as the real budget experiments.
2. **On Spider 2.0-Lite, SlayQL links worse than AutoLink with the same model** (`spider2_linking.md`, 79 paired questions).
   - Table recall is 6.1 points lower (95% CI −10.8 to −2.3), and strict table recall is 11.4 points lower.
   - SlayQL keeps more columns (a median of 106 of 280 raw columns, vs AutoLink's 100 of 293) and uses more prompt tokens.
   - This is **Scenario B**: frame the paper as a measurement study and do not claim better linking than AutoLink.
3. **The 178-question SlayQL run is unreliable:** 52 of its 80 gold-SQL schema prompts contain no tables. The paired comparison therefore uses the full 547-question SlayQL run, which has intact prompts. Its EX on the subset (72/163) should not be compared with AutoLink either.
4. **The old 178-question ablation measured pipeline failures** (`old_ablation_diagnosis.md`):
   - no RBP: all 356 selections failed;
   - no BM25: all 178 failed;
   - no QOC: 150 of 316 failed.

   It must not be reported as component effects. The new BIRD runs replace it.
5. **On BIRD, linking keeps nearly everything, and selection and generation cause most errors** (v1.8, k=5):
   - column recall is 99.5% in the prompt the generator sees, while the schema shrinks only 26% (45 of 76 columns);
   - of the 672 wrong answers, 452 have everything needed in the prompt with no correct candidate (generation), and 185 had a correct candidate that was not selected;
   - only 35 miss a gold table or column.
6. **Statistics check:** v1.0 → v1.8 on BIRD (k=5) is +7.04 points EX [95% CI +4.76, +9.32], McNemar p < 0.0001.

---

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Python environment not found` | Create `.venv` (Section 2.1) |
| Run waits for input or asks for the BIRD directory | `SLAYQL_NONINTERACTIVE` was not set; use `pub_run_all.ps1`, which sets it |
| `Existing run configuration differs` | See Section 4.3 |
| Many `429` or timeout messages in `.err.log` | OpenRouter rate limit: use `-Parallel 1` or `-CompletionProcesses 3`. (`-Workers` is part of the run configuration; changing it requires `-Force`.) |
| A run makes no progress for a long time | Look at the last timestamps in `run\<run_id>\usage\*.jsonl`. With the 300 s timeout, a stuck call is retried within 15 minutes. If nothing moves for over 30 minutes, stop the run (Section 4.4) and rerun the same command to resume. |
| CUDA out of memory | Use `-Parallel 1` |
| `UnicodeEncodeError` in the analysis | Run through `..\.venv\Scripts\python -m pub....` (the scripts switch output to UTF-8) |
| A run shows `Complete = NO` in `REPORT.md` | It has not finished; resume it (Section 4.3) |
| Analysis step `FAILED` in `REPORT.md` | The traceback is printed in the console; other steps still run |

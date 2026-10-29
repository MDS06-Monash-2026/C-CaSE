# Quick start: running the SlayQL paper experiments

You are running 7 experiments of the SlayQL Text-to-SQL pipeline on the BIRD dev set (1,534 questions each). One command runs everything; this page covers setup, running, monitoring and sending the results back. The full details are in [`PUBLICATION_RUNBOOK.md`](PUBLICATION_RUNBOOK.md).

**What you need:**
- a computer that can stay on for 1–2 days, with internet and about 20 GB free disk space;
- Python 3.12 (3.10 or 3.11 also work);
- the OpenRouter API key (from Kian Lok);
- an NVIDIA GPU helps but is not required.

**Budget:** about $20–70 of API credit in total. Ask for a spending limit on the key.

---

## 1. Set up (once, about 15–30 minutes)

1. Unzip the handover package somewhere without special characters in the path, for example `C:\slayql\C-CaSE`.
2. Open **PowerShell** in the `run` folder:

   ```powershell
   cd C:\slayql\C-CaSE\run
   Set-ExecutionPolicy -Scope Process Bypass     # allows the scripts to run in this window only
   .\pub_setup.ps1
   ```

   The script:
   - creates the Python environment;
   - installs the packages (including a GPU or CPU build of PyTorch);
   - unpacks the BIRD databases;
   - creates `run\.env`.
3. The first time, it stops and asks you to add the key. Open `run\.env` in Notepad, replace `<your OpenRouter key>` with the key, save, and run `.\pub_setup.ps1` again.
4. Setup is done when the last lines say **`Preflight: 0 FAIL`** and **`Setup complete`**.

**Never share, upload or commit `run\.env`**: it contains the key.

On macOS or Linux, install PowerShell 7 (`pwsh`) and run the same commands with `pwsh ./pub_setup.ps1`.

## 2. Smoke test (about 1 hour, about $0.15)

```powershell
.\pub_run_all.ps1 -Mode smoke
```

This runs each experiment on 2 questions. At the end it prints a table of checks and **`0 failed check(s)`**. If anything says `FAIL`, stop and send `run\pub_results_smoke\smoke_check.md` and the `run\logs_pub` folder to Kian Lok.

## 3. Full runs (about 1–2 days)

```powershell
.\pub_run_all.ps1 -Mode full -Parallel 2 -CompletionProcesses 6
```

Leave the window open and the computer awake: turn off sleep in the Windows power settings.

**What happens:**
- 7 runs, two at a time; each run covers the complete BIRD dev set (all 1,534 questions) with one SQL candidate per question (k=1). Only run 5-candidate versions (`-NumCandidates 5`, folders named `bird_dev_v18_k5_*`) if Kian Lok asks: they cost and take about 3-5x more;
- the analysis runs automatically at the end;
- results appear in `run\pub_results\REPORT.md`.

**Checking progress:**

| Question | Where to look |
|---|---|
| Which runs finished? | `run\logs_pub\status.csv` (`exit_code` 0 = success) |
| What is a run doing now? | `Get-Content logs_pub\bird_dev_v18_k1_ref.log -Wait -Tail 20` (Ctrl+C stops watching, not the run) |
| Errors? | `run\logs_pub\<run>.err.log` |

**If something goes wrong:**
- **Many `429` messages, the window was closed, the computer restarted, or a run shows FAILED:** run the same command again. Finished runs are skipped, and unfinished runs continue where they stopped. After repeated `429` messages, use `-Parallel 1 -CompletionProcesses 3` instead.
- **To stop everything:** press Ctrl+C in the window, then run the command below. Start again later with the same command.

  ```powershell
  Get-Process python | Where-Object { $_.Path -like "*C-CaSE*" } | Stop-Process
  ```

**Do not edit any `.py` file while runs are going.** Every run records a fingerprint of the code, and the report flags runs made with different code.

## 4. Send the results back

When the runner finishes (or if you have to stop early), run:

```powershell
..\.venv\Scripts\python -m pub.package_results
```

This creates `run\pub_results_package_<computer>_<date>.zip`, a few hundred MB at most. Send that file, plus `run\pub_results\REPORT.md` if it exists, to Kian Lok. Don't send `.env`.

---

## Command summary

```powershell
cd C:\slayql\C-CaSE\run
Set-ExecutionPolicy -Scope Process Bypass
.\pub_setup.ps1                                                   # once
.\pub_run_all.ps1 -Mode smoke                                     # check (1 h)
.\pub_run_all.ps1 -Mode full -Parallel 2 -CompletionProcesses 6   # run (1-2 days)
..\.venv\Scripts\python -m pub.package_results                    # send back
```

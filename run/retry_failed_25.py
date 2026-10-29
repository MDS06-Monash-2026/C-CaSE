#!/usr/bin/env python3
"""Retry pipeline for instances that ended with error.txt (no result.csv)."""
import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from tqdm import tqdm

# run/ on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sql_revise import SQLReviser, run_task, collect_tasks
from sql_selection import process_instance
import threading


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def find_failed_ids(log_path: str) -> list[str]:
    sel_final = os.path.join(log_path, "sql_selection", "final")
    failed = []
    for iid in sorted(os.listdir(sel_final)):
        d = os.path.join(sel_final, iid)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "error.txt")):
            failed.append(iid)
    return failed


def print_instance_status(log_path: str, task: str, iid: str, num_candidates: int) -> None:
    err_path = os.path.join(log_path, "sql_selection", "final", iid, "error.txt")
    old_err = open(err_path, encoding="utf-8", errors="replace").read().strip().split("\n")[0][:100]
    log(f"  {iid} | selection error: {old_err}")
    for cid in range(num_candidates):
        gen_csv = os.path.join(log_path, "sql_gen", f"{task}_execution_result_{cid}", f"{iid}.csv")
        gen_err = os.path.join(log_path, "sql_gen", f"{task}_execution_error_{cid}", f"{iid}.txt")
        rev_sql = os.path.join(log_path, "sql_revise", f"{task}_sql_{cid}", f"{iid}.sql")
        rev_csv = os.path.join(log_path, "sql_revise", f"{task}_sql_{cid}", f"{iid}.csv")
        gen_ok = os.path.isfile(gen_csv)
        rev_ok = os.path.isfile(rev_csv)
        log(f"    cand{cid}: gen_ok={gen_ok} gen_err={os.path.isfile(gen_err)} "
            f"rev_sql={os.path.isfile(rev_sql)} rev_ok={rev_ok}")


def clear_revise_outputs(log_path: str, task: str, iids: list[str], num_candidates: int) -> int:
    removed = 0
    for iid in iids:
        for cid in range(num_candidates):
            for sub, ext in [(f"{task}_sql_{cid}", ".sql"), (f"{task}_sql_{cid}", ".txt"),
                             (f"{task}_sql_{cid}", ".csv"), (f"{task}_messages_{cid}", ".json")]:
                p = os.path.join(log_path, "sql_revise", sub, f"{iid}{ext}")
                if os.path.isfile(p):
                    os.remove(p)
                    removed += 1
    return removed


def run_revision_filtered(
    data_file: str,
    schema_dir: str,
    log_path: str,
    task: str,
    iids: set[str],
    num_candidates: int,
    num_workers: int,
) -> None:
    from sql_revise import DataLoader

    data = DataLoader().load(data_file)
    reviser = SQLReviser()
    all_tasks = collect_tasks(schema_dir, log_path, task, num_candidates)
    tasks = [(iid, cid) for iid, cid in all_tasks if iid in iids]
    log(f"Revision: {len(tasks)} tasks for {len(iids)} instances (filtered from {len(all_tasks)} total pending)")

    def wrapped_run(iid, cid):
        log(f"REVISION START {iid} cand{cid}")
        try:
            run_task(reviser, data, schema_dir, log_path, task, iid, cid)
            rev_csv = os.path.join(log_path, "sql_revise", f"{task}_sql_{cid}", f"{iid}.csv")
            rev_err = os.path.join(log_path, "sql_revise", f"{task}_sql_{cid}", f"{iid}.txt")
            if os.path.isfile(rev_csv):
                log(f"REVISION OK    {iid} cand{cid} -> success (csv written)")
            elif os.path.isfile(rev_err):
                err = open(rev_err, encoding="utf-8", errors="replace").read().strip().split("\n")[0][:80]
                log(f"REVISION FAIL  {iid} cand{cid} -> still error: {err}")
            else:
                log(f"REVISION DONE  {iid} cand{cid} -> no csv/error file (check sql_revise output)")
        except Exception as e:
            log(f"REVISION ERROR {iid} cand{cid} -> {type(e).__name__}: {e}")

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(wrapped_run, iid, cid) for iid, cid in tasks]
        for future in tqdm(as_completed(futures), total=len(futures), desc="SQL Revision (25)"):
            future.result()


def run_selection_filtered(log_path: str, data_file: str, task: str, iids: list[str], workers: int) -> None:
    class Args:
        pass

    args = Args()
    args.log_path = log_path
    args.num_candidates = 5
    args.max_rows = 1000
    args.max_chars = 10000
    args.workers = workers
    args.task = task
    args.data_file = data_file

    lock = threading.Lock()
    log(f"Selection: re-running {len(iids)} instances")

    for iid in iids:
        final_dir = os.path.join(log_path, "sql_selection", "final", iid)
        err_f = os.path.join(final_dir, "error.txt")
        res_f = os.path.join(final_dir, "result.csv")
        if os.path.isfile(err_f):
            os.remove(err_f)
            log(f"  cleared old error.txt for {iid}")
        if os.path.isfile(res_f):
            os.remove(res_f)
            log(f"  cleared old result.csv for {iid}")

    def wrapped_selection(iid):
        log(f"SELECTION START {iid}")
        try:
            process_instance(f"{iid}.txt", args, lock)
            res_f = os.path.join(log_path, "sql_selection", "final", iid, "result.csv")
            err_f = os.path.join(log_path, "sql_selection", "final", iid, "error.txt")
            if os.path.isfile(res_f):
                log(f"SELECTION OK    {iid} -> result.csv created")
            elif os.path.isfile(err_f):
                err = open(err_f, encoding="utf-8", errors="replace").read().strip().split("\n")[0][:80]
                log(f"SELECTION FAIL  {iid} -> {err}")
            else:
                log(f"SELECTION WARN  {iid} -> no result.csv or error.txt")
        except Exception as e:
            log(f"SELECTION ERROR {iid} -> {type(e).__name__}: {e}")

    with ThreadPoolExecutor(max_workers=min(workers, len(iids))) as executor:
        futures = [executor.submit(wrapped_selection, iid) for iid in iids]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Selection (25)"):
            future.result()


def rerun_eval(log_path: str, data_file: str, task: str) -> None:
    import subprocess

    sel = os.path.join(log_path, "sql_selection", "final")
    eval_suite = os.path.join(os.path.dirname(log_path), "..", "evaluation_suite")
    eval_suite = os.path.normpath(eval_suite)
    out = os.path.join(log_path, "eval_result.txt")
    backup = out + ".before_retry"

    if os.path.isfile(out):
        shutil.copy2(out, backup)
        log(f"Backed up eval to {backup}")

    result_dir = os.path.join("..", "run", log_path, "sql_selection", "final")
    cmd = [
        sys.executable, "evaluate.py",
        "--mode", "exec_result",
        "--result_dir", result_dir,
        "--gold_dir", "gold",
        "--data_file", os.path.join("..", "run", data_file),
    ]
    log(f"Running eval: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=eval_suite, capture_output=True, text=True, encoding="utf-8", errors="replace")
    with open(out, "w", encoding="utf-8") as f:
        f.write(proc.stdout)
        if proc.stderr:
            f.write("\n--- stderr ---\n")
            f.write(proc.stderr)

    for line in proc.stdout.splitlines():
        if "Results:" in line or "Evaluating IDs" in line:
            log(f"EVAL {line.strip()}")

    parse_cmd = [sys.executable, "parse_tokens.py", "--log_path", log_path, "--data_file", data_file]
    subprocess.run(parse_cmd, cwd=os.path.dirname(os.path.abspath(__file__)),
                   stdout=open(out, "a", encoding="utf-8"), stderr=subprocess.STDOUT)


def main():
    parser = argparse.ArgumentParser(description="Retry failed instances (error.txt only)")
    parser.add_argument("--log_path", default="log_spider2_full_slayql")
    parser.add_argument("--data_file", default="spider2_data.json")
    parser.add_argument("--task", default="r1_lite")
    parser.add_argument("--num_candidates", type=int, default=5)
    parser.add_argument("--num_workers", type=int, default=8)
    parser.add_argument("--selection_workers", type=int, default=8)
    args = parser.parse_args()

    schema_dir = os.path.join(args.log_path, "final_schema_prompts")

    log("=" * 60)
    log("RETRY FAILED INSTANCES")
    log(f"log_path={args.log_path} data_file={args.data_file}")
    log("=" * 60)

    failed = find_failed_ids(args.log_path)
    if not failed:
        log("No instances with error.txt found. Nothing to do.")
        return

    log(f"Found {len(failed)} instances with error.txt (no result.csv):")
    for iid in failed:
        print_instance_status(args.log_path, args.task, iid, args.num_candidates)

    log("")
    log("Step 1: Clear sql_revise outputs so revision will re-run...")
    n = clear_revise_outputs(args.log_path, args.task, failed, args.num_candidates)
    log(f"  Removed {n} revise files")

    log("")
    log("Step 2: SQL Revision (LLM + inline re-exec)...")
    run_revision_filtered(
        args.data_file, schema_dir, args.log_path, args.task,
        set(failed), args.num_candidates, args.num_workers,
    )

    log("")
    log("Step 3: SQL Selection for failed instances only...")
    run_selection_filtered(
        args.log_path, args.data_file, args.task, failed, args.selection_workers,
    )

    log("")
    log("Step 4: Summary after retry")
    recovered = []
    still_failed = []
    for iid in failed:
        res_f = os.path.join(args.log_path, "sql_selection", "final", iid, "result.csv")
        if os.path.isfile(res_f):
            recovered.append(iid)
            log(f"  RECOVERED {iid}")
        else:
            still_failed.append(iid)
            err_f = os.path.join(args.log_path, "sql_selection", "final", iid, "error.txt")
            err = open(err_f, encoding="utf-8", errors="replace").read().strip().split("\n")[0][:80] if os.path.isfile(err_f) else "?"
            log(f"  STILL FAIL {iid}: {err}")

    log(f"Recovered: {len(recovered)}/{len(failed)} | Still failed: {len(still_failed)}")

    log("")
    log("Step 5: Re-evaluate full log...")
    rerun_eval(args.log_path, args.data_file, args.task)
    log("Done.")


if __name__ == "__main__":
    main()

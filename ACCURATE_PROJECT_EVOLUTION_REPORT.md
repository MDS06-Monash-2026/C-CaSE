# Accurate Project Evolution Report: C-CaSE / SlayQL

**Project**: C-CaSE / SlayQL  
**Repository checked**: `D:\C-CaSE`  
**Primary remote**: `https://github.com/MDS06-Monash-2026/C-CaSE`  
**Verification date**: 2026-07-25  
**Verification source**: local Git branches, local tags, committed artifacts, and current working-tree report/result files.

---

## Verification Summary

This file is a corrected evolution summary for the project. It follows the style of `PROJECT_EVOLUTION_REPORT.md`, but it only states claims that are supported by the local Git graph or committed/current artifacts.

The original `PROJECT_EVOLUTION_REPORT.md` is directionally useful, but it contains several important inaccuracies:

1. The project history is not a single linear sequence from `AutoLink` to `c-case-v1` to `slayql-1` to `slayql-2` to `slayql-lite`.
2. The `v1.0.0-slayql-lite` release tag resolves to commit `02599b2`, not `251c7bb`.
3. The branch `c-case-op-1` points to `af6bad0`, not to the `c-case-v1` tag commit `a72cce2`.
4. The `slayql-2` branch implements SGSA as **Self-Generated Semantic Assertions**, not the reported **Sub-Graph Search Algorithm / Steiner pruning** system.
5. Some benchmark and token numbers are supported, while others are conflicting or not reproducible from committed artifacts.

---

## 1. Actual Git Reference State

### 1.1 Local Branches

| Branch | Commit | Date | Subject |
|---|---:|---|---|
| `c-case-op-1` | `af6bad0` | 2026-06-13 | Initial commit |
| `main` | `2b1719f` | 2026-07-24 | merge(slayql-lite): integrate production SlayQL-Lite architecture, ablation suites, and master documentation into main |
| `slayql-1` | `475ce87` | 2026-06-23 | feat: implement enhanced value grounder with stop-word filtering, numeric thresholding, and capped hint injection. |
| `slayql-2` | `b015e42` | 2026-06-23 | Introduce SGSA validation module |
| `slayql-lite` | `ba00dc2` | 2026-07-24 | docs: merge complete architectural evolution manuscript, formulas, and primary research attribution into README |

### 1.2 Tags / Releases

| Tag | Tag Type | Resolves To | Date | Meaning |
|---|---|---:|---|---|
| `AutoLink` | lightweight tag | `af6bad0` | 2026-06-13 | Initial AutoLink baseline snapshot |
| `c-case-v1` | lightweight tag | `a72cce2` | 2026-06-16 | Evaluation/infrastructure milestone |
| `v1.0.0-slayql-lite` | annotated tag | tag object `839c8d5`, commit `02599b2` | 2026-07-24 | SlayQL-Lite release tag |

Important correction: `251c7bb` is **one commit after** `v1.0.0-slayql-lite`, not the release tag target.

---

## 2. Actual Commit Graph

The local graph is:

```text
*   2b1719f 2026-07-24  main, origin/main
|\            merge(slayql-lite): integrate production SlayQL-Lite architecture, ablation suites, and master documentation into main
| *
| * ba00dc2 2026-07-24  slayql-lite, origin/slayql-lite
| * 5932669 2026-07-24  docs: update README with architectural evolution, benchmark results, and ablation findings
| * 251c7bb 2026-07-24  feat(slayql): merge resilient batch engine, ablation scripts, and handoff docs
| * 02599b2 2026-07-24  tag: v1.0.0-slayql-lite
| |                        feat(slayql): add ablation study controls, robustness fixes, and baseline comparison report
* | 3b53c20 2026-06-17  SlayQL v2
* | a72cce2 2026-06-16  tag: c-case-v1
| |
| | * b015e42 2026-06-23  slayql-2, origin/slayql-2
| |/                         Introduce SGSA validation module
| * 475ce87 2026-06-23  slayql-1, origin/slayql-1
| * 8770692 2026-06-22  feat: implement full RBP graph propagation and SQL generation pipeline with value grounding support
|/
* af6bad0 2026-06-13  tag: AutoLink, c-case-op-1
                           Initial commit
```

### Key ancestry facts

| Claim | Verified Status |
|---|---|
| `af6bad0` is the common baseline for the later branches | Correct |
| `a72cce2` is an ancestor of `8770692` / `slayql-1` | Incorrect |
| `8770692` is an ancestor of `a72cce2` / `c-case-v1` | Incorrect |
| `475ce87` is an ancestor of `02599b2` / `v1.0.0-slayql-lite` | Correct |
| `02599b2` is an ancestor of `251c7bb`, `5932669`, `ba00dc2`, and `main` | Correct |

The correct interpretation is that there were parallel lines of work from the `AutoLink` base, later integrated into `main`.

---

## 3. Corrected Evolution Timeline

| Phase | Ref | Commit | Verified Milestone | Result Evidence |
|---|---|---:|---|---|
| Phase 0 | `AutoLink` tag / `c-case-op-1` branch | `af6bad0` | Initial AutoLink baseline snapshot. | Current comparison artifacts later report baseline scores, but the score should be attributed to result artifacts, not automatically to the tag itself. |
| Phase 1 | `c-case-v1` tag | `a72cce2` | Evaluation and infrastructure milestone: comparison tools, subset evaluation wrapper, credential/load handling, BigQuery/Snowflake/SQLite execution support in repo code. | No repo-contained `evaluation_suite/` directory was found at this commit; `run/evaluate_subset.py` calls `../evaluation_suite/evaluate.py`, apparently external to this repo snapshot. |
| Phase 1b | main-line commit | `3b53c20` | Adds `SlayQL v2` code including `run/slayql2_schema_engine.py`, scratch schema-completion utilities, config changes, and SQL generation/revision changes. | This commit exists on the main-line path and is omitted from the original report's evolution table. |
| Phase 2 | `slayql-1` branch history | `8770692` | Adds full RBP graph propagation and SQL generation pipeline with value grounding support. | Supported by committed changes including `run/rbp_graph.py`, `run/value_grounder.py`, and retrieval/generation changes. |
| Phase 2b | `slayql-1` branch tip | `475ce87` | Enhances value grounding with stop-word filtering, numeric thresholding, capped hint injection, and improved RBP behavior. | Supported by `run/value_grounder.py`, `run/rbp_graph.py`, and `run/it_ee.py` on branch `slayql-1`. |
| Phase 3 | `slayql-2` branch | `b015e42` | Introduces SGSA as **Self-Generated Semantic Assertions** validation. | Supported by `run/semantic_validator.py`, `run/sql_execution.py`, `run/sql_generation.py`, and `run/sql_revise.py` on branch `slayql-2`. |
| Phase 4 | `v1.0.0-slayql-lite` tag | `02599b2` | SlayQL-Lite release snapshot with RBP/value grounding/IT-EE-related code and comparison/report generation scripts. | This is the actual release tag target. |
| Phase 4b | post-release branch commit | `251c7bb` | Adds resilient batch generation, retry handling, failed-task tracking, ablation scripts, status/memory docs, and related SQL generation updates. | Supported by `run/sql_generation.py`, `STATUS.md`, `memory.txt`, and ablation scripts. |
| Phase 4c | docs commit | `5932669` | Updates `README.md` with architecture, benchmark results, and ablation findings. | Documentation-only or documentation-heavy update. |
| Phase 4d | `slayql-lite` tip | `ba00dc2` | Adds/updates `PROJECT_EVOLUTION_REPORT.md` and expands README manuscript content. | Current `slayql-lite` branch tip. |
| Phase 5 | `main` | `2b1719f` | Merges `slayql-lite` into `main`. | Current production-integrated main branch. |

---

## 4. Architecture Evolution, Corrected

### 4.1 AutoLink Baseline

The `AutoLink` tag points to the initial repository snapshot at `af6bad0`.

The original report describes the AutoLink baseline as a fixed-turn schema exploration and SQL generation pipeline over dense schema retrieval. The local repository structure supports the presence of baseline pipeline components, including:

- `run/generate_docs.py`
- `run/embedding_docs.py`
- `run/retrieve_topk_schema.py`
- `run/complete_schema.py`
- `run/sql_generation.py`
- `run/sql_selection.py`

The current result artifact `run/comparison_report.md` reports:

| Framework | Correct / Total | Accuracy |
|---|---:|---:|
| Baseline | 71 / 178 | 39.9% |
| SlayQL Enhanced | 72 / 178 | 40.4% |

This is a valid local artifact result, but it should be cited as a comparison-artifact result, not as proof that the `AutoLink` tag itself originally contained that exact benchmark state.

### 4.2 `c-case-v1`: Evaluation and Execution Infrastructure

The `c-case-v1` tag points to `a72cce2`.

Verified code changes include:

- comparison tooling such as `run/compare_batch_ex.py` and `run/compare_outputs.py`;
- subset evaluation wrapper `run/evaluate_subset.py`;
- credential and execution handling in `run/complete_schema.py` and `run/sql_execution.py`;
- BigQuery and Snowflake references in configuration and execution code;
- generated comparison/detailed-analysis artifacts.

Correction to the original report:

- `c-case-v1` is a tag at `a72cce2`, not the tip of `c-case-op-1`.
- `c-case-op-1` remains at `af6bad0`.
- The file `evaluation_suite/evaluate.py` is not tracked inside this repository at `a72cce2`; the repo wrapper calls it from `../evaluation_suite/evaluate.py`.

### 4.3 `3b53c20`: Main-Line SlayQL v2 Commit

The commit `3b53c20` exists between `c-case-v1` and the final main merge path.

Verified changed files include:

- `run/slayql2_schema_engine.py`
- `run/scratch_complete_schema.py`
- `run/scratch_update_config.py`
- `run/restore.py`
- `run/sql_generation.py`
- `run/sql_revise.py`
- `run/config.py`
- `run/run_diverse_batch.py`

This milestone is absent from the original report's master version table, but it is part of the actual main-line evolution.

### 4.4 `slayql-1`: RBP and BM25 Value Grounding

The `slayql-1` branch contains commits `8770692` and `475ce87` on top of `AutoLink`.

Verified implementation evidence:

- `run/rbp_graph.py` implements RBP graph propagation logic.
- `run/retrieve_topk_schema.py` integrates RBP into schema retrieval.
- `run/value_grounder.py` uses `rank_bm25.BM25Okapi`.
- `run/build_value_indices.py` appears in the branch history for value index construction.
- `run/it_ee.py` implements IT-EE-related analysis, but the code comments at `475ce87` describe a "Safe Exit" design where `should_early_exit` is always `False` in that refactored version.

Important correction:

- The code labels RBP as **Relevance-Based Propagation** in `run/rbp_graph.py`.
- The old report's "Relational Boost Propagation" name is a narrative name, but the code itself uses "Relevance-Based Propagation".
- The old report says value hints are capped at `K=5`; the current `run/value_grounder.py` uses `MAX_HINTS_PER_PROMPT = 3`.

### 4.5 `slayql-2`: SGSA Semantic Assertions, Not Steiner Pruning

The `slayql-2` branch points to `b015e42`.

The committed code shows SGSA means:

```text
Self-Generated Semantic Assertions
```

Verified files on that branch include:

- `run/semantic_validator.py`
- `run/test_semantic_validator.py`
- `run/sql_execution.py`
- `run/sql_generation.py`
- `run/sql_revise.py`

The branch introduces semantic assertion parsing, result validation, and revision-loop integration.

The original report's description of `slayql-2` as:

- Sub-Graph Search Algorithm;
- Steiner Minimal Tree;
- destructive pruning;
- counterfactual rollback;
- over-pruning trap;

is not supported by the local Git evidence. Searches against the branch did not find matching implementation evidence for Steiner/subgraph pruning.

However, the poor `slayql-2` result itself is supported by committed artifacts:

| Artifact at `b015e42` | Baseline | SlayQL / SGSA Variant | Change |
|---|---:|---:|---:|
| `run/comparison_report_v2.md` | 67 / 178 | 27 / 178 | -40 |
| `run/csv_only_comparison_report_v2.md` | 67 / 178 | 27 / 178 | -40 |

Correct interpretation:

> `slayql-2` appears to have been a semantic-assertion validation experiment that performed worse in the available committed comparison artifacts. The cause should not be described as Steiner-tree over-pruning unless separate evidence is added.

### 4.6 `v1.0.0-slayql-lite`: Release Snapshot

The release tag `v1.0.0-slayql-lite` is annotated.

```text
tag object: 839c8d5
target commit: 02599b2
tag message: Release SlayQL Lite
```

Verified release-snapshot files include:

- `README.md`
- `run/rbp_graph.py`
- `run/value_grounder.py`
- `run/it_ee.py`
- `run/generate_ablation_report.py`
- `run/run_autolink_baseline.ps1`
- `run/run_autolink_baseline.sh`
- `run/ablation2_scalability.sh`
- `run/ablation3_hyperparameter.sh`
- `run/ablation4_model_agnostic.sh`

Correction:

- The release tag is not `251c7bb`.
- `251c7bb` is post-release work that adds more batch/ablation operational support.

### 4.7 Post-Release `slayql-lite` Branch and Main Merge

After the release tag:

| Commit | Role |
|---:|---|
| `251c7bb` | Adds resilient batch engine, ablation scripts, failed-task tracking, `STATUS.md`, and `memory.txt`. |
| `5932669` | Updates README with architecture, benchmark results, and ablation findings. |
| `ba00dc2` | Adds/updates full manuscript-style `PROJECT_EVOLUTION_REPORT.md` and README content. |
| `2b1719f` | Merges `slayql-lite` into `main`. |

Verified retry/batch features in `run/sql_generation.py` include:

- `run_batch(...)`;
- `--max_retries`;
- exponential backoff with jitter;
- `sql_gen_failed_tasks.json`;
- rerun handling for failed tasks.

---

## 5. Benchmark Result Evidence

### 5.1 Current Working-Tree Comparison Reports

The current working tree contains multiple comparison artifacts with different meanings/results.

| Artifact | Baseline | SlayQL / Enhanced | Notes |
|---|---:|---:|---|
| `run/comparison_report.md` | 71 / 178 | 72 / 178 | Matches the original report's headline 39.89% vs 40.45%. |
| `run/csv_only_comparison_report.md` | 67 / 178 | 72 / 178 | CSV-only evaluation result; baseline differs from `comparison_report.md`. |
| `run/comparison_report_autolink.md` | 6 / 178 | 18 / 178 | Appears to be a different/incomplete comparison context; should not be used as the main benchmark without explanation. |

Correct headline if using `run/comparison_report.md`:

| Framework | Correct / Total | Accuracy | Delta |
|---|---:|---:|---:|
| Baseline | 71 / 178 | 39.89% | - |
| SlayQL Enhanced | 72 / 178 | 40.45% | +1 task |

Correct headline if using `run/csv_only_comparison_report.md`:

| Framework | Correct / Total | Accuracy | Delta |
|---|---:|---:|---:|
| Baseline | 67 / 178 | 37.64% | - |
| SlayQL Enhanced | 72 / 178 | 40.45% | +5 tasks |

Recommendation:

> The report should explicitly choose one artifact as authoritative. Otherwise, the baseline score is ambiguous.

### 5.2 `slayql-2` Result Evidence

The committed artifacts at `b015e42` report:

| Variant | Correct / Total | Accuracy |
|---|---:|---:|
| Baseline | 67 / 178 | 37.6% |
| `slayql-2` / SGSA variant | 27 / 178 | 15.2% |

This supports the conclusion that the `slayql-2` experiment degraded performance. It does **not** support the original report's claimed cause of "Steiner/subgraph over-pruning."

### 5.3 Dataset Size

The file `run/subset_diverse_20_evaluation.json` currently contains 178 records despite its name.

This supports use of a 178-instance denominator in the current reports.

---

## 6. Ablation Evidence

### 6.1 Verified Local Ablation Summaries

| Variant | Local Summary File | Correct / Evaluated | Score | Token Evidence |
|---|---|---:|---:|---|
| `w/o RBP` | `run/ablation1_no_rbp/eval_result.txt` | 4 / 178 | 2.25% | 17,418,471 total; 217,730 avg/query |
| `w/o BM25` | `run/ablation1_no_bm25/ablation1_no_bm25/eval_result.txt` | 3 / 178 | 1.69% | 5,652,427 total; 171,285 avg/query |
| `w/o IT-EE` | `run/ablation1_no_itee/ablation1_no_itee/eval_result.txt` | 78 / 168 | 46.43% | 20,473,386 total; 189,568 avg/query |
| `w/o QOC` | `run/ablation1_no_qoc/ablation1_no_qoc/eval_result.txt` | 23 / 66 | 34.85% | Token parser shows 0 total because no token records were parsed in that summary. |

### 6.2 Corrections to the Original Ablation Table

| Original Claim | Verification Result |
|---|---|
| `w/o RBP` = 4 / 178, 17,418,471 tokens | Correct. |
| `w/o BM25` = 3 / 178 | Correct. |
| `w/o BM25` = 18,210,400 tokens, 168,614 avg/query | Not supported by the local `eval_result.txt` checked. Local file says 5,652,427 total and 171,285 avg/query. |
| `w/o IT-EE` = 78 / 168, 20,473,386 tokens, 189,568 avg/query | Correct. |
| `w/o QOC` = 23 / 66 incomplete | Correct as an incomplete accuracy summary. |
| Full SlayQL-Lite = ~28,500,000 tokens | Not reproducible from `run/ablation1_full_slayql`; that directory only contains checkpoint files in the current working tree. |

### 6.3 Interpretation

The ablation artifacts support this cautious conclusion:

- Removing RBP causes severe collapse in the available run.
- Removing BM25 causes severe collapse in the available run.
- Removing IT-EE did not reduce accuracy in the available evaluated subset, but it used high average tokens/query.
- The `w/o QOC` run is incomplete and has no usable token summary in the parsed artifact.

The stronger claim that IT-EE saves exactly or approximately 60% of tokens is plausible from the project narrative, but it is not directly reproducible from a complete full-run token summary in the current local artifacts.

---

## 7. Corrected Summary Matrix

| Identifier | Type | Correct Commit | Verified Description | Result Status |
|---|---|---:|---|---|
| `AutoLink` | Tag | `af6bad0` | Initial baseline snapshot. | Baseline result available in later comparison artifacts. |
| `c-case-op-1` | Branch | `af6bad0` | Branch still points to initial commit. | Not `c-case-v1`. |
| `c-case-v1` | Tag | `a72cce2` | Evaluation/infrastructure milestone. | No repo-contained `evaluation_suite/` directory found. |
| `SlayQL v2` | Commit | `3b53c20` | Main-line SlayQL v2 implementation changes. | Omitted from old report but present in graph. |
| `slayql-1` | Branch | `475ce87` | RBP/value-grounding branch with enhancements. | Implementation supported. |
| `slayql-2` | Branch | `b015e42` | Self-Generated Semantic Assertions validation experiment. | 27 / 178 supported by committed v2 comparison artifacts. |
| `v1.0.0-slayql-lite` | Annotated tag | `02599b2` | SlayQL-Lite release snapshot. | Actual release target. |
| post-release SlayQL-Lite | Commit | `251c7bb` | Resilient batch engine, failed-task tracking, ablation scripts. | Post-release, not the tag target. |
| `slayql-lite` | Branch | `ba00dc2` | Documentation/manuscript branch tip. | Merged to main. |
| `main` | Branch | `2b1719f` | Merge of `slayql-lite` into main. | Current integrated branch. |

---

## 8. Final Corrected Narrative

The project began with the `AutoLink` baseline at `af6bad0`, which provided the initial text-to-SQL pipeline and schema exploration foundation.

From that baseline, the repository evolved along more than one path:

1. The `c-case-v1` tag at `a72cce2` added evaluation and execution infrastructure, including comparison utilities, subset evaluation wrappers, credential handling, and multi-provider execution support. This work is not the direct ancestor of the `slayql-1` branch.
2. The main line then added a `SlayQL v2` commit at `3b53c20`, which introduced additional schema engine and SQL generation/revision work.
3. The `slayql-1` branch developed the core RBP/value-grounding direction, adding graph propagation and BM25-based value grounding.
4. The `slayql-2` branch tested SGSA semantic assertion validation. The committed comparison reports show degraded performance at 27/178, but the implementation is semantic validation, not Steiner-tree schema pruning.
5. The `v1.0.0-slayql-lite` release tag points to `02599b2`, where SlayQL-Lite had the main RBP/value-grounding/IT-EE/report-generation structure.
6. After the release tag, `251c7bb`, `5932669`, and `ba00dc2` added operational robustness, ablation automation, status/memory documentation, and expanded manuscript-style documentation.
7. Finally, `main` at `2b1719f` merged the `slayql-lite` branch into the integrated project state.

The strongest supported empirical headline is:

```text
Using run/comparison_report.md:
Baseline:        71 / 178 = 39.89%
SlayQL Enhanced: 72 / 178 = 40.45%
Delta:           +1 task
```

The alternative current CSV-only artifact reports:

```text
Using run/csv_only_comparison_report.md:
Baseline:        67 / 178 = 37.64%
SlayQL Enhanced: 72 / 178 = 40.45%
Delta:           +5 tasks
```

The corrected report should therefore avoid presenting a single baseline number without naming the exact source artifact.

---

## 9. Recommended Fixes for the Original Report

If `PROJECT_EVOLUTION_REPORT.md` is kept, these edits are required:

1. Replace every `v1.0.0-slayql-lite -> 251c7bb` entry with `v1.0.0-slayql-lite -> 02599b2`; describe `251c7bb` as post-release.
2. Replace `c-case-v1` branch attribution from `c-case-op-1` to a tag-only milestone at `a72cce2`.
3. Add `3b53c20` as a real main-line milestone.
4. Rewrite the `slayql-2` section to describe **Self-Generated Semantic Assertions**, not Sub-Graph Search Algorithm / Steiner pruning.
5. Remove or caveat the "Over-Pruning Trap" explanation unless separate evidence is added.
6. State which result artifact is authoritative: `comparison_report.md` or `csv_only_comparison_report.md`.
7. Correct the `w/o BM25` token totals to match the local eval summary, or cite the missing artifact that supports the old number.
8. Caveat full SlayQL token totals because the current `ablation1_full_slayql` directory does not contain a reproducible `eval_result.txt`.
9. Change the BM25 hint cap from `K=5` to `MAX_HINTS_PER_PROMPT = 3` if describing the current code.
10. Avoid claiming `evaluation_suite/evaluate.py` is repo-contained at `c-case-v1`; describe it as an external evaluator invoked by repo wrappers unless that directory is added.


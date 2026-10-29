# SlayQL v1.5 Research Suite

v1.5 is a targeted relational multi-path revision. It preserves v1.4's model,
candidate counts, existing revision stage, evaluator, metrics, run manifests,
and checkpoint protocol. It does not claim a target score before measurement.

## Why this change exists

The completed BIRD v1.4 subset scored 100/307 (32.57%) with a candidate oracle
of 143/307 (46.58%). The selector regretted 43 instances. Among the 164 cases
where no candidate was correct, 128 (78%) used the same table set in all five
candidates. Selected-vs-gold structural differences were dominated by literal
mapping (79), projection count (57), join count (52), DISTINCT (52), predicate
count (50), aggregation (48), and table set (44). A gold table was absent in 32
cases. These counts identify two actionable gaps:

1. Candidate roles changed wording but usually followed the same semantic path.
2. Model verification saw result shapes, not the values it was choosing between.

Examples confirm the mechanism: a racer query chose `results` instead of the
gold `driverStandings` path; a lap-time query used the plausible `lapTimes`
table instead of the benchmark's `results.FastestLapTime`; count questions
invented latest-row/DISTINCT semantics; identity questions changed requested
output arity.

## What changed

- Interaction evidence computes a shortest-path relational closure over up to
  six question-linked tables. Bridge tables and join endpoints are retained.
- Admitted BM25 value matches are handed to schema linking before focus, so
  unquoted entities can identify their owning table without another model call.
- Schema focus is relaxed from 5/12/48 to 8 tables, 16 columns per table, and 72
  columns total. Closure seeds receive priority while two slots remain reserved
  for the original semantic/RBP retrieval order.
- Five candidates now use different reasoning representations: direct output
  contract, relational DDL path, execution-plan decomposition, counterfactual
  table path, and adversarial semantic audit.
- Join-path and counterfactual candidates receive a complementary DDL-style
  schema view. This is appended to, not substituted for, the normal schema.
- Close, materially disagreeing unique result groups enter a bounded pairwise
  tournament. Comparisons include SQL, contract checks, relationship evidence,
  result column names, and up to five actual rows.
- Prompts explicitly prohibit unrequested DISTINCT, deduplication,
  latest-per-entity logic, concatenation, and output-column changes.

The existing revision stage is intentionally unchanged. Agentar's published
ablation attributes much more value to complementary generation paths than to
iterative refinement, matching the local finding that v1.4 revision usage rose
while semantic errors remained.

## Research basis

- BIRD's official leaderboard reports strong agentic systems above 70% dev EX:
  https://bird-bench.github.io/
- Agentar-Scale-SQL uses intrinsic reasoning, iterative refinement, diverse
  synthesis, and tournament selection; its ablation makes diverse generators
  the strongest directly reusable component: https://arxiv.org/abs/2509.24403
- DeepEye-SQL combines relational closure, N-version generation, deterministic
  validation, and confidence-aware execution selection:
  https://arxiv.org/abs/2510.17586
- CHASE-SQL uses complementary divide-and-conquer/execution-plan paths and
  pairwise candidate selection: https://arxiv.org/abs/2410.01943
- CHESS supports targeted schema selection and specialized agents rather than
  one monolithic prompt: https://arxiv.org/abs/2405.16755
- ReViSQL documents material BIRD annotation/data issues. v1.5 therefore keeps
  official metrics but treats some plausible-vs-gold mismatches as an analysis
  caveat, never as inference-time gold access: https://arxiv.org/abs/2603.20004

Fine-tuning/RL and unconditional metadata extraction were not added. They need
separate training-data and ablation protocols and do not directly isolate the
measured v1.4 gaps.

## Pre-run structural check

An offline diagnostic applied v1.5 focus to the unfocused v1.3 prompts for the
same 307 BIRD questions. Gold-table macro recall was 99.89%, with every gold
table retained for 306/307 questions, compared with v1.4's measured 96.73%
table recall. The remaining unquoted-name case (`Lewis Hamilton`) was resolved
by the BM25 schema-seed handoff in a separate no-LLM probe. This diagnostic uses
gold SQL only after retrieval to measure coverage; gold is never available to
the inference stages. It validates schema availability, not execution accuracy.

## Subset commands

Run from `D:\SlayQL-v1.1` in PowerShell. Re-run the exact command and run ID
after an interruption; completed stages and per-instance artifacts resume.

```powershell
# BIRD dev, five candidates
.\C-CaSE\run\run_research_suite_v15.ps1 `
  -Command run -Dataset bird -Split dev -Mode subset20 `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\bird_dev_full\aggregates\summary_metrics.json" `
  -RunId v15_bird_dev_subset20

# Spider 1.0, three candidates
.\C-CaSE\run\run_research_suite_v15.ps1 `
  -Command run -Dataset spider1 -Split test -Mode subset20 `
  -NumCandidates 3 `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\spider1_test_full_3cand\aggregates\summary_metrics.json" `
  -RunId v15_spider1_test_subset20

# Spider 2.0-Lite local + BigQuery; Snowflake remains excluded by default
.\C-CaSE\run\run_research_suite_v15.ps1 `
  -Command run -Dataset spider2-lite -Split test -Mode subset20 `
  -RunId v15_spider2lite_test_subset20
```

v1.2-v1.4 SQL-generation outputs cannot be resumed into a v1.5 run because the
candidate prompts and schema evidence changed. Their evaluation summaries are
valid reference inputs for deterministic subset stratification and comparison.

`aggregates/summary_metrics.json` remains canonical. Also inspect
`research_summary.json`, `schema_focus_manifest.json`, `interaction/*.json`,
and `selection/*.json` for oracle accuracy, regret, closure coverage, tournament
decisions, usage, and backend exclusions.

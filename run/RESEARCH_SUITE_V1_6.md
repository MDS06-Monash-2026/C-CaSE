# SlayQL v1.6 Research Suite

v1.6 is a targeted semantic-fidelity and candidate-diversity revision. It keeps
the v1.5 model, retrieval/RBP, BM25 grounding, schema limits, candidate counts,
SQL execution/revision stages, evaluator, metrics, and checkpoint protocol. It
does not claim an accuracy increase until the same deterministic subset is run.

## What the completed runs established

The comparable 307-question BIRD subset has the following trajectory:

| Version | Final correct | Candidate oracle | Selection regret |
| --- | ---: | ---: | ---: |
| v1.1 reference stratum | 61 | not available | not available |
| v1.2 | 93 (30.29%) | 137 (44.63%) | 44 |
| v1.3 | 99 (32.25%) | 137 (44.63%) | 38 |
| v1.4 | 100 (32.57%) | 143 (46.58%) | 43 |
| v1.5 | 100 (32.57%) | 144 (46.91%) | 44 |

This subset intentionally contains 20% v1.1-correct and 80% v1.1-wrong cases,
so its raw accuracy is a hard-case development gate, not an unbiased estimate
of full-dev accuracy. Reweighting the two strata to the full BIRD dev
distribution gave a v1.5 proxy of 52.42%, still well below the 75% target.

The v1.5 change improved schema availability but not final accuracy:

- Gold-table macro recall rose from 96.73% to 99.10%, while column recall rose
  from 91.73% to 96.16%.
- Prompt tokens rose 26.68%, total tokens rose 16.81%, and estimated cost rose
  8.98% compared with v1.4.
- Among v1.5 no-oracle cases, 130/163 still used one table set across all five
  candidates. The average number of unique table sets was only 1.23.
- The v1.5 pairwise tournament changed 84 selections, improved 14, and harmed
  8. v1.4's simpler verifier had a larger measured net gain (+13 versus +6).
- 168 questions were wrong in every v1.2-v1.5 final output. Of these, 126 never
  had a correct candidate and 42 had a correct candidate in at least one run.

Broad inspection, rather than one-example tuning, found recurring failures:

1. Evidence fidelity: generated SQL replaced provided formulas or row
   multiplicity with plausible `AVG`, `DISTINCT`, latest-row, `EXISTS`, or
   deduplication semantics.
2. Output fidelity: candidates exposed filter/order/helper fields or returned
   an entity plus extra descriptive columns not requested by the question.
3. Correlated relation paths: different-looking SQL repeatedly chose the same
   fact table and missed alternatives such as standings versus results.
4. Aggregation/grouping/set behavior: v1.5 solved only 3/37 grouping cases and
   0/2 set-operation cases on this subset.
5. Selection: result-aware judging sometimes preferred a richer or more
   realistic answer over the benchmark's exact evidence and output contract.
6. Dataset noise: several question/evidence/gold triples are contradictory.
   v1.6 records this limitation; it never reads gold SQL during inference.

## v1.6 architecture

### Deterministic semantic contract

`semantic_contract.py` compiles the raw question and dataset evidence into
required formula operations, mapped columns, literals, and a minimal output
contract. The same cached contract is appended to generation context and scored
by the selector. This costs no model call. Projection count is enforced only
for high-confidence grammar; lower-confidence parses remain advisory.

The contract explicitly rejects unrequested `DISTINCT`, latest-row logic,
deduplication, formula substitutions, and extra output columns. This addresses
the dominant literal/projection/predicate/aggregation errors as one semantic
class instead of adding fixes for individual question IDs.

### Enforced relation-route diversity

`candidate_router.py` builds connected route hypotheses from lexical matches,
BM25 value links, relational closure, and the relationship catalog. Candidates
0, 1, 3, and 4 receive different bounded table views when alternatives exist.
Candidate 2 always receives the complete focused schema as a recall fallback.

Assignments are saved in `candidate_routes/<instance>_<candidate>.json`.
Unlike v1.5's appended DDL guidance, routed candidates cannot silently collapse
onto an unassigned dominant table path. Spider 1.0's three-candidate default
still includes primary, alternative, and full-schema routes.

### One contract/result verifier

The deterministic selector now scores semantic-contract compliance alongside
execution, legacy contract checks, result shape, grounding, and diversity. On a
close material disagreement, v1.6 sends the top three distinct execution-result
groups to one listwise verifier call. It includes bounded result previews and
instructs the verifier that dataset evidence and minimal requested output
outrank outside-world plausibility. This replaces v1.5's up-to-three-call
pairwise tournament without reducing SQL-generation turns or prompt context.

SQL revision is unchanged. The local evidence shows semantic interpretation
and correlated candidates are the bottlenecks; a larger unconditional repair
stage would spend tokens after the important decisions were already wrong.

## Offline validation before model execution

These checks use the 307 completed v1.5 artifacts only to test deterministic
mechanics. Gold SQL is inspected after contract/route construction for
diagnostics and is never an input to inference.

- All 307 questions received at least three unique assigned table sets across
  five candidates. Mean assigned diversity was 4.59; 191 received five unique
  views, 107 received four, and 9 received three.
- Candidate 2 retained the full focused schema for all 307 questions.
- High-confidence output contracts matched the prior gold projection shape in
  117/123 cases (95.12%). Ambiguous parses are not projection-scored.
- The new and modified Python modules compile successfully. Focused unit tests
  cover contracts, full-name mappings, route diversity/fallback, and v1.6
  interaction caching; the full test suite is left for the requested user run.

These validate architecture invariants, not accuracy. Candidate execution and
official evaluation are required to determine whether v1.6 improves results.

## Research basis

- The current [BIRD leaderboard](https://bird-bench.github.io/) shows that
  strong systems use substantial orchestration and reports both EX and R-VES.
  It also identifies a cleaner 2026 dev release; record the exact BIRD split in
  comparisons because this workspace currently uses `dev_20240627`.
- [Agentar-Scale-SQL](https://arxiv.org/abs/2509.24403) combines diverse
  synthesis, refinement, and tournament selection. v1.6 keeps diversity but
  makes relation routes deterministic and replaces the locally weaker
  tournament.
- [CHASE-SQL](https://arxiv.org/abs/2410.01943) supports complementary
  generation paths and candidate selection. v1.6 adopts the multi-path
  principle without adding model calls for synthetic examples.
- [CHESS](https://arxiv.org/abs/2405.16755) supports targeted schema selection
  and specialized stages rather than a single monolithic prompt.
- [Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards](https://arxiv.org/abs/2601.08778)
  measures material annotation problems in BIRD and Spider 2.0-Snow.
- [ReViSQL](https://arxiv.org/abs/2603.20004) argues that verified data and
  model training can outperform added harness complexity. v1.6 therefore stays
  small; RLVR or fine-tuning requires a separate training-data protocol.

## Subset commands

Run from `D:\SlayQL-v1.1` in PowerShell. If interrupted, rerun the exact command
with the same run ID. Existing task artifacts and completed stages resume.

```powershell
# BIRD dev, five candidates
.\C-CaSE\run\run_research_suite_v16.ps1 `
  -Command run -Dataset bird -Split dev -Mode subset20 `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\bird_dev_full\aggregates\summary_metrics.json" `
  -RunId v16_bird_dev_subset20

# Spider 1.0, three candidates
.\C-CaSE\run\run_research_suite_v16.ps1 `
  -Command run -Dataset spider1 -Split test -Mode subset20 `
  -NumCandidates 3 `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\spider1_test_full_3cand\aggregates\summary_metrics.json" `
  -RunId v16_spider1_test_subset20

# Spider 2.0-Lite local + BigQuery; Snowflake is excluded by default
.\C-CaSE\run\run_research_suite_v16.ps1 `
  -Command run -Dataset spider2-lite -Split test -Mode subset20 `
  -RunId v16_spider2lite_test_subset20
```

v1.5 SQL-generation outputs cannot be resumed into v1.6 because candidate
schema views and prompts changed. Previous `summary_metrics.json` files remain
valid reference inputs for subset stratification and paired comparison.

The canonical evaluation remains `aggregates/summary_metrics.json`. Also inspect
`research_summary.json`, `interaction/*.json`, `candidate_routes/*.json`,
`schema_focus_manifest.json`, `selection/*.json`, and `usage/` for target gap,
oracle accuracy, regret, route diversity, semantic checks, and token cost.

# SLAYQL Lightweight Accuracy Handover

## 1. Purpose

This document describes the lightweight accuracy work added to the SLAYQL
Spider 2.0 pipeline, why each change exists, how the components fit together,
and how to run the three-question end-to-end smoke test.

The implementation is intended to improve SQL accuracy without replacing the
existing SLAYQL architecture or returning to an expensive, fixed-cost strategy
for every question. The main approach is to spend more computation only when a
question appears structurally difficult, while preserving explicit evidence
between retrieval, schema completion, generation, execution, and selection.

The original implementation plan remains in:

```text
SLAYQL_LIGHTWEIGHT_ACCURACY_IMPLEMENTATION_PLAN.md
```

## 2. Baseline Problems Addressed

Analysis of the previous Spider 2.0 run identified the following architectural
problems:

1. Retrieval uncertainty was effectively saturated, causing almost every
   question to receive the same expensive schema-completion budget.
2. Relationship-based pruning received table names but little useful graph
   evidence about how tables could be joined.
3. Schema completion could execute a useful SQL draft but did not reliably
   preserve that draft as evidence for later stages.
4. Multiple SQL candidates came from the same model and prompt, making their
   errors highly correlated. Majority agreement therefore did not necessarily
   indicate correctness.
5. Revision mainly handled SQL that failed to execute. SQL that executed but
   violated the question semantics could pass through unchanged.
6. Dialect routing was duplicated, including inconsistent handling of `ga*`
   instances.
7. SQL extraction could choose the longest fenced block instead of the final
   answer block.
8. Evaluation and logs emphasized aggregate accuracy and did not provide a
   durable per-question explanation of retrieval, generation, execution,
   selection, and correctness.
9. The fixed five-candidate and high-turn strategy consumed unnecessary tokens
   on straightforward questions.

## 3. New Architecture

The intended lightweight path is:

```text
Spider question subset
    -> retrieval pool
    -> focused table-balanced schema
    -> relationship metadata
    -> easy/medium/hard operating mode
    -> query contract
    -> adaptive schema completion
    -> contract-augmented final schema prompt
    -> adaptive SQL candidates
    -> execution and bounded error artifacts
    -> semantic validation and optional one-shot repair
    -> evidence-based selection
    -> official evaluation and per-question report
```

The original pipeline remains available. New outputs use explicit log and
artifact directories so baseline results are not overwritten.

## 4. Configuration

The central configuration is:

```text
run/config/lightweight_accuracy.json
```

Important defaults are:

| Area | Setting | Default |
|---|---|---:|
| Retrieval | Initial column pool | 40 |
| Retrieval | Maximum selected tables | 5 |
| Retrieval | Maximum columns per table | 6 |
| Retrieval | Maximum prompt columns | 30 |
| Completion | Easy turns | 1 |
| Completion | Medium turns | 2 |
| Completion | Hard turns | 4 |
| Generation | Easy candidates | 1 |
| Generation | Medium candidates | 2 |
| Generation | Hard candidates | 3 |
| Generation | Maximum output tokens | 4096 |
| Revision | Semantic repair attempts | 1 |

Selection weights reserve most of the score for contract and result evidence,
with smaller contributions from schema coverage, consistency, and simplicity.
This prevents same-model majority agreement from dominating stronger semantic
evidence.

## 5. Implemented Components

### 5.1 Shared Artifact Storage

File:

```text
run/artifact_store.py
```

This module provides:

- Atomic text and JSON writes using a temporary file and `os.replace`.
- Per-instance artifact paths.
- JSONL and CSV writers.
- SHA-256 helpers for reproducibility and future manifest validation.
- Loading of the central lightweight configuration.

Atomic writes reduce the chance of partially written artifacts when a run is
interrupted.

### 5.2 Central Dialect Routing

File:

```text
run/dialect.py
```

The shared mapping is:

| Instance prefix | Dialect |
|---|---|
| `bq*` | BigQuery |
| `ga*` | BigQuery |
| `sf*` | Snowflake |
| `local*` | SQLite |

Unknown prefixes fail closed with `ValueError`. The purpose is to eliminate
silent fallback to the wrong SQL dialect.

### 5.3 Query Contracts

File:

```text
run/pipeline_types.py
```

The `QueryContract` structure carries durable semantic information such as:

- Required and optional tables.
- Required columns.
- Join evidence.
- Literal filters extracted from the question.
- Grouping and operation requirements.
- Required output invariants.
- Forbidden assumptions and SQL patterns.
- Operating mode.
- Optional validated SQL draft evidence.

The contract is deliberately conservative. It should record evidence from the
question and schema, not infer unsupported business rules.

Special protections include the previously observed failure patterns around
unrequested `event_name` filters, incorrect city partitioning, and missing
state abbreviations.

### 5.4 Relationship Metadata

File:

```text
run/relationship_metadata.py
```

Relationship metadata is built from:

- BigQuery and Snowflake schema documents.
- SQLite `PRAGMA table_info` and `PRAGMA foreign_key_list` metadata.
- Conservative inferred edges when non-generic columns ending in `_id` match
  across selected tables and have compatible types.

The resulting graph records node count, explicit edges, inferred edges, and a
`ready` or `no_graph` status. Inferred edges remain distinguishable from
explicit foreign keys.

### 5.5 Focused Retrieval and Adaptive Completion

File:

```text
run/prepare_lightweight_inputs.py
```

This stage consumes the keyed `initial_candidates.json` produced by the
existing retriever. It:

1. Reconstructs ranked column records from the parallel candidate arrays.
2. Selects the strongest tables while retaining multiple useful columns from
   each table.
3. Caps the final prompt schema using the central configuration.
4. Builds relationship metadata for the selected tables.
5. Classifies the question as easy, medium, or hard.
6. Sets `dynamic_t_max`, which is already consumed by `complete_schema.py`.
7. Writes retrieval and contract artifacts per question.

A multi-table question without relationship evidence is escalated to hard.
Questions involving ranking, exclusion, per-group output, or temporal
comparison are also conservatively escalated.

### 5.6 Contract Handoff to SQL Generation

File:

```text
run/augment_schema_prompts.py
```

This stage appends a compact JSON contract to each final schema prompt. It uses
the marker:

```text
-- SLAYQL_QUERY_CONTRACT_V1 --
```

The operation is idempotent. Re-running it does not append the contract twice.
This allows the existing SQL generator to receive the contract without a large
rewrite of its prompt-loading architecture.

### 5.7 SQL Semantic Validation

File:

```text
run/semantic_validator.py
```

The validator provides:

- Final fenced SQL block extraction.
- Optional dialect-aware parsing through `sqlglot`.
- Single-statement and query-only checks.
- Placeholder detection.
- Required table and column checks.
- Forbidden SQL-pattern checks.
- Execution-result existence, shape, emptiness, and null checks.
- Selected output-invariant checks.
- Symmetric DataFrame result equivalence that ignores row and column order.

`sqlglot` is optional at import time, but installing it is recommended because
AST validation is stronger than text-only fallback checks.

### 5.8 Execution Artifacts

File:

```text
run/record_execution_artifacts.py
```

The recorder understands the existing directory convention:

```text
<log>/sql_gen/<task>_execution_result_<candidate>/
<log>/sql_gen/<task>_execution_error_<candidate>/
```

For every candidate it records:

- Instance and candidate IDs.
- Success or error status.
- CSV path.
- Result row and column shape.
- Output column names.
- Bounded error text.

Common API key, token, password, secret, and bearer-token patterns are redacted
before errors are persisted.

### 5.9 Adaptive Generation Preparation

File:

```text
run/prepare_generation_inputs.py
```

This optional stage is intended to partition completed questions by operating
mode and materialize a successfully validated schema-completion draft as
candidate zero. The intended candidate budgets are 1/2/3 for easy, medium, and
hard questions.

This stage is not invoked by the current three-question Bash smoke runner. It
must receive an end-to-end compatibility pass against the exact completion
output before being used for a full 547-question run.

### 5.10 Semantic Repair Queue

File:

```text
run/prepare_semantic_repairs.py
```

This optional stage identifies candidates that executed successfully but have
hard semantic validation failures. It writes a separate repair queue containing
the SQL and machine-readable contract violations. The intended repair budget is
one attempt, which prevents open-ended token use.

This queue is not automatically consumed by the three-question smoke runner.

### 5.11 Evidence-Based Selection

File:

```text
run/select_lightweight_sql.py
```

The intended selector:

1. Rejects executed candidates with hard contract failures.
2. Groups genuinely equivalent results using symmetric comparison.
3. Scores execution, contract compliance, validated-draft evidence,
   consistency, and SQL simplicity.
4. Selects the highest-evidence candidate rather than the largest correlated
   model majority.
5. Writes a complete selection manifest and per-question artifacts.

The current smoke runner deliberately uses the established `sql_selection.py`
directory contract. The standalone lightweight selector still requires an
integration pass against the existing `r1_lite_sql_N` and execution-result
directory layout before it should replace legacy selection in a benchmark run.

### 5.12 Per-Question Report

File:

```text
run/build_question_report.py
```

This optional reporting stage produces JSONL and CSV rows for every source
question, including questions with missing predictions or unknown evaluation
status. It attaches retrieval, contract, and selection evidence and assigns a
high-level failure category such as:

- Missing prediction.
- Dialect or syntax failure.
- Schema grounding failure.
- Semantic constraint failure.
- Result-shape failure.
- Execution or evaluation failure.
- Logical mismatch.

The official evaluator currently emits its normal text output in the smoke
path. Producing the detailed question report requires a structured evaluation
JSON input.

### 5.13 Dependencies

The following dependencies were added to `requirements.txt`:

```text
python-dotenv
rank-bm25
sqlglot
tiktoken
```

They support environment loading, value retrieval, SQL parsing, and token
accounting.

### 5.14 Tests

Files:

```text
tests/conftest.py
tests/test_lightweight_accuracy.py
tests/test_lightweight_preparation.py
```

The focused tests cover:

- BigQuery, GA, Snowflake, and SQLite dialect routing.
- Failing closed on unknown dialect prefixes.
- Selecting the final fenced SQL block.
- Symmetric result equivalence.
- Focused retrieval table and column limits.
- Escalating multi-table questions when join evidence is absent.

These tests were created but were not executed during implementation, following
the instruction not to launch runs at that stage.

## 6. Three-Question Smoke Test

Script:

```text
run/run_lightweight_smoke_3.sh
```

The selected Spider 2.0 questions are:

| ID | Backend | Reason for inclusion |
|---|---|---|
| `bq011` | BigQuery / GA4 | Set exclusion and engagement-time semantics; previously identified difficult pattern |
| `sf_bq029` | Snowflake | Time bucketing, aggregation, and inventor filtering |
| `local002` | SQLite | Local execution, regression-derived values, and moving averages |

Together they test all three supported execution backends and several difficult
query structures. This is a pipeline smoke test, not a representative accuracy
benchmark.

### 6.1 Smoke-Test Stages

The script runs:

1. Create `smoke_lightweight_3.json` from the canonical 547-question file.
2. Build BM25 value indices for the subset.
3. Retrieve a pool of 40 schema columns.
4. Focus retrieval, build relationships, create contracts, and assign adaptive
   completion turns.
5. Inject schema IDs.
6. Generate initial schema prompts.
7. Run adaptive schema completion.
8. Postprocess completed schema candidates.
9. Generate final schema prompts and append contracts.
10. Generate at most three SQL candidates per question.
11. Execute candidates and record structured artifacts.
12. Revise execution failures.
13. Select final SQL and run official evaluation unless disabled.

The smoke runner currently uses three candidates for each question because the
legacy generator accepts one global candidate count per invocation. Full
1/2/3 adaptive generation requires running mode partitions separately.

## 7. Prerequisites

Run commands from the repository root unless otherwise stated.

### 7.1 Python Environment

Install project dependencies in the environment used by `python`:

```bash
python -m pip install -r requirements.txt
```

### 7.2 Existing Retrieval Resources

The following directories must already exist:

```text
run/documents/
run/embeddings/
```

The smoke script fails immediately with a clear message if either is absent.

### 7.3 Model Configuration

Configure the model provider variables expected by the existing code in:

```text
run/.env
```

The Bash runner loads this file using `source`. Keep the file compatible with
shell assignment syntax and do not commit credentials.

### 7.4 Database Access

The three-question run requires:

- Working BigQuery credentials for `bq011`.
- Working Snowflake credentials for `sf_bq029`.
- The Spider 2.0 local SQLite resources for `local002`.

Existing credential locations include:

```text
run/bigquery_credentials/
run/snowflake_credential/
run/resource/databases/
```

Credential failures are recorded as execution errors, but a backend connection
failure means that backend has not been fully smoke-tested.

## 8. How to Run

### 8.1 Git Bash

From the repository root:

```bash
bash run/run_lightweight_smoke_3.sh --fresh
```

### 8.2 PowerShell with Git Bash

On Windows:

```powershell
& "C:\Program Files\Git\bin\bash.exe" run/run_lightweight_smoke_3.sh --fresh
```

The default Windows `bash.exe` may route to WSL. If WSL is unavailable or
blocked, use the explicit Git Bash command above.

### 8.3 Resume an Interrupted Run

Run without `--fresh`:

```bash
bash run/run_lightweight_smoke_3.sh
```

The script uses:

```text
run/log_smoke_lightweight_3/.pipeline_ckpt
```

Completed stages are skipped where safe, and pipeline components with their own
per-instance caching resume from existing artifacts.

### 8.4 Run Without Official Evaluation

```bash
bash run/run_lightweight_smoke_3.sh --fresh --skip-eval
```

This runs through selection but does not invoke `evaluation_suite/evaluate.py`.

### 8.5 Clean Restart Behavior

`--fresh` removes only these dedicated smoke-test outputs:

```text
run/log_smoke_lightweight_3/
run/smoke_lightweight_3.json
```

The script contains a guard that refuses to recursively remove an unexpected
log directory. It does not modify full-run or ablation log directories.

## 9. Output Layout

Primary output directory:

```text
run/log_smoke_lightweight_3/
```

Important outputs are:

| Path | Meaning |
|---|---|
| `.pipeline_ckpt` | Resume checkpoints |
| `initial_candidates.raw.json` | Unmodified retrieval output |
| `initial_candidates.json` | Focused retrieval used downstream |
| `artifacts/retrieval/<id>.json` | Operating mode, turns, tables, columns, graph metadata |
| `artifacts/contracts/<id>.json` | Per-question query contract |
| `schema_prompts/<id>.txt` | Initial schema prompt |
| `candidates/` | Schema-completion cache |
| `filled_schema.json` | Postprocessed completed schema |
| `final_schema_prompts/<id>.txt` | Final prompt including compact query contract |
| `sql_gen/r1_lite_sql_generation_N/` | Raw model responses |
| `sql_gen/r1_lite_sql_N/` | Extracted SQL candidates |
| `sql_gen/r1_lite_execution_result_N/` | Successful execution CSV files |
| `sql_gen/r1_lite_execution_error_N/` | Execution error files |
| `artifacts/execution/candidate_N/<id>.json` | Sanitized execution artifact |
| `sql_revise/` | Revised SQL for failed candidates |
| `sql_selection/final/` | Selected final execution results |
| `eval_result.txt` | Official evaluator output |

The raw retrieval file is retained so focused retrieval decisions can be
audited against the original ranking.

## 10. Smoke-Test Success Criteria

A successful smoke test should satisfy all of the following:

1. The subset file contains exactly `bq011`, `sf_bq029`, and `local002`.
2. Retrieval produces an entry for all three IDs.
3. Three focused retrieval artifacts and three contracts exist.
4. Initial and final schema prompts exist for all three IDs.
5. At least one SQL file is generated for every question.
6. Every generated candidate is represented by either a result CSV or an error
   file.
7. SQL revision and selection complete without an uncaught exception.
8. Official evaluation writes `eval_result.txt`, unless `--skip-eval` was used.
9. No full-run or ablation output directory is modified.

The script enforces minimum generated-SQL and execution-artifact counts. An SQL
execution error is recorded and can proceed to revision; it is not silently
treated as success.

## 11. Troubleshooting

### Missing Documents or Embeddings

Symptom:

```text
Missing run/documents
```

or:

```text
Missing run/embeddings
```

Generate the repository's schema documents and embeddings before retrying.

### Model Authentication Failure

Check `run/.env` and the model configuration used by `run/model_manager.py`.
Avoid printing secrets into logs.

### BigQuery Failure

Confirm the active credentials can access the GA4 dataset required by `bq011`.
Inspect:

```text
run/log_smoke_lightweight_3/sql_gen/r1_lite_execution_error_*/bq011.txt
run/log_smoke_lightweight_3/artifacts/execution/candidate_*/bq011.json
```

### Snowflake Failure

Confirm the configured Snowflake account, warehouse, database, and role can
query the patents data required by `sf_bq029`.

### Local SQLite Failure

Confirm the local Spider database files exist below
`run/resource/databases/`. Check that the configured database path matches the
`E_commerce` database used by `local002`.

### Script Resumes from an Unwanted Stage

Use:

```bash
bash run/run_lightweight_smoke_3.sh --fresh
```

Do not manually remove shared retrieval documents, embeddings, or full-run log
directories.

### WSL Bash Access Denied

Use Git Bash explicitly:

```powershell
& "C:\Program Files\Git\bin\bash.exe" run/run_lightweight_smoke_3.sh --fresh
```

## 12. Verification Performed

The following non-pipeline verification was completed:

- Git Bash accepted `run_lightweight_smoke_3.sh` with `bash -n`.
- The touched Python modules passed AST syntax parsing.
- `bq011`, `sf_bq029`, and `local002` were confirmed in
  `run/spider2_data.json`.
- `git diff --check` reported no whitespace errors for the smoke-test changes.

The following were deliberately not run:

- The three-question smoke pipeline.
- Model API requests.
- BigQuery, Snowflake, or SQLite queries.
- The focused unit tests.
- The full 547-question benchmark.

Therefore, syntax and static integration have been checked, but runtime success
and accuracy have not yet been established.

## 13. Current Integration Status

| Component | Implemented | Used by three-question smoke | Runtime validated |
|---|---:|---:|---:|
| Focused retrieval | Yes | Yes | No |
| Relationship metadata | Yes | Yes | No |
| Query contracts | Yes | Yes | No |
| Adaptive completion turns | Yes | Yes | No |
| Contract prompt handoff | Yes | Yes | No |
| Three-candidate cap | Yes | Yes | No |
| Structured execution artifacts | Yes | Yes | No |
| Semantic validator | Yes | Indirect/future selection path | No |
| Adaptive 1/2/3 generation partitions | Partial integration | No | No |
| Semantic repair queue | Implemented as optional stage | No | No |
| Evidence-based selector | Implemented as optional stage | No | No |
| Per-question JSONL/CSV report | Implemented as optional stage | No | No |
| Official evaluator | Existing | Yes | No for this smoke run |

## 14. Recommended Next Steps

1. Run the three-question smoke test with `--fresh` and preserve the complete
   console output.
2. Confirm all three backends connect and each ID reaches selection.
3. Run the focused unit tests.
4. Fix any runtime interface mismatch before expanding the subset.
5. Integrate mode-partitioned generation so easy, medium, and hard questions
   actually use 1, 2, and 3 candidates respectively.
6. Adapt the evidence-based selector to the repository's existing
   `r1_lite_sql_N` and execution directory structure, then add it to the smoke
   path behind a feature flag.
7. Feed semantic failures through the one-attempt repair queue and re-execute
   repaired candidates before selection.
8. Make official evaluation emit structured per-question records and run
   `build_question_report.py`.
9. Expand to a balanced 20-question subset before attempting all 547 questions.
10. Compare accuracy, execution failure rate, average completion turns,
    generated candidates, and token use against the preserved baseline.

## 15. Handover Summary

The core improvement is a shift from fixed-cost, majority-driven generation to
an evidence-preserving architecture. Retrieval is compact and table-balanced,
relationship evidence is explicit, completion effort depends on difficulty,
and each question receives a durable contract and execution trail.

The three-question runner provides the first end-to-end runtime checkpoint for
the enhanced retrieval, contract, completion, generation, execution, revision,
selection, and evaluation flow. It is intentionally isolated from full-run and
ablation outputs. The next engineer should run this smoke test before enabling
the optional semantic repair, adaptive generation partitioning, or standalone
evidence-based selector on a larger dataset.

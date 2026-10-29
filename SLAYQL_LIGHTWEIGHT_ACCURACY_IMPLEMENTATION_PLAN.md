# SlayQL Lightweight Accuracy Implementation Plan

Status: Proposed  
Scope: Spider 2.0-Lite SlayQL pipeline  
Baseline: 251 correct out of 527 evaluated outputs (47.63%), with 20 additional non-evaluable IDs  
Primary objective: Improve semantic accuracy while reducing model calls, prompt size, token consumption, and avoidable database work  

## 1. Purpose

This plan improves the existing SlayQL architecture without replacing its overall pipeline:

```text
1. BM25 value index
2. Schema retrieval
3. Identifier enrichment
4. Initial schema prompt
5. Schema completion
6. Candidate post-processing
7. Final schema prompt
8. SQL generation
9. SQL execution
10. SQL revision
11. SQL selection
12. Evaluation and reporting
```

The implementation changes what each stage produces, what evidence is preserved between stages, when expensive work is allowed, how candidates are validated and selected, and how every question is logged after evaluation.

No Text-to-SQL architecture can guarantee that every answer is correct. In this plan, "bulletproof" means:

- Every known architectural failure has prevention, detection, fallback, tests, and logging.
- Runtime stages never have access to gold answers or correctness labels.
- Every expected dataset ID receives a terminal status.
- Every selected query is traceable to retrieval evidence, a query contract, candidates, checks, execution, selection, and evaluation.
- Historical logs are preserved and new behavior is feature-gated and reversible.
- A new version cannot replace the baseline unless it passes explicit accuracy, coverage, reliability, and efficiency gates.

## 2. Goals and Non-Goals

### 2.1 Goals

- Improve full-set execution accuracy above the current 251 correct IDs.
- Recover correct candidates currently discarded by majority-result selection.
- Reduce silent semantic errors such as wrong filters, joins, grouping grain, date windows, ranking scope, and output shape.
- Preserve validated schema-completion drafts instead of regenerating from scratch.
- Reduce normal schema context from up to 100 columns to a focused, expandable set.
- Make completion turns and candidate count adaptive.
- Use deterministic local checks before spending another LLM call.
- Log every question, selected SQL, output metadata, candidate evidence, correctness, error category, token usage, calls, and timing.
- Keep the existing Windows/PowerShell and resume-safe workflow.

### 2.2 Non-goals

- Replacing SlayQL with a separate agent framework.
- Adding a hosted service, vector database, workflow engine, or new model provider.
- Using gold results during retrieval, generation, revision, or selection.
- Guaranteeing a fixed accuracy gain before controlled evaluation.
- Re-running or overwriting `run/log_spider2_full_slayql/`.
- Treating inaccessible external tables or credentials as model-quality failures.
- Increasing candidate count or completion turns globally.

## 3. Baseline to Freeze

| Metric | Current value | Reporting rule |
|---|---:|---|
| Expected IDs | 547 | Fixed primary denominator |
| Evaluated outputs | 527 | Report as execution/evaluation coverage |
| Correct outputs | 251 | Preserve exact ID set for paired comparison |
| Evaluated-only EX | 47.63% | Secondary metric: 251 / 527 |
| Full-set EX | 45.89% | Primary metric: 251 / 547 |
| Executed but incorrect | 276 | Main semantic-accuracy target |
| Non-evaluable failures | 20 | Report by stable failure category |
| Traced completion questions | 187 | Preserve token-accounting scope |
| Approximate average traced tokens | 158,873 | Existing token baseline, with estimation caveat |

### 3.1 Baseline artifacts

Preserve these without modification:

- `run/log_spider2_full_slayql/`
- `run/log_spider2_full_slayql/eval_result.txt`
- `run/log_spider2_full_slayql/eval_result.txt.before_retry`
- `run/comparison_report_full.md`
- `run/retry_failed_25.log`
- `error_log.txt`

All new work must use a versioned directory such as:

```text
run/log_spider2_full_slayql_v2/
```

### 3.2 Known failures this plan must address

| Problem | Current evidence | Required defense |
|---|---|---|
| Entropy saturation | Correct and wrong cases average about 0.995 and 0.996; all 547 get 10 turns | Replace entropy-only control with score margin, schema coverage, and ambiguity features |
| RBP lacks relationship edges | Retrieval passes only table names to graph code | Build and pass real foreign-key/table metadata; log no-graph fallback |
| Retrieval is too broad | Top-N is 100; prompts include large nested types and samples | Table-first retrieval, column caps, nested leaf paths, bounded expansion |
| Exact lookup uses embeddings | Exact ACS `VALUE` request can return unrelated timeseries columns | Exact identifier lookup before semantic fallback |
| Validated work is discarded | `local070` completion found and ran the correct draft, but only schema columns were persisted | Compact query contract plus persisted validated draft |
| Candidate errors are correlated | Five candidates use the same model and prompt | Role-specific candidates and adaptive count |
| Successful wrong SQL is accepted | Revision only handles execution errors | Static semantic checks, result invariants, and one bounded semantic repair |
| Majority voting reinforces errors | Wrong 3-candidate cluster beat correct `local070` candidate | Contract-first scoring; consistency only weak evidence |
| Tie voting repeats model bias | Correct and wrong `bq011` results tied; model chose unsupported extra filter | Deterministic constraint checks before optional tie call |
| Dialect routing is inconsistent | `ga*` executes as BigQuery but generation/revision can use Unknown/SQLite | One shared dialect resolver |
| SQL extraction contradicts prompt | Prompt says final block; parser chooses longest block | Parse final non-empty SQL block and validate one statement |
| Candidate clustering is permissive | Comparison is asymmetric and does not enforce one-to-one columns | Symmetric result signatures and one-to-one column matching |
| Evaluator logs only correct IDs | Aggregate output and correct-ID CSV omit complete wrong/missing records | Per-ID evaluation JSON plus complete JSONL/CSV/Markdown reports |
| Evaluator has shared side effect | Global `log.txt` is opened at import | Explicit log path and no import-time file writes |

## 4. Design Principles

1. Preserve evidence, not conversation bulk.
2. Spend computation only when uncertainty is actionable.
3. Treat execution success as necessary but not sufficient.
4. Prefer deterministic validation to additional model calls.
5. Generate alternatives for named ambiguities, not random duplicates.
6. Use exact schema resolution before semantic retrieval.
7. Keep inference and gold evaluation physically and logically separate.
8. Make every artifact versioned, atomic, resumable, and attributable.
9. Report accuracy on all 547 IDs as the primary number.
10. Evaluate changes by paired question IDs, not aggregate percentage alone.

## 5. Target Architecture

```text
Question
  -> focused table/column/value retrieval
  -> compact query contract
  -> optional bounded exploration and validated draft
  -> 1 to 3 role-specific candidates
  -> SQL parse and semantic checks
  -> execution and result invariants
  -> at most one semantic repair when justified
  -> contract-aware selection
  -> final SQL/result artifact
  -> isolated gold evaluation
  -> per-question correctness and aggregate reports
```

### 5.1 Lightweight operating modes

| Mode | Trigger | Completion turns | Candidate policy | Tie-break |
|---|---|---:|---:|---:|
| Easy | Strong retrieval margin, one table, complete schema coverage, no unresolved relation | 0-1 | 1 | Never |
| Medium | Multiple operations or one verified join, but complete contract | Up to 2 | Up to 2 | Only on material unresolved disagreement |
| Hard | Missing join path, nested structure, ambiguous metric, set exclusion, ranking, or failed draft | Up to 4 | Up to 3 | At most once |

Ten completion turns must not remain the default. Four is the initial hard cap, and any increase requires measured development-set benefit.

## 6. Shared Artifact Contracts

Use Python dataclasses or validated dictionaries and JSON persistence. Do not add a database or service.

### 6.1 Query contract

Each ID receives:

```text
<log_path>/contracts/<instance_id>.json
```

Logical example:

```json
{
  "schema_version": "1.0",
  "instance_id": "local070",
  "db_name": "city_legislation",
  "dialect": "sqlite",
  "objective": "Find shortest and longest global streaks of distinct dates",
  "required_tables": ["cities"],
  "optional_tables": [],
  "required_columns": [
    "cities.country_code_2",
    "cities.insert_date",
    "cities.city_name"
  ],
  "joins": [],
  "filters": [
    {
      "expression": "country_code_2 = 'cn'",
      "source": "question",
      "required": true
    },
    {
      "expression": "insert_date in July 2021",
      "source": "question",
      "required": true
    }
  ],
  "grouping_grain": "one row per selected distinct date",
  "operations": [
    "deduplicate dates",
    "group consecutive dates",
    "select minimum and maximum streak lengths",
    "select one city per date"
  ],
  "output_columns": ["date", "city_name"],
  "ordering": ["date ascending"],
  "required_invariants": [
    "one output row per selected date",
    "streaks are global across Chinese-city dates"
  ],
  "forbidden_assumptions": [
    "do not partition streaks by city",
    "do not add an unrelated country-table join"
  ],
  "ambiguities": [],
  "evidence": [],
  "validated_draft": {
    "sql_path": null,
    "execution_status": "not_run",
    "result_shape": null
  },
  "contract_status": "complete"
}
```

Contract rules:

- Initial size budget: approximately 600 tokens.
- Keep question-derived requirements separate from assumptions.
- Preserve explicit boundaries, inclusivity, ranking values, and output grain.
- Use `unknown` rather than inventing unresolved schema facts.
- Mark incomplete contracts with exact missing fields.
- Record forbidden assumptions for detected semantic traps.
- Never include gold SQL, gold rows, correctness, or evaluator metadata.

### 6.2 Retrieved field record

```json
{
  "table": "events_*",
  "column": "event_params",
  "leaf_path": "event_params.value.int_value",
  "type": "INT64",
  "description": "Integer event parameter value",
  "source": "dense|exact|relationship|bm25|tool",
  "raw_score": 0.0,
  "rank": 1,
  "sample_values": [],
  "required_by_contract": true
}
```

Rules:

- Deduplicate by normalized fully qualified path.
- Prefer exact source over semantic source.
- Cap samples to three values and 80 characters per value.
- Prefer relevant nested leaf paths over entire large STRUCT definitions.
- Record why each field was included.

### 6.3 Candidate record

```json
{
  "candidate_id": 0,
  "origin": "validated_draft|direct|alternative|repair",
  "sql_path": "...",
  "sql_hash": "...",
  "dialect": "bigquery",
  "generation_call_count": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "execution": {
    "status": "success|empty|error|timeout|not_run",
    "error_type": null,
    "row_count": 0,
    "column_count": 0,
    "columns": [],
    "null_rates": {},
    "result_hash": null,
    "preview_path": null
  },
  "semantic_checks": [],
  "semantic_score": 0.0,
  "selection_score": 0.0,
  "selected": false
}
```

### 6.4 Per-question terminal result

After stage 12, every expected ID must have one record in `question_results.jsonl` and one row in `question_results.csv`.

Allowed correctness states:

- `correct`
- `incorrect`
- `not_evaluable`
- `not_run`

Logical JSONL record:

```json
{
  "schema_version": "1.0",
  "run_id": "slayql_v2_YYYYMMDD_HHMMSS",
  "instance_id": "bq011",
  "db_name": "ga4",
  "dialect": "bigquery",
  "question": "...",
  "pipeline_status": "completed",
  "selected_candidate_id": 0,
  "selected_sql_path": ".../selected.sql",
  "selected_sql_hash": "...",
  "output_status": "success",
  "output_path": ".../result.csv",
  "output_row_count": 1,
  "output_columns": ["distinct_pseudo_users"],
  "output_preview_path": ".../result_preview.json",
  "correctness": "correct",
  "score": 1,
  "evaluation_error": null,
  "matched_gold_variant": 0,
  "failure_category": null,
  "retrieved_table_count": 1,
  "retrieved_column_count": 18,
  "completion_turns": 2,
  "candidate_count": 2,
  "llm_call_count": 3,
  "input_tokens": 8200,
  "output_tokens": 1200,
  "token_source": "provider",
  "elapsed_ms": 12500,
  "contract_path": ".../contracts/bq011.json",
  "candidate_manifest_path": ".../candidates/bq011.json",
  "selection_path": ".../selection/bq011.json",
  "evaluation_path": ".../evaluation/bq011.json"
}
```

Stable CSV columns:

```text
run_id,instance_id,db_name,dialect,correctness,score,pipeline_status,
output_status,failure_category,selected_candidate_id,output_row_count,
output_column_count,retrieved_table_count,retrieved_column_count,
completion_turns,candidate_count,llm_call_count,input_tokens,output_tokens,
token_source,elapsed_ms,selected_sql_path,output_path
```

### 6.5 Gold isolation

Correctness is written only during stage 12.

- Stages 1-11 must not import evaluator modules.
- Stages 1-11 must not read `evaluation_suite/gold`.
- Inference artifacts flow into evaluation; evaluation objects never flow into inference.
- Evaluation-only fields such as candidate correctness and selection regret live under `<log_path>/evaluation/`.
- Add an automated test for forbidden runtime imports and gold paths.
- Any leakage invalidates the entire run.

## 7. Detailed Implementation Phases

### Phase 0: Freeze Baseline and Reproducibility

Tasks:

- [ ] Preserve the current full-run directory unchanged.
- [ ] Record current Git commit, dirty state, Python version, model name, API base, dataset hash, schema-document hashes, embedding hashes, and configuration.
- [ ] Save a run manifest schema with stage statuses and timestamps.
- [ ] Save the exact 251 correct baseline IDs.
- [ ] Save all 296 non-correct IDs and the known 20 non-evaluable categories.
- [ ] Build a paired comparison utility reporting gained IDs, lost IDs, net gain, and unchanged IDs.
- [ ] Define a fixed stratified development set before tuning.
- [ ] Keep the final 547 run untouched until thresholds and weights are frozen.
- [ ] Record every attempted development configuration.

Development-set coverage:

- BigQuery, GA BigQuery, Snowflake, and SQLite.
- Simple lookup, temporal logic, aggregation, nested data, set exclusion, ranking, and multi-join cases.
- Diagnostic IDs `bq001`, `bq011`, `local070`, and `sf003`.

Exit criteria:

- Baseline metrics regenerate from existing artifacts.
- Every baseline ID has a known terminal status.
- New runs cannot overwrite historical directories.

### Phase 1: Fix Cross-Cutting Reliability Defects

#### 1.1 Central dialect routing

Create `run/dialect.py` and use it in retrieval, completion, generation, execution, revision, and selection.

| Prefix | Dialect | Executor |
|---|---|---|
| `bq` | BigQuery | BigQuery |
| `ga` | BigQuery | BigQuery |
| `sf` | Snowflake | Snowflake |
| `sf_bq` | Snowflake | Snowflake |
| `local` | SQLite | SQLite |

Tasks:

- [ ] Replace duplicated `startswith` branches.
- [ ] Resolve overlapping prefixes in one tested order.
- [ ] Reject unknown prefixes before model calls.
- [ ] Persist normalized dialect in all traces.
- [ ] Test every prefix, including `sf_bq` and all 25 `ga*` IDs.

#### 1.2 Deterministic SQL extraction

- [ ] Extract the final non-empty fenced SQL block.
- [ ] Fall back to raw content only when no block exists.
- [ ] Detect placeholders such as `YOUR_DATABASE_NAME`.
- [ ] Enforce one query statement unless an explicit benchmark exception exists.
- [ ] Reject DDL, DML, and destructive statements.
- [ ] Normalize trailing semicolons without semantic rewriting.
- [ ] Log extraction method and warnings.

#### 1.3 Atomic and resumable artifacts

- [ ] Write per-ID JSON through temporary file plus atomic rename.
- [ ] Do not append to shared JSONL from worker threads.
- [ ] Aggregate sorted per-ID files after workers finish.
- [ ] Use UTF-8 explicitly.
- [ ] Include schema version in every JSON artifact.
- [ ] Treat malformed or partial files as incomplete during resume.

Exit criteria:

- Every `ga*` generation and revision uses BigQuery instructions.
- Multi-block extraction selects the declared final SQL.
- Worker concurrency cannot corrupt selection or evaluation logs.

### Phase 2: Compact Query Contract and Validated-Draft Handoff

#### 2.1 Produce the contract without a mandatory new agent

Preferred behavior:

- Easy mode: derive a draft contract from deterministic question/schema signals and let the existing generation response confirm it.
- Medium/hard mode: schema completion finalizes the structured contract before `@stop()`.
- Successful `@sql_draft` attaches SQL path, output shape, and evidence.

Tasks:

- [ ] Add contract schema and validation.
- [ ] Require objective, filters, grain, operations, output, and ordering.
- [ ] Require join evidence for multi-table contracts.
- [ ] Separate question facts, schema facts, tool evidence, and assumptions.
- [ ] Add forbidden assumptions for detected ambiguity.
- [ ] Persist incomplete contracts with exact reasons.
- [ ] Pass only contract, focused schema, and relevant external knowledge to generation.

#### 2.2 Preserve validated drafts

- [ ] Save each draft separately from exploration SQL.
- [ ] Record execution status, shape, row count, columns, null rates, and capped preview.
- [ ] Mark a draft validated only after execution and contract checks.
- [ ] Reuse the best validated draft as candidate 0 without a generation call.
- [ ] Preserve draft references through `postprocess.py` and `generate_schema.py`.
- [ ] Never equate execution success alone with semantic correctness.

#### 2.3 Compact stage handoff

Include:

- Query contract.
- Focused schema fields.
- Up to three value hints.
- Short evidence summaries.
- Validated draft when present.
- Only relevant external-knowledge excerpts.

Exclude:

- Repeated system instructions.
- Full random-row tables.
- Repeated failed SQL after error summarization.
- Entire nested structures when only leaf paths matter.
- Unrelated retrieved fields.

Diagnostic acceptance:

- `local070`: global distinct-date grain is explicit and the correct 15-row draft survives as candidate 0.
- `bq011`: positive engagement is required without inventing `event_name = 'user_engagement'`.
- `sf003`: state abbreviation is required and must have valid geography evidence.

### Phase 3: Focused Retrieval and Real Relationship Propagation

#### 3.1 Table-first retrieval

Use existing embeddings.

1. Retrieve an initial pool of about 40 columns.
2. Aggregate scores by table using maximum score plus limited top-column support.
3. Select at most five tables, fewer with a strong margin.
4. Select at most six relevant columns per table.
5. Add exact join keys and contract-required fields.
6. Apply a normal global cap of 30 columns.
7. Expand once only when the contract identifies a missing concept or join.

Initial configurable limits:

```json
{
  "retrieval_pool_columns": 40,
  "max_tables": 5,
  "max_columns_per_table": 6,
  "max_prompt_columns": 30,
  "max_value_hints": 3,
  "max_sample_values": 3,
  "max_sample_value_chars": 80,
  "max_expansions": 1
}
```

Tune these values on the fixed development set rather than assuming they are optimal.

#### 3.2 Exact identifier lookup

- [ ] Build a normalized index by database, fully qualified table, suffix, column, and nested path.
- [ ] Attempt exact lookup first when table and column are supplied.
- [ ] Return one authoritative exact result when found.
- [ ] Use semantic top-k only for failed exact lookup or descriptive requests.
- [ ] Log lookup mode and success.
- [ ] Resolve conflicting types in favor of authoritative schema documents.

#### 3.3 Real relationship metadata for RBP

- [ ] SQLite: extract primary and foreign keys with PRAGMA.
- [ ] BigQuery/Snowflake: load documented relationships where available.
- [ ] Infer relationships only from high-confidence table-qualified IDs and compatible types.
- [ ] Never create edges solely from generic `id`, `name`, `date`, or `value` columns.
- [ ] Pass `foreign_keys` and `table_info` into RBP.
- [ ] Record node count, edge count, explicit/inferred edge counts, and chosen paths.
- [ ] Skip propagation and log `no_graph` when no edges exist.

#### 3.4 Replace saturated entropy control

Use:

- Top-1 versus top-5 score margin.
- Table score margin.
- Number of competing tables.
- Missing contract concepts.
- Missing join path.
- Nested-field requirement.
- Temporal, set, ranking, and grouped operations.
- Exact-lookup failure count.

Tasks:

- [ ] Retain entropy only as a diagnostic until predictive value is demonstrated.
- [ ] Define a calibrated complexity score.
- [ ] Fit thresholds on the development set.
- [ ] Log every feature and selected mode.
- [ ] Confirm the mode distribution is not constant.

Retrieval metrics:

- Required table recall.
- Required column recall.
- Join-key recall.
- Average tables and columns.
- Prompt characters/tokens.
- Expansion rate.
- Accuracy by mode.

Exit criteria:

- Normal focused prompts contain at most 30 columns.
- RBP receives real edges when available.
- Easy, medium, and hard cases receive different budgets.
- Exact ACS `VALUE` lookup returns the ACS field, not unrelated timeseries fields.

### Phase 4: Bounded Schema Completion

Use a small state machine:

```text
DISCOVER_MISSING_SCHEMA
VERIFY_VALUES_AND_RELATIONSHIPS
VALIDATE_DRAFT
FINALIZE_CONTRACT
```

Rules:

- Easy mode may move directly to finalization.
- Every turn must advance state or terminate.
- Empty output is not progress.
- Equivalent failed tool queries cannot repeat.
- A timeout receives one cheaper fallback query, then becomes summarized evidence.
- Medium mode has at most two turns.
- Hard mode has at most four turns.
- Complex questions attempt one draft when execution is available.
- A second draft is allowed only for a specific issue revealed by the first.

Compact tool behavior:

- [ ] Return only requested fields.
- [ ] Cap previews at five rows.
- [ ] Prefer counts, min/max, distinct values, and schema introspection over `SELECT *`.
- [ ] Block expensive `ORDER BY RANDOM()` on large cloud tables.
- [ ] Summarize errors into type, object, and actionable message.
- [ ] Maintain rolling evidence rather than replaying full history.
- [ ] Preserve exact facts learned through execution.

Completion can stop only when:

- Required concepts map to known fields or explicit assumptions.
- Required join paths are known, or single-table use is confirmed.
- Relevant date/value representations are known.
- Output grain is explicit.
- Any unresolved blocker is recorded with a safe fallback.

Exit criteria:

- Average completion turns are below two.
- No question exceeds four turns.
- Repeated conversation history no longer causes quadratic input growth.
- Every hard question has a valid contract and a validated draft or recorded reason drafting was unavailable.

### Phase 5: Adaptive and Diverse SQL Generation

Candidate policy:

| Condition | Candidates |
|---|---:|
| Validated draft passes checks and no ambiguity remains | 1 |
| Complete contract and strong retrieval, no draft | 1 |
| One material ambiguity or first candidate fails checks | 2 |
| Hard case with distinct plausible interpretations | 3 maximum |

Candidate roles:

- Candidate 0: validated draft.
- Candidate 1: direct contract implementation.
- Candidate 2: alternative targeting one recorded ambiguity.

Generation requirements:

- [ ] Use shared normalized dialect.
- [ ] Put compact contract before schema details.
- [ ] Distinguish required constraints from assumptions.
- [ ] Require one final fenced SQL block.
- [ ] Reject placeholders and multi-statements.
- [ ] Make alternative candidates differ only on named ambiguity.
- [ ] Avoid long persisted prose reasoning.
- [ ] Set bounded output tokens appropriate for SQL.
- [ ] Validate referenced schema before execution.
- [ ] Flag extra tables, filters, and missing outputs.
- [ ] Deduplicate normalized SQL.
- [ ] Log role, prompt hash, model, tokens, and latency.

Exit criteria:

- Average candidates are at most two.
- Easy cases normally use one generation call or reuse a draft.
- Candidate diversity corresponds to explicit ambiguities.

### Phase 6: Deterministic Semantic Validation and Bounded Revision

#### 6.1 Lightweight SQL parser

Preferred option: add a pinned `sqlglot` dependency for BigQuery, Snowflake, and SQLite AST parsing. This is local CPU work and replaces model calls.

Fallback:

- Parser failure for supported syntax is a warning, not automatic rejection.
- Conservative text checks and execution continue.
- Destructive statements, placeholders, and multiple statements remain hard failures.

#### 6.2 Static checks

| Check ID | Purpose | Default severity |
|---|---|---|
| `SQL001` | Parses in expected dialect | Warning |
| `SQL002` | Exactly one query statement | Error |
| `SQL003` | No DDL/DML/destructive operation | Error |
| `SQL004` | No placeholder identifiers | Error |
| `SEM001` | Required tables present | Error |
| `SEM002` | Required fields/equivalent expressions present | Error |
| `SEM003` | Required filters present | Error |
| `SEM004` | Unsupported restrictive filters absent | Confidence-based |
| `SEM005` | Grouping/window partition matches grain | Error |
| `SEM006` | Required set inclusion/exclusion represented | Error |
| `SEM007` | Ranking level and rank value match | Error |
| `SEM008` | Date boundaries and inclusivity match | Error |
| `SEM009` | Required output fields represented | Error |
| `SEM010` | Joins have known compatible evidence | Error |
| `SEM011` | Nested arrays/STRUCTs handled correctly | Confidence-based |
| `SEM012` | Unnecessary joins penalized | Warning |

Low-confidence checks influence ranking but must not automatically reject candidates.

#### 6.3 Runtime result checks

| Check ID | Purpose |
|---|---|
| `RES001` | Execution succeeded |
| `RES002` | Result non-empty unless empty is plausible |
| `RES003` | Required output width present |
| `RES004` | Uniqueness matches output grain |
| `RES005` | Required enrichment is not predominantly null |
| `RES006` | Row count matches explicit one-row/limit requirements |
| `RES007` | Numeric outputs are finite and domain-plausible |
| `RES008` | Result is not entirely null |

Diagnostic expectations:

- `bq011`: `SEM004` penalizes unsupported `event_name = 'user_engagement'`.
- `local070`: `SEM005` rejects partitioning streaks by city; `RES004` catches duplicate dates.
- `sf003`: `RES005` catches all-`N/A` state abbreviation.

#### 6.4 Revision policy

Trigger revision for:

- Actionable execution error or timeout.
- High-confidence semantic error.
- Result invariant failure.

Limits:

- Maximum one semantic repair per candidate path.
- Transient API retries are counted separately and bounded.
- Repair prompt contains only contract, SQL, failed checks, compact schema, and capped result/error evidence.
- Re-execute and revalidate repairs.
- Retain the pre-repair candidate if repair adds worse violations.
- Do not repeatedly revise infrastructure errors.

Exit criteria:

- Executed but suspicious SQL can be repaired.
- GA revision always uses BigQuery.
- Unfixable access/mapping failures terminate without loops.

### Phase 7: Contract-Aware Selection

Initial configurable score:

| Component | Weight |
|---|---:|
| Contract requirement coverage | 0.45 |
| Execution and result invariants | 0.20 |
| Validated evidence/draft provenance | 0.15 |
| Schema/join evidence | 0.10 |
| Result consistency | 0.05 |
| Simplicity/no unsupported assumptions | 0.05 |

Calibrate weights on the development set, not the final full-set score.

Rules:

- Hard validation errors make a candidate ineligible unless all candidates fail.
- Validated draft provenance helps but never bypasses checks.
- Majority consistency cannot override materially better contract compliance.
- Penalize unsupported filters, joins, partitions, and placeholders.
- Prefer simpler SQL when semantic/execution scores tie.
- If every candidate fails, emit a terminal error unless a clearly least-bad executable fallback is explicitly logged.

Result comparison changes:

- [ ] Make comparison symmetric.
- [ ] Require compatible row counts and column multiplicity.
- [ ] Enforce one-to-one column matching.
- [ ] Canonicalize null and numeric handling consistently.
- [ ] Ignore row order only when the contract allows it.
- [ ] Store clusters for analysis, not primary selection.
- [ ] Deduplicate identical candidates so repetition adds no voting weight.

Optional model tie-break is allowed only when:

- Top scores are within a configured margin.
- Results materially differ.
- Deterministic checks cannot resolve a recorded ambiguity.

Tie input is limited to contract, SQL, check summaries, shape, and five rows. Do not use pairwise all-combination voting.

After evaluation, calculate:

- `oracle_candidate_correct`
- `selected_candidate_correct`
- `selection_regret`
- `generation_failure`

These are evaluation-only fields.

Exit criteria:

- `local070` selects the correct 15-row candidate over the wrong majority.
- `bq011` prefers the correct set interpretation without gold.
- Selection regret decreases on the development set.

### Phase 8: Evaluation and Per-Question Correctness Logging

#### 8.1 Evaluator changes

Preserve official comparison semantics while improving persistence.

- [ ] Remove import-time `TeeOutput("log.txt")`.
- [ ] Add `--log_file`, `--output_jsonl`, and `--output_csv`.
- [ ] Evaluate all expected IDs from `--data_file`, not only discovered predictions.
- [ ] Mark missing predictions `not_evaluable` with a precise cause.
- [ ] Persist every result, not only correct IDs.
- [ ] Preserve correct-ID CSV for compatibility.
- [ ] Return matched gold-alternative index.
- [ ] Record prediction shape and paths without duplicating full results.
- [ ] Keep execution-result mode read-only toward selected artifacts.
- [ ] Use isolated temporary directories and explicit ownership.

#### 8.2 Stable failure taxonomy

```text
correct
semantic_result_mismatch
empty_result
missing_output
sql_parse_error
sql_execution_error
timeout
missing_table
missing_column
wrong_database_mapping
permission_denied
table_not_found_external
credential_error
multi_statement
placeholder_identifier
unsupported_dialect
evaluation_error
unknown
```

Raw errors remain available per ID, but aggregate reports sanitize credentials and connection details.

#### 8.3 Final report builder

Create `run/build_question_report.py` to join:

- Question metadata.
- Retrieval record.
- Contract.
- Completion summary.
- Candidate manifest.
- Selection record.
- Final SQL and output metadata.
- Token/call/timing data.
- Evaluation result.

Outputs:

```text
<log_path>/question_results.jsonl
<log_path>/question_results.csv
<log_path>/question_report.md
<log_path>/summary_metrics.json
<log_path>/evaluation/<instance_id>.json
```

Each question section in Markdown includes:

- ID, database, dialect, and question.
- CORRECT, INCORRECT, NOT EVALUABLE, or NOT RUN.
- Selected candidate and origin.
- Selected SQL in a collapsible section.
- Output shape and first five rows.
- Gold preview only in the clearly separated evaluation section.
- Semantic checks and selection score.
- Candidate execution and post-evaluation correctness summary.
- Failure category and concise root cause.
- Tokens, calls, turns, and elapsed time.
- Paths to complete artifacts.

Preview limits:

- Five rows.
- Ten columns.
- Full results remain in `result.csv`.
- Large result data is never copied into JSONL or Markdown.

#### 8.4 Aggregate metrics

- Correct / 547 and percentage.
- Correct / evaluated and percentage.
- Execution coverage.
- Correct, incorrect, non-evaluable, and not-run counts.
- Accuracy by prefix and database.
- Accuracy by easy/medium/hard mode.
- Accuracy by candidate count.
- Accuracy with/without completion.
- Candidate oracle accuracy.
- Selection regret.
- Average, median, and p95 input/output tokens.
- Average calls per question.
- Average completion turns.
- Average retrieved tables/columns.
- Average and p95 elapsed time.
- Failure-category counts.

Exit criteria:

- Full run JSONL contains exactly 547 unique IDs.
- Every record has terminal correctness.
- Correct count equals evaluator numerator.
- JSONL, CSV, Markdown, and summary totals agree.
- No gold field exists in pre-evaluation runtime artifacts.

### Phase 9: Token, Call, Compute, and Query Accounting

- [ ] Capture provider prompt/completion tokens when available.
- [ ] Estimate only when provider usage is absent.
- [ ] Mark token source as `provider`, `tokenizer`, or `approximation`.
- [ ] Count model calls by stage and ID.
- [ ] Separate transient retries from logical calls.
- [ ] Record database query count and timeout count.
- [ ] Record per-stage elapsed time with a monotonic clock.
- [ ] Record prompt characters as a provider-independent measure.

Initial efficiency targets:

| Metric | Target |
|---|---:|
| Average completion turns | Less than 2 |
| Maximum completion turns | 4 |
| Average candidates | At most 2 |
| Maximum candidates | 3 |
| Tie-break calls | Less than 10% of IDs |
| Normal focused schema | At most 30 columns |
| Average traced input tokens | At least 60% below current traced baseline |
| Average total model calls | At least 50% below always-five-candidate architecture |

Efficiency is accepted only when accuracy is non-regressive.

### Phase 10: Tests

#### 10.1 Unit tests

- [ ] Dialect routing for every prefix.
- [ ] Final SQL block extraction.
- [ ] Placeholder, multi-statement, and destructive-query detection.
- [ ] Exact lookup before semantic fallback.
- [ ] Explicit/inferred graph edges and generic-edge rejection.
- [ ] Retrieval deduplication and caps.
- [ ] Complexity mode assignment.
- [ ] Contract validation and serialization.
- [ ] Filter, grouping, partition, ranking, join, date, and output checks.
- [ ] Symmetric one-to-one result comparison.
- [ ] Candidate scoring independent of input order.
- [ ] Duplicate candidates add no weight.
- [ ] Atomic per-ID writes and stable aggregation.
- [ ] Evaluator correct/incorrect/missing/empty/malformed handling.
- [ ] Runtime gold-isolation checks.

#### 10.2 Integration tests

| Scenario | Assertion |
|---|---|
| `bq001` | Existing correct behavior remains correct and uses lightweight path |
| `bq011` | Unsupported event filter is detected; correct interpretation is preferred |
| `local070` | Validated draft persists; global streak candidate beats per-city majority |
| `sf003` | Missing or null state enrichment fails result validation |
| Any `ga*` | Generation and revision use BigQuery |
| Missing table | Category distinguishes mapping issue from generic SQL error |
| Permission failure | No repeated revisions; terminal infrastructure category |
| Empty result | One bounded repair then terminal status |
| Interrupted run | Complete IDs resume; partial IDs rerun |
| Parallel workers | No shared-log or JSON corruption |

#### 10.3 Regression tests

- [ ] Refactored evaluator reproduces exactly 251 historical correct IDs.
- [ ] Official comparison behavior remains unchanged.
- [ ] New versus old outputs are compared per ID.
- [ ] Previously correct diagnostics cannot silently regress.
- [ ] Any evaluator comparison change is reviewed separately from architecture changes.

#### 10.4 Failure injection

- [ ] API returns `content=None`.
- [ ] Database times out.
- [ ] Credential denied.
- [ ] Exact schema metadata conflicts.
- [ ] Candidate file is missing.
- [ ] JSON artifact is truncated.
- [ ] Nested schema exceeds normal size.
- [ ] Parser does not support a valid dialect construct.
- [ ] Report input is partially missing.
- [ ] Error contains credential-like text and must be sanitized.

### Phase 11: Rollout

Feature/config switches:

```text
--contract-handoff
--focused-retrieval
--exact-schema-lookup
--real-rbp-graph
--adaptive-completion
--adaptive-candidates
--semantic-validation
--contract-selection
--question-result-report
--legacy-selection
```

Requirements:

- Legacy behavior remains runnable.
- New behavior uses a new log path.
- Manifest records every flag.
- Rollback is configuration-based.

Rollout sequence:

1. Refactor evaluator outputs and replay historical results without model calls.
2. Replay improved selection over existing candidates where possible.
3. Run diagnostic IDs and targeted failure cases.
4. Run a stratified canary of about 25 questions.
5. Run the fixed development set for a frozen configuration.
6. Preserve legacy and new selections in shadow mode.
7. Freeze thresholds, weights, model, prompts, and config.
8. Run the full 547 set once.
9. Produce paired gained/lost and efficiency reports.

Mandatory release gates:

- Full-set correct count is not below 251.
- Historical evaluator replay produces the exact baseline correct-ID set.
- No gold leakage.
- `local070`, `bq011`, and GA routing defects are addressed.
- `bq001` remains correct.
- Every expected ID has a terminal record.
- Every lost previously correct ID is listed and inspected.
- Report totals agree across formats.

Target release gates:

- Aim for at least three percentage points absolute gain on the 547 denominator.
- Materially reduce selection regret.
- Reduce average traced input tokens by at least 60%.
- Reduce average model calls by at least 50%.
- Maintain or improve coverage after separating external access failures.

Stop rollout if:

- Correct-ID losses exceed gains on development data.
- Focused retrieval materially lowers required-field recall.
- Semantic checks reject many historically correct SQLs.
- Parser failures concentrate in one dialect.
- Token savings come mainly from abandoning hard cases.
- Cloud query cost or timeout rate increases materially.
- Per-question and aggregate totals disagree.

## 8. File-by-File Change Map

### 8.1 Existing files

| File | Planned responsibility |
|---|---|
| `run/retrieve_topk_schema.py` | Table-first retrieval, limits, complexity features, real graph metadata |
| `run/rbp_graph.py` | Explicit/conservative edges, diagnostics, no-graph fallback |
| `run/it_ee.py` | Feature-based mode/budget; entropy retained as diagnostic |
| `run/add_id.py` | Add contract-required identifiers and join keys, not every generic field |
| `run/complete_schema.py` | Bounded state machine, exact lookup, compact evidence, contract, validated drafts |
| `run/postprocess.py` | Merge schema plus contract/evidence/draft references |
| `run/generate_schema.py` | Focused prompts and nested leaf paths |
| `run/value_grounder.py` | Keep high-confidence cap; restrict hints to selected schema |
| `run/sql_generation.py` | Shared dialect, adaptive roles, contract prompt, final-block extraction, usage logging |
| `run/sql_execution.py` | Structured execution metadata and stable error categories |
| `run/sql_revise.py` | Shared dialect, one semantic repair, compact prompts, bounded retries |
| `run/sql_selection.py` | Contract scoring, strict result comparison, optional one tie-break |
| `evaluation_suite/evaluate.py` | Explicit log/output files, all-ID results, matched gold variant |
| `run/parse_tokens.py` | Per-stage and per-ID provider-first accounting |
| `run/run_phase1_full.ps1` | Versioned v2 run only; config/report stages; no baseline restart |
| `requirements.txt` | Add/pin direct dependencies, including SQL parser if approved |

### 8.2 Proposed new files

| File | Purpose |
|---|---|
| `run/dialect.py` | Single dialect/executor source of truth |
| `run/pipeline_types.py` | Contract, candidate, trace, and evaluation dataclasses/validators |
| `run/artifact_store.py` | Atomic writes, hashes, resume validation, aggregation |
| `run/semantic_validator.py` | Static SQL checks and runtime invariants |
| `run/relationship_metadata.py` | Explicit and conservative graph metadata |
| `run/build_question_report.py` | JSONL/CSV/Markdown/summary report generation |
| `run/config/lightweight_accuracy.json` | Versioned budgets, thresholds, weights, flags |
| `tests/test_dialect.py` | Prefix/dialect behavior |
| `tests/test_sql_extraction.py` | Final block and query safety |
| `tests/test_contract.py` | Contract validation and serialization |
| `tests/test_retrieval.py` | Exact lookup, limits, graph, complexity |
| `tests/test_semantic_validator.py` | SQL/result checks |
| `tests/test_selection.py` | Scoring, deduplication, tie handling |
| `tests/test_evaluation_logging.py` | Complete per-ID correctness artifacts |

Do not create a generic framework. Keep modules small, local, and ownership-specific.

## 9. Initial Configuration

Store a resolved, versioned JSON configuration:

```json
{
  "schema_version": "1.0",
  "retrieval": {
    "pool_columns": 40,
    "max_tables": 5,
    "max_columns_per_table": 6,
    "max_prompt_columns": 30,
    "exact_lookup_first": true,
    "max_value_hints": 3,
    "max_expansions": 1
  },
  "completion": {
    "easy_max_turns": 1,
    "medium_max_turns": 2,
    "hard_max_turns": 4,
    "max_drafts": 2,
    "max_preview_rows": 5
  },
  "generation": {
    "easy_candidates": 1,
    "medium_candidates": 2,
    "hard_candidates": 3,
    "max_output_tokens": 4096
  },
  "revision": {
    "max_semantic_repairs": 1,
    "max_transient_retries": 3
  },
  "selection": {
    "contract_weight": 0.45,
    "result_weight": 0.20,
    "evidence_weight": 0.15,
    "schema_weight": 0.10,
    "consistency_weight": 0.05,
    "simplicity_weight": 0.05,
    "tie_break_margin": 0.03
  },
  "logging": {
    "max_preview_rows": 5,
    "max_preview_columns": 10,
    "write_question_json": true,
    "write_jsonl": true,
    "write_csv": true,
    "write_markdown": true
  }
}
```

Each run copies the resolved config into its log directory and stores its SHA-256 hash.

## 10. Observability and Data Safety

Record per ID and stage:

- Status and terminal error category.
- Start/end timestamps and elapsed time.
- Input/output paths and hashes.
- Model and logical call count.
- Provider tokens or marked estimate.
- Database query and timeout counts.
- Resume/cache status.

Never log:

- API keys.
- Credential contents.
- Passwords or connection strings.
- Full environment dumps.
- Unlimited database rows.
- Full sensitive values when hashes/shapes/previews are sufficient.

Result preview rules:

- Five rows and ten columns maximum.
- Full result remains in existing CSV.
- Record shape and null rates separately.
- Sanitize errors before aggregation.

## 11. Risk Register

| Risk | Consequence | Prevention | Detection | Fallback |
|---|---|---|---|---|
| Wrong contract | All candidates follow bad interpretation | Explicit assumptions/ambiguities; challenged alternative | Contract diagnostics and disagreement | Generate one targeted alternative |
| Retrieval cap removes needed field | Lower recall | Required-field expansion and join-key injection | Recall metrics | One bounded expansion |
| Stale exact metadata | Wrong field/type | Hash/version metadata | Unknown-column errors | Semantic fallback and refresh marker |
| False graph edge | Wrong join | Conservative type-qualified inference | Join evidence logs | Explicit-only graph mode |
| Parser rejects valid SQL | False penalty | Parse failure is warning | Failure rate by dialect | Conservative checks plus execution |
| Semantic checker overreaches | Correct SQL rejected | Confidence/severity levels | Replay historical correct SQL | Downgrade check to warning |
| Fewer candidates lower oracle accuracy | Fewer correct opportunities | Expand only after failed checks | Oracle accuracy | Add targeted candidate for hard mode |
| Executable draft is semantically wrong | Bad provenance preference | Draft still passes all checks | Validator failures | Direct candidate competes normally |
| Tie-break erodes savings | More calls/tokens | Strict score-margin gate | Tie rate | Deterministic choice |
| External failure loops | Cost and delay | Infrastructure taxonomy | Retry counts | Terminal non-evaluable status |
| Gold leakage | Invalid benchmark | Stage/path isolation | Automated audit | Reject run |
| Concurrent log corruption | Missing/duplicate records | Per-ID atomic files | Count/hash validation | Rebuild aggregates |
| Development overfitting | Inflated expectation | Freeze protocol/config history | Attempt log | One final run after freeze |
| Token estimate is misleading | Invalid efficiency claim | Provider usage first | Compare sample estimates | Report source/range |

## 12. Recommended Work Order

| Order | Work package | Dependency | Main payoff |
|---:|---|---|---|
| 1 | Evaluator per-ID JSONL/CSV and baseline replay | None | Trustworthy correctness logging |
| 2 | Shared dialect and final SQL extraction | None | Concrete correctness fixes |
| 3 | Artifact schemas and atomic store | 1 | Reliable trace/resume |
| 4 | Query contract and draft preservation | 3 | Prevent semantic handoff loss |
| 5 | Semantic validator and result invariants | 4 | Detect silent wrong SQL |
| 6 | Contract-aware selection replay | 5 | Recover correct minority candidates cheaply |
| 7 | Focused retrieval and exact lookup | 3, 4 | Reduce noise and schema errors |
| 8 | Real relationship metadata and RBP | 7 | Improve multi-table retrieval |
| 9 | Bounded completion state machine | 4, 7 | Reduce token growth |
| 10 | Adaptive generation and semantic repair | 5, 9 | Reduce calls while targeting hard cases |
| 11 | Question report and aggregate analytics | 1, 3 | Complete audit trail |
| 12 | Canary, development run, freeze, full run | All | Final measured outcome |

The first accuracy experiment should replay contract-aware selection over existing candidates. This is cheaper than regeneration and directly tests whether correct candidates already exist but are discarded by current selection.

## 13. Definition of Done

### Functional

- [ ] Existing 12 stages remain independently executable and resumable.
- [ ] Every ID has a complete contract or explicit incompleteness reason.
- [ ] Validated drafts survive to selection.
- [ ] Candidate generation adapts from one to three.
- [ ] Successful SQL receives semantic/result validation.
- [ ] Selection is contract-aware and deterministic unless a gated tie is unresolved.
- [ ] Dialect routing is consistent across all stages.
- [ ] SQL extraction follows the declared final block.

### Logging

- [ ] Full run has exactly 547 unique terminal records.
- [ ] Every question includes output status and post-evaluation correctness.
- [ ] JSONL, CSV, Markdown, summary JSON, and evaluator counts agree.
- [ ] Candidate correctness and selection regret are available after evaluation.
- [ ] Tokens, calls, timings, retrieval, completion, and candidates are logged per ID.
- [ ] Logs contain no credentials or unbounded result data.

### Quality

- [ ] Evaluator replay preserves exactly 251 historical correct IDs.
- [ ] Unit, integration, regression, concurrency, and failure tests pass.
- [ ] `bq001` remains correct.
- [ ] `bq011` avoids unsupported event-name restriction.
- [ ] `local070` preserves and selects the correct global-streak candidate.
- [ ] `sf003` detects invalid null state enrichment.
- [ ] Unknown dialect, placeholder SQL, and multi-statements cannot execute unnoticed.

### Performance

- [ ] No ID exceeds four completion turns.
- [ ] Average candidates are at most two.
- [ ] Normal prompts contain at most 30 columns.
- [ ] Model-call and input-token gates are met.
- [ ] Efficiency changes do not reduce full-set correct count.

### Release

- [ ] New version uses a new log directory.
- [ ] Run manifest and resolved config exist.
- [ ] Gained/lost ID report is reviewed.
- [ ] Regressions have documented causes.
- [ ] Final claims use 547 as primary denominator and evaluated-only EX as secondary.

## 14. Final Deliverables

```text
SLAYQL_LIGHTWEIGHT_ACCURACY_IMPLEMENTATION_PLAN.md
run/config/lightweight_accuracy.json
run/dialect.py
run/pipeline_types.py
run/artifact_store.py
run/semantic_validator.py
run/relationship_metadata.py
run/build_question_report.py
tests/...
run/log_spider2_full_slayql_v2/run_manifest.json
run/log_spider2_full_slayql_v2/resolved_config.json
run/log_spider2_full_slayql_v2/question_results.jsonl
run/log_spider2_full_slayql_v2/question_results.csv
run/log_spider2_full_slayql_v2/question_report.md
run/log_spider2_full_slayql_v2/summary_metrics.json
run/log_spider2_full_slayql_v2/evaluation/<instance_id>.json
```

The final report must clearly separate:

- Evidence available to SlayQL during inference.
- Post-run gold evaluation.
- Correctness gains and losses against the frozen baseline.
- External/infrastructure failures outside model control.
- Accuracy, coverage, tokens, calls, database queries, and elapsed time.


# SlayQL v1.1 Dataset Pipeline Handover

## 1. Purpose and current status

This document is the operational and architectural handover for the active SlayQL v1.1
dataset pipeline in this repository.

The implementation is intentionally a low-deviation extension of the highest-accuracy
Phase-1 SlayQL v1 system. Its main accuracy experiment is a new selector-first candidate
selection stage. The rest of the work mainly adds dataset adapters, isolated runs,
checkpointing, usage accounting, evaluation metrics, and ablation support.

Important status at handover:

- The historical v1 artifacts are preserved and must remain read-only.
- The historical recorded Spider 2.0-Lite result is `251/527 = 47.63%` over evaluable
  instances.
- The historical run contains 547 questions, 527 result files, and 20 error-only cases.
- V1.1 has not yet completed a new end-to-end benchmark run.
- No claim should be made that v1.1 has reached 52% until a completed, frozen evaluation
  demonstrates it.
- The active normal runner is `run/dataset_pipeline.py`.
- The recommended Windows entry point is `run/run_dataset_pipeline.ps1`.
- Older lightweight/OCAL-style scripts remain in `run/`, but they are not the default
  v1.1 execution path.

## 2. Repository locations

Repository root:

```text
D:\SlayQL-v1.1\C-CaSE
```

Active pipeline directory:

```text
D:\SlayQL-v1.1\C-CaSE\run
```

Frozen highest-accuracy v1 result:

```text
D:\SlayQL-v1.1\C-CaSE\run\log_spider2_full_slayql
```

The current Git branch is based on `slayql-1` at commit `475ce87`. V1.1 exists as a
working-tree extension on top of that baseline. Do not use the historical result directory
as a new output directory.

The tests in `tests/test_v1_baseline_artifacts.py` protect the following historical facts:

| Property | Frozen value |
|---|---:|
| Questions/final folders | 547 |
| Executable result files | 527 |
| Error-only folders | 20 |
| Recorded correct | 251 |
| Recorded EX over evaluable results | 47.63% |
| Fixed-denominator score | 251/547 = 45.89% |

## 3. Design goal

The goal is to improve selection accuracy without making a large change to the candidate
generation system that produced the strongest historical result.

The working hypothesis is:

1. V1 already generates five candidates per question.
2. Some v1 mistakes occur when a correct candidate exists but the legacy selector chooses a
   different result cluster.
3. Improving how candidates are compared is lower risk than replacing retrieval, schema
   completion, prompts, or generation.
4. Deterministic selection can reduce routine LLM selector calls.
5. A single bounded verification call can be reserved for close, meaningful disagreements.

V1.1 therefore preserves the candidate pool first and changes the decision process at the end.
The selector cannot recover an answer that is absent from all generated candidates, so upstream
candidate-oracle accuracy remains an important metric.

## 4. What remains from Phase-1 v1

The active default configuration keeps these core behaviors:

- Broad schema retrieval with top N set to 100 by default.
- RBP graph propagation.
- IT-EE completion budgeting.
- A maximum schema-completion ceiling of ten turns.
- BM25 cell-value grounding.
- Raw BM25 threshold `5.0` by default.
- Maximum of three value hints per prompt by default.
- Existing schema completion.
- Five independently generated SQL candidates by default.
- Candidate execution.
- Existing execution-error revision stage.
- Existing SQL generation prompt and query-output contract by default.

V1.1 does not enable these more disruptive ideas in its normal path:

- No global top-40 retrieval replacement.
- No hard 30-column or 40-column prompt cap.
- No default reduction from five candidates to three.
- No easy/medium/hard candidate-count router.
- No completion plateau stopping.
- No strict semantic obligation gate that rejects otherwise executable candidates.
- No broad semantic-repair queue.
- No full multi-agent or all-pairs selector architecture.

## 5. Active pipeline flow

A fresh run does not jump directly to selection. It must first produce and execute the candidate
pool.

```text
Dataset discovery and normalization
  -> run/subset/config manifests
  -> BM25 and schema asset preparation
  -> schema retrieval
  -> schema completion
  -> final schema prompts
  -> five SQL candidates per question
  -> candidate execution
  -> execution-error revision
  -> selector-first ranking and optional verification
  -> final evaluation and aggregate metrics
```

### 5.1 Spider 2.0-Lite preparation

Spider 2.0-Lite uses the existing v1 resources and performs:

1. Build or reuse BM25 value indices.
2. Retrieve top-N schema elements.
3. Apply the existing ID/rule augmentation.
4. Generate initial schema prompts.
5. Run schema completion.
6. Postprocess completed schema candidates.
7. Generate final schema prompts.

Spider 2.0-Lite BM25 indices are shared immutable corpus assets under `run/bm25_indices`.
Threshold settings and BM25 traces remain specific to each new run.

### 5.2 BIRD and Spider 1.0 preparation

BIRD and Spider 1.0 use SQLite databases. Their preparation performs:

1. Inspect each SQLite database.
2. Build local schema documents.
3. Build FAISS schema embeddings.
4. Build a per-database BM25 cell-value index.
5. Run the normal retrieval, schema completion, and prompt stages.

Local assets are kept inside the run root. In particular, BIRD and Spider 1.0 BM25 indices are
written to:

```text
run/<run-id>/bm25_indices/
```

This means a BIRD run does build its BM25 indices before schema completion and SQL generation.
Building a BM25 index is local preprocessing and does not consume LLM tokens.

## 6. Primary v1.1 accuracy change: selector-first

The active selector is `run/selector_first.py`. The normal dataset pipeline calls it after SQL
generation, execution, and revision.

### 6.1 Legacy v1 behavior

The legacy selector grouped successful candidates by equivalent execution result. The largest
cluster won. If multiple clusters had the same size, an LLM performed pairwise voting.

This approach has two weaknesses:

- Repeated equivalent candidates receive more influence even though they add no new evidence.
- Majority agreement can favor a repeated semantic mistake over a unique correct candidate.

### 6.2 Candidate parsing

V1.1 parses SQL with SQLGlot using the candidate's target dialect. It extracts and records:

- Statement count and statement type.
- Tables and columns.
- Join structure.
- Projections.
- Filters and literals.
- Aggregations.
- Grouping and output grain.
- Ordering and limits.
- Set operations.
- `DISTINCT` placement.
- Time-filter evidence.
- Division and denominator-protection evidence.
- Execution status and result shape.

### 6.3 Question contract

The selector derives a conservative heuristic contract from the question. It looks for evidence
such as:

- Count, average, sum, maximum, or minimum intent.
- Per-group output.
- Top/bottom/ranking intent.
- Required ordering or a stated top-k limit.
- Distinct/unique intent.
- Date or time constraints.
- Ratio, percentage, rate, share, or proportion intent.
- Exclusion, intersection, or union behavior.
- Quoted literals and explicit date literals.

These checks are keyword/structure heuristics, not a learned semantic parser. Failing a heuristic
normally creates a score penalty; it does not automatically discard an executable query.

### 6.4 Hard safety gates

A candidate is normally eligible only when it:

- Parses for the target dialect.
- Contains one statement.
- Has an execution result.
- Is query-only rather than a mutation.
- References valid tables when a complete authoritative local schema is available.

If no candidate passes every gate, the selector falls back to the strongest executable
representative. If none executed, it still retains a deterministic representative rather than
failing without an artifact.

### 6.5 Deduplication

Candidates are grouped when either:

- Their canonical SQL is identical; or
- Their executed results are equivalent.

For order-sensitive questions, ordered result hashes are used. For other questions, row-order
differences do not create extra groups.

Only one representative from each duplicate group is ranked. Duplicate count is recorded for
diagnostics but does not provide majority-vote weight.

### 6.6 Deterministic scoring

Default selector weights are:

| Component | Default weight | Meaning |
|---|---:|---|
| Execution | 0.36 | Candidate produced an execution result |
| Contract | 0.24 | SQL structure agrees with question cues |
| Result shape | 0.20 | Output shape/grain is plausible |
| Grounded value | 0.08 | SQL uses available literal/value evidence |
| Diversity | 0.04 | Avoids rewarding repeated structural duplicates |
| Risk penalty | 0.12 | Penalizes failed material contract checks |

The selector ranks eligible representatives by score and uses candidate ID as a stable final
tie-breaker.

These weights are implemented defaults, not yet validated as the optimal calibration for BIRD,
Spider 1.0, or Spider 2.0-Lite.

### 6.7 Disagreement-only verification

The default selector margin is `0.10`. An LLM verification call is made only when both conditions
are true:

1. The top two deterministic scores differ by less than the configured margin.
2. Their structures or execution results materially disagree.

The verifier receives at most the top three candidates. It is asked to choose an existing
candidate ID and is not asked to generate new SQL.

If the API key is unavailable, verification is disabled, the response is invalid, or the call
fails, the deterministic winner remains the fallback.

### 6.8 Selector outputs

For each instance, v1.1 writes:

```text
selection/<instance-id>.json
sql_selection_v1/final/<instance-id>/selected.sql
sql_selection_v1/final/<instance-id>/result.csv
```

An error artifact is written instead of `result.csv` when no selected result is available. The
selection JSON records candidate scores, gates, duplicate groups, margin, disagreement reasons,
verification status, and the chosen candidate.

## 7. Supported datasets

### 7.1 BIRD

BIRD is external/user-owned data. Every BIRD `prepare` or `run` invocation, including a resume:

1. Prompts for the BIRD directory.
2. Lists the directory's immediate contents.
3. Requires explicit confirmation.
4. Finds the selected split JSON/JSONL and optional SQL file.
5. Resolves the corresponding SQLite databases.

`-BirdRoot` supplies a suggested/pre-filled path but does not bypass the confirmation prompt.

Example train location:

```text
D:\Downloads\train
```

The selected directory must contain, directly or recursively, the requested split data and the
SQLite databases referenced by that data.

### 7.2 Spider 1.0

Spider 1.0 is resolved only from the repository-local copy:

```text
spider_data/spider_data
```

It does not prompt for an external dataset directory.

### 7.3 Spider 2.0-Lite

Spider 2.0-Lite uses:

```text
run/spider2_data.json
```

and the existing Snowflake, BigQuery, SQLite, evaluator, and result resources inherited from v1.
The historical `run/log_spider2_full_slayql` directory is reference-only.

## 8. Run modes and combinations

The PowerShell menu exposes the nine required standalone combinations:

| Menu | Dataset | Mode | Selection size |
|---:|---|---|---|
| 1 | BIRD | smoke | First 5 deterministic IDs |
| 2 | BIRD | subset20 | Seeded 20% of selected split |
| 3 | BIRD | full | 100% of selected split |
| 4 | Spider 1.0 | smoke | First 5 deterministic IDs |
| 5 | Spider 1.0 | subset20 | Seeded 20% of selected split |
| 6 | Spider 1.0 | full | 100% of selected split |
| 7 | Spider 2.0-Lite | smoke | First 5 deterministic IDs |
| 8 | Spider 2.0-Lite | subset20 | Existing diverse subset file |
| 9 | Spider 2.0-Lite | full | Full normalized manifest |

There is also an explicit `backend-smoke` mode. It selects up to three Snowflake, three BigQuery,
and three SQLite instances when those backends are available. For BIRD and Spider 1.0, only
SQLite is applicable.

By default every smoke, 20%, and full run is standalone. A full run can be launched without an
earlier smoke run. Add `-EnforceGates` only when a research protocol should require:

```text
smoke -> backend-smoke -> subset20 -> full
```

Gate matching requires the same dataset, split, source hash, and resolved configuration.

The default smoke size remains five. `-SmokeCount` can select a smaller explicit diagnostic set,
and `-ExcludeBackend` can remove one or more backends before selection. Both values are frozen in
the run manifest/configuration. Example: `-SmokeCount 3 -ExcludeBackend snowflake`.
An excluded-backend smoke is selected round-robin across the remaining available backends, so a
three-instance Spider 2.0-Lite smoke without Snowflake covers BigQuery and local SQLite.

## 9. Prerequisites

### 9.1 Python packages

Install the repository requirements in the Python environment that will run the pipeline:

```powershell
cd D:\SlayQL-v1.1\C-CaSE
python -m pip install -r .\requirements.txt
```

Important added dependencies include:

- `python-dotenv`
- `rank-bm25`
- `sqlglot`
- `tiktoken`

The existing dependencies also include FAISS, sentence-transformers, OpenAI-compatible clients,
Snowflake, BigQuery, pandas, and timeout support.

### 9.2 Model configuration

The active scripts load `run/.env`. Required names depend on the provider, but the normal
OpenRouter-compatible setup is:

```dotenv
OPENROUTER_API_KEY=<secret>
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=<provider/model-name>
```

`OPENAI_API_KEY` may be used instead of `OPENROUTER_API_KEY` for an OpenAI-compatible endpoint.
Do not commit keys or include their values in reports.

### 9.3 Database access

- BIRD and Spider 1.0 require their local SQLite files.
- Spider 2.0-Lite SQLite files must remain under the existing resource layout.
- Spider 2.0-Lite Snowflake and BigQuery runs require the credentials expected by the inherited
  v1 scripts.
- The Hugging Face model cache defaults to the repository-local `hf_cache` directory to reduce
  use of the system drive.

## 10. How to run

All examples below start from:

```powershell
cd D:\SlayQL-v1.1\C-CaSE
```

### 10.1 Prepare without inference

`prepare` validates/normalizes the dataset and writes manifests. It does not run model inference.

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command prepare `
  -Dataset spider1 `
  -Split dev `
  -Mode smoke `
  -RunId spider1_dev_smoke
```

BIRD preparation still asks for and confirms its directory:

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command prepare `
  -Dataset bird `
  -Split train `
  -Mode smoke `
  -BirdRoot "D:\Downloads\train" `
  -RunId bird_train_smoke
```

### 10.2 Interactive menu

```powershell
.\run\run_dataset_pipeline.ps1
```

Choose one of the nine dataset/run-size combinations. The defaults are split `dev`, five
candidates, four workers, and seed `20260813`.

### 10.3 Explicit smoke runs

BIRD:

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command run -Dataset bird -Split train -Mode smoke `
  -BirdRoot "D:\Downloads\train" -RunId bird_train_smoke
```

Spider 1.0:

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command run -Dataset spider1 -Split dev -Mode smoke `
  -RunId spider1_dev_smoke
```

Spider 2.0-Lite:

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command run -Dataset spider2-lite -Split dev -Mode smoke `
  -RunId spider2_dev_smoke
```

Three-instance Spider 2.0-Lite smoke excluding Snowflake:

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command run -Dataset spider2-lite -Split dev -Mode smoke `
  -SmokeCount 3 -ExcludeBackend snowflake `
  -RunId spider2_dev_smoke3_no_sf
```

### 10.4 Explicit 20% runs

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset bird `
  -Split train -Mode subset20 -BirdRoot "D:\Downloads\train" `
  -RunId bird_train_subset20

.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider1 `
  -Split dev -Mode subset20 -RunId spider1_dev_subset20

.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite `
  -Split dev -Mode subset20 -RunId spider2_dev_subset20
```

For Spider 2.0-Lite, `subset20` preserves all IDs already present in
`run/subset_diverse_20_evaluation.json`. It does not take another 20% sample of that file.

### 10.5 Explicit full runs

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset bird `
  -Split train -Mode full -BirdRoot "D:\Downloads\train" `
  -RunId bird_train_full

.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider1 `
  -Split dev -Mode full -RunId spider1_dev_full

.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite `
  -Split dev -Mode full -RunId spider2_dev_full
```

Do not start with a full run until the applicable smoke output has been manually checked, even
though standalone full runs are technically allowed.

### 10.6 Three-backend smoke

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command run -Dataset spider2-lite -Split dev -Mode backend-smoke `
  -RunId spider2_dev_backend_smoke
```

### 10.7 Enforced research gate sequence

Run each mode using the same dataset, split, model, thresholds, candidate count, and source data.
Use `-EnforceGates` on the modes that should require earlier successful gates.

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite `
  -Split dev -Mode full -RunId spider2_dev_full_gated -EnforceGates
```

The full command will fail early if matching completed smoke, backend-smoke, and subset20 runs do
not exist.

### 10.8 Bash entry point

The Bash wrapper is a thin explicit-argument wrapper and does not provide the PowerShell menu:

```bash
./run/run_dataset_pipeline.sh run \
  --dataset spider1 --split dev --mode smoke \
  --run-id spider1_dev_smoke
```

BIRD still prompts from Python even when invoked through Bash.

## 11. Resume behavior

Use the same command, run ID, dataset, split, candidate count, worker count, thresholds, model, and
source data to resume.

Example:

```powershell
.\run\run_dataset_pipeline.ps1 `
  -Command run -Dataset spider1 -Split dev -Mode subset20 `
  -RunId spider1_dev_subset20 -NumCandidates 5 -Workers 4
```

On resume:

- The existing run manifest is loaded.
- The resolved configuration hash is compared.
- Completed stages are skipped when their expected artifacts still exist.
- Generation and execution are checked per instance and per candidate.
- Selection and evaluation artifacts are checked per instance.
- Missing required artifacts invalidate the corresponding completed stage.
- Atomic writes reduce the chance of treating a partially written artifact as complete.
- BIRD asks for and confirms the directory again.

Do not reuse a run ID for a different dataset, split, run size, candidate count, model, or
threshold setting. Use a new run ID for each experiment.

Current checkpoint limitation: local asset/preparation stages and SQL revision primarily use
stage-level completion markers. Generation, execution, selection, and evaluation have stronger
per-instance artifact validation.

## 12. Offline selector replay

Offline replay tests the v1.1 selector against an existing candidate pool without rerunning:

- Schema retrieval.
- Schema completion.
- SQL generation.
- Candidate database execution.
- Candidate revision.

This is the lowest-cost first experiment for determining whether selection alone improves the
historical v1 result.

From the repository root:

```powershell
python .\run\selector_first.py `
  --log_path .\run\log_spider2_full_slayql `
  --data_file .\run\spider2_data.json `
  --num_candidates 5 `
  --offline-replay-output .\run\replay_spider2_v1_1
```

Replay characteristics:

- Writes to a separate output directory.
- Does not modify the historical v1 result directory.
- Disables LLM verification by default.
- Hashes candidate artifacts, data, selector/evaluator code, gold resources, Git state, and
  relevant configuration.
- Resumes already completed instances.
- Refuses to resume if the frozen inputs or configuration changed.

To explicitly permit bounded provider verification during replay:

```powershell
python .\run\selector_first.py `
  --log_path .\run\log_spider2_full_slayql `
  --data_file .\run\spider2_data.json `
  --num_candidates 5 `
  --offline-replay-output .\run\replay_spider2_v1_1_verified `
  --allow-replay-verification
```

Use a different replay output directory when changing selector settings.

## 13. Configuration controls

The active pipeline records relevant environment settings in `resolved_config.json`. Important
controls are:

| Variable | Default | Purpose |
|---|---:|---|
| `SLAYQL_TOP_N` | `100` | Retrieval depth |
| `SLAYQL_BM25_THRESHOLD` | `5.0` | Raw or normalized BM25 admission threshold |
| `SLAYQL_BM25_NORMALIZED` | `0` | Use normalized BM25 score when `1` |
| `SLAYQL_VALUE_HINT_CAP` | `3` | Maximum value hints entering a prompt |
| `SLAYQL_SELECTOR_MARGIN` | `0.10` | Close-score verification threshold |
| `SLAYQL_SELECTOR_MIN_SCORE` | `0.35` | Logged low-confidence threshold |
| `SLAYQL_SELECTOR_VERIFY` | `1` | Enable bounded verification when conditions match |
| `SLAYQL_SELECTOR_W_EXEC` | `0.36` | Execution score weight |
| `SLAYQL_SELECTOR_W_CONTRACT` | `0.24` | Contract score weight |
| `SLAYQL_SELECTOR_W_SHAPE` | `0.20` | Result-shape score weight |
| `SLAYQL_SELECTOR_W_VALUE` | `0.08` | Value-evidence score weight |
| `SLAYQL_SELECTOR_W_DIVERSITY` | `0.04` | Structural-diversity score weight |
| `SLAYQL_SELECTOR_W_RISK` | `0.12` | Risk penalty weight |

Ablation flags include:

| Variable | Effect |
|---|---|
| `ABLATION_NO_BM25=1` | Disable BM25 hints |
| `ABLATION_NO_RBP=1` | Disable RBP graph propagation |
| `ABLATION_RBP_ALPHA=<value>` | Override RBP alpha |
| `ABLATION_NO_ITEE=1` | Force full completion budget |
| `ABLATION_ITEE_THRESHOLD=<value>` | Override IT-EE threshold |
| `ABLATION_NO_QOC=1` | Disable the strict output-contract wording |

Do not tune values on a final test/full result and then report that same result as an unbiased
benchmark. Calibrate on a designated development partition and freeze the configuration first.

## 14. BM25 behavior

BM25 value grounding is used during schema completion and SQL generation unless explicitly
disabled.

For each extracted question literal, the grounder records:

- Literal text.
- Best matched database value.
- Matched table/column path.
- Raw BM25 score.
- Normalized score.
- Active threshold and threshold scale.
- Exact-match status.
- Whether the match was admitted.
- Whether it entered the prompt before the hint cap was reached.

Traces are written to:

```text
run/<run-id>/bm25_traces/
```

An exact value match may be admitted even when it does not pass the numeric threshold. Missing
indices and questions without extractable literals are also represented in trace status.

## 15. Token and cost accounting

The pipeline records provider-reported usage immediately after active model calls in:

- Schema completion.
- SQL generation.
- SQL revision.
- Selector verification.

Per-instance records are appended to:

```text
run/<run-id>/usage/<instance-id>.jsonl
```

Each record can contain:

- Provider response ID.
- Model name.
- Pipeline stage.
- Instance and candidate ID.
- Attempt number.
- Latency.
- Prompt tokens.
- Completion tokens.
- Reasoning tokens when provided.
- Cached/cache-write tokens when provided.
- Total tokens.
- Provider cost and cost details when provided.

If the provider does not return usage, the record is marked `provider_usage_missing`. The code
does not silently replace missing values with a manual tokenizer estimate.

Current limitation: there is no implemented `/generation` reconciliation request for missing
OpenRouter usage records.

Cost expectations:

- BM25 building, deterministic selector scoring, metric calculation, and offline replay without
  verification do not consume model tokens.
- A normal v1.1 run still pays for schema completion, five-candidate generation, and any revisions.
- V1.1 should reduce selection cost relative to repeated pairwise voting on clear cases.
- Close material disagreements can add one selector verification call.
- Retry attempts can increase cost when provider calls fail after being accepted upstream.
- No cost-reduction claim is valid until provider usage from comparable complete runs is measured.

## 16. Evaluation metrics

Final evaluation is implemented in `run/evaluate_dataset.py`. Intermediate artifacts are retained,
then aggregate metrics are calculated at the end.

### 16.1 SQL/result metrics

- Execution accuracy: correct results divided by evaluable instances.
- Fixed-denominator accuracy: correct results divided by all expected instances.
- Coverage: instances with a selected SQL prediction divided by expected instances.
- SQL exact match: whitespace-normalized selected SQL equal to gold SQL.
- Execution error count.
- Gold/evaluator error count.

### 16.2 Schema-linking metrics

The evaluator reports table, column, join, and combined schema metrics:

```text
precision = true positives / predicted linked elements
recall    = true positives / gold required elements
F1        = 2 * precision * recall / (precision + recall)
```

It reports micro and macro precision, recall, and F1, plus:

- Strict recall: all gold elements are present.
- Schema noise: predicted elements not present in the gold set.

The table and column linking prediction is derived from stored retrieval/schema-linking artifacts.
Join comparison is derived from selected and gold SQL ASTs. These definitions must be reported
explicitly when comparing against papers that use a different schema-linking protocol.

### 16.3 Candidate and selector metrics

- Candidate-oracle correct: at least one generated/revised candidate has a correct result.
- Candidate-oracle accuracy: oracle-correct instances divided by evaluable instances.
- Selection regret: a correct candidate existed but the selected candidate was incorrect.
- Selection accuracy given oracle: selected correct answers divided by oracle-correct instances.
- Verification call rate.
- Deterministic selection rate.
- Verification fallback rate.
- Mean selector margin.

### 16.4 Evaluation limitations

- BIRD or Spider 1.0 instances without usable gold SQL are not execution-evaluable.
- Spider 2.0-Lite requires the existing official gold result assets.
- SQL exact match is a strict string-normalized diagnostic, not semantic equivalence.
- Schema-linking numbers depend on SQLGlot's successful parsing of the applicable dialect.
- Historical and new scores must use the same evaluator/data hashes before attributing a delta to
  the model or selector.

## 17. Output layout

A typical run root is:

```text
run/<run-id>/
  run_manifest.json
  dataset_manifest.json
  subset_manifest.json
  resolved_config.json
  reproducibility_manifest.json
  dataset.json

  checkpoints/
    stages.json
    instances/<instance-id>.json

  documents/
  embeddings/
  bm25_indices/
  bm25_traces/

  initial_candidates.json
  cache/
  schema_prompts/
  final_schema_prompts/

  sql_gen/
  sql_revise/
  sql_selection_v1/final/<instance-id>/
  selection/<instance-id>.json

  usage/<instance-id>.jsonl
  metrics/<instance-id>.json
  evaluation/<instance-id>.json

  aggregates/
    summary_metrics.json
    summary_metrics.jsonl
    summary_metrics.csv
    checkpoint_integrity.json
```

Spider 2.0-Lite normally reuses the shared `run/bm25_indices/` directory rather than duplicating
it under every run root.

`reproducibility_manifest.json` records data, configuration, and important code hashes. Preserve
it with any reported result.

## 18. Ablation studies

The primary launcher is:

```text
run/run_ablation.ps1
```

Supported studies:

| Study | Values |
|---|---|
| BM25 | Raw 5.0, disabled, normalized 0.10/0.20/0.30/0.40/0.50 |
| Retrieval top N | 50, 75, 100, 125 |
| Candidate count | 3, 5, 7 |
| RBP alpha | 0.5, 0.7, 0.9 |
| IT-EE threshold | 0.3, 0.4, 0.5 |
| Selector margin | 0.00, 0.05, 0.10, 0.20, 0.30 |
| Value-hint cap | 1, 3, 5 |

Examples:

```powershell
.\run\run_ablation.ps1 `
  -Study bm25 -Dataset spider2-lite -Split dev -Mode subset20

.\run\run_ablation.ps1 `
  -Study topn -Dataset spider2-lite -Split dev -Mode subset20

.\run\run_ablation.ps1 `
  -Study candidates -Dataset spider1 -Split dev -Mode subset20

.\run\run_ablation.ps1 `
  -Study selector -Dataset bird -Split train -Mode smoke `
  -BirdRoot "D:\Downloads\train"
```

The ablation runner:

- Creates an isolated run ID for every value and gate mode.
- Runs all gate modes up to the requested mode.
- Writes an `ablation_manifest.json` into each variant run.
- Produces JSON and Markdown comparisons under `run/ablation_reports/`.

BIRD directory confirmation still occurs for each BIRD pipeline invocation.

Avoid `-Study all` until individual smoke studies have passed; it expands into many complete
pipeline runs and can be expensive.

## 19. Failure handling and troubleshooting

### 19.1 Run reports a configuration mismatch

Cause: the same run ID was reused with different workers, candidates, model, thresholds, seed, or
other recorded settings.

Action: restore the exact original configuration to resume, or choose a new run ID.

### 19.2 BIRD database is missing

Cause: a BIRD record's database ID could not be resolved to a SQLite file.

Action: confirm the chosen root includes the database directory and that each database folder/file
matches the dataset's database ID.

### 19.3 BM25 trace says `index_missing`

Cause: the per-database index was not built, was built in a different run root, or the normalized
dataset uses a different database ID.

Action: inspect `asset_manifest.json`, `bm25_indices/`, the normalized `dataset.json`, and the
`local_assets` checkpoint before rerunning later stages.

### 19.4 Generation stops with failed tasks

The generator performs up to five retries with exponential backoff and jitter, followed by a
dedicated rerun pass. Remaining failures are recorded in:

```text
run/<run-id>/sql_gen_failed_tasks.json
```

Fix the provider or data issue, then repeat the same command/run ID to resume.

### 19.5 Selector verification is unavailable

If no API key exists, selection continues with the deterministic winner and records
`unavailable_no_api_key`. This is not a selection-stage crash.

### 19.6 Usage is missing

Inspect the relevant per-instance JSONL record. `provider_usage_missing` means the provider response
did not expose a usable usage object. Do not infer a zero-token or zero-cost call from that status.

### 19.7 Evaluation reports no evaluable instances

Confirm the selected split includes usable gold SQL for local datasets or that Spider 2 official
gold result files are present. A generated prediction alone is insufficient for EX calculation.

## 20. Active files and ownership

| File | Responsibility |
|---|---|
| `run/dataset_pipeline.py` | Dataset adapters, manifests, run modes, orchestration, checkpoints |
| `run/run_dataset_pipeline.ps1` | Windows menu and explicit launcher |
| `run/run_dataset_pipeline.sh` | Thin Bash argument wrapper |
| `run/build_local_dataset_assets.py` | SQLite documents, embeddings, BM25 indices |
| `run/build_value_indices.py` | Existing Spider 2 BM25 index builder with configurable output |
| `run/retrieve_topk_schema.py` | V1 retrieval/RBP/IT-EE plus ablation controls |
| `run/complete_schema.py` | V1 schema completion, BM25 controls, usage capture |
| `run/sql_generation.py` | Five-candidate generation, bounded retry/resume, usage capture |
| `run/sql_execution.py` | Candidate execution with external SQLite path support |
| `run/sql_revise.py` | Existing error revision with usage capture |
| `run/selector_first.py` | New v1.1 selector and offline replay |
| `run/evaluate_dataset.py` | Per-instance and aggregate evaluation |
| `run/usage_accounting.py` | Provider response usage persistence |
| `run/artifact_store.py` | Atomic files, hashing, JSONL/CSV helpers |
| `run/value_grounder.py` | Configurable BM25 matching and traces |
| `run/run_ablation.ps1` | Research sweep orchestration |
| `run/summarize_ablation.py` | Ablation comparison reports |
| `tests/test_dataset_pipeline.py` | Pipeline/selector/evaluator unit coverage |
| `tests/test_v1_baseline_artifacts.py` | Frozen v1 artifact protection |

## 21. Older experimental files not in the normal path

The repository also contains an earlier lightweight architecture, including files such as:

- `prepare_lightweight_inputs.py`
- `prepare_generation_inputs.py`
- `prepare_semantic_repairs.py`
- `select_lightweight_sql.py`
- `lightweight_accuracy_stage.ps1`
- `run_lightweight_smoke_3.sh`
- `config/lightweight_accuracy.json`

Those scripts explore focused schema limits, adaptive completion, adaptive candidate counts,
semantic repair, and a different evidence selector. `dataset_pipeline.py` does not call that
standalone architecture.

Some shared utility code, such as deterministic result signatures from `semantic_validator.py`,
is reused by the v1.1 selector. That does not enable the older semantic-repair pipeline.

Do not assume settings in `config/lightweight_accuracy.json` apply to a normal v1.1 run. The active
v1.1 configuration is determined by `dataset_pipeline.py`, command-line arguments, environment
variables, and the resulting `resolved_config.json`.

## 22. Known limitations and unvalidated assumptions

- V1.1 accuracy has not yet been measured on a completed run.
- Selector defaults are heuristic and have not yet been calibrated on all three datasets.
- The 52% Spider 2.0-Lite target is an experiment target, not an achieved result.
- Candidate selection cannot repair a candidate pool with no correct answer.
- Completion plateau stopping is not implemented in the active path.
- OpenRouter missing-usage reconciliation is not implemented.
- BIRD and Spider 1.0 execution support is SQLite-focused.
- Local preparation and SQL revision do not have the same per-instance checkpoint validation as
  generation/execution/selection/evaluation.
- The Bash launcher has no nine-option interactive menu; PowerShell is the primary menu launcher.
- Backend smoke is truly multi-backend only for datasets containing those backends.
- Historical evaluator drift must not be reported as a model improvement.
- Existing ablation logs from older experiments are not evidence for the new v1.1 selector.

## 23. Recommended first validation sequence

No full pipeline should be the first execution. Use this order:

1. Confirm Python dependencies and provider/database credentials.
2. Run `prepare` for the intended dataset and inspect all manifests.
3. Run one five-instance smoke for BIRD.
4. Run one five-instance smoke for Spider 1.0.
5. Run Spider 2.0-Lite backend-smoke to exercise Snowflake, BigQuery, and SQLite.
6. Inspect checkpoints, BM25 traces, usage records, selection JSON, and evaluation outputs.
7. Run the deterministic offline replay against the frozen historical v1 candidate pool.
8. Compare v1 legacy selections with replayed v1.1 selections using the same evaluator hashes.
9. Only then run the curated Spider 2.0-Lite 20% subset.
10. Calibrate selector/BM25 settings on an explicitly designated development partition.
11. Freeze all settings and hashes.
12. Run full benchmarks only after the smaller runs have no unresolved integrity failures.

## 24. Result reporting checklist

Every reported experiment should include:

- Dataset and split.
- Smoke, subset20, backend-smoke, or full mode.
- Expected, evaluable, covered, and correct counts.
- EX denominator and fixed-denominator score.
- Candidate-oracle count and selection regret.
- Selector verification rate.
- Model name and endpoint family.
- Candidate count.
- Retrieval, BM25, RBP, IT-EE, hint-cap, and selector settings.
- Provider prompt/completion/total tokens and cost.
- Missing-usage count.
- Source, configuration, evaluator, and code hashes.
- Run ID and output path.
- Any excluded or non-evaluable IDs with reasons.

Never compare a historical score and a new score as an architecture improvement unless the
dataset and evaluator versions are frozen or the evaluator difference is separately reported.

## 25. Handover summary

SlayQL v1.1 is not a wholesale replacement of the strongest v1 system. Its active default path
keeps broad retrieval, RBP, IT-EE, BM25 grounding, schema completion, five-candidate generation,
execution, and revision. Its central accuracy experiment is the selector-first replacement for
legacy majority clustering and pairwise voting.

The surrounding work makes that experiment usable across BIRD, Spider 1.0, and Spider 2.0-Lite:
isolated smoke/20%/full runs, BIRD path confirmation, local SQLite assets and BM25 indices,
checkpointed resume, provider usage accounting, research metrics, offline replay, and controlled
ablations.

The immediate next step is validation, not architectural expansion: run smoke tests, replay the
historical candidate pool, measure selection regret and token usage, and only then decide whether
any further upstream change is justified.

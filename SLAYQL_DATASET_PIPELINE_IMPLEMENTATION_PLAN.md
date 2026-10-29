# SlayQL Dataset Pipeline and Research Evaluation Plan

Status: design only. No implementation or benchmark pipeline should be run until this plan is reviewed and approved.

## 1. Objectives and non-negotiable constraints

This implementation will:

1. Add one user-facing pipeline entry point with explicit dataset selection:
   - `bird`
   - `spider1`
   - `spider2-lite`
2. Re-establish the `slayql-1` configuration as the accuracy baseline, while applying only the previously selected low-deviation improvement: selector-first candidate ranking with conservative contract/result-shape checks and disagreement-only verification.
3. Add research-grade BM25 and related-threshold ablations without modifying or overwriting the historical v1 artifacts.
4. Support nine standalone dataset/run-size combinations (`bird`, `spider1`, `spider2-lite` crossed
   with `smoke`, `subset20`, and `full`), with the staged smoke/backend/20%/full gate sequence
   available as an explicit strict-run option.
5. Persist per-instance intermediate artifacts and calculate aggregate metrics only after all instance results are available.
6. Record provider-reported OpenRouter tokens and cost from each model response; no manual token estimation is used for the primary accounting.
7. Resume from the last valid checkpoint after interruption, including interruption during a single instance.

Existing historical directories, especially `run/log_spider2_full_slayql/`, remain read-only reference artifacts. New work must use versioned run roots such as `run/pipeline_bird_<run_id>/`, `run/pipeline_spider1_<run_id>/`, and `run/pipeline_spider2lite_<run_id>/`.

## 2. Dataset and path contract

### 2.1 Dataset adapters

Create a small adapter layer rather than making the current Spider 2 scripts guess file layouts. Each adapter resolves:

- question records and stable instance IDs;
- database/backend type and database identifier;
- schema source and local database/resource path;
- gold SQL and gold result locations for evaluation only;
- dialect and execution connector;
- the canonical answer representation used for metric calculation.

The adapters must validate a manifest before any model call and write the resolved paths, file hashes, record count, and dataset version into `run_manifest.json`.

### 2.2 BIRD

`bird` must always ask the user for the BIRD dataset directory at the start of the shell/PowerShell entry point, including smoke runs. The script must:

- display the entered and resolved absolute path;
- list the directory contents (without reading credential files);
- verify the expected BIRD dev/train files and database directory are present;
- ask for confirmation before continuing;
- fail without creating a run if the path is missing or ambiguous.

The default prompt may show `D:\Downloads\train` as a suggested path, but the chosen path must be user-supplied/resolved at runtime. The heavy BIRD train data must never be silently assumed or copied into the repository.

The BIRD adapter must distinguish dev from train and require an explicit `--split`/menu selection. Smoke and 20% runs should default to dev unless the user explicitly selects train.

### 2.3 Spider 1.0

`spider1` resolves only from the current repository copy, primarily `spider_data\spider_data` and its `database`/`test_database` resources. It must not prompt for an external directory. The adapter should recognize the standard Spider 1.0 JSON/SQL/table files and normalize them to the shared instance schema.

### 2.4 Spider 2.0-Lite

`spider2-lite` continues to use the existing Spider 2.0-Lite manifest and backend resources under `run/` and `resource/`, with the dataset ID set matching the established 547-instance target. The current v1 full-run artifacts are reference-only and must not be used as an output directory.

## 3. User-facing pipeline entry point

Add one primary script (PowerShell on Windows, with a thin POSIX wrapper if needed), for example `run/run_dataset_pipeline.ps1` and `run/run_dataset_pipeline.sh`.

The menu/arguments must support:

```text
dataset: bird | spider1 | spider2-lite
split: dev | train | test (valid combinations only)
stage: smoke | subset20 | full | resume
backend smoke: auto | sf | bq | local | all-applicable
run id/output root
ablation configuration (baseline or named variant)
```

The script must print a resolved run manifest before model calls and refuse to reuse a run directory with a different dataset/config hash. It must retain the existing credential-loading conventions and never print secrets.

## 4. Execution gates and test matrix

The primary runner allows each dataset/run-size combination to execute independently. For controlled
research promotion, `--enforce-gates`/`-EnforceGates` applies the sequence below. Each run writes its
own checkpoint and evaluation summary.

### 4.1 Dataset smoke gate: five instances

- BIRD: exactly five instances from the selected split, after the mandatory directory prompt/listing.
- Spider 1.0: exactly five instances from the selected split, using the repository-local data.
- Spider 2.0-Lite: five fixed representative IDs, retained in a checked-in selection manifest.

The five-instance gate validates loading, schema retrieval, generation, execution, revision/selection, evaluation, artifact writing, usage extraction, and resume behavior. It is not used as a publishable accuracy estimate.

### 4.2 Backend smoke gate: three instances per applicable backend

For every dataset/backend combination that exists in its adapter, run three fixed instances for:

- Snowflake (`sf`)
- BigQuery (`bq`)
- local SQLite (`local`)

Spider 2.0-Lite is expected to exercise all three. BIRD and Spider 1.0 are normally local-database datasets; their `sf` and `bq` rows should be reported as `not_applicable`, not fabricated. If a future adapter supplies a cloud backend, it inherits the same three-instance gate. Backend smoke selection must be deterministic and cover at least one simple, one join, and one aggregation query when the split permits.

### 4.3 Twenty-percent gate

After smoke passes, select a deterministic 20% subset using a stored seed and stratification by backend, difficulty/available metadata, and query shape. The subset manifest is immutable for that run. Evaluation must report coverage and failures, not silently shrink the denominator.

### 4.4 Full gate

Only after the five-instance and applicable three-backend gates pass, and the 20% run has no unresolved integrity/checkpoint errors, may the user choose `full`. Full runs use 100% of the selected split and a new output root. A failed gate blocks automatic escalation and prints the failing instance IDs and artifact paths.

## 5. Restoring the `slayql-1` baseline and the accuracy change

### 5.1 Baseline freeze

Before implementation, record:

- Git commit and dirty-worktree status;
- model, endpoint, and generation settings;
- dataset and schema hashes;
- candidate count, retrieval cap, BM25 settings, IT-EE/RBP/QOC settings, and worker counts;
- evaluator version and gold manifest hash.

The historical result remains the comparison point: 251/527 executable Spider 2.0-Lite results (47.63% as recorded by the v1 report). Current evaluator replay differences must be labeled as evaluator drift, not as a model improvement.

### 5.2 Low-deviation v1.1 change

The first v1.1 change is intentionally limited to candidate selection. The purpose is to improve the choice among SQL candidates that v1 already generates, rather than changing retrieval, schema completion, prompting, dialect handling, or database execution. This isolates the hypothesis and makes any accuracy change attributable to selection instead of a broad architecture rewrite.

#### 5.2.1 What remains frozen from `slayql-1`

The following are invariants for the first v1.1 experiment:

- the same dataset IDs and split;
- the same schema retrieval breadth and `top_n` cap;
- the same BM25 value index, grounding behavior, and hint budget;
- the same five generated candidates per question;
- the same schema-completion turns, IT-EE, RBP, QOC, and dialect prompts;
- the same SQL execution connectors, timeout policy, and revision stages;
- the same model, model parameters, worker limits, and evaluator;
- the same final result normalization and denominator.

These invariants matter because prior versions changed several of these at once. A result that changes retrieval and selection simultaneously cannot tell us whether a missing table, a bad SQL candidate, or a bad winner decision caused the change. The baseline run and its artifacts therefore remain untouched, while v1.1 writes to a new run root with a manifest proving which settings were held constant.

#### 5.2.2 Selection data contract

Every candidate entering selection must have a structured record, even if generation or execution failed. The record should contain:

- instance ID, candidate ID, SQL text, and source stage;
- parse status and canonicalized SQL/AST representation;
- execution status, error class, row/column counts, and normalized result hash;
- required output-shape observations (number of columns, aliases, ordering, null/type information);
- contract observations: referenced tables/columns, joins, filters, grouping, aggregation, ordering, and forbidden-pattern matches;
- BM25/value-grounding evidence used by the candidate;
- revision attempt and whether the SQL was original or repaired.

This record is necessary for two reasons. First, selection must compare evidence that already exists rather than issue a new open-ended reasoning call for every question. Second, it gives the evaluator enough information to diagnose whether v1.1 improved selection, merely changed retries, or selected an accidental executable query.

#### 5.2.3 Step A: normalize and deduplicate candidates

Before scoring, normalize SQL in a semantics-preserving way: whitespace, comments, casing where safe, and formatting are removed, while literals, identifiers, operators, grouping, ordering, and dialect-specific syntax are retained. Build a structural fingerprint from the normalized SQL/AST and a separate result-shape fingerprint from the executed output.

Candidates are grouped when they are exact structural duplicates or produce the same normalized result shape with equivalent execution evidence. Keep the highest-quality representative and retain links to all duplicates for audit. This is not a semantic equivalence claim: two queries with the same rows are not automatically treated as interchangeable if their SQL structure, ordering, or contract evidence differs.

Why this change is low risk and useful:

- v1 already spends generation and execution budget producing multiple candidates; duplicate candidates add no information to the selector;
- removing duplicates reduces vote dilution, so several formatting variants cannot outvote a structurally stronger candidate;
- deduplication does not remove a unique schema path or candidate before it has been executed;
- preserving duplicate links makes the step reversible and prevents a misleading reduction in the reported candidate oracle.

#### 5.2.4 Step B: apply only hard safety gates

Hard gates remove candidates that cannot safely be selected. A candidate fails a hard gate if it has any of the following:

1. SQL cannot be parsed for the target dialect.
2. SQL execution failed, timed out, or produced no trustworthy result artifact.
3. It violates an explicit forbidden SQL pattern or a database safety rule.
4. It violates a required output-shape invariant that is mechanically observable, such as an impossible column count or missing required ordering.
5. It has an explicit contract contradiction, such as referencing a forbidden table/column or omitting a required join that the contract marks as mandatory.

The gates must be conservative. An unknown or ambiguous semantic property is not a rejection; it becomes a soft penalty or a verification trigger. This distinction is important because a strict validator can discard the correct query when the contract is incomplete, particularly for nested queries, set operations, dialect-specific functions, and implicit relationships.

For transparency, store one gate decision and reason per candidate. If every candidate fails, preserve all candidates and route the question to the existing revision/verification path rather than returning an empty selection.

#### 5.2.5 Step C: score the surviving candidates

Score only evidence available at selection time. The initial score should be a weighted, configuration-driven sum with each component logged separately:

```text
selection_score =
    w_exec      * execution_quality
  + w_contract  * contract_and_ast_coverage
  + w_shape     * result_shape_consistency
  + w_value     * value_grounding_support
  + w_diversity * candidate_information_gain
  - w_risk      * soft_risk_penalties
```

Suggested component meanings are:

- `execution_quality`: successful execution, stable result artifact, and absence of recoverable-error markers;
- `contract_and_ast_coverage`: observed tables, columns, joins, filters, grouping, aggregation, and ordering that agree with the inferred contract, without requiring every inferred field to be present;
- `result_shape_consistency`: agreement with the question's requested grain, projected fields, ordering, and result-shape constraints;
- `value_grounding_support`: valid BM25/value hits supporting predicates or literals used by the candidate, without treating a missing hit as proof of incorrectness;
- `candidate_information_gain`: a small tie-break preference for a structurally distinct candidate when it contributes evidence not represented by duplicates;
- `soft_risk_penalties`: suspicious but non-fatal patterns such as unnecessary joins, unexplained filters, possible duplicate multiplication, or an uncertain contract match.

The weights are not to be hand-tuned on the Spider 2.0-Lite test/full result. They are selected on the designated development/calibration split and frozen in `resolved_config.json`. A zero-weight or disabled component must still be recorded so the ablation report can distinguish "not available" from "available but not useful."

Why this should improve accuracy: v1's five candidates often contain at least one executable answer, but a weak selector can prefer a majority pattern, a shorter query, or a plausible-looking result over the candidate whose joins, grain, and filters match the question. The proposed score makes those distinctions explicit while retaining all five candidates until after execution. Why it should reduce cost: the score is deterministic and reuses execution/contract artifacts; it does not add an LLM call for every question.

#### 5.2.6 Step D: deterministic winner and disagreement gate

Select the highest-scoring candidate without a model call when all of the following hold:

- at least one candidate passes the hard gates;
- the top score exceeds a minimum validity score;
- the top-to-second score margin is at least the configured `selector_margin_threshold`;
- no high-severity soft risk is present;
- the top candidates do not disagree on a required result-shape or contract invariant.

The margin threshold is a calibration parameter, not an implicit constant. The selector must log the top scores, margin, tie decision, and reason for deterministic selection. This path is expected to preserve accuracy on clear cases while eliminating unnecessary selector calls and reducing token cost.

#### 5.2.7 Step E: verification only for genuine disagreement

Invoke the selector model only when the deterministic gate cannot safely choose, for example:

- the score margin is below the configured threshold;
- two structurally different candidates both pass and disagree on an important contract/result-shape property;
- all candidates are executable but the hard evidence is contradictory;
- the only available candidates have material soft risks.

The verification prompt must contain the question, the compact contract, candidate IDs, normalized SQL, execution summaries, result-shape summaries, and score components. It must not include gold SQL, gold rows, or evaluator labels. The model returns one candidate ID plus a bounded reason; it must not regenerate a new unrestricted SQL query in this stage. If verification fails or returns an invalid ID, use the deterministic score winner and record the fallback.

This disagreement-only design addresses the main cost concern without making an unverified hard decision on ambiguous cases. It also creates a measurable research variable: verification-call rate versus selection accuracy and regret.

#### 5.2.8 Expected effects and explicit non-goals

The expected first-order effects are:

- accuracy: fewer incorrect winners when a correct executable candidate already exists;
- coverage: no intentional reduction, because failed candidates remain represented and every ID still receives a terminal state;
- token cost: fewer selector-model calls and shorter selector prompts, with no change to generation/schema prompts;
- latency: more local scoring and potentially fewer model round trips, offset by the existing execution cost;
- interpretability: candidate-level reasons, score components, and selection regret become auditable.

The first v1.1 implementation must not add:

- a hard keyword classifier or dataset-specific routing rules;
- top-30/top-40 schema pruning or a smaller global candidate count;
- strict rejection based only on semantic heuristics or missing BM25 hits;
- gold-derived contracts, result shapes, thresholds, or candidate scores;
- a new broad repair loop inside selection;
- simultaneous changes to retrieval, completion, generation, and selection.

These non-goals are deliberate. Earlier failed variants showed that aggressive pruning and hard semantic routing can remove the evidence needed for difficult queries, making a later selector incapable of recovery. The first experiment must test selection quality while keeping the evidence pool intact.

#### 5.2.9 Validation, comparison, and rollback

Validate the change in this order:

1. Unit tests for SQL normalization, duplicate grouping, hard-gate decisions, score calculation, margin handling, invalid-verification fallback, and artifact schemas.
2. Five-instance smoke and applicable backend smoke using the same fixed IDs as the baseline gate.
3. The deterministic 20% subset, paired instance-by-instance against `slayql-1` under the same evaluator.
4. Only after the 20% integrity checks pass, a frozen full run in a new output directory.

The comparison report must include:

- baseline and v1.1 execution accuracy on the same denominator;
- candidate-oracle accuracy (whether any candidate was correct);
- selection accuracy conditional on a correct candidate existing;
- selection regret and the number of recoverable baseline mistakes;
- deterministic-selection rate, verification-call rate, and fallback rate;
- per-stage prompt/completion tokens, cost, latency, and error categories;
- paired wins, losses, unchanged IDs, and confidence intervals.

Promote the selector-first change only if it passes artifact-integrity checks and shows a positive or clearly explainable accuracy delta without an unacceptable coverage or cost regression. If it fails, disable the v1.1 selector flag and retain the run artifacts for diagnosis; do not modify the frozen `slayql-1` implementation or its historical results.

Plateau stopping may be evaluated later as a separate cost ablation. It should begin as disabled, then test only a conservative two-consecutive-no-new-evidence-turn rule, with its own run root and report. It must not be combined with selector-first changes until the selector experiment has been independently evaluated.

## 6. Ablation study design

Implement a single ablation runner that creates an isolated run root per condition, runs the same gate sequence, and emits a machine-readable `ablation_manifest.json` and final comparison report.

### 6.1 BM25 threshold sweep (primary contribution)

Define the BM25 value-grounding threshold in one configuration file and log both raw and normalized scores. Recommended initial sweep, to be confirmed on the dev/20% calibration set:

```text
bm25_threshold: disabled, 0.10, 0.20, 0.30, 0.40, 0.50 (normalized score)
```

The threshold must control hint admission only; it must not remove schema tables/columns required by the question. Every value hit records query terms, matched field/value, score, threshold, and whether it entered the prompt.

### 6.2 Other bounded threshold/factor studies

Run one-factor-at-a-time sweeps before a small final combination study:

- schema retrieval `top_n`: 50, 75, 100, 125;
- candidate count: 3, 5, 7 (five is the frozen v1 baseline);
- RBP damping/expansion factor: 0.5, 0.7, 0.9;
- IT-EE stopping threshold: values around the baseline, selected on dev only;
- selector tie/margin threshold: deterministic choice versus disagreement verification;
- completion plateau patience: disabled versus two no-new-evidence turns;
- value-hint cap per question/database;
- retrieval expansion budget and maximum completion turns.

The runner must keep model, prompts, data subset, worker limits, and evaluator constant within a sweep. Thresholds are selected on the development/calibration split and then frozen before test/full reporting. Do not tune on Spider 2.0-Lite test or on the final full result.

### 6.3 Ablation outputs

For each variant, preserve per-instance artifacts and report:

- execution accuracy and coverage;
- schema linking metrics;
- SQL/result metrics;
- model calls, provider tokens, cost, latency, and database queries;
- error categories and recovered/resumed instances;
- paired deltas against the frozen `slayql-1` baseline;
- bootstrap confidence intervals or a paired significance test where sample size permits.

## 7. Artifact and checkpoint contract

Every run uses atomic writes and append-only or immutable per-instance records. Suggested layout:

```text
run/<run_id>/
  run_manifest.json
  resolved_config.json
  dataset_manifest.json
  subset_manifest.json
  checkpoints/stages.json
  checkpoints/instances/<instance_id>.json
  inputs/<instance_id>.json
  retrieval/<instance_id>.json
  contracts/<instance_id>.json
  candidates/<instance_id>/<candidate_id>.json
  executions/<instance_id>/<candidate_id>.json
  selection/<instance_id>.json
  usage/<instance_id>.jsonl
  metrics/<instance_id>.json
  evaluation/<instance_id>.json
  aggregates/summary_metrics.json
  aggregates/summary_metrics.csv
  logs/pipeline.log
```

Each instance state records its stage, attempt number, status, input/config hashes, artifact hashes, timestamps, error category, and resume decision. A stage is complete only when its output passes schema/hash validation. Partial temporary files are ignored and rerun. State transitions must be written atomically before the next stage begins.

On resume:

- verify the run manifest and configuration hash;
- skip only validated completed stages/instances;
- rerun incomplete or corrupt outputs;
- preserve previous attempts under an attempt number;
- never overwrite a successful artifact with a failed retry;
- update a final run summary only after all selected IDs have terminal states.

The evaluator must include every expected ID in its denominator and explicitly distinguish correct, incorrect, execution error, timeout, not-applicable, and incomplete.

## 8. Metrics and calculation rules

Metrics are calculated after inference from stored artifacts. Gold files are read only by the isolated evaluation stage; retrieval, generation, revision, selection, and runtime metric logging must not import or access gold answers.

### 8.1 Execution and SQL metrics

- **Execution accuracy (EX):** `correct execution results / evaluable instances`, with the denominator and error count reported separately. For the paper headline, also report the fixed full-set denominator.
- **Result exact match:** normalized predicted result equals any accepted gold result variant, with deterministic ordering/type/null normalization documented per dataset.
- **SQL exact match (auxiliary):** canonicalized predicted SQL string equals a gold SQL variant. This is secondary because equivalent SQL can differ textually.
- **Coverage:** instances with a terminal prediction/result artifact divided by expected instances.
- **Error rate:** execution errors, timeouts, invalid SQL, and missing artifacts by category.

### 8.2 Schema-linking metrics

Extract predicted linked tables, columns, and join keys from the final schema artifact/candidate contract. Extract gold required elements only in evaluation. For each instance:

```text
precision = |predicted intersection gold| / |predicted|
recall    = |predicted intersection gold| / |gold|
F1        = 2 * precision * recall / (precision + recall)
```

Use zero when the relevant denominator is zero, and report macro and micro aggregation. Report separately:

- strict schema linking recall (all required schema elements present);
- table recall/precision/F1;
- column recall/precision/F1;
- join-key recall/precision/F1;
- strict-recall rate: fraction of instances with every gold-required element present;
- schema noise/over-selection: predicted elements not required divided by predicted elements;
- selected schema size and prompt tokens.

This follows AutoLink's strict schema linking recall framing; the paper reports 97.4% on BIRD-Dev and 91.2% on Spider 2.0-Lite, so our report must label whether it is strict recall, micro recall, or macro recall and must not compare unlike definitions. AutoLink also reports execution accuracy separately, including 68.7% EX on BIRD-Dev and 34.9% EX on Spider 2.0-Lite. Cite the paper in the generated research report.

### 8.3 Candidate/selection diagnostics

Store candidate-level execution status, selected candidate, score components, score margin, disagreement flag, and whether verification was invoked. Report selector accuracy among executable candidates, tie rate, candidate oracle upper bound, selection regret, and the number of model verification calls.

### 8.4 Token, cost, and latency metrics

For each OpenRouter response, persist the response ID and the complete non-secret `usage` fields when present:

- `prompt_tokens`;
- `completion_tokens`;
- `total_tokens`;
- `completion_tokens_details.reasoning_tokens`;
- `prompt_tokens_details.cached_tokens` and `cache_write_tokens`;
- `cost` and `cost_details.upstream_inference_cost`;
- model, stage, instance ID, attempt, and timestamp.

OpenRouter documents that usage is returned automatically in non-streaming responses and in the final SSE chunk for streaming responses; deprecated `usage.include` flags should not be relied upon. If a response lacks usage, mark the record `provider_usage_missing` and do not silently replace it with a manual estimate. A generation-ID reconciliation step may query the `/generation` endpoint after completion, but the raw response and reconciliation status remain stored. Aggregate prompt, completion, reasoning, cached, total tokens, cost, cost per evaluated instance, calls per instance, and p50/p95 latency only at the final aggregation stage.

## 9. Evaluation and reporting workflow

The final stage consumes only completed per-instance artifacts and produces:

1. `summary_metrics.json` with formulas, denominators, exclusions, and hashes;
2. a CSV/JSONL instance table for statistical analysis;
3. an ablation comparison Markdown report;
4. a checkpoint-integrity report;
5. a reproducibility manifest containing code/config/data/evaluator hashes.

Reports must show smoke, 20%, and full results separately, and must never merge them into one headline number. BIRD, Spider 1.0, and Spider 2.0-Lite results must remain separate because their schemas, SQL dialects, gold formats, and benchmark protocols differ.

## 10. Validation and acceptance criteria before implementation is considered complete

- `--help` and dataset selection work without model calls.
- BIRD always prompts, lists, validates, and confirms the supplied directory.
- Spider 1.0 resolves only repository-local data; Spider 2.0-Lite resolves its existing manifest/resources.
- Five-instance smoke manifests are deterministic and complete.
- Three-instance backend smoke manifests are present for every applicable backend, with explicit N/A rows otherwise.
- A deterministic 20% subset is reproducible from its manifest seed.
- Interrupting after each major stage and resuming produces the same final per-instance artifact hashes as an uninterrupted run.
- A failed/corrupt artifact is retried without deleting the prior attempt.
- Provider usage and cost are present or explicitly marked missing for every model call.
- Aggregate metrics can be regenerated from per-instance artifacts without rerunning inference.
- Gold-isolation checks prevent runtime stages from reading evaluation gold.
- Ablation reports include BM25 threshold curves, related-factor sweeps, paired deltas, and confidence intervals.
- No historical v1/v1.1 result directory is overwritten.

## 11. Implementation order

1. Freeze manifests, paths, baseline configuration, and evaluator semantics.
2. Implement dataset adapters and non-running manifest validation.
3. Implement the user-facing menu/arguments, BIRD prompt/list/confirmation, and run-root creation.
4. Implement checkpointed stage/instance artifact storage and resume validation.
5. Implement the five-instance and backend smoke selectors.
6. Implement the minimal selector-first v1.1 change behind a configuration flag.
7. Implement OpenRouter usage extraction/reconciliation and per-instance accounting.
8. Implement isolated gold evaluation and metric aggregation.
9. Implement the 20% and full gates.
10. Implement BM25 and related threshold ablations plus paired reporting.
11. Add tests for manifests, path prompting, subset determinism, artifact recovery, metric formulas, usage parsing, and gold isolation.
12. Only after code review and approval, run the smoke gates in the prescribed order; no full pipeline is part of this planning step.

## References

- AutoLink: <https://ojs.aaai.org/index.php/AAAI/article/view/40672>
- AutoLink paper PDF and metric definition: <https://ojs.aaai.org/index.php/AAAI/article/download/40672/44633>
- OpenRouter Usage Accounting: <https://openrouter.ai/docs/cookbook/administration/usage-accounting>

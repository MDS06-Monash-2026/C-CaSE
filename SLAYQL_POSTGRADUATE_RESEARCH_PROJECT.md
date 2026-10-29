# SlayQL: Budget-Aware Execution-Grounded Agents for Cross-Dialect Text-to-SQL

## Postgraduate Research Project Specification

**Repository:** `D:\SlayQL-v1.1\C-CaSE`  
**Current baseline:** SlayQL v1.9  
**Primary datasets:** BIRD, Spider1.0, Spider2.0-Lite  
**Inference setting:** API-based large language model; no parameter updates or reinforcement learning  
**Document status:** Research design, current evidence, and publication plan

## Abstract

This project investigates whether a database-grounded, budget-aware agent can improve Text-to-SQL reliability beyond single-shot prompting while preserving reproducibility and controlling API cost. SlayQL combines schema and value retrieval, relation propagation, iterative schema completion, answer-plan constraints, multiple SQL candidates, execution feedback, bounded repair, and deterministic candidate selection. The project is designed for three increasingly realistic benchmarks: BIRD, Spider1.0, and Spider2.0-Lite.

The recorded BIRD full-run baseline improved from 49.15% to 56.19% execution accuracy. The five-candidate pool reached 68.77% candidate-oracle accuracy, showing that candidate generation and candidate selection are separate scientific problems. The central proposed contribution is a controlled study of a risk- and evidence-aware interaction controller: it allocates retrieval, database inspection, candidate generation, repair, and selection effort according to unresolved question obligations rather than applying the same expensive procedure to every question.

The work is not presented as proven state of the art. Its publishable value is a reproducible analysis of agentic Text-to-SQL under fixed API budgets, heterogeneous database backends, provider failures, and explicit selection-regret measurement.

## 1. Problem Statement

Text-to-SQL errors are often caused by incorrect interpretation of the question rather than invalid SQL syntax. Typical failures include:

- selecting the wrong table or column despite a syntactically valid query;
- missing a bridge table or using an invalid join path;
- confusing row-level, group-level, and database-level output grain;
- applying the wrong aggregation, denominator, ranking, or duplicate policy;
- grounding a phrase to the wrong database value;
- selecting an inferior candidate when another generated candidate is correct.

Large language models can often repair syntax, but repair alone does not recover a missing semantic obligation. SlayQL therefore treats SQL generation as an evidence acquisition, hypothesis generation, execution, and selection process.

## 2. Research Objectives

1. Improve execution accuracy on BIRD, Spider1.0, and the available portions of Spider2.0-Lite.
2. Measure candidate generation and candidate selection independently.
3. Increase useful database interaction without increasing the fixed prompt and turn budgets indiscriminately.
4. Reduce wasted API calls by routing high-cost actions only to uncertain questions.
5. Provide strict checkpointing, failure recovery, cost accounting, and audit artifacts.
6. Establish a fair comparison protocol that remains valid when Snowflake is unavailable.

## 3. Research Questions and Hypotheses

### RQ1: Evidence and generation

Does schema/value evidence, relation routing, and an explicit answer plan increase the probability that at least one candidate is correct?

**H1:** Obligation-aware evidence and join-path closure increase candidate-oracle accuracy over the v1.9 baseline.

### RQ2: Selection

When a correct candidate exists, can execution results and semantic constraints select it reliably?

**H2:** Deterministic audit-based selection reduces selection regret and selector failures compared with an unconstrained tournament selector.

### RQ3: Interaction efficiency

Can adaptive interaction preserve accuracy at lower cost than applying maximum retrieval, completion, repair, and candidate counts to every question?

**H3:** Risk-based routing reduces tokens and latency at a statistically negligible accuracy loss, or improves accuracy at a fixed budget.

### RQ4: Cross-dialect robustness

Do the same controls transfer between SQLite, BigQuery, and Snowflake-style SQL environments?

**H4:** Explicit dialect and execution contracts reduce backend-specific failures, but gains will differ by database engine and schema complexity.

## 4. System Design

```text
Question and database manifest
              |
              v
  BM25/embedding evidence retrieval
              |
              v
  Question obligation and answer-plan extraction
              |
              v
  RBP relation propagation and typed join-path closure
              |
              v
  Protected schema tiers and token-budget allocation
              |
              v
  Risk router: low / medium / high interaction plan
              |
              v
  Diverse SQL candidates with dialect constraints
              |
              v
  Query-only execution and result-shape diagnostics
              |
              v
  At most one targeted semantic repair when justified
              |
              v
  Audited deterministic selection
              |
              v
  Sealed official evaluation and post-hoc oracle/regret analysis
```

### 4.1 Evidence layer

BM25 and embedding retrieval produce a ranked pool of tables, columns, descriptions, and values. Retrieval is not treated as the final schema: relation propagation and typed graph closure add plausible bridge paths and foreign-key-compatible context.

### 4.2 Semantic control layer

The question is represented as obligations such as entities, filters, aggregations, ordering, limits, time constraints, and output fields. Each candidate must be auditable against these obligations. This makes missing meaning observable before syntax repair is attempted.

### 4.3 Interaction controller

The controller estimates uncertainty from retrieval disagreement, unresolved obligations, join ambiguity, value-grounding confidence, and execution diagnostics. Low-risk questions receive a compact path; high-risk questions receive additional schema completion, relation verification, candidate diversity, or one targeted repair.

### 4.4 Candidate and selector layer

Candidates are generated along distinct semantic routes, for example alternative join paths, aggregation plans, or value interpretations. Selection uses SQL validity, obligation coverage, result shape, execution status, and deterministic tie-breaking. Gold SQL is never supplied to generation, repair, or selection.

## 5. Versioned Research Baseline

The v1.1-v1.9 progression is treated as an ablation history, not as independent claims of novelty. The major lessons are:

- v1.1 established the retrieval, interaction, execution, revision, and selector pipeline.
- v1.6 produced the first clear controlled candidate-generation improvement through semantic contracts and relation-aware routes.
- v1.8 was the strongest recorded full BIRD run: 862/1534 = 56.19%.
- v1.8 candidate-oracle accuracy was 1055/1534 = 68.77%; 193 questions were selection-regret cases.
- 479 questions had no correct candidate, so selector improvements alone could not reach the target.
- v1.9 reduced comparable subset cost but did not establish a new full-run accuracy ceiling.
- Schema recall was high but precision was poor, indicating that noisy context and join reasoning remained larger gaps than basic retrieval recall.
- Provider quota errors and incomplete backend access are experimental confounds and must be separated from model errors.

The complete historical tables remain in [`SLAYQL_MASTER_THESIS_RESEARCH_REPORT.md`](D:/SlayQL-v1.1/C-CaSE/SLAYQL_MASTER_THESIS_RESEARCH_REPORT.md).

## 6. Experimental Protocol

### 6.1 Dataset splits

- **BIRD:** development set for local iteration and final reported development evaluation; training data may provide demonstrations only.
- **Spider1.0:** official train/dev/test conventions must be recorded; test labels must not enter inference.
- **Spider2.0-Lite:** report local, BigQuery, and Snowflake subsets separately, then report a combined denominator only when the inclusion policy is explicit.

### 6.2 Subset screening

Before a full run, use a deterministic 20% subset containing approximately 20% representative/easier questions and 80% difficult or failure-prone questions. The subset policy, seed, IDs, and reference metrics must be saved. Subset results are for capability screening and are not directly comparable with a full benchmark score unless the same fixed IDs and denominator are reused.

### 6.3 Required comparisons

Every proposed improvement must compare:

1. v1.9 baseline versus the new controller.
2. Equal model, prompts, candidate budget, and eligible questions.
3. Full final accuracy and candidate-oracle accuracy.
4. Selector regret, selector error/fallback rate, and no-oracle count.
5. Schema table/column recall and precision, join-path coverage, and obligation coverage.
6. API calls, input/output tokens, cost, latency percentiles, retries, and failures.

### 6.4 Ablations

At minimum, remove one component at a time:

- obligation extraction;
- relation graph closure;
- adaptive risk routing;
- candidate diversity;
- bounded semantic repair;
- deterministic audit-based selection.

An ablation is valid only when the dataset IDs, model settings, and denominator are held constant.

## 7. Metrics

### Primary

- official execution accuracy;
- exact-match or benchmark-specific official metric;
- fixed-denominator accuracy including explicit error-only records.

### Diagnostic

- candidate-oracle accuracy;
- selection given oracle availability;
- selection regret;
- selector invocation, success, and fallback rates;
- obligation and join coverage;
- schema precision, recall, and F1;
- execution error categories and result-shape mismatches.

### Efficiency and reliability

- total and per-question API calls;
- input/output/total tokens and estimated cost;
- p50/p95 latency;
- retry and provider-error counts;
- checkpoint recovery success;
- number of incomplete or missing terminal records.

## 8. Data Leakage and Validity Controls

Gold SQL, gold result files, and evaluator outputs must be inaccessible to retrieval, generation, repair, and selection. Gold evaluation is performed only after the inference artifacts are sealed. Demonstration files must be separated from evaluation IDs. Every run should record configuration hashes, dataset hashes, model identifiers, prompt version, candidate budget, backend availability, and the exact denominator.

Snowflake downtime is reported as a limitation, not silently converted into a full-benchmark claim. Provider quota failures are counted separately from SQL or semantic failures.

## 9. Expected Contributions

The defensible contributions are:

1. A reproducible API-based Text-to-SQL pipeline with stage and question-level checkpointing.
2. A budget-aware interaction controller that allocates database reasoning effort by semantic risk.
3. A unified analysis separating candidate generation failure from selector failure.
4. An execution-grounded evaluation protocol for heterogeneous database backends.
5. An empirical study of cost, latency, reliability, and accuracy trade-offs across BIRD, Spider1.0, and Spider2.0-Lite.

The project should not claim that BM25, multi-candidate sampling, SQL repair, or execution feedback are individually novel. Novelty lies in their controlled integration, risk-based allocation, and measurement of the interaction/selection boundary under fixed API constraints.

## 10. Threats to Validity

- Results depend on the selected API model, temperature, and provider reliability.
- BIRD development performance is not equivalent to hidden test performance.
- A 20% subset cannot establish benchmark-level superiority.
- Snowflake-unavailable Spider2.0-Lite results are restricted evaluations.
- Official SQL comparison can penalize semantically equivalent queries when the evaluator is strict.
- Adaptive routing can overfit if thresholds are tuned on the evaluation questions.
- Cost estimates vary with provider pricing and cached prompt policies.

## 11. Thesis Chapter Structure

1. Introduction and motivation.
2. Background: Text-to-SQL, schema linking, execution-guided generation, and agentic systems.
3. Benchmark and infrastructure constraints.
4. SlayQL baseline and failure analysis from v1.1-v1.9.
5. Proposed budget-aware evidence and interaction controller.
6. Experimental methodology and leakage controls.
7. Accuracy, selection, efficiency, and robustness results.
8. Ablation and error analysis.
9. Limitations, reproducibility, and ethical considerations.
10. Conclusion and future work.

## 12. Publication Positioning

The current work is suitable for a postgraduate thesis and can support a workshop, system/demo, applied database/AI, or industry-track submission. A main-track NLP or machine-learning submission requires a completed controlled comparison, statistically defensible ablations, reliable backend coverage, and a clear improvement over strong published baselines. The publication claim should be about budget-aware execution-grounded interaction and selection reliability, not an unsupported claim of state-of-the-art accuracy.

## 13. Completion Criteria

The project is ready for submission when:

- all three dataset protocols and denominators are documented;
- at least one full, reproducible baseline and proposed-method run is complete;
- Snowflake availability and exclusions are explicit;
- all ablations use identical question IDs and model settings;
- candidate-oracle and selector-regret reports are generated;
- cost, latency, retry, and checkpoint metrics are included;
- no inference artifact contains gold information;
- code, configuration, environment requirements, and run commands are archived;
- failures are classified rather than omitted.

## Final Research Position

SlayQL is a strong postgraduate research platform because it turns Text-to-SQL from a single generation call into an auditable decision process. Its scientific value will come from demonstrating which interactions actually improve semantic correctness, when candidate selection becomes the bottleneck, and how much reliability can be obtained per API token under realistic database constraints. The v1.9 system is the baseline; the research contribution is the experimentally validated controller and the analysis framework built around it.

## Appendix A. Complete Recorded Experiment Evidence

This appendix records the experiments currently available in the repository. A run is only comparable with another run when the dataset IDs, denominator, model, prompt policy, candidate budget, evaluator, and backend policy are the same.

### A.1 Full benchmark runs

| Experiment | Dataset and scope | Candidates | Correct | Denominator | Final accuracy | Candidate oracle | Oracle accuracy | Regret | Given-oracle selection |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Earlier full baseline | BIRD dev, local SQLite | 5 | 754 | 1534 | 49.15% | 947 | 61.73% | 193 | 79.62% |
| v1.8 full | BIRD dev, local SQLite | 5 | 862 | 1534 | **56.19%** | 1055 | **68.77%** | 193 | **81.71%** |
| Spider1.0 full | Spider1.0 test, local SQLite | 3 | 1404 | 2147 | **65.39%** | 1535 | **71.50%** | 136 | **91.47%** |
| Historical Spider2.0-Lite v1 | Mixed local, BigQuery, Snowflake | not recorded | 251 | 547 fixed | **45.89%** | not recorded | not available | not available | not available |

The BIRD v1.8 improvement is 108 additional correct questions, or +7.04 percentage points, over the earlier full baseline. Its ceiling is still limited: 479 questions had no correct candidate, while 193 had a correct candidate that was not selected. Reaching 75% on 1534 BIRD questions requires 1151 correct answers, so v1.8 is 289 questions short of that target.

Spider1.0 has a much stronger selector: 91.47% of questions with an oracle-correct candidate were selected correctly. Its main gap is generation and interpretation, not result comparison. The 80% target requires 1718/2147 correct, approximately 314 more than the recorded run.

Spider2.0-Lite v1 contains 527 evaluable outputs and 20 error-only outputs. The 45.89% fixed-denominator score is therefore not directly comparable with a run that excludes errors. Snowflake became unavailable in later work; local/BigQuery-only results must be labelled as restricted rather than full Spider2.0-Lite results.

### A.2 Controlled BIRD subset progression

These runs use the recorded 307-question reference-style subset unless explicitly marked otherwise. They are development experiments, not unbiased estimates of full BIRD accuracy.

| Version | Main change | Selected | Selected accuracy | Oracle | Oracle accuracy | Regret | Given-oracle selection | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v1.2 | Evidence before completion; independent candidate roles | 93 | 30.29% | 137 | 44.63% | 44 | 67.88% | $1.590 |
| v1.3 | Question-linked evidence; ordinal contract | 99 | 32.25% | 137 | 44.63% | 38 | 72.26% | $1.670 |
| v1.4 | Grounded plan; schema focus; strict values | 100 | 32.57% | 143 | 46.58% | 43 | 69.93% | $1.596 |
| v1.5 | Relational closure; dual schema views; value tournament | 100 | 32.57% | 144 | 46.91% | 44 | 69.44% | $1.740 |
| v1.6 | Shared semantic contract; relation routes | 130 | 42.35% | 171 | 55.70% | 41 | 76.02% | $1.975 |
| v1.7 reference | Train-only structural prompting; execution repair | 130 | 42.35% | 177 | 57.65% | 47 | 73.45% | $1.997 |
| v1.7 main | Different difficulty-proxy subset; not longitudinally comparable | 160 | 52.12% | 201 | 65.47% | 41 | 79.60% | $2.037 |
| v1.8 | Answer plan; cardinality guard; four-way tournament | 136 | **44.30%** | 171 | 55.70% | **35** | 79.53% | $2.134 |
| v1.9 | Adaptive projection; top-two verification; conditional regeneration | 134 | 43.65% | 170 | 55.37% | 36 | 78.82% | **$1.943** |

The valid longitudinal result is that v1.6 improved candidate generation, v1.8 produced the best controlled selected score and lowest regret, and v1.9 reduced cost by approximately 9% relative to v1.8 with a 0.65-point accuracy decrease. The v1.7 main score must not be used as evidence of a version improvement because it used a different subset.

### A.3 v1.8 selector and error details

The v1.8 full BIRD selector recorded 392 deterministic/non-invoked decisions, 805 successful verification selections, and 337 verification-error fallbacks. Of 193 regret cases, 116 came from a successful tournament selecting the wrong candidate, 60 followed verification failure and fallback, and 17 came from deterministic selection.

Overlapping regret labels were: execution-result disagreement (192), projection (175), filter (163), join (131), literal/value (113), table (70), ranking (32), output grain (30), aggregation (29), grouping (21), `DISTINCT` placement (18), ratio logic (15), time boundary (7), and set operation (6). These counts show that semantic alternatives, not merely malformed SQL, dominate selection difficulty.

The v1.8 full schema diagnostics were:

| Evidence type | Precision | Recall | F1 |
|---|---:|---:|---:|
| Tables | 28.27% | 99.53% | 44.03% |
| Columns | 7.08% | 99.58% | 13.23% |
| Combined schema | 9.47% | 99.56% | 17.29% |
| Joins | 0.58% | 0.56% | 0.57% |

The system usually retained required schema elements, but with substantial irrelevant context. This supports focusing future work on connected, typed schema paths and semantic obligation coverage rather than maximizing recall alone.

### A.4 v1.8 resource and cost profile

| Stage | Calls | Total tokens | Cost |
|---|---:|---:|---:|
| SQL generation | 7,671 | 40.11M | $6.22 |
| Schema completion | 1,916 | 19.23M | $1.20 |
| Selector tournament | 3,916 | 11.13M | $1.63 |
| SQL revision | 677 | 4.44M | $0.63 |
| Semantic revision | 317 | 2.91M | $0.41 |
| **Total** | **14,497** | **77.83M** | **$10.10** |

Median latency was 11.99 seconds and P95 latency was 104.09 seconds. Generation and schema completion dominate cost, so selector-only optimization cannot recover the 479 no-oracle questions.

## Appendix B. Comparison With Published and Current SOTA Results

Published scores are context, not automatically comparable results. Backbone model, database access, prompt resources, candidate count, test-time compute, gold-schema access, and evaluation track can change the score substantially.

### B.1 BIRD comparison

The repository's literature table records the following representative BIRD-dev results:

| Method | Reported BIRD result | Main strategy |
|---|---:|---|
| MCS-SQL | 65.5% | Multi-prompt candidates and selection |
| CHESS | 65.0% | Value/context retrieval and schema pruning |
| CHASE-SQL | 73.01% | Multi-path reasoning and query-plan selection |
| XiYan-SQL | 75.63% | Schema filtering, multi-generator ensemble, self-refinement |
| DeepEye-SQL | 73.5% | Value retrieval, N-version SQL, unit-test revision |
| SIRIUS-SQL | 75.88% | Execution-grounded lifecycle and hybrid selector |
| Agentar-Scale-SQL | 81.67% | Test-time scaling and orchestration |
| **SlayQL v1.8** | **56.19%** | Retrieval, relation propagation, five candidates, execution and selection |

SlayQL is therefore below the reported BIRD SOTA range by roughly 17-26 percentage points. This does not mean the architecture is useless: its candidate-oracle score of 68.77% shows meaningful generation capacity, and its analysis exposes selection and schema-noise failure modes that final accuracy hides. It does mean that the thesis must claim an empirical orchestration and diagnostic contribution, not leaderboard superiority.

The official [BIRD benchmark page](https://bird-bench.github.io/) should be checked at submission time because leaderboard tracks, backbones, and evaluation protocols change.

### B.2 Spider1.0 comparison

The recorded SlayQL Spider1.0 result is 65.39% with three candidates. Published Text-to-SQL systems commonly report approximately 85-92% on Spider1.0 test under stronger or differently configured settings. The 91.47% given-oracle selection rate indicates that the selector is not the principal bottleneck; missing or semantically incorrect candidates are.

Spider1.0 is also substantially easier than BIRD and Spider2.0-Lite in schema scale and enterprise complexity. Consequently, a cross-dataset average is not scientifically meaningful. Report each benchmark separately.

### B.3 Spider2.0-Lite comparison

The original Spider2.0 paper reported only 5.68% overall execution accuracy for DAIL-SQL + GPT-4o on Spider2.0-Lite, with 5.79%, 1.46%, and 0.43% on easy, medium, and hard examples respectively. The benchmark contains 547 questions across BigQuery, Snowflake, and SQLite and is designed around realistic enterprise schemas and dialects. See the [Spider2.0 paper](https://arxiv.org/abs/2411.07763) and the [official Spider2 site](https://spider2-sql.github.io/).

More recent public leaderboard snapshots report substantially higher numbers. For example, the SOTA2 listing currently shows SOMA-SQL at 69.3% with GPT-5.3 Codex, 65.8% with GPT-5, and AutoLink at 46.3% with GPT-5.3 Codex. These are useful current-context figures, but they are not a substitute for official submission verification and may use different backend availability and evaluation policies. See the [current Spider Lite 2.0 leaderboard snapshot](https://www.sota2.com/research/sota/text-to-sql-on-spider-lite-2-0).

The historical SlayQL Spider2.0-Lite score of 45.89% fixed-denominator is therefore competitive with some older agentic/parser baselines but cannot be called current SOTA. It is also not a complete apples-to-apples comparison if later SlayQL runs omit Snowflake. The correct claim is: “SlayQL demonstrates a strong restricted-backend baseline and a reproducible path for improving cross-dialect execution,” followed by separate local, BigQuery, and Snowflake results.

### B.4 What current SOTA systems do better

The highest-performing systems generally combine several capabilities that SlayQL only partially implements:

- stronger or specialized backbone models;
- larger test-time candidate budgets or deliberate scaling;
- aggressive minimal-schema filtering rather than high-recall noisy context;
- explicit query-plan or multi-path reasoning;
- richer value and documentation retrieval;
- stronger preference/reranking or verifier models;
- training or reinforcement learning on verified SQL data in some systems;
- complete access to all benchmark backends.

SlayQL's distinctive research opportunity is the API-only setting: test whether structured obligation tracking, typed relation closure, risk routing, and deterministic audit selection recover some of these gains without updating the base model. The comparison must report model and token budgets so that additional inference compute is not misrepresented as an architectural gain.

## Appendix C. Publication-Ready Claims

### Supported claims

- Execution-grounded orchestration improved the recorded BIRD baseline by 7.04 percentage points.
- Candidate-oracle analysis separates generation failure from selection regret.
- v1.8 produced 68.77% candidate-oracle accuracy and 81.71% selection given oracle availability.
- Adaptive v1.9 selection reduced comparable subset cost by approximately 9% with a small accuracy trade-off.
- The pipeline provides resumable, auditable artifacts and explicit backend/error accounting.

### Claims requiring additional experiments

- OCAL/v3 improves Spider2.0-Lite accuracy over v1.9 under equal backend and token conditions.
- The architecture generalizes to Snowflake; this requires restored credentials or an officially approved alternative evaluation.
- The controller improves accuracy rather than merely increasing test-time compute.
- The method is SOTA on BIRD, Spider1.0, or Spider2.0-Lite.

The final paper should lead with the supported claims and use the additional experiments to test, rather than assume, the stronger claims.

## Appendix D. Model Provenance and Experimental Narrative

### D.1 Which model was used?

The pipeline does not hard-code a model identifier. The generation, revision, schema-completion, and selection scripts read the `MODEL_NAME` environment variable and send API requests through the configured OpenAI-compatible endpoint. The resolved run manifests record the architecture, seed, candidate count, prompt policy, and configuration hash, but they do not preserve the concrete value of `MODEL_NAME`.

This is a reproducibility gap that must be fixed before publication. The final report must record, for every run:

```text
model_id, provider, endpoint family, model revision/date,
temperature, max output tokens, reasoning setting,
candidate count, worker count, prompt version, and demonstration hash
```

The project notes and ablation scripts refer to strong API backbones such as DeepSeek-V3 and GPT-4o, but the exact backbone used for each completed v1.1-v1.9 result cannot be proven from the current manifests alone. Therefore this document does not falsely attribute a particular score to DeepSeek-V3. A thesis table should use `model_id=unverified` for historical runs and rerun the final baseline/proposed comparison with the exact identifier recorded.

### D.2 Why this model class was selected

The project deliberately uses a strong general-purpose API model rather than fine-tuning a local Text-to-SQL model. The reason is methodological: the experiment studies orchestration and database interaction, not parameter learning. A capable model reduces basic syntax failures and leaves the harder research questions visible: schema interpretation, value grounding, join selection, aggregation, output grain, and candidate selection. API inference also permits the same controller to be tested across SQLite, BigQuery, and Snowflake dialects.

This choice has two consequences. First, performance is a property of the model-plus-controller system, not the controller alone. Second, rate limits, provider outages, model revisions, and hidden endpoint changes are experimental variables. They must be logged and separated from semantic failure.

### D.3 The version-by-version story

The progression was driven by observed failure evidence rather than arbitrary feature accumulation.

**v1.1 established the baseline.** The original path combined BM25 value grounding, RBP relation propagation, IT-EE schema completion, multiple SQL candidates, execution, revision, and selection. The full BIRD run produced 754/1534 = 49.15%. This demonstrated that database interaction helped, but also showed that execution success was not equivalent to semantic correctness.

**v1.2 addressed evidence ordering.** Evidence was retrieved before completion and candidates were assigned independent roles. The controlled subset reached 93/307 = 30.29%, with only 137/307 = 44.63% oracle coverage. The result showed that a selector cannot compensate when the generator never produces a correct query.

**v1.3 addressed question linkage and ordinal meaning.** Question-linked evidence and an ordinal contract increased selected accuracy to 32.25% and reduced regret from 44 to 38, while oracle accuracy remained 44.63%. This worked primarily as a selection improvement, not as a generation improvement.

**v1.4 added grounded planning and stricter value handling.** Oracle accuracy rose to 46.58%, but selected accuracy moved only to 32.57% and regret increased to 43. More useful candidates were produced, but the selector still confused plausible alternatives.

**v1.5 added relational closure and multi-path routes.** Oracle accuracy increased slightly to 46.91%, but selected accuracy remained 32.57% and regret reached 44. The lesson was that candidate diversity without a shared semantic interpretation can make selection harder by creating multiple executable but wrong queries.

**v1.6 introduced the shared semantic contract.** Generation and selection received the same interpretation of filters, aggregation, ranking, projection, and relation routes. Selected accuracy rose to 42.35%, oracle accuracy to 55.70%, and given-oracle selection to 76.02%. This is the clearest generation breakthrough in the controlled sequence.

**v1.7 tested training-only structural prompting and repair.** The main subset scored 52.12% with 65.47% oracle accuracy, but it used a different difficulty policy. The reference-style rerun scored 42.35% and 57.65% oracle accuracy. Thus v1.7's high raw score is useful as a diagnostic observation, not as a clean longitudinal improvement.

**v1.8 concentrated on answer plans, cardinality, and selection.** The controlled subset reached the best comparable selected accuracy, 44.30%, and the lowest regret, 35. The full BIRD run reached 862/1534 = 56.19%, with 1055 oracle-correct candidates and 193 regret cases. The answer-plan guard improved selection, but the four-way selector incurred 3916 calls and the full run had 337 verification fallbacks, including quota failures.

**v1.9 tested efficiency.** Adaptive projection, top-two verification, and conditional regeneration reduced calls from 3073 to 2319 (-24.5%), tokens from 15.936M to 14.515M (-8.9%), and cost from $2.134 to $1.943 (-9.0%). Accuracy fell from 44.30% to 43.65%, while regret increased from 35 to 36. The result is an efficiency success, not an accuracy success. Prompt learning was disabled in the v1.9 resolved configuration, so the comparison is not a perfect one-variable ablation.

### D.4 What worked overall

The strongest evidence is concentrated in four findings:

1. Shared semantic contracts improved the candidate pool: v1.5 to v1.6 increased oracle accuracy by 8.79 percentage points on the reference subset.
2. Full BIRD accuracy improved 7.04 percentage points from the earlier baseline to v1.8.
3. Candidate-oracle analysis exposed 479 no-oracle questions and 193 regret questions; this identifies the next intervention more precisely than final accuracy alone.
4. Adaptive selection reduced v1.9 subset cost by 9.0% and calls by 24.5% while preserving 100% coverage and zero recorded execution errors.

### D.5 What did not work or remains unproven

- High-recall schema retrieval produced very low precision: 7.08% column precision and 17.29% combined-schema F1 in the v1.8 full diagnostic.
- Join matching was only approximately 0.57% F1, so relational reasoning is not solved.
- Adding relation routes in v1.5 did not improve selected accuracy.
- More selector comparisons cannot recover the 479 questions with no correct candidate.
- Semantic repair was rarely accepted; the v1.9 run triggered 56 repairs but accepted only one.
- The physical projection gate had too few applicable cases to establish a reliable effect.
- v1.8 selector conclusions are confounded by 337 provider-error fallbacks.
- v1.9's lower cost came with a 0.65-point accuracy loss on the comparable subset.
- The exact historical backbone model is not preserved in the manifests.
- Snowflake unavailability prevents a complete mixed-backend Spider2.0-Lite comparison.

### D.6 Interpretation for the thesis narrative

The research story is not “each version made the model smarter.” The evidence supports a more precise narrative:

```text
single baseline
 -> retrieve more evidence
 -> link evidence to the question
 -> generate relational alternatives
 -> share a semantic contract
 -> improve candidate generation
 -> improve candidate selection
 -> reduce selection cost
 -> identify generation, schema, and infrastructure ceilings
```

The central finding is that the bottleneck moved. Early versions were limited by missing evidence and missing candidates. v1.6 improved the candidate ceiling. v1.8 improved selection quality. v1.9 showed that cheaper selection can preserve operational reliability but slightly reduce accuracy. The remaining gap is primarily semantic planning, connected join reasoning, schema-noise control, and reliable cross-dialect execution.

### D.7 Required final-model table

Before submitting the thesis, replace the historical provenance gap with a table like this for every final run:

| Run | Model ID and revision | Provider | Temperature | Candidates | Dataset IDs | Backend policy | Total tokens | Cost | Accuracy |
|---|---|---|---:|---:|---|---|---:|---:|---:|
| v1.9 baseline rerun | to be recorded | to be recorded | to be recorded | 5 | frozen subset/full split | local/BQ/SF status | to be recorded | to be recorded | to be recorded |
| proposed controller | to be recorded | to be recorded | to be recorded | matched | identical IDs | identical policy | to be recorded | to be recorded | to be recorded |

Without this table, the numerical results remain useful engineering evidence but are weaker as a reproducible model comparison.

## Appendix E. Version-by-Version Metrics Table

This is the consolidated metrics table for the thesis. `P/R/F1` means precision, recall, and F1. Accuracy values for v1.2-v1.9 are from the same 307-question BIRD development subset family, except that v1.7 main used a different subset policy. The full BIRD and Spider1.0 rows are separate experiments and must not be averaged with the subset rows.

### E.1 Accuracy, selection, and reliability

| Version/run | Dataset/scope | Correct / N | Final accuracy | Coverage | Candidate oracle | Oracle accuracy | Regret | Given-oracle selection | Exact match | Exec errors | Gold errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1.0 historical | Spider2.0-Lite mixed backends | 251 / 547 | **45.89% fixed**; 47.63% evaluable | 96.34% evaluable | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded | 20 error-only | Not recorded |
| v1.1-era baseline | BIRD dev full | 754 / 1534 | **49.15%** | 100% | 947 | 61.73% | 193 | 79.62% | 0.261% | 0 | 0 |
| v1.1-era baseline | Spider1.0 test full, 3 candidates | 1404 / 2147 | **65.39%** | 100% | 1535 | 71.50% | 136 | 91.47% | 0.093% | 0 | 0 |
| v1.2 | BIRD subset20, 307 | 93 / 307 | **30.29%** | 100% | 137 | 44.63% | 44 | 67.88% | 0.326% | 0 | 0 |
| v1.3 | BIRD subset20, 307 | 99 / 307 | **32.25%** | 100% | 137 | 44.63% | 38 | 72.26% | 0.000% | 0 | 0 |
| v1.4 | BIRD subset20, 307 | 100 / 307 | **32.57%** | 100% | 143 | 46.58% | 43 | 69.93% | 0.000% | 0 | 0 |
| v1.5 | BIRD subset20, 307 | 100 / 307 | **32.57%** | 100% | 144 | 46.91% | 44 | 69.44% | 0.000% | 0 | 0 |
| v1.6 | BIRD subset20, 307 | 130 / 307 | **42.35%** | 100% | 171 | 55.70% | 41 | 76.02% | 0.000% | 0 | 0 |
| v1.7 main | BIRD difficulty-proxy subset, 307 | 160 / 307 | **52.12%** | 100% | 201 | 65.47% | 41 | 79.60% | 0.000% | 0 | 0 |
| v1.7 reference | BIRD reference-style subset, 307 | 130 / 307 | **42.35%** | 100% | 177 | 57.65% | 47 | 73.45% | 0.652% | 0 | 0 |
| v1.8 | BIRD subset20, 307 | 136 / 307 | **44.30%** | 100% | 171 | 55.70% | **35** | 79.53% | 0.000% | 0 | 0 |
| v1.9 | BIRD subset20, 307 | 134 / 307 | **43.65%** | 100% | 170 | 55.37% | 36 | 78.82% | 0.652% | 0 | 0 |
| v1.8 full | BIRD dev full | 862 / 1534 | **56.19%** | 100% | 1055 | **68.77%** | 193 | **81.71%** | Not reported in aggregate | 0 | 0 |

The v1.0 Spider2.0-Lite coverage value is `527/547 = 96.34%` when error-only records are included in the denominator. The BIRD and Spider1.0 runs achieved complete coverage, so their execution and fixed-denominator accuracies coincide.

### E.2 Schema-linking metrics

| Version/run | Table P/R/F1 | Column P/R/F1 | Combined schema P/R/F1 | Strict schema recall | Schema noise | Join F1 |
|---|---:|---:|---:|---:|---:|---:|
| v1.0 historical Spider2.0-Lite | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded |
| v1.1-era BIRD full | 28.28 / 99.57 / 44.05 | 7.08 / 99.54 / 13.22 | 9.47 / 99.55 / 17.30 | 98.44% | 86.14% | 0.00 |
| v1.1-era Spider1.0 full | 32.07 / 100.00 / 48.56 | 14.98 / 91.35 / 25.73 | 18.88 / 94.53 / 31.48 | 81.09% | 75.68% | 0.00 |
| v1.2 | 30.06 / 99.83 / 46.21 | 7.20 / 99.40 / 13.42 | 9.73 / 99.55 / 17.72 | 98.37% | 85.32% | 0.00 |
| v1.3 | 30.05 / 99.83 / 46.20 | 7.20 / 99.32 / 13.43 | 9.73 / 99.49 / 17.73 | 98.05% | 85.32% | 0.00 |
| v1.4 | 40.10 / 95.04 / 56.40 | 16.96 / 89.65 / 28.53 | 21.32 / 91.49 / 34.58 | 74.27% | 75.74% | 0.00 |
| v1.5 | 32.41 / 98.68 / 48.79 | 11.37 / 95.30 / 20.32 | 14.70 / 96.45 / 25.52 | 86.64% | 82.24% | 0.00 |
| v1.6 | 32.45 / 98.68 / 48.83 | 11.40 / 95.21 / 20.37 | 14.74 / 96.39 / 25.57 | 86.32% | 82.20% | 0.00 |
| v1.7 main | 33.17 / 97.77 / 49.54 | 11.69 / 94.57 / 20.80 | 15.05 / 95.65 / 26.00 | 84.04% | 81.46% | 0.33 |
| v1.7 reference | 32.36 / 98.68 / 48.73 | 11.35 / 95.30 / 20.29 | 14.68 / 96.45 / 25.47 | 86.64% | 82.25% | 0.00 |
| v1.8 | 29.96 / 99.83 / 46.09 | 7.20 / 99.40 / 13.44 | 9.73 / 99.55 / 17.73 | 98.37% | 85.32% | 1.07 |
| v1.9 | 30.00 / 99.83 / 46.14 | 7.21 / 99.40 / 13.44 | 9.74 / 99.55 / 17.74 | 98.37% | 85.31% | 0.00 |

The schema results tell a consistent story: recall was already very high, but precision and F1 were low. In v1.8, combined schema recall was 99.55% while combined F1 was only 17.73%, implying approximately 85.32% schema noise. Improving recall further is unlikely to solve the main semantic errors; the system needs minimal connected schema projections and more reliable join-path reasoning.

### E.3 Calls, tokens, cost, and latency

| Version/run | SQL generation calls | Schema completion | SQL revision | Selector | Semantic revision | Total calls | Total tokens | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1.0 historical Spider2.0-Lite | Not recorded | Not recorded | Not recorded | Not recorded | Not recorded | 187 instrumented queries | 29.709M instrumented | Not recorded |
| v1.1-era BIRD full | 7,672 | 1,823 | 599 | 1,129 | 0 | **11,223** | **56.851M** | **$5.243** |
| v1.1-era Spider1.0 full | 6,445 | n/a | 445 | 1,056 | 0 | **7,946** | **19.436M** | **$2.919** |
| v1.2 | 1,535 | 366 | 160 | 237 | 0 | **2,298** | **13.471M** | **$1.590** |
| v1.3 | 1,535 | 370 | 141 | 235 | 0 | **2,281** | **13.075M** | **$1.670** |
| v1.4 | 1,535 | 451 | 229 | 233 | 0 | **2,448** | **11.478M** | **$1.596** |
| v1.5 | 1,535 | 415 | 149 | 531 | 0 | **2,630** | **13.407M** | **$1.740** |
| v1.6 | 1,536 | 449 | 159 | 242 | 0 | **2,386** | **12.939M** | **$1.975** |
| v1.7 main | 1,535 | 419 | 189 | 209 | 69 | **2,421** | **13.342M** | **$2.037** |
| v1.7 reference | 1,537 | 448 | 162 | 213 | 59 | **2,419** | **13.394M** | **$1.997** |
| v1.8 | 1,535 | 346 | 164 | 948 | 80 | **3,073** | **15.936M** | **$2.134** |
| v1.9 | 1,535 | 366 | 160 | 202 | 56 | **2,319** | **14.515M** | **$1.943** |

The v1.8 full BIRD run has a separate detailed usage ledger: 14,497 calls, 77.83M total tokens, $10.10, 11.99-second median latency, and 104.09-second P95 latency. The difference between this and the compact stage table reflects additional instrumentation and verification events in the full run; the thesis should cite the full-run usage ledger for full BIRD and the compact table for the 307-question subset experiments.

For the directly comparable v1.8/v1.9 subset pair:

| Metric | v1.8 | v1.9 | Change |
|---|---:|---:|---:|
| Calls | 3,073 | 2,319 | -24.5% |
| Prompt tokens | 11.873M | 11.242M | -5.3% |
| Completion tokens | 4.064M | 3.272M | -19.5% |
| Total tokens | 15.936M | 14.515M | -8.9% |
| Reasoning tokens | 3.502M | 2.767M | -21.0% |
| Cost | $2.134 | $1.943 | -9.0% |
| Median latency | 13.54s | 14.41s | +0.87s |
| P95 latency | 96.69s | 91.91s | -4.78s |

### E.4 Checkpoint and completion metrics

| Version/run family | Coverage | Incomplete instances | Stage completion | Interpretation |
|---|---:|---:|---:|---|
| v1.1-era BIRD full | 100% | 0 / 1534 | Complete | Reliable local baseline |
| v1.1-era Spider1.0 full | 100% | 0 / 2147 | Complete | Reliable local baseline |
| v1.2-v1.9 subset runs | 100% each | 0 / 307 each | Complete | Checkpointing worked in completed experiments |
| v1.8 full BIRD | 100% | 0 / 1534 | Complete | Full integrity report available |
| v1.0 Spider2.0-Lite | 96.34% evaluable coverage | 20 error-only | Historical complete artifact | Errors retained in fixed denominator |

### E.5 Research interpretation of the numbers

The numerical progression supports five conclusions.

1. **The large gain came from semantics, not syntax repair.** v1.5 to v1.6 increased subset oracle accuracy from 46.91% to 55.70% (+8.79 points) and selected accuracy from 32.57% to 42.35% (+9.78 points). This is the strongest controlled generation improvement.
2. **Selection matters, but its ceiling is bounded.** v1.8 full BIRD had 193 selection-regret cases, yet 479 questions had no correct candidate. A perfect selector could reach only 68.77%, below the 75% target.
3. **The v1.8 selector improved quality at high cost.** On the subset, v1.8 reduced regret to 35 but used 948 selector calls. v1.9 reduced selector calls to 202 and total cost by 9%, but selected accuracy fell 0.65 points and regret rose by one.
4. **High schema recall hides weak schema precision.** v1.8 retained 99.55% of required schema elements but achieved only 17.73% combined F1. The model was given most required evidence together with substantial irrelevant context.
5. **Operational reliability is not semantic accuracy.** All local runs had full coverage and zero execution errors, but executable SQL could still use the wrong join, filter, aggregation, or projection. This is why the thesis reports execution accuracy, oracle coverage, regret, schema metrics, and provider failures separately.

### E.6 Historical model limitation

The run artifacts preserve architecture revisions, dataset hashes, candidate counts, token usage, costs, and checkpoints, but the exact `MODEL_NAME` value is not embedded in every historical manifest. The scripts obtain it from the environment. Consequently, the table above reports system metrics without attributing them to DeepSeek-V3, GPT-4o, or another specific model. A final reproducible rerun must record the exact model identifier and provider alongside these metrics.

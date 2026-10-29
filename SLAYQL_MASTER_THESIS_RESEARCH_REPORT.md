# SlayQL: An Execution-Grounded Agentic Framework for Cross-Dataset Text-to-SQL

## Master Thesis Research Report

**Version:** 1.0  
**Report date:** 2026-08-31  
**Repository:** `D:\SlayQL-v1.1\C-CaSE`  
**Primary full BIRD run:** `run\bird_dev_v18_full`  
**Status:** Complete for the recorded BIRD and Spider1.0 runs; historical Spider2.0-Lite v1 retained as a reference baseline.

## Abstract

Large language models can translate natural-language questions into executable SQL, but accuracy falls when a question requires implicit schema interpretation, value grounding, multi-table joins, aggregation, ranking, or duplicate control. This project studies SlayQL, an API-based agentic Text-to-SQL pipeline that combines schema and value retrieval, relational propagation, database interaction, multi-candidate SQL generation, execution feedback, revision, and candidate selection.

The system was developed incrementally from v1.1 through v1.9. The main research question is whether additional agentic interaction and execution-grounded candidate selection improve accuracy under a fixed prompt and API-based inference setting. The strongest completed full local run, SlayQL v1.8 on BIRD development, achieves **862/1534 = 56.19% execution accuracy**, improving the earlier full baseline of **754/1534 = 49.15%** by **7.04 percentage points**. The five-candidate pool contains at least one correct answer for **1055/1534 = 68.77%** of questions, establishing a candidate-generation ceiling for the run. The remaining difference consists of 193 selection-regret cases, where a correct candidate existed but the selected candidate was incorrect under the evaluator.

The results show that selection is important but not sufficient. There are 479 BIRD questions for which none of the five candidates is correct, so no selector can recover them. The dominant remaining errors concern semantic interpretation, join-path construction, aggregation, filtering, and output grain. The v1.8 run also contains a provider-quota confound: 337 verification decisions ended in an error fallback, including HTTP 403 total-key-limit failures. Consequently, a scientifically valid selector comparison must separate model disagreement from API failure and strict result-shape effects.

The thesis conclusion is that SlayQL is a useful execution-grounded research platform and demonstrates measurable progress, but the current architecture should not be claimed as state of the art or as a fundamentally novel algorithm. A stronger publication contribution would formalize a budget-aware controller that selects among schema projection, relation verification, value retrieval, repair, regeneration, and abstention using execution and semantic uncertainty.

**Keywords:** Text-to-SQL, large language models, agentic systems, execution feedback, candidate generation, candidate selection, schema linking, BIRD, Spider, API inference, cost-aware reasoning.

## 1. Research Problem

### 1.1 Motivation

Traditional Text-to-SQL systems often treat generation as a single prediction problem. That assumption is weak for real databases because a correct answer may require:

- resolving an ambiguous natural-language reference to a database value;
- identifying a connected multi-table relation path;
- distinguishing maximum value from top-ranked row;
- preserving the requested row grain after a one-to-many join;
- choosing the correct aggregate denominator;
- applying time and literal constraints exactly;
- selecting the requested output attributes rather than returning extra columns.

SlayQL treats Text-to-SQL as a sequence of evidence and decision stages. The database is used as an execution environment, and multiple SQL candidates are generated so that the system can compare alternatives rather than trust one sample.

### 1.2 Research objective

The project evaluates whether a progressively improved agentic pipeline can increase execution accuracy on BIRD, Spider1.0, and Spider2.0-Lite while preserving:

1. Full checkpointing and resumability.
2. Fixed prompt length and turn budgets where accuracy depends on them.
3. API-only inference without reinforcement-learning updates to the base model.
4. Explicit cost, latency, and coverage accounting.
5. Strict separation between training demonstrations and evaluation questions.
6. Support for local SQLite, BigQuery, and optional Snowflake backends.

### 1.3 Research questions

**RQ1. Candidate generation:** Does structured evidence, semantic contracting, relation routing, and targeted revision increase the probability that at least one candidate is correct?

**RQ2. Candidate selection:** Given a pool containing a correct candidate, can execution-result comparison and answer-plan constraints reliably select it?

**RQ3. Interaction:** Does giving the model database evidence and execution feedback improve semantic correctness more than adding generic SQL repair turns?

**RQ4. Efficiency:** Can selector and repair calls be gated by uncertainty to reduce API cost without reducing accuracy?

**RQ5. Robustness:** Do the findings transfer across BIRD, Spider1.0, and the mixed local/BigQuery portion of Spider2.0-Lite?

**RQ6. Scientific validity:** Can the pipeline distinguish model errors from provider failures, evaluator strictness, incomplete backend access, and subset-selection effects?

## 2. Claims and Non-Claims

### 2.1 Claims supported by the artifacts

- v1.8 improves the recorded full BIRD baseline from 49.15% to 56.19%.
- Candidate-oracle measurement reveals a generation ceiling that final accuracy alone hides.
- Semantic contracts and relation-route candidates in v1.6 produce the first clear candidate-pool improvement in the controlled subset series.
- v1.8 reduces subset selection regret relative to v1.7 reference and v1.9, although its full-run selector was affected by API quota errors.
- v1.9 demonstrates a cost reduction relative to v1.8 on the comparable subset, at a small accuracy loss.
- Checkpointing and artifact manifests provide reproducible stage-level recovery.

### 2.2 Claims not supported by the current evidence

- SlayQL is not demonstrated to be SOTA on BIRD or Spider1.0.
- The 75% BIRD and 80% Spider1.0 targets are not reached.
- The current combination of BM25, schema focus, execution repair, multiple candidates, and tournament selection is not by itself a novel algorithmic contribution; related methods already use these ideas.
- The v1.7 main subset score is not a clean architecture improvement because its subset policy differs from the reference-style subset.
- The historical Spider2.0-Lite v1 run has no recorded candidate-oracle accuracy.
- Static BIRD execution evaluation alone does not establish a claim about dynamic user interaction.

## 3. System Architecture

### 3.1 High-level pipeline

```text
Dataset normalization
        |
        v
Local/backend asset validation
        |
        v
BM25 value grounding + schema retrieval
        |
        v
RBP relation propagation + IT-EE schema completion
        |
        v
Question-linked schema focus and interaction context
        |
        v
Semantic contract / answer plan
        |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
  Candidate route 0   Candidate route 1   Full-schema fallback
        |                   |                   |
        +-------------------+-------------------+
                            |
                            v
                  SQL candidate execution
                            |
                            v
                  SQL revision / repair
                            |
                            v
            Execution result and structural diagnostics
                            |
                            v
                Selector or bounded verification
                            |
                            v
                    Selected SQL and result
                            |
                            v
              Strict evaluation + research metrics
```

### 3.2 Stage descriptions

#### Dataset normalization

Dataset adapters convert BIRD, Spider1.0, and Spider2.0-Lite records into a common manifest. Each instance stores the question, evidence, gold SQL where available, backend, database path or service identifier, and split. Local assets are validated before inference.

#### Value grounding

BM25 indices retrieve database cell values related to entities and literals in the question. Exact-match overrides and strict subphrase rejection were added in later versions to reduce unsupported literal insertion. Value grounding is important for BIRD questions whose schema names do not directly reveal the required values.

#### Schema and relation evidence

Initial schema retrieval obtains candidate tables and columns. RBP-style propagation expands evidence through relational links. IT-EE completion asks the model to complete or refine the schema context. Later versions add question-linked focus, relational closure, and multiple relation hypotheses.

#### Semantic contract and answer plan

Later versions derive deterministic fields from the question and dataset evidence. These include expected aggregations, ranking intent, grouping, ratio logic, time constraints, requested entities, expected output grain, and projection requirements. The contract is shared by generation and selection.

#### Candidate generation

The default BIRD configuration generates five independent candidates. Candidates are routed through different schema views or relation hypotheses. A full-schema fallback prevents an incorrect retrieval decision from permanently excluding a needed table.

#### Execution and revision

Candidates are executed against local SQLite or supported remote backends. Runtime errors, empty results, and structural contradictions can trigger revision or semantic regeneration. Original candidates are preserved so that revisions do not destroy the evidence needed for oracle analysis.

#### Candidate selection

The selector receives candidate SQL, execution outcomes, structural comparisons, and the semantic contract. v1.8 uses a four-way pairwise result tournament with an answer-plan guard. v1.9 reduces the budget to top-two conditional verification and adds a physical projection gate.

#### Evaluation

The evaluator computes strict execution accuracy, fixed-denominator accuracy, coverage, execution errors, gold errors, candidate-oracle accuracy, selection regret, schema metrics, join metrics, exact match, token usage, latency, and selection status counts.

### 3.3 Checkpointing and reproducibility

Every stage writes per-instance or stage-level artifacts. The v1.8 full integrity report contains:

- 1534 expected instances;
- 1534 instance checkpoints;
- zero incomplete instances;
- complete local assets, retrieval, schema, interaction, generation, execution, revision, selection, and evaluation stages.

The run manifest stores the schema version, architecture revision, dataset, split, seed, candidate count, worker count, target, configuration hash, and status. Demonstration files are recorded with SHA-256 hashes.

## 4. Experimental Protocol

### 4.1 Datasets and splits

| Dataset | Split used | Backend | Role in the study |
|---|---|---|---|
| BIRD | Dev, 1534 instances | Local SQLite | Primary full-run development benchmark |
| Spider1.0 | Test, 2147 instances | Local SQLite | Cross-dataset generalization benchmark |
| Spider2.0-Lite | Historical full v1, 547 instances | Local SQLite, BigQuery, Snowflake | Original project baseline; later Snowflake access unavailable |

BIRD dev and Spider1.0 test are reported separately. BIRD dev is not a hidden test set and should not be presented as an official test score.

### 4.2 Subset protocol

The research-suite `subset20` mode selects 20% of a dataset for rapid iteration and concentrates the remaining 80% on harder or previously incorrect questions. This is useful for development but is not a blind sample. The v1.7 main run used a different difficulty-proxy subset and is therefore not directly comparable with the reference-style subset used by v1.8 and v1.9.

The correct use of the subset is:

- select architectural hypotheses;
- inspect failure categories;
- compare fixed configurations;
- gate an expensive full run.

The incorrect use is to report the subset score as a leaderboard result or as an unbiased estimate of full-dataset accuracy.

### 4.3 Demonstration and leakage protocol

v1.7 and v1.8 use BIRD training examples for structural prompt learning. The v1.8 full run records the demonstration source as:

```text
D:\Downloads\train\train\train.json
D:\Downloads\train\train\train_gold.sql
```

The files are hashed in `resolved_config.json`. No BIRD dev examples are listed as demonstrations. The reference-correctness subset uses prior correctness information to construct a diagnostic sample, so it remains development data and cannot be treated as a leakage-free test protocol.

### 4.4 Candidate count and API setting

The v1.8 BIRD run uses five candidates per instance, four workers, a 12,000-character interaction context cap, and API-based inference. The base model is not updated through reinforcement learning. Prompt learning is training-only retrieval and formatting guidance.

### 4.5 Primary metrics

For a set of evaluable instances `E`:

```text
Execution accuracy = correct selected results / |E|
```

For all expected instances `N`:

```text
Fixed-denominator accuracy = correct selected results / N
```

Coverage is the proportion of instances with a selected prediction. A candidate is oracle-correct if at least one generated or revised candidate matches a gold result under the evaluator. Selection regret is defined as:

```text
candidate-oracle-correct AND selected-result-incorrect
```

The candidate oracle is an upper bound for the existing candidate pool, not a model confidence score.

## 5. Full Benchmark Results

### 5.1 BIRD full runs

| Run | Correct | Expected | Execution accuracy | Coverage | Candidate oracle | Oracle accuracy | Selection regret | Given-oracle selection |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Earlier full baseline (`bird_dev_full`) | 754 | 1534 | **49.15%** | 100% | 947 | 61.73% | 193 | 79.62% |
| v1.8 full (`bird_dev_v18_full`) | 862 | 1534 | **56.19%** | 100% | 1055 | **68.77%** | 193 | **81.71%** |

The v1.8 run improves by 108 correct questions. The oracle ceiling rises by 108 questions as well, from 947 to 1055. The absolute number of regret cases remains 193, but the selector's recovery among oracle-correct cases improves from 79.62% to 81.71%.

The 75% target requires at least 1151 correct answers on 1534 questions. The v1.8 run therefore needs 289 additional correct answers, or 18.81 percentage points.

### 5.2 Spider1.0 full run

| Run | Correct | Expected | Execution accuracy | Coverage | Candidate oracle | Oracle accuracy | Selection regret | Given-oracle selection |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Spider1.0 full, three candidates | 1404 | 2147 | **65.39%** | 100% | 1535 | 71.50% | 136 | 91.47% |

The 80% target requires at least 1718 correct answers, so this run needs approximately 314 additional correct answers. The high given-oracle selection rate indicates that candidate selection is less limiting on Spider1.0 than on BIRD; the remaining gap is primarily candidate generation and task interpretation.

### 5.3 Historical Spider2.0-Lite v1

| Metric | Value |
|---|---:|
| Manifest instances | 547 |
| Evaluable result files | 527 |
| Error-only outputs | 20 |
| Correct | 251 |
| Accuracy over evaluable outputs | **47.63%** |
| Fixed-denominator accuracy | **45.89%** |
| Candidate-oracle accuracy | **Not recorded** |

The later three-instance no-Snowflake smoke run reports 2/3 final correct and 3/3 candidate-oracle correct. That is an infrastructure check, not a Spider2.0-Lite benchmark result. Snowflake became unavailable, so a later full score using only local and BigQuery instances would not be directly comparable with the mixed-backend v1 baseline.

## 6. BIRD Subset Version Progression

The following rows use the recorded 307-question subset runs. v1.7 main is explicitly non-comparable because it uses a different subset policy.

| Version | Architectural change | Selected | Selected accuracy | Oracle | Oracle accuracy | Regret | Given-oracle selection | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v1.2 | Evidence before completion; independent candidate roles | 93 | 30.29% | 137 | 44.63% | 44 | 67.88% | $1.590 |
| v1.3 | Question-linked evidence; ordinal contract | 99 | 32.25% | 137 | 44.63% | 38 | 72.26% | $1.670 |
| v1.4 | Grounded plan; schema focus; strict values | 100 | 32.57% | 143 | 46.58% | 43 | 69.93% | $1.596 |
| v1.5 | Relational closure; dual schema views; value tournament | 100 | 32.57% | 144 | 46.91% | 44 | 69.44% | $1.740 |
| v1.6 | Shared semantic contract; relation routes | 130 | 42.35% | 171 | 55.70% | 41 | 76.02% | $1.975 |
| v1.7 main | Train-only structural prompting; execution repair; different subset | 160 | **52.12%** | 201 | **65.47%** | 41 | 79.60% | $2.037 |
| v1.7 reference | Same v1.7 architecture; reference-style subset | 130 | 42.35% | 177 | 57.65% | 47 | 73.45% | $1.997 |
| v1.8 | Answer plan; cardinality guard; four-way tournament | 136 | **44.30%** | 171 | 55.70% | **35** | 79.53% | $2.134 |
| v1.9 | Adaptive projection; top-two verification; conditional regeneration | 134 | 43.65% | 170 | 55.37% | 36 | 78.82% | **$1.943** |

### 6.1 Version conclusions

**v1.2:** Established the versioned subset, evidence-first processing, and independent candidate roles. The low oracle score shows that selection could not compensate for weak candidate generation.

**v1.3:** Reduced regret without increasing the candidate oracle. This supports a selector benefit, but not a generation benefit.

**v1.4:** Increased oracle coverage through grounded planning and stricter values, but selected accuracy barely moved because regret remained high.

**v1.5:** Added relational closure and multi-path alternatives. The slight oracle increase did not improve selected accuracy; more plausible alternatives made selection harder.

**v1.6:** Introduced the strongest controlled generation improvement. A shared semantic contract gave generation and selection the same interpretation of aggregation, ranking, projection, and relation routes.

**v1.7:** Train-only structural prompt retrieval and selective repair helped on the main subset, but the changed subset makes the raw 52.12% score unsuitable for a longitudinal claim. The reference rerun is the valid comparison.

**v1.8:** Produced the best controlled subset selected score and lowest subset regret. Its answer-plan/cardinality guard improved comparison quality, but its selector was expensive and the full run suffered API verification failures.

**v1.9:** Reduced selector calls and cost but slightly reduced accuracy. Prompt learning was disabled in its resolved configuration, so the v1.8-to-v1.9 comparison is not a perfect one-variable ablation.

## 7. Selector-Focused Analysis

### 7.1 Generation versus selection decomposition

For v1.8 full BIRD:

| Outcome | Questions | Share |
|---|---:|---:|
| At least one candidate is correct | 1055 | 68.77% |
| No candidate is correct | 479 | 31.23% |
| Final selected answer is correct | 862 | 56.19% |
| Correct candidate existed but was not selected | 193 | 12.58% of all questions |

The 479 no-oracle questions are generation/planning failures. The 193 regret questions are selection, verification, projection, or evaluator-equivalence failures. A perfect selector can reach at most 68.77% on the existing candidate files.

To reach 75%, the candidate pool must gain at least 96 additional oracle-correct questions beyond 1055. This makes candidate generation and semantic planning the primary research bottleneck.

### 7.2 Selector status and provider reliability

The v1.8 full selection summary records:

| Selector status | Count | Share |
|---|---:|---:|
| Deterministic / verifier not invoked | 392 | 25.55% |
| Verification selected a winner | 805 | 52.48% |
| Verification error and deterministic fallback | 337 | 21.97% |

Among the 193 regret cases:

| Regret path | Count | Share of regret |
|---|---:|---:|
| Successful tournament selected wrong candidate | 116 | 60.1% |
| Verification error caused wrong fallback | 60 | 31.1% |
| Deterministic selection selected wrong candidate | 17 | 8.8% |

One stored error contains:

```text
Error code: 403 - Key limit exceeded (total limit)
```

The selector retried three times, then fell back. Those 60 error-path regrets should not be interpreted as pure model-selection failures. A quota-stable rerun is required before claiming an unbiased selector comparison.

### 7.3 Disagreement categories

The v1.8 regret artifacts contain overlapping disagreement labels:

| Reason | Regret cases |
|---|---:|
| Execution-result disagreement | 192 |
| Projection disagreement | 175 |
| Filter disagreement | 163 |
| Join disagreement | 131 |
| Literal/value disagreement | 113 |
| Table disagreement | 70 |
| Ranking disagreement | 32 |
| Output-grain disagreement | 30 |
| Aggregation disagreement | 29 |
| Grouping disagreement | 21 |
| DISTINCT placement | 18 |
| Ratio logic | 15 |
| Time boundary | 7 |
| Set operation | 6 |

The selector therefore faces semantic alternatives, not only malformed SQL. Execution-result disagreement is nearly universal, but result disagreement alone cannot identify which candidate best matches the user's intent.

### 7.4 Projection and evaluator-equivalence issue

Instance `local_bird_dev_1002_01002` provides a representative case. The question asks for the full name, nationality, and first race of the youngest racer.

Two candidates return four columns:

```text
forename | surname | nationality | race_name
Lance    | Stroll  | Canadian    | Australian Grand Prix
```

The selected candidate returns three columns:

```text
full_name    | nationality | race_name
Lance Stroll | Canadian    | Australian Grand Prix
```

The selected query is arguably acceptable under the natural-language phrase “full name,” but the strict evaluator expects separate `forename` and `surname` columns and rejects the different shape. This is reported as selection regret even though it is partly an output-contract issue.

The correct methodological response is not to silently relax the official score. The evaluator should report two metrics:

1. **Strict benchmark execution accuracy:** exact result shape and values under the benchmark protocol.
2. **Intent-normalized diagnostic accuracy:** safe equivalences such as aliases, user-requested name concatenation, and non-semantic column naming differences.

### 7.5 Selector interpretation

The results support four conclusions:

1. A selector is useful because 193 correct candidates were available but not selected.
2. A selector cannot recover the 479 no-oracle questions.
3. Pairwise LLM judgments can prefer a concise or plausible query over one that better satisfies output grain and benchmark projection.
4. Provider quota errors and evaluator projection rules materially affect the observed regret count.

## 8. Schema, Join, and Semantic Diagnostics

### 8.1 v1.8 full schema metrics

| Metric | Precision | Recall | F1 |
|---|---:|---:|---:|
| Tables | 28.27% | 99.53% | 44.03% |
| Columns | 7.08% | 99.58% | 13.23% |
| Combined schema | 9.47% | 99.56% | 17.29% |
| Joins | 0.58% | 0.56% | 0.57% |

Combined schema noise is approximately 86.14%. The system usually includes the needed elements, but passes a large amount of irrelevant context to the model. Join identification remains the weakest direct metric. Join scores may be partly sensitive to SQL aliases, but they still do not support a claim that relation reasoning is solved.

### 8.2 Implication for architecture

The project initially treated high schema recall as a success condition. The later metrics show why this is insufficient. If required columns are present but the prompt contains many irrelevant columns, the model can still choose the wrong relation, aggregation, or output grain. Future retrieval should optimize a joint objective:

```text
retain required elements + minimize irrelevant elements + preserve connected join paths
```

A table-only or column-only retrieval score is not enough. The retrieval stage should produce explicit connected relation hypotheses and cardinality warnings for one-to-many joins.

## 9. Cost and Latency Analysis

### 9.1 v1.8 full resource use

| Resource | Value |
|---|---:|
| API calls | 14,497 |
| Prompt tokens | 59.57M |
| Completion tokens | 18.26M |
| Total tokens | 77.83M |
| Reasoning tokens | 15.66M |
| Recorded cost | $10.10 |
| Cost per question | $0.00658 |
| Median latency | 11.99 s |
| P95 latency | 104.09 s |

### 9.2 v1.8 stage distribution

| Stage | Calls | Total tokens | Cost |
|---|---:|---:|---:|
| SQL generation | 7,671 | 40.11M | $6.22 |
| Schema completion | 1,916 | 19.23M | $1.20 |
| Selector tournament | 3,916 | 11.13M | $1.63 |
| SQL revision | 677 | 4.44M | $0.63 |
| Semantic revision | 317 | 2.91M | $0.41 |

Generation and schema completion dominate cost. Selector optimization matters, but reducing selector calls alone cannot solve the 479 no-oracle questions.

### 9.3 v1.8 versus v1.9 subset efficiency

| Metric | v1.8 | v1.9 | Change |
|---|---:|---:|---:|
| Calls | 3,073 | 2,319 | -24.5% |
| Total tokens | 15.936M | 14.515M | -8.9% |
| Cost | $2.134 | $1.943 | -9.0% |
| Accuracy | 44.30% | 43.65% | -0.65 pp |
| Regret | 35 | 36 | +1 |

v1.9 is a valid efficiency experiment, not an accuracy improvement. The disabled prompt-learning configuration also limits the strength of the comparison.

## 10. Literature Positioning

The current SlayQL architecture overlaps with several published or publicly available methods:

| Prior work | Relevant idea | Reported result |
|---|---|---:|
| [MCS-SQL](https://arxiv.org/abs/2405.07467) | Multiple prompts, schema linking, candidates, confidence filtering, multiple-choice selection | 65.5% BIRD; 89.6% Spider |
| [CHESS](https://arxiv.org/pdf/2405.16755) | Value/context retrieval, schema pruning, generation pipeline, execution-aware evaluation | 65.0% BIRD dev in the reported setup |
| [CHASE-SQL](https://arxiv.org/abs/2410.01943) | Multi-path reasoning, query-plan reasoning, synthetic examples, preference selector | 73.01% BIRD dev |
| [XiYan-SQL](https://arxiv.org/abs/2507.04701) | Schema filter, multi-generator ensemble, self-refine, candidate reorganization | 75.63% BIRD; 89.65% Spider |
| [DeepEye-SQL](https://arxiv.org/abs/2510.17586) | Semantic value retrieval, N-version SQL, unit-test style revision, confidence-aware selection | 73.5% BIRD dev; 89.8% Spider |
| [Agentar-Scale-SQL](https://arxiv.org/abs/2509.24403) | Orchestrated internal, sequential, and parallel test-time scaling | 81.67% BIRD test reported |
| [SIRIUS-SQL](https://arxiv.org/abs/2606.01246) | Execution-grounded lifecycle, targeted repair, hybrid selector, structural tie-breaker | 75.88% BIRD dev; 91.20% Spider |
| [BIRD-Interact](https://arxiv.org/abs/2510.05318) | Dynamic clarification, tool exploration, user simulation, follow-up tasks | Interaction benchmark rather than static EX |

The official [BIRD benchmark page](https://bird-bench.github.io/) currently lists many dev results in the 70% range and emphasizes that leaderboard settings may differ in backbone, oracle knowledge, candidate scale, and evaluation track. SlayQL's 56.19% result therefore should not be presented as a direct SOTA comparison without matching those conditions.

### 10.1 Novelty assessment

The following elements are established patterns rather than sufficient novelty by themselves:

- BM25 value grounding;
- schema linking and schema pruning;
- multiple SQL candidates;
- execution-result voting or tournament selection;
- SQL self-repair;
- answer-plan or query-plan prompting;
- deterministic checkpoints and concurrent API calls.

A defensible novel contribution would need a new algorithmic controller or a new empirical finding. A promising formulation is:

> **Budget-Constrained Evidence-Directed Test-Time Orchestration for Text-to-SQL:** a controller that chooses schema projection, relation verification, value retrieval, repair, regeneration, or abstention based on a structured uncertainty state and estimated marginal accuracy per token.

To support this claim, the policy must be formalized, implemented independently of fixed prompts, and compared against strong baselines under equal model, candidate, evidence, and budget conditions.

## 11. Error Taxonomy and Causal Interpretation

### 11.1 Error classes

| Error class | Observable evidence | Likely cause | Selector can fix? |
|---|---|---|---|
| No correct candidate | Oracle false | Wrong schema, join, filter, aggregation, value, or grain | No |
| Correct candidate not selected | Oracle true, final false | Ranking, contract, execution disagreement, projection | Yes, sometimes |
| Provider verification failure | Status `error`, HTTP 403/429 or empty response | API quota, transient service, malformed response | No; requires infrastructure handling |
| Projection mismatch | Same semantic content, different output shape | Candidate contract or strict evaluator | Partly |
| Join fan-out | Duplicate or wrong-grain rows | Missing cardinality reasoning | Sometimes |
| Value mismatch | Wrong literal or unsupported synonym | Retrieval or value grounding | Sometimes |
| Aggregate mismatch | Wrong MAX, COUNT, AVG, denominator, or grouping | Question interpretation | Sometimes |
| Evaluation mismatch | Strict shape/order differs from natural-language answer | Benchmark protocol | No under strict score; report diagnostic metric |

### 11.2 Causal ranking of bottlenecks

For v1.8 full BIRD, the evidence supports this order:

1. Candidate generation and semantic planning: 479 no-oracle questions.
2. Candidate selection and contract enforcement: 193 regret questions.
3. Provider reliability: 337 selector error fallbacks, including 60 regret cases.
4. Schema precision and relation selection: high recall but high noise and very low join F1.
5. SQL syntax repair: operationally useful, but not the dominant accuracy gap.

This ranking explains why simply increasing SQL revision turns is unlikely to reach 75%.

## 12. Future Improvement Program

### 12.1 Phase A: Make selector evaluation scientifically clean

1. Run the selector on the frozen v1.8 candidate files with a quota-stable API key.
2. Persist each pairwise decision and retry state atomically.
3. Add a circuit breaker for repeated 403/429 responses.
4. Report `provider_error`, `invalid_response`, and `model_disagreement` separately.
5. Compare v1.8 tournament, v1.9 top-two verification, deterministic execution voting, and contract-first selection.
6. Do not regenerate SQL during this phase.

This isolates selection quality from candidate generation.

### 12.2 Phase B: Add projection and grain semantics

The selector should enforce hard constraints before pairwise judgment:

- requested entity and attributes;
- output grain;
- number and role of projected attributes;
- aggregation and denominator;
- duplicate policy;
- connected join path;
- expected ranking or limit;
- literal and time constraints.

Candidate comparison should then combine:

```text
hard contract validity
+ execution result evidence
+ relation-path validity
+ answer-plan agreement
+ calibrated selector confidence
```

LLM explanations should not override a hard contract violation.

### 12.3 Phase C: Target no-oracle questions

The generator should route additional calls based on diagnosed failure type instead of adding unconditional candidates. Recommended routes include:

- join-graph reconstruction with primary/foreign-key checks;
- aggregation and denominator decomposition;
- max/min versus top-k distinction;
- time-boundary normalization;
- set-operation reasoning;
- output-grain and fan-out testing;
- value lookup with exact and approximate matches.

Conditional regeneration should occur only when the current candidate pool fails a contract or execution gate. This keeps prompt length and turn depth available while spending extra calls where the oracle is currently absent.

### 12.4 Phase D: Cost-aware orchestration

Define an inference state:

```text
state = {
  candidate disagreement,
  execution status distribution,
  contract violations,
  schema uncertainty,
  relation-path uncertainty,
  current token cost,
  remaining budget
}
```

The controller chooses the next action using expected value:

```text
action value = expected accuracy gain / expected incremental token cost
```

Actions with low expected value should terminate early. Close selector margins, missing join paths, and unresolved projection conflicts should receive more budget than unanimous, contract-valid candidates.

### 12.5 Phase E: Evaluate actual interaction

Static BIRD execution demonstrates database-grounded SQL generation, but not dynamic dialogue. The interaction claim should be evaluated on BIRD-Interact or Mini-Interact, where the agent can request clarification, inspect evidence, and recover from errors. Report success rate, interaction count, token cost, and recovery rate separately from static execution accuracy.

### 12.6 Phase F: Controlled publication experiment

The final experiment should use:

- one frozen model version;
- one fixed dataset revision;
- identical demonstrations;
- identical candidate counts;
- identical maximum turns;
- identical backend availability;
- at least three random seeds or repeated API samples;
- confidence intervals or bootstrap intervals;
- full BIRD dev and Spider1.0 test;
- a separate Spider2.0-Lite local/BigQuery analysis labeled as non-comparable to the historical mixed-backend score;
- ablations for retrieval, semantic contract, relation routes, repair, selector, and adaptive controller.

## 13. Recommended Thesis Contributions

A realistic master-thesis contribution statement is:

1. **A reproducible execution-grounded Text-to-SQL framework** supporting multiple datasets, local and remote backends, resumable checkpoints, and detailed usage metrics.
2. **A candidate-oracle and selection-regret analysis protocol** that decomposes final accuracy into generation and selection effects.
3. **A semantic-contract candidate routing design** that improves the candidate pool on a controlled BIRD subset.
4. **An empirical study of cost-accuracy tradeoffs** between four-way tournament selection and top-two conditional verification.
5. **A failure taxonomy** showing that join reasoning, aggregation semantics, projection, provider reliability, and strict evaluation shape are separate causes of failure.

This is a strong systems and empirical thesis even if the method is not a new SOTA algorithm. The novelty should be claimed in the analysis, controlled orchestration policy, and reproducible evaluation rather than in the existence of candidate generation or voting alone.

## 14. Threats to Validity

### 14.1 External validity

BIRD dev and Spider1.0 test use local SQLite databases in this project. Results may not transfer to production databases, other SQL dialects, or unavailable Spider2.0-Lite Snowflake instances.

### 14.2 Backbone and provider effects

API model behavior, rate limits, caching, temperature, and provider routing affect candidate diversity and selector reliability. A 403 key-limit failure in v1.8 demonstrates that provider state can change the final score.

### 14.3 Subset selection bias

The 20% subset is intentionally difficulty-stratified and includes a reference-correctness policy. It is not an unbiased sample. v1.7 main cannot be compared directly with v1.8 or v1.9 without the reference-style rerun.

### 14.4 Metric strictness

Execution comparison requires matching dataframe shape and values. Different headers alone are ignored, but different column counts can cause rejection. This may undercount user-acceptable answers and should be reported as a separate diagnostic, not silently changed in the official metric.

### 14.5 Gold-query execution cost

Some BIRD gold queries are inefficient on SQLite. A query can be semantically simple but slow because of an aggregate subquery and missing indexes. Evaluation runtime should therefore be instrumented independently from model latency.

### 14.6 Exact match interpretation

Exact SQL match is near zero in these runs. This is not evidence that the system cannot produce correct SQL because multiple SQL formulations can produce the same execution result. Exact match remains a secondary diagnostic.

## 15. Reproducibility Checklist

- [x] Dataset manifest stored per run.
- [x] Database paths validated.
- [x] Per-instance checkpoints stored.
- [x] Stage completion and incomplete-instance report stored.
- [x] Configuration hashes stored.
- [x] Demonstration file hashes stored.
- [x] Candidate SQL and execution result artifacts preserved.
- [x] Selected SQL and selector decisions preserved.
- [x] Token, cost, and latency accounting preserved.
- [x] Candidate-oracle and selection-regret metrics reported.
- [x] Historical Spider2.0-Lite artifact preserved read-only.
- [ ] Quota-stable selector rerun completed.
- [ ] Full hidden-test submissions completed.
- [ ] Confidence intervals across repeated runs reported.
- [ ] BIRD-Interact evaluation completed.

## 16. Presentation Structure

### Slide 1: Problem

Natural-language SQL generation fails on schema ambiguity, joins, aggregation, values, and output grain.

### Slide 2: Research hypothesis

Execution-grounded interaction and structured candidate selection should improve reliability under a fixed API model.

### Slide 3: SlayQL architecture

Show the retrieval, interaction, candidate generation, execution, revision, and selection flow.

### Slide 4: Experimental protocol

Show BIRD, Spider1.0, Spider2.0-Lite, train-only demonstrations, subset gate, and checkpointing.

### Slide 5: Metrics

Explain selected accuracy, candidate oracle, selection regret, coverage, schema metrics, cost, and latency.

### Slide 6: Version timeline

Show v1.2 through v1.9 and the hypotheses tested at each step.

### Slide 7: Main full-run result

Show BIRD baseline 49.15% versus v1.8 56.19%.

### Slide 8: Oracle decomposition

Show 1055 oracle-correct, 862 selected-correct, 193 regret, and 479 no-oracle questions.

### Slide 9: Selector failure

Show verification errors, 403 quota failures, projection mismatch, and disagreement categories.

### Slide 10: Semantic bottleneck

Show high schema recall, low precision, high noise, and very low join F1.

### Slide 11: Literature positioning

Compare with CHESS, CHASE-SQL, XiYan-SQL, DeepEye-SQL, Agentar-Scale-SQL, and SIRIUS-SQL.

### Slide 12: Contribution and future work

Frame the contribution as reproducible cost-aware orchestration and oracle/regret analysis, then propose adaptive budgeted action selection and dynamic interaction evaluation.

## 17. Final Conclusion

SlayQL v1.1-v1.9 demonstrates that an API-based agentic pipeline can improve BIRD execution accuracy by 7.04 percentage points over the earlier full baseline. The best completed full result is v1.8 at 56.19%, with a 68.77% candidate-oracle ceiling. The system is fully covered and operationally resumable, but the target of 75% is not reached.

The central scientific finding is the separation between candidate generation and candidate selection. Of the 672 final BIRD failures in v1.8, 479 contain no correct candidate and cannot be repaired by selection. The remaining 193 contain a correct candidate but are affected by tournament decisions, provider errors, projection/grain conflicts, or strict evaluator shape. This explains why selector improvements produce useful but bounded gains.

The next version should therefore focus on a formal, uncertainty-driven, cost-aware controller for semantic planning, relation validation, candidate regeneration, and selection. The system should be evaluated under quota-stable conditions, with strict and intent-normalized metrics, fixed ablation protocols, confidence intervals, and a dynamic interaction benchmark. That framing is suitable for a rigorous master thesis and provides a credible path toward a stronger publication contribution without claiming unsupported SOTA performance.

## References

1. [BIRD benchmark and official leaderboard](https://bird-bench.github.io/)
2. [MCS-SQL: Leveraging Multiple Prompts and Multiple-Choice Selection for Text-to-SQL Generation](https://arxiv.org/abs/2405.07467)
3. [CHESS: Contextual Harnessing for Efficient SQL](https://arxiv.org/pdf/2405.16755)
4. [CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection in Text-to-SQL](https://arxiv.org/abs/2410.01943)
5. [XiYan-SQL: A Novel Multi-Generator Framework for Text-to-SQL](https://arxiv.org/abs/2507.04701)
6. [DeepEye-SQL: A Software-Engineering-Inspired Text-to-SQL Framework](https://arxiv.org/abs/2510.17586)
7. [Agentar-Scale-SQL: Advancing Text-to-SQL through Orchestrated Test-Time Scaling](https://arxiv.org/abs/2509.24403)
8. [SIRIUS-SQL: Anchoring Multi-Candidate Text-to-SQL in Execution Feedback](https://arxiv.org/abs/2606.01246)
9. [BIRD-Interact: Re-imagining Text-to-SQL Evaluation via Dynamic Interactions](https://arxiv.org/abs/2510.05318)
10. [The Death of Schema Linking? Text-to-SQL in the Age of Well-Reasoned Language Models](https://arxiv.org/abs/2408.07702)


# SlayQL Research Report: v1.0 to v1.9

**Report date:** 2026-08-31  
**Repository:** `D:\SlayQL-v1.1\C-CaSE`  
**Scope:** historical Spider2.0-Lite baseline, the local BIRD and Spider1.0 pivot, and all recorded SlayQL v1.1-v1.9 research runs.

## Executive Summary

The project began as a three-dataset text-to-SQL study covering BIRD, Spider1.0, and Spider2.0-Lite. The historical v1.0 Spider2.0-Lite run achieved **251/527 = 47.63% execution accuracy over evaluable instances**, or **251/547 = 45.89% using the fixed denominator**. Twenty Spider2.0-Lite questions had error-only outputs. That run depended on the mixed-backend evaluation environment, including Snowflake.

Snowflake access subsequently became unavailable. BigQuery and local SQLite remained usable, so the research focus shifted to BIRD and Spider1.0, both of which can be evaluated locally and reproducibly. Spider2.0-Lite support was retained, including backend exclusion, but no later full Spider2.0-Lite result is a fair replacement for the historical Snowflake-dependent baseline. A three-instance no-Snowflake smoke run is an infrastructure check, not a benchmark result.

The main findings are:

- The local pipeline is reliable: completed BIRD and Spider1.0 runs had full coverage and zero execution errors.
- The strongest recorded full local baselines are **49.15% on BIRD dev** and **65.39% on Spider1.0 test with three candidates**.
- On the controlled BIRD `subset20` family, v1.6 produced the first large generation improvement, and v1.7 produced the highest raw score (**52.12%**). However, that v1.7 run used a different subset policy and is not directly comparable with v1.8 or v1.9.
- The strongest directly comparable subset result is **v1.8 at 44.30%**, with 171/307 candidate-oracle accuracy and 35 selection-regret cases.
- v1.9 reduced API calls by **24.5%** and cost by **9.0%** versus v1.8, but accuracy fell slightly to **43.65%**. It is an efficiency variant, not an accuracy improvement.
- Candidate generation remains the dominant ceiling. In v1.9, only 170/307 questions had a correct candidate. Even a perfect selector could have reached only 55.37%, well below the 75% BIRD target.
- Schema recall is already very high, but precision is low and schema noise is high. Join-linking metrics are near zero. The remaining gap is semantic and relational reasoning, not basic database-file access or SQL execution reliability.

The `bird_dev_v18_full` run is now complete: 862/1534 = **56.19%** execution accuracy, with 1,055/1534 = **68.77%** candidate-oracle accuracy and 193 selection-regret cases. Its provider-error fallback rate is reported separately in the selector-focused report.

## Dataset Shift and Experimental Scope

### Original Spider2.0-Lite objective

The first evaluation path targeted Spider2.0-Lite across local SQLite, BigQuery, and Snowflake instances. Its official-style evaluator compared execution results and retained error-only cases in the fixed denominator.

Historical v1.0 artifact facts:

| Metric | Value |
|---|---:|
| Questions in manifest | 547 |
| Evaluable result files | 527 |
| Error-only cases | 20 |
| Correct results | 251 |
| Execution accuracy over evaluable results | 251/527 = **47.63%** |
| Fixed-denominator accuracy | 251/547 = **45.89%** |
| Instrumented token input | 29,286,499 |
| Instrumented token output | 422,869 |
| Instrumented total | 29,709,368 |
| Instrumented query count | 187 |
| Cost | Not recorded in the historical evaluator |

The token counter above is not directly comparable with later provider usage accounting because it covers only the instrumented historical query subset.

### Why the focus moved to BIRD and Spider1.0

Snowflake credentials/access were unavailable for the later research period. Continuing to claim a new full Spider2.0-Lite score would have mixed backend availability, incomplete coverage, and a different evaluation population. The project therefore used:

- **BIRD:** local SQLite databases, BIRD dev split for development, and train-only demonstrations when prompt learning was enabled.
- **Spider1.0:** repository-local SQLite databases and the standard Spider test split artifact.
- **Spider2.0-Lite:** retained as a supported adapter, with `-ExcludeBackend snowflake` available for smoke and local/BigQuery checks.

This is a methodological shift, not a claim that BIRD or Spider1.0 are substitutes for the Spider2.0-Lite leaderboard. Results across datasets must be reported separately.

## Evaluation Method

The active pipeline is staged:

1. Normalize the selected dataset and resolve local database assets.
2. Build or reuse BM25 value indices and retrieve schema/value evidence.
3. Propagate relational evidence with RBP and perform IT-EE-style schema completion.
4. Build question-linked schema focus and interaction context.
5. Generate independent SQL candidates.
6. Execute candidates against the local database where applicable.
7. Apply SQL revision and, in later versions, selective semantic revision.
8. Select the final candidate using deterministic evidence and/or a bounded verifier.
9. Evaluate execution, schema-linking, selector, usage, and checkpoint metrics.

The pipeline writes stage checkpoints and per-instance checkpoints. A run can resume completed stages, and final integrity reports list incomplete instances. All completed local runs cited below have zero incomplete instances.

### Metric definitions

| Metric | Definition |
|---|---|
| Execution accuracy | Correct result rows divided by evaluable instances |
| Fixed-denominator accuracy | Correct result rows divided by all expected instances |
| Coverage | Instances with a selected prediction divided by expected instances |
| SQL exact match | Whitespace-normalized selected SQL equal to gold SQL; diagnostic only |
| Candidate oracle | An instance has at least one correct generated/revised candidate |
| Candidate-oracle accuracy | Candidate-oracle instances divided by evaluable instances |
| Selection regret | A correct candidate existed, but the selected candidate was wrong |
| Selection accuracy given oracle | Correct selected answers divided by oracle-correct instances |
| Schema precision/recall/F1 | Linked schema elements compared with required table/column/join elements |
| Schema noise | Predicted linked elements not required by the gold query |
| Verification rate | Fraction of selection decisions requiring an LLM verifier |
| Deterministic rate | Fraction of decisions resolved without a verifier |

The complete JSON artifacts contain macro and micro table, column, join, and combined-schema metrics. The tables below report the principal micro metrics and the run-level operational metrics.

## Full Baseline Results Before the v1.2-v1.9 Subset Series

The two local full runs below are schema-version `1.0` artifacts produced by the active pipeline and used as the v1.1-era baseline. They do not contain a `research_version` field, so calling them a fully isolated v1.1 architecture experiment would overstate the evidence.

| Run | Dataset/split | Candidates | Correct / expected | Execution and fixed accuracy | Coverage | Oracle | Oracle acc. | Regret | Given-oracle selection | Exact match | Calls | Total tokens | Cost | Missing usage |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `bird_dev_full` | BIRD dev | legacy pool | 754 / 1534 | **49.15%** | 100% | 947 | 61.73% | 193 | 79.62% | 0.261% | 11,223 | 56.851M | $5.243 | 0 |
| `spider1_test_full_3cand` | Spider1.0 test | 3 | 1404 / 2147 | **65.39%** | 100% | 1535 | 71.50% | 136 | 91.47% | 0.093% | 7,946 | 19.436M | $2.919 | 3 |

Both full local runs reported zero execution errors and zero gold/evaluator errors. The BIRD run had 1,534/1,534 instance checkpoints complete; the Spider1.0 run had 2,147/2,147 complete.

### Baseline interpretation

- **BIRD:** 49.15% is 25.85 percentage points below the stated 75% target. A 75% score would require at least 1,151 correct answers, so the baseline needs approximately 397 additional correct questions.
- **Spider1.0:** 65.39% is 14.61 percentage points below the stated 80% target. An 80% score requires at least 1,718 correct answers, approximately 314 above this run.
- The BIRD selector already lost 193 cases where a correct candidate existed. The candidate-oracle ceiling (61.73%) is itself below the target, so selector work alone cannot close the BIRD gap.

## v1.2-v1.9 BIRD Development Progression

All rows below contain 307 questions and five candidates unless noted. Most runs use a reference-correctness-stratified subset (`20%` easy/correct and `80%` hard/incorrect by the reference policy). v1.7 also has a main run using a different difficulty-proxy subset. The subset is an iteration tool, not a blind benchmark.

| Version/run | Main architectural change | Correct / 307 | Accuracy | Oracle / 307 | Oracle acc. | Regret | Given-oracle | Calls | Total tokens | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1.2 `v12_bird_dev_subset20` | Evidence before completion; independent candidate roles | 93 | **30.29%** | 137 | 44.63% | 44 | 67.88% | 2,298 | 13.471M | $1.590 |
| v1.3 `v13_bird_dev_subset20` | Selective question-linked evidence and ordinal contract | 99 | **32.25%** | 137 | 44.63% | 38 | 72.26% | 2,281 | 13.075M | $1.670 |
| v1.4 `v14_bird_dev_subset20` | Grounded question plan, schema focus, strict value grounding | 100 | **32.57%** | 143 | 46.58% | 43 | 69.93% | 2,448 | 11.478M | $1.596 |
| v1.5 `v15_bird_dev_subset20` | Relational closure, dual schema views, value-aware tournament | 100 | **32.57%** | 144 | 46.91% | 44 | 69.44% | 2,630 | 13.407M | $1.740 |
| v1.6 `v16_bird_dev_subset20` | Shared semantic contract and relation-route candidates | 130 | **42.35%** | 171 | 55.70% | 41 | 76.02% | 2,386 | 12.939M | $1.975 |
| v1.7 main `v17_bird_dev_subset20` | Train-only structural prompt learning and execution-grounded repair; different difficulty-proxy subset | 160 | **52.12%** | 201 | 65.47% | 41 | 79.60% | 2,421 | 13.342M | $2.037 |
| v1.7 reference `v17_bird_dev_subset20_reference` | Same v1.7 architecture on the reference-style subset | 130 | **42.35%** | 177 | 57.65% | 47 | 73.45% | 2,419 | 13.394M | $1.997 |
| v1.8 `bird_dev_v18_subset20` | Answer-plan/cardinality guard and four-way result tournament | 136 | **44.30%** | 171 | 55.70% | 35 | 79.53% | 3,073 | 15.936M | $2.134 |
| v1.9 `bird_dev_v19_subset20` | Adaptive schema projection, physical projection contract, top-two conditional verification | 134 | **43.65%** | 170 | 55.37% | 36 | 78.82% | 2,319 | 14.515M | $1.943 |

All these completed subset runs had 307/307 coverage, zero execution errors, and zero gold/evaluator errors. Their exact-match rates were between 0% and 0.65%; this is expected to be a weak diagnostic because semantically equivalent SQL often differs textually.

### Version-by-version research interpretation

#### v1.1: operational foundation and selector-first hypothesis

The v1.1 work made the pipeline researchable across datasets. It preserved broad retrieval, BM25 value grounding, RBP propagation, IT-EE completion, five-candidate generation, execution, revision, and evaluation. The main proposed accuracy change was selector-first candidate comparison: if a correct candidate already exists, improve final selection before replacing the generator.

This was a reasonable low-deviation hypothesis, but the full BIRD baseline showed why it was insufficient by itself: the candidate-oracle ceiling was only 61.73%, and selection regret was 193.

#### v1.2: evidence-guided generation

v1.2 moved evidence collection earlier and assigned deterministic roles to independent candidates. It established the versioned subset and usage accounting, but the selected score was only 30.29%. The oracle was 44.63%, proving that most errors were still upstream candidate-generation failures rather than only selector failures.

#### v1.3: selective interaction

v1.3 narrowed interaction to question-linked evidence and added an ordinal contract. Accuracy rose 1.96 percentage points without increasing the oracle count, while regret fell from 44 to 38. This is evidence that better candidate comparison helped, but it did not yet create more correct SQL.

#### v1.4: grounded planning and value controls

v1.4 introduced a grounded question plan, focused schema limits, and stricter value matching. The candidate oracle rose from 137 to 143, and combined schema precision improved substantially on this subset. However, selected accuracy rose by only one answer because regret remained high at 43. The run reduced irrelevant schema context but also reduced schema recall and strict recall.

#### v1.5: relational multi-path reasoning

v1.5 expanded the focused schema through relational closure and generated multiple relation paths. Oracle accuracy increased slightly to 46.91%, but selected accuracy did not improve. The value-aware tournament increased selector calls and cost. This indicates that adding relation paths without stronger semantic constraints created more alternatives than the selector could reliably distinguish.

#### v1.6: semantic contracts and routed candidates

v1.6 shared a deterministic semantic contract between generation and selection and routed candidates through relation hypotheses, with a full-schema fallback. This was the first clear generation breakthrough in the reference-style subset: 100 to 130 correct answers and oracle accuracy from 46.91% to 55.70%. Regret fell modestly from 44 to 41. The improvement supports the hypothesis that explicit question semantics and relation routes matter more than SQL syntax repair alone.

#### v1.7: prompt learning and execution-grounded repair

v1.7 added train-only structural retrieval demonstrations, selective semantic repair, and consensus-aware selection. Its main run scored 52.12%, but it used `difficulty_proxy_20_easy_80_hard`, unlike the reference-style subset used by v1.8 and v1.9. The separate v1.7 reference run scored 42.35%. Therefore the 52.12% result cannot be treated as a clean architecture gain over v1.6 or v1.8. It does show that train-only structural examples and repair can substantially help when the evaluation subset is favorable.

There is no evidence of dev-gold prompt leakage in the recorded configuration: the demonstration source is the BIRD train set. Nevertheless, a subset selected using reference correctness is development data and must not be presented as an untouched test result.

#### v1.8: answer plans and tournament selection

v1.8 added answer-plan/cardinality guards, non-destructive semantic repair, and a four-way result tournament. On the same reference-style 307-question source used by v1.9, it achieved the best directly comparable accuracy: 136/307 = 44.30%. It also achieved the lowest regret in the v1.8-v1.9 pair, 35 cases. The cost was high: 948 selector tournament calls and $0.501 of selector cost on the subset.

The improvement was mainly in selecting among existing candidates, not in expanding the candidate oracle: v1.8 and v1.6 both had 171 oracle-correct instances.

#### v1.9: adaptive projection and cost reduction

v1.9 replaced the four-way tournament with top-two contract verification and added conditional regeneration and a physical projection gate. This reduced calls from 3,073 to 2,319 and cost from $2.134 to $1.943. However, accuracy fell from 44.30% to 43.65%, oracle accuracy fell from 55.70% to 55.37%, and regret increased from 35 to 36.

The v1.9 run also had prompt learning disabled in `resolved_config.json`, whereas v1.8 used the train demonstration configuration. This is an experimental confound and means the v1.8/v1.9 comparison is not a perfect one-variable ablation. The physical projection gate was present but only a few physical-output contracts occurred, so it was effectively inactive at aggregate scale.

## Operational and Stage Metrics

### Stage call counts

The pipeline intentionally keeps generation at approximately five calls per BIRD question and spends additional calls only on completion, revision, repair, and selection.

| Run | SQL generation | Schema completion | SQL revision | Selector | Semantic revision | Total calls |
|---|---:|---:|---:|---:|---:|---:|
| BIRD full baseline | 7,672 | 1,823 | 599 | 1,129 | 0 | 11,223 |
| Spider1.0 full, 3 candidates | 6,445 | n/a | 445 | 1,056 | 0 | 7,946 |
| v1.2 | 1,535 | 366 | 160 | 237 | 0 | 2,298 |
| v1.3 | 1,535 | 370 | 141 | 235 | 0 | 2,281 |
| v1.4 | 1,535 | 451 | 229 | 233 | 0 | 2,448 |
| v1.5 | 1,535 | 415 | 149 | 531 | 0 | 2,630 |
| v1.6 | 1,536 | 449 | 159 | 242 | 0 | 2,386 |
| v1.7 main | 1,535 | 419 | 189 | 209 | 69 | 2,421 |
| v1.7 reference | 1,537 | 448 | 162 | 213 | 59 | 2,419 |
| v1.8 | 1,535 | 346 | 164 | 948 | 80 | 3,073 |
| v1.9 | 1,535 | 366 | 160 | 202 | 56 | 2,319 |

### v1.8 versus v1.9 resource delta

| Metric | v1.8 | v1.9 | Delta |
|---|---:|---:|---:|
| API calls | 3,073 | 2,319 | **-24.5%** |
| Prompt tokens | 11.873M | 11.242M | -5.3% |
| Completion tokens | 4.064M | 3.272M | -19.5% |
| Total tokens | 15.936M | 14.515M | **-8.9%** |
| Reasoning tokens | 3.502M | 2.767M | -21.0% |
| Cached tokens | 2.429M | 2.308M | -5.0% |
| Cost | $2.134 | $1.943 | **-9.0%** |
| Cost per expected question | $0.006953 | $0.006330 | -9.0% |
| Median latency | 13.54 s | 14.41 s | +0.87 s |
| P95 latency | 96.69 s | 91.91 s | -4.78 s |

The cost reduction came primarily from selector calls: v1.8 used a 948-call tournament at $0.501, while v1.9 used 202 top-two verifier calls at $0.117. v1.9 actually spent more tokens on SQL generation and SQL revision than v1.8, so the efficiency gain was not a general reduction in reasoning context.

## Schema-Linking Findings

The combined schema metrics show why schema retrieval should not be judged only by recall.

| Run | Table P/R/F1 | Column P/R/F1 | Combined schema P/R/F1 | Strict schema recall | Schema noise | Join F1 |
|---|---:|---:|---:|---:|---:|---:|
| BIRD full baseline | 28.28 / 99.57 / 44.05 | 7.08 / 99.54 / 13.22 | 9.47 / 99.55 / 17.30 | 98.44% | 86.14% | 0.00 |
| Spider1.0 full | 32.07 / 100.00 / 48.56 | 14.98 / 91.35 / 25.73 | 18.88 / 94.53 / 31.48 | 81.09% | 75.68% | 0.00 |
| v1.2 | 30.06 / 99.83 / 46.21 | 7.20 / 99.40 / 13.42 | 9.73 / 99.55 / 17.72 | 98.37% | 85.32% | 0.00 |
| v1.3 | 30.05 / 99.83 / 46.20 | 7.20 / 99.32 / 13.43 | 9.73 / 99.49 / 17.73 | 98.05% | 85.32% | 0.00 |
| v1.4 | 40.10 / 95.04 / 56.40 | 16.96 / 89.65 / 28.53 | 21.32 / 91.49 / 34.58 | 74.27% | 75.74% | 0.00 |
| v1.5 | 32.41 / 98.68 / 48.79 | 11.37 / 95.30 / 20.32 | 14.70 / 96.45 / 25.52 | 86.64% | 82.24% | 0.00 |
| v1.6 | 32.45 / 98.68 / 48.83 | 11.40 / 95.21 / 20.37 | 14.74 / 96.39 / 25.57 | 86.32% | 82.20% | 0.00 |
| v1.7 main | 33.17 / 97.77 / 49.54 | 11.69 / 94.57 / 20.80 | 15.05 / 95.65 / 26.00 | 84.04% | 81.46% | 0.33 |
| v1.7 reference | 32.36 / 98.68 / 48.73 | 11.35 / 95.30 / 20.29 | 14.68 / 96.45 / 25.47 | 86.64% | 82.25% | 0.00 |
| v1.8 | 29.96 / 99.83 / 46.09 | 7.20 / 99.40 / 13.44 | 9.73 / 99.55 / 17.73 | 98.37% | 85.32% | 1.07 |
| v1.9 | 30.00 / 99.83 / 46.14 | 7.21 / 99.40 / 13.44 | 9.74 / 99.55 / 17.74 | 98.37% | 85.31% | 0.00 |

The main inference is:

- Required tables and columns are almost always present, with combined recall around 95-100%.
- Precision is low, especially for columns, so the model sees a large amount of irrelevant schema.
- Focus-size changes between v1.8 and v1.9 were small: roughly six tables and forty columns per question. The adaptive projection did not materially change the information burden.
- Join-linking remains the weakest reported diagnostic. The zero values may include evaluator/parser limitations, but they provide no evidence that relation identification is solved.

## What Went Well

- Dataset adapters and local-asset validation made BIRD and Spider1.0 reproducible after the Snowflake outage.
- BM25 retrieval, RBP propagation, schema completion, SQL execution, and evaluation were retained across versions, allowing targeted architectural changes.
- Checkpointing worked in every completed run. For example, v1.9 reports 307 instance checkpoints, no incomplete instances, and every stage complete.
- v1.6's semantic contracts and relation routes materially increased candidate coverage on the reference-style subset.
- v1.8's tournament reduced selection regret to 35 on the directly comparable subset.
- v1.9 demonstrated a practical 9% cost reduction while maintaining full coverage and zero execution errors.
- Train-only demonstrations were explicitly recorded with hashes in v1.7 and v1.8 configurations, enabling leakage audits.

## What Did Not Work

- Selector improvements cannot recover missing candidates. This is the fundamental ceiling visible in both the full BIRD baseline and v1.9.
- More relation paths and larger focused schema views did not automatically produce better selected accuracy.
- Semantic repair was rarely accepted. In v1.9 it triggered 56 times but accepted only one repair.
- v1.9's top-two selector was cheaper but slightly less accurate than v1.8's tournament. Examples in the stored outcomes show correct candidates being rejected in favor of semantically plausible but wrong candidates.
- The selector can overvalue textual evidence. A majority/mode question can be misread as a lexical `MAX` operation even when execution evidence contradicts that interpretation.
- The v1.9 physical projection gate had too few applicable cases to validate its contribution.
- Schema noise remains high despite high recall. The pipeline has not yet demonstrated reliable join-graph grounding or robust aggregation semantics.
- The v1.7 main score is not a clean longitudinal improvement because its subset policy differs from the reference-style v1.2-v1.6/v1.8/v1.9 subset.
- The v1.9 run disabled prompt learning while v1.8 enabled it, so that pair is not a perfect controlled ablation.

## Target Gaps

| Dataset/metric | Current recorded result | Target | Gap |
|---|---:|---:|---:|
| Spider2.0-Lite fixed denominator | 45.89% (251/547) | 52% | 6.11 percentage points; at least 34 more fixed-denominator correct answers |
| BIRD full dev baseline | 49.15% (754/1534) | 75% | 25.85 percentage points; approximately 397 more correct answers |
| BIRD v1.9 subset20 | 43.65% (134/307) | 75% | 31.35 percentage points; 97 more selected correct answers |
| BIRD v1.9 candidate oracle | 55.37% (170/307) | 75% | 19.63 percentage points; at least 61 additional questions need a correct candidate even with a perfect selector |
| Spider1.0 full test, 3 candidates | 65.39% (1404/2147) | 80% | 14.61 percentage points; approximately 314 more correct answers |

The BIRD v1.9 oracle calculation is the most important diagnostic. The current selector has 36 regret cases, but eliminating all regret would raise the score only to 55.37%. Candidate generation, semantic interpretation, and relation reasoning must improve before selector tuning can reach 75%.

## Research Narrative

The project began with a practical agentic premise: a language model can improve text-to-SQL by interacting with schema, values, and execution feedback rather than producing one SQL string in isolation. The initial system already had the basic ingredients - BM25 value grounding, RBP relation propagation, IT-EE completion, candidate generation, execution, revision, and selection - but the first complete local BIRD result showed two distinct failure classes.

First, the candidate pool often lacked any correct query. Second, even when a correct candidate existed, the selector could choose a plausible but semantically wrong alternative. This led to a staged research strategy. v1.2-v1.5 concentrated on evidence, value grounding, schema focus, and relation closure. Those changes improved diagnostics but produced only modest selected accuracy. v1.6 then made the semantic interpretation explicit and shared it between generation and selection, which produced the first substantial oracle improvement. v1.7 explored train-only structural prompt learning and execution-grounded repair, but the highest score was confounded by a more favorable subset. v1.8 shifted effort to answer plans, cardinality checks, and stronger candidate comparison, yielding the best controlled subset result. v1.9 tested whether that comparison could be made cheaper with top-two verification and adaptive projection; it succeeded operationally but not in accuracy.

The resulting research conclusion is not that more SQL repair turns are required. The SQL syntax itself is rarely the only problem. The larger gap is understanding what the user asks, identifying the correct relation path, choosing the correct aggregation or set operation, and constraining the output projection. The next meaningful accuracy gain therefore requires better semantic query planning and relation-grounded candidate generation, with execution used as evidence rather than as a substitute for understanding.

## Reproducibility and Leakage Notes

- The historical Spider2.0-Lite artifacts are preserved under `run/log_spider2_full_slayql` and should be treated as read-only.
- BIRD and Spider1.0 full baseline artifacts are complete and locally evaluable.
- v1.2-v1.9 subset runs use deterministic run IDs, manifests, configuration hashes, and source hashes.
- v1.7 and v1.8 prompt learning uses BIRD train examples. No dev examples are listed as demonstration sources.
- v1.9 prompt learning is disabled in its resolved configuration.
- The reference-correctness subset policy uses prior correctness information to construct a hard diagnostic subset. This is acceptable for development iteration but is not a blind test protocol and must not be presented as an official leaderboard score.
- The completed `bird_dev_v18_full` run has `record_count=1534`, `num_candidates=5`, and `status=complete`; its score and checkpoint integrity report are available in the linked artifacts below.

## Artifact Index

### Historical v1.0 Spider2.0-Lite

- [Frozen handover and baseline facts](/D:/SlayQL-v1.1/C-CaSE/SLAYQL_V1_1_HANDOVER.md)
- [Historical SlayQL evaluator output](/D:/SlayQL-v1.1/C-CaSE/run/log_spider2_full_slayql/eval_result.txt)
- [Spider2.0-Lite evaluation suite README](/D:/SlayQL-v1.1/C-CaSE/evaluation_suite/README.md)

### Full local baselines

- [BIRD full summary](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_full/aggregates/summary_metrics.json)
- [BIRD full manifest](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_full/run_manifest.json)
- [Spider1.0 full, three-candidate summary](/D:/SlayQL-v1.1/C-CaSE/run/spider1_test_full_3cand/aggregates/summary_metrics.json)
- [Spider1.0 full manifest](/D:/SlayQL-v1.1/C-CaSE/run/spider1_test_full_3cand/run_manifest.json)

### Versioned BIRD subset results

- [v1.2 summary](/D:/SlayQL-v1.1/C-CaSE/run/v12_bird_dev_subset20/aggregates/summary_metrics.json)
- [v1.3 summary](/D:/SlayQL-v1.1/C-CaSE/run/v13_bird_dev_subset20/aggregates/summary_metrics.json)
- [v1.4 summary](/D:/SlayQL-v1.1/C-CaSE/run/v14_bird_dev_subset20/aggregates/summary_metrics.json)
- [v1.5 summary](/D:/SlayQL-v1.1/C-CaSE/run/v15_bird_dev_subset20/aggregates/summary_metrics.json)
- [v1.6 summary](/D:/SlayQL-v1.1/C-CaSE/run/v16_bird_dev_subset20/aggregates/summary_metrics.json)
- [v1.7 main summary](/D:/SlayQL-v1.1/C-CaSE/run/v17_bird_dev_subset20/aggregates/summary_metrics.json)
- [v1.7 reference summary](/D:/SlayQL-v1.1/C-CaSE/run/v17_bird_dev_subset20_reference/aggregates/summary_metrics.json)
- [v1.8 summary](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_subset20/aggregates/summary_metrics.json)
- [v1.9 summary](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v19_subset20/aggregates/summary_metrics.json)
- [v1.9 research summary](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v19_subset20/research_summary.json)
- [v1.9 resolved configuration](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v19_subset20/resolved_config.json)
- [v1.9 checkpoint integrity](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v19_subset20/aggregates/checkpoint_integrity.json)

### Completed full v1.8 run

- [BIRD full v1.8 manifest](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/run_manifest.json)
- [BIRD full v1.8 summary](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/aggregates/summary_metrics.json)
- [BIRD full v1.8 research summary](/D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/research_summary.json)

### Selector-focused analysis

- [Selector-focused v1.1-v1.9 report](/D:/SlayQL-v1.1/C-CaSE/SLAYQL_SELECTOR_FOCUSED_REPORT_V1_1_TO_V1_9.md)

## Final Conclusion

The most defensible current result is a split conclusion:

- **Best historical Spider2.0-Lite baseline:** v1.0, 45.89% fixed denominator and 47.63% over evaluable instances, with the Snowflake-dependent environment.
- **Best completed full local baseline:** the active pipeline's BIRD dev result at 49.15% and Spider1.0 test result at 65.39%.
- **Best completed full v1.8 BIRD run:** 862/1534 = **56.19%**, with a 68.77% candidate-oracle ceiling and 193 selection-regret cases.
- **Best directly comparable BIRD subset accuracy:** v1.8 at 44.30%.
- **Best BIRD subset efficiency:** v1.9 at 43.65% with 9% lower cost and 24.5% fewer calls.
- **Best raw subset score:** v1.7 main at 52.12%, but it is not comparable because the subset policy changed.

SlayQL v1.1-v1.9 demonstrates a functioning, checkpointed, execution-grounded agentic pipeline and identifies the important bottleneck. It does not yet match the stated 75% BIRD or 80% Spider1.0 targets, and it should not be described as SOTA on the basis of the current artifacts. A valid final comparison requires completed full runs on a frozen split, identical evaluator definitions, identical candidate and demonstration settings, and explicit reporting of candidate-oracle accuracy alongside selected accuracy.

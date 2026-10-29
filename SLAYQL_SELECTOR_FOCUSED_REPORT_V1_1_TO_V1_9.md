# SlayQL Selector-Focused Research Report: v1.1-v1.9

**Report date:** 2026-08-31  
**Repository:** `D:\SlayQL-v1.1\C-CaSE`  
**Primary full run:** `run\bird_dev_v18_full`  
**Scope:** candidate generation, execution, revision, selection, evaluation effects, and future improvements.

## Executive conclusion

SlayQL has made a measurable improvement on BIRD. The completed v1.8 full run scored **862/1534 = 56.19%**, compared with **754/1534 = 49.15%** for the earlier full baseline. This is an improvement of 108 correct questions, or **+7.04 percentage points**.

The result is not yet close to the 75% target. The most important diagnostic is the separation between candidate generation and selection:

| Quantity | Count | Accuracy |
|---|---:|---:|
| Final selected answer | 862 / 1534 | **56.19%** |
| At least one correct candidate | 1055 / 1534 | **68.77%** |
| Selection regret | 193 | 193 correct candidates were not selected |
| Perfect-selector ceiling | 1055 / 1534 | **68.77%** |

The selector is a real source of error, but it is not the only bottleneck. Even a perfect selector cannot reach 75% with the current candidate pool. At least 96 additional questions need a correct candidate before the target becomes reachable.

The v1.8 result also contains an infrastructure confound: **337 of 1534 verification decisions ended in an error fallback**, including OpenRouter HTTP 403 total-key-limit failures. Therefore, the final score measures the combined system under quota failure, not only the intended selector algorithm.

## Run validity and artifacts

The v1.8 full run is complete and has full coverage:

| Property | Value |
|---|---:|
| Dataset | BIRD dev |
| Expected/evaluable | 1534 / 1534 |
| Candidates | 5 per question |
| Coverage | 100% |
| Execution errors | 0 |
| Gold/evaluator errors | 0 |
| Target | 75% |
| Target reached | No |
| LLM calls | 14,497 |
| Total tokens | 77.83M |
| Recorded cost | $10.10 |

Artifacts:

- [v1.8 full summary](D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/aggregates/summary_metrics.json)
- [v1.8 full research summary](D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/research_summary.json)
- [v1.8 full selection artifacts](D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/selection)
- [Per-instance evaluation records](D:/SlayQL-v1.1/C-CaSE/run/bird_dev_v18_full/aggregates/summary_metrics.jsonl)

## What candidate-oracle accuracy means

Candidate-oracle accuracy asks:

> Did any generated, revised, and executed candidate produce the correct result?

It ignores which candidate was finally selected. For example, if candidate 2 is correct but the selector chooses candidate 0, the question counts as oracle-correct but final-wrong.

For v1.8 full BIRD:

- 1,055 questions had at least one correct candidate.
- 862 of those questions ended with a correct selected candidate.
- 193 questions had a correct candidate but selected the wrong candidate.
- 479 questions had no correct candidate at all.

This partitions the 672 failures as follows:

| Failure source | Questions | Interpretation |
|---|---:|---|
| No correct candidate | 479 | Generation, schema reasoning, value interpretation, or SQL logic failure |
| Correct candidate not selected | 193 | Selection, verification, projection, or evaluator-equivalence failure |
| Total incorrect final answers | 672 | 1534 - 862 |

The selector can recover only the second group. Improving selection alone cannot fix the 479 questions where every candidate is wrong.

## Selector behavior in the v1.8 full run

The recorded selector statuses were:

| Status | Count | Share |
|---|---:|---:|
| Deterministic/no verifier invoked | 392 | 25.55% |
| Verification selected a winner | 805 | 52.48% |
| Verification error and deterministic fallback | 337 | 21.97% |

Among the 193 selection-regret questions:

| Regret path | Count | Share of regret |
|---|---:|---:|
| Successful pairwise tournament selected the wrong answer | 116 | 60.1% |
| Verification error caused fallback to the wrong answer | 60 | 31.1% |
| Deterministic selection chose the wrong answer | 17 | 8.8% |

The 60 error-path regrets are not clean evidence against the selector logic. One stored example, `local_bird_dev_575_00575`, contains:

```text
Error code: 403 ... Key limit exceeded (total limit)
```

The system retried three times and then used the deterministic fallback. This is an API quota failure that changed the selected answer.

The remaining 116 successful-tournament regrets are the more meaningful selector research signal.

### Disagreement reasons on regret cases

The selection artifacts record the following material disagreements among the 193 regret cases:

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

These are overlapping labels, not mutually exclusive error categories. The pattern says that the selector often sees multiple executable candidates with different projections, joins, filters, and result values. It is not merely fixing SQL syntax.

## Concrete selector failure: projection equivalence

Instance `local_bird_dev_1002_01002` illustrates an important evaluation and selection issue.

The question asks for the full name, nationality, and first race of the youngest racer. Candidates 0 and 1 return:

```text
forename | surname | nationality | race_name
Lance    | Stroll  | Canadian    | Australian Grand Prix
```

Candidate 4, which the tournament selected, returns:

```text
full_name   | nationality | race_name
Lance Stroll| Canadian    | Australian Grand Prix
```

The selected query is arguably a valid answer to the natural-language question, but the official gold result has four columns, so the evaluator rejects the selected three-column result due to shape mismatch. This is recorded as selection regret even though part of the problem is output-schema equivalence.

This does not mean the evaluator should simply accept every projection. It means the system should distinguish:

1. Wrong values or wrong row grain.
2. Correct values with an equivalent projection requested by the user.
3. Correct values but an unacceptable projection under the benchmark protocol.

The report should retain strict benchmark accuracy while adding a separate intent-normalized projection metric.

## Version progression

The table below uses the recorded BIRD `subset20` runs. v1.7 main is marked as non-comparable because it used a different subset policy.

| Version | Main change | Selected | Oracle | Regret | Given-oracle selection | Assessment |
|---|---|---:|---:|---:|---:|---|
| v1.1 baseline | Broad retrieval, BM25, RBP, IT-EE, five candidates, selector-first | 754/1534 = 49.15% | 947/1534 = 61.73% | 193 | 79.62% | Generation ceiling already limited selector gains |
| v1.2 | Evidence before completion; independent candidate roles | 93/307 = 30.29% | 137/307 = 44.63% | 44 | 67.88% | Too many questions had no correct candidate |
| v1.3 | Question-linked evidence and ordinal contract | 99/307 = 32.25% | 137/307 = 44.63% | 38 | 72.26% | Better selection, no generation-ceiling improvement |
| v1.4 | Grounded plan, schema focus, strict value grounding | 100/307 = 32.57% | 143/307 = 46.58% | 43 | 69.93% | More oracle coverage, unstable selector |
| v1.5 | Relational closure and multi-path routes | 100/307 = 32.57% | 144/307 = 46.91% | 44 | 69.44% | More alternatives without enough discrimination |
| v1.6 | Shared semantic contract and relation routes | 130/307 = 42.35% | 171/307 = 55.70% | 41 | 76.02% | First clear generation breakthrough |
| v1.7 main | Train-only structural demonstrations and repair | 160/307 = 52.12% | 201/307 = 65.47% | 41 | 79.60% | Higher score, but different subset |
| v1.7 reference | Same architecture on reference-style subset | 130/307 = 42.35% | 177/307 = 57.65% | 47 | 73.45% | Shows v1.7 main was not a clean architecture comparison |
| v1.8 subset | Answer plan, cardinality guard, four-way tournament | 136/307 = 44.30% | 171/307 = 55.70% | 35 | 79.53% | Best controlled subset selected score |
| v1.9 subset | Adaptive projection and top-two conditional verification | 134/307 = 43.65% | 170/307 = 55.37% | 36 | 78.82% | 24.5% fewer calls, slightly worse accuracy |
| v1.8 full | Same v1.8 architecture on all BIRD dev | 862/1534 = **56.19%** | 1055/1534 = **68.77%** | **193** | **81.71%** | Best completed full BIRD run |

### Version interpretation

#### v1.1

The selector-first hypothesis was reasonable: if a correct candidate already exists, better comparison is cheaper than replacing the entire generator. The full BIRD baseline disproved the stronger version of that hypothesis. The oracle ceiling was only 61.73%, so the system needed more correct candidates as well as a better selector.

#### v1.2-v1.5

These versions improved evidence collection, value grounding, schema focus, and relation closure. They changed diagnostics more than final accuracy. v1.5 is a useful warning: adding relation routes increases candidate diversity, but without a stronger semantic contract it can create more plausible wrong alternatives for the selector.

#### v1.6

The shared semantic contract was the first change that improved the candidate pool substantially. It gave generation and selection the same interpretation of aggregation, ranking, projection, and relation hypotheses. This supports a general conclusion: the selector needs a representation of user intent, not only SQL text and result voting.

#### v1.7

Train-only structural demonstrations and execution-grounded repair helped on the main subset, but the subset policy changed. The reference-style rerun was 42.35%, so the 52.12% main score must not be presented as a clean v1.6-to-v1.7 architecture gain.

#### v1.8

The answer-plan/cardinality guard and four-way tournament produced the best controlled subset score and the lowest subset regret. The full run reached 56.19% and raised the candidate oracle to 68.77%. However, the full run had a provider quota failure affecting 337 verification decisions, so selector conclusions must be split between successful tournament decisions and fallback decisions.

#### v1.9

v1.9 reduced selector cost using top-two verification and conditional regeneration. On the comparable subset, it reduced calls by 24.5% and total tokens by 8.9%, but selected accuracy fell from 44.30% to 43.65%. This shows that selector efficiency and selector quality are currently in tension. It also had prompt learning disabled, so it was not a perfect one-variable comparison with v1.8.

## Other diagnostic findings

### Schema and joins

The v1.8 full metrics show very high schema recall but low precision:

| Metric | Value |
|---|---:|
| Table precision / recall | 28.27% / 99.53% |
| Column precision / recall | 7.08% / 99.58% |
| Join F1 | 0.57% |
| Combined schema precision / recall | 9.47% / 99.56% |
| Combined schema noise | 86.14% |

The system usually includes the required table and column, but also includes a large amount of irrelevant schema. The join metric is especially weak. It may be partially alias-sensitive, but it still provides no evidence that relation selection is solved.

### Execution and evaluator effects

All 1534 v1.8 full questions were covered, with zero recorded execution or gold errors. This is good operationally, but execution success does not imply semantic correctness. A query can execute successfully and still use the wrong join, wrong aggregation, wrong filter, or wrong projection.

The evaluator compares result values and shape. Column-header names alone do not matter, but a different number of columns does matter. Therefore, combined-name versus separate-name outputs can appear as selector regret even when the natural-language answer is arguably acceptable.

### Historical Spider2.0-Lite v1

The historical v1 Spider2.0-Lite run recorded:

- 251/527 = 47.63% over evaluable outputs.
- 251/547 = 45.89% using the fixed denominator.
- 20 error-only outputs.

It did **not** record candidate-oracle accuracy. The later three-instance smoke run reported 3/3 oracle accuracy, but that is only an infrastructure smoke test and must not be used as a full benchmark result.

## What future selector work should improve

### 1. Separate provider failure from model failure

The selector must not silently fold quota failures into deterministic model decisions.

Required changes:

- Add a circuit breaker for repeated HTTP 403/429 failures.
- Persist each pairwise decision and retry state atomically.
- Distinguish `provider_error`, `invalid_response`, and `model_disagreement` in metrics.
- Stop issuing redundant retries after a key-limit error.
- Run a quota-stable selector rerun before claiming selector accuracy.

This will not increase the candidate oracle, but it will make the selector result scientifically interpretable.

### 2. Make selection intent-aware

The current selector can prefer a concise, plausible SQL query over a candidate that matches the benchmark's required output structure. Selection should score a structured contract containing:

- answer entity and requested attributes;
- expected row grain and cardinality;
- projection equivalence rules;
- aggregation and ranking semantics;
- required join path;
- literal and time constraints;
- execution result signature.

The selector should first reject candidates that violate hard contract constraints, then compare the remaining candidates using execution evidence and semantic structure. A textual explanation should not override a hard projection or grain violation.

### 3. Add projection-aware result signatures

Keep strict benchmark execution accuracy, but compute an additional diagnostic that canonicalizes safe projection equivalences. Examples include:

- `forename, surname` versus a user-requested `full_name` expression;
- equivalent aliases;
- stable column reordering where the question does not impose an order;
- duplicate removal only when the question requests entities rather than events.

This should be implemented as an explicit evaluator mode, not by changing the official score silently.

### 4. Improve candidate generation before expanding selector complexity

The full v1.8 pool has 479 no-oracle questions. These cannot be recovered by any selector. The generator should use targeted routes for:

- multi-table joins and bridge tables;
- max/min versus top-k semantics;
- aggregation and denominator choice;
- set operations and nested subqueries;
- temporal boundaries;
- output grain and duplicate control.

The candidate budget should be adaptive: generate an additional route only when the current candidates fail an execution/contract gate. More unconditional candidates increase cost without guaranteeing diversity.

### 5. Use relation and cardinality checks as hard evidence

The join failure signal is much stronger than the current schema recall signal. Candidate generation should produce an explicit relation graph, then verify:

- join keys exist in both tables;
- the path is connected;
- the expected grain is preserved;
- one-to-many joins do not introduce accidental fan-out;
- aggregate placement matches the question.

The selector should penalize candidates that require unsupported or unobserved join paths, but it must retain a full-schema fallback so retrieval mistakes do not become hard exclusions.

### 6. Calibrate the selector on a fixed development protocol

Use the same frozen subset, same demonstration configuration, same candidate count, and same provider availability for every selector ablation. Report:

- final execution accuracy;
- candidate-oracle accuracy;
- regret among oracle-correct cases;
- provider-error rate;
- invalid-response rate;
- projection-normalized accuracy;
- cost, latency, and calls per question.

The v1.8 and v1.9 subset comparison is informative but not fully controlled because v1.9 disabled prompt learning.

### 7. Evaluate true interaction separately

The present BIRD run uses execution feedback, but it is still a static single-turn benchmark. A claim about interactive database agents requires a dynamic benchmark with clarification, tool use, and follow-up tasks. BIRD-Interact is designed for that purpose. The research question should become whether SlayQL's uncertainty-driven action policy improves success under a fixed interaction and token budget.

## Recommended next experiment

Run a selector-only controlled study on the same v1.8 full artifacts:

1. Recompute selection with a quota-stable API key or offline deterministic selector.
2. Keep the five candidate SQL files fixed.
3. Compare v1.8 tournament, v1.9 top-two, execution-result majority, and contract-first selection.
4. Report both strict benchmark accuracy and projection-normalized diagnostic accuracy.
5. Do not regenerate SQL during this study.

This isolates the 1,055-question candidate pool and answers the selector question directly. A separate generation study should then target the 479 no-oracle questions.

## Final assessment

SlayQL v1.1-v1.9 is a functioning execution-grounded, checkpointed research platform and v1.8 is a genuine improvement over the earlier full baseline. The selector analysis identifies three different phenomena that must not be conflated:

1. **No correct candidate:** the generator or semantic planner failed.
2. **Correct candidate not selected:** the selector or contract failed.
3. **Provider/evaluator artifact:** quota failure or strict projection shape changed the reported result.

The current v1.8 full score is strong evidence of progress, but it does not establish SOTA performance or a solved selector. The most useful next step is a quota-stable selector ablation with explicit projection and grain diagnostics, followed by targeted candidate generation for join and aggregation failures. Only after the candidate oracle rises above the target should selector optimization be expected to close the remaining gap.

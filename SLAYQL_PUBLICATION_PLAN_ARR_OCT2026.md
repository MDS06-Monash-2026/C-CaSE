# SlayQL Publication Plan: ARR October 2026 Short Paper

**Prepared:** 26 September 2026
**Submission target:** ACL Rolling Review (ARR), October 2026 cycle, which feeds NAACL 2027 and COLING 2027
**Deadline:** Monday 12 October 2026, 23:59 AoE (confirm at https://aclrollingreview.org/dates)
**Fallbacks:** PAKDD 2027 (20 Nov 2026), DASFAA 2027 (25 Nov 2026), EACL 2027 Student Research Workshop (15 Dec 2026)
**Supervisor's focus:** schema linking and budget awareness
**Time available:** one week of experiments, one day of drafting, the rest as buffer

---

## Status update (26 September, after implementation)

The code is implemented and smoke-tested. How to run everything is in [`run/PUBLICATION_RUNBOOK.md`](run/PUBLICATION_RUNBOOK.md). Changes to this plan based on the offline analysis:

1. **Runs R3 (no IT-EE), R8 (threshold 0.2) and R9 (threshold 0.7) are dropped.**
   - Retrieval entropy is always 0.95–1.0, so IT-EE assigns the full 10-turn budget at those settings, the same as R1.
   - They are replaced by `itee_max` (threshold 1.01), the setting at which IT-EE is most active.
   - Core runs are now: ref, topn20, no_rbp, no_bm25, itee_max, topn50, no_qoc (+ optional topn10000).
2. **Scenario C applies** (Section 10): IT-EE never shortened a budget in the existing runs, and the keyword override forces the full budget for 78% of BIRD and 97% of Spider 2.0-Lite questions. Report this as a finding.
3. **Scenario B applies** (Section 10): on the 79 paired Spider 2.0-Lite questions, SlayQL has lower table recall than AutoLink with the same model (−6.1 points, 95% CI −10.8 to −2.3) and keeps a similar number of columns. Do not claim better linking than AutoLink.
4. **The 178-question SlayQL run is excluded** from the paired comparison (52 of 80 schema prompts are empty). The full 547-question SlayQL run is used instead.
5. **The old 178-question ablation is invalid:** most selections failed in the no-RBP, no-BM25 and no-QOC runs. The BIRD ablation replaces it.
6. **Few-shot demonstrations** are rebuilt from the v1.8 run's own selections; they reproduce them exactly (200/200 checked).

---

## Contents

1. Summary
2. Motivation
3. Contributions
4. Research questions, hypotheses and what counts as evidence
5. What we compare
6. Datasets and evaluation protocol
7. Metrics (definitions)
8. How we compare accuracy fairly
9. Experiments
10. Scenarios: what we do if the results are not strong enough
11. Paper outline, tables and figures
12. Claims we may and may not make
13. Schedule
14. Run protocol and commands
15. Risks
16. Submission checklist
17. Out of scope

---

## 1. Summary

**What the paper is:** an empirical study of how schema linking and token budget interact in a training-free, agentic Text-to-SQL pipeline (SlayQL). We measure:
- how much of the database schema the linker keeps;
- how many tokens the linking and generation stages cost;
- how both affect execution accuracy.

We do this on small schemas (BIRD) and very large enterprise schemas (Spider 2.0-Lite).

**What the paper is not:** a claim of state-of-the-art accuracy.

**Working title:** *How Much Schema Is Enough? Schema Linking and Token Budgets in Agentic Text-to-SQL*

**Format:** ARR short paper, 4 pages plus unlimited references, limitations and appendix.

**The evidence we will have:**

| Evidence | Status | Cost |
|---|---|---|
| Spider 2.0-Lite full run, 547 questions, EX 45.89% | Exists | $0 |
| Spider 2.0-Lite linking quality on 250 instances with gold SQL, plus a paired comparison with AutoLink on 80 | Offline analysis | $0 |
| BIRD dev v1.0 and v1.8 full runs (k=5) | Exist | $0 |
| 9 new BIRD dev runs: component ablations and budget sweeps | To run | ~$25–40 |
| Token and cost accounting for every run | Offline analysis | $0 |

---

## 2. Motivation

### 2.1 The problem

A Text-to-SQL system must show the language model the parts of the database schema that the question needs. On enterprise databases this is hard:

1. **Large schemas do not fit, or cost too much.** Enterprise warehouses such as those in Spider 2.0-Lite have hundreds to thousands of columns per database. (We will measure the exact numbers from our schema documents in O1.) Sending the full schema is expensive or impossible, and a long, noisy prompt also lowers accuracy.
2. **Schema linking is a trade-off.**
   - A linker that keeps too little misses a table or column, and the SQL cannot be correct no matter how good the generator is.
   - A linker that keeps too much wastes tokens and distracts the model.
   - So both **recall** (did we keep everything needed?) and **precision** (how much noise did we add?) matter.
3. **Agentic linking has its own cost.** Recent linkers (AutoLink, LinkAlign, Graph-Link) explore the schema over several LLM turns. The linking stage itself spends tokens, and most papers do not report how many.
4. **Fixed budgets waste tokens.** Most pipelines give every question the same number of exploration turns, retrieved columns and SQL candidates. Easy questions do not need this; hard ones may need more.

### 2.2 The gap in published work

From the team's `Comparisons.pdf`:
- Of about 37 recent methods, **only about 10 report schema-linking results at all**.
- Those that do use **different recall definitions**: strict, plain and count-based.
- Very few report **precision**, and almost none report **token cost per stage**.
- Graph-Link's linker-only table is the main exception: it reports tokens per question on BIRD.

So it is hard to answer basic questions such as "how much schema does a linker keep, what does it cost, and what does that buy in accuracy?"

### 2.3 Why SlayQL is a useful case study

SlayQL combines several ideas that target exactly this trade-off:
- **Retrieval:** embedding-based column retrieval, controlled by `top_n`.
- **RBP (relevance propagation):** spreads relevance over the foreign-key graph, so join tables are not dropped.
- **IT-EE (entropy-based exploration budget):** gives confident questions fewer exploration turns and uncertain ones more.
- **BM25 value grounding:** finds the database values mentioned in the question.
- **QOC (output constraints):** keeps the output format correct.

Each of these has a switch, so we can measure its effect on linking quality, tokens and accuracy **without redesigning anything**.

### 2.4 What we already observed (motivating findings)

1. **On BIRD, SlayQL keeps almost the whole schema:**
   - 6.87 of 7.08 tables and 54.1 of 75.6 columns on average;
   - every table is kept in 87.7% of questions.
   - Recall is therefore about 99.8% (tables) and 99.6% (columns), but precision is only about 34% and 12%.
   - Small schemas give linking little to do.
2. **On BIRD, the bottleneck is choosing among candidates, not linking.** With 5 candidates, a correct SQL exists for 68.77% of questions, but the selector picks it for only 56.19%. For 193 questions a correct candidate was generated and not chosen.
3. **On Spider 2.0-Lite, linking must prune heavily:** schemas are far larger, and SlayQL reached 45.89% EX. The same-model comparison with AutoLink on 178 questions was 40.4% vs 39.9%, which is not a meaningful difference.

These findings shape the story: **linking matters where schemas are large; budget matters everywhere; on small schemas the remaining errors come from generation and selection.**

---

## 3. Contributions

What the paper will contribute, if the results support it (Section 10 covers what changes if they do not):

1. **A consistent measurement of schema-linking quality and cost** on small (BIRD) and large (Spider 2.0-Lite) schemas, reporting precision, recall, strict recall, schema size and tokens together, with definitions stated.
2. **A component analysis** of relevance propagation (RBP), entropy-based exploration budgets (IT-EE), value grounding (BM25) and output constraints (QOC), under one fixed model, question set and denominator.
3. **Accuracy–token trade-off curves** along three budget axes: how many columns are retrieved, how many exploration turns are allowed, and how many SQL candidates are generated.
4. **An error analysis** showing where accuracy is lost (linking misses vs generation vs selection) and how that differs between small and large schemas.

---

## 4. Research questions, hypotheses and what counts as evidence

### RQ1: Linking quality

*How complete and how precise is the linked schema, and how much does it shrink the prompt, on small vs large schemas?*

| Hypothesis | Supported if | Refuted if |
|---|---|---|
| H1a: On large schemas (Spider 2.0-Lite), SlayQL cuts schema tokens by a large fraction while keeping high table recall | Schema-size reduction is large (e.g. more than 80%) with table recall above ~85% | Recall is low (many gold tables dropped), or the reduction is small |
| H1b: SlayQL's linking is at least as good as AutoLink's with the same model | Paired recall difference ≥ 0 (CI includes or exceeds 0), and precision or tokens are better | AutoLink has significantly higher recall |
| H1c: On small schemas (BIRD), linking is near-saturated: recall ≈ 100% because almost everything is kept | Tables kept ≈ tables in the database | — (this is descriptive) |

### RQ2: Component contribution

*What does each component add to linking quality, tokens and accuracy?*

| Hypothesis | Supported if | Refuted if |
|---|---|---|
| H2a: RBP improves recall of join tables | Recall drops without RBP (R2 vs R1), especially for multi-table gold SQL | No difference |
| H2b: IT-EE saves tokens at little or no accuracy cost | R3 (no IT-EE) uses clearly more tokens, and EX is not significantly higher | R3 has the same tokens, or significantly higher EX |
| H2c: BM25 value grounding improves accuracy on value-dependent questions | EX drops without BM25 (R4 vs R1), especially on questions with literal values | No difference |
| H2d: QOC reduces output-format errors | EX drops without QOC (R5 vs R1) | No difference |

### RQ3: Budget

*How do accuracy and linking recall change with the token budget, and is there a cheaper setting with similar accuracy?*

| Hypothesis | Supported if | Refuted if |
|---|---|---|
| H3a: A smaller retrieval size (`top_n` 20 or 50) saves tokens with a small accuracy loss | R6/R7 on or near the Pareto frontier (Section 7.5) | Large EX loss for small savings |
| H3b: The IT-EE threshold trades tokens for accuracy smoothly | R8 → R1 → R9 moves monotonically in tokens | Tokens do not change (the budget control does not activate) |
| H3c: Extra candidates improve the chance a correct SQL exists more than they improve final accuracy | oracle@k rises faster than vote@k and selected accuracy | Both rise equally |

---

## 5. What we compare

### 5.1 Three kinds of comparison

| Kind | What | Can we claim "better or worse"? |
|---|---|---|
| **Internal** | SlayQL variants: ablations and budget settings | **Yes.** Same model, same questions, same denominator, paired statistics. |
| **Reproduced baseline** | AutoLink, run by us with the same model on the same questions | **Yes.** Paired, but only 80 Spider 2.0-Lite instances have gold SQL. |
| **Reported baselines** | Numbers copied from published papers | **No, context only.** Different models, settings and metric definitions. |

### 5.2 Internal comparisons (the core of the paper)

| Comparison | Runs | Question it answers |
|---|---|---|
| Full system vs no RBP / no IT-EE / no BM25 / no QOC | R1 vs R2, R3, R4, R5 | RQ2 |
| Retrieval budget sweep | R6 (`top_n` 20), R7 (50), R1 (100), R10 (10000) | RQ3 (H3a) |
| Exploration budget sweep | R8 (IT-EE threshold 0.2), R1 (0.4), R9 (0.7), R3 (no IT-EE) | RQ3 (H3b) |
| Candidate budget | oracle@k and vote@k for k = 1…5 from v1.0 and v1.8 | RQ3 (H3c) |
| Base vs full pipeline | v1.0 (49.15%) vs v1.8 (56.19%), both k=5 | Context: what the non-linking stages add |

### 5.3 Reproduced baseline: AutoLink

- **Why AutoLink:** SlayQL is built on AutoLink, it is the closest published method, and we already have same-model runs of it.
- **Data:** the 178-question Spider 2.0-Lite subset run with `deepseek-v4-flash` for both systems. Of these, 80 have gold SQL for linking evaluation.
- **What we compare:** per-instance linking precision, recall and strict recall; schema tokens; LLM tokens per question; EX on all 178 (already known: 40.4% vs 39.9%).

### 5.4 Reported baselines (from `Comparisons.pdf`)

All numbers must be **re-checked against the original papers** before submission (Section 5.5).

**Rules for every table:**
1. Every row states its **backbone model**, **training type** (prompting vs fine-tuning or RL) and **reported or reproduced**.
2. Recall definitions differ: **strict** (all gold items kept; AutoLink), **plain** table or column recall, and **count-based** (GenLink). Put the definition in a column, and never rank rows with different definitions against each other.
3. Only same-backbone, same-question rows support claims.

#### A. Primary comparisons (discussed in the text)

| Method | Venue | Why primary | Spider 2.0-Lite (reported) | BIRD (reported) | How we use it |
|---|---|---|---|---|---|
| **AutoLink** | AAAI 2026 | Base of SlayQL; same linking style | EX 34.92, strict recall 91.20 (DeepSeek) | EX 68.71, strict recall 97.40 (DeepSeek) | **Reproduced** on the same model (Section 5.3); reported numbers as context |
| **LinkAlign** | EMNLP 2025 | Linking for large databases; reports Spider 2.0-Lite | EX 33.09 (DeepSeek) | EX 61.60, recall 79.40 | Reported, labelled |
| **Graph-Link** | ICML 2026 | Graph-based linking, closest to RBP; source of the token table | P 69.7, R 91.30 | EX 68.50, P 70.40, R 95.90 (Qwen3-max) | Reported; token numbers as context for RQ3 |
| **SchemaGraphSQL** | EACL 2026 | Graph-based linking; reports P and R on both datasets | P 59.88, R 47.37 | EX 62.91, P 86.21, R 95.71 (Gemini 2.5-Flash) | Reported |

#### B. Schema-linking table (T1): methods that report linking metrics

| Method | Venue | Training | Backbone | BIRD EX | BIRD P | BIRD R | Recall type |
|---|---|---|---|---|---|---|---|
| RSL-SQL | 2024 (arXiv) | Prompting | GPT-4o | 67.21 | — | 94.32 | to verify |
| MCS-SQL | COLING 2025 | Prompting | GPT-4 | 65.50 | — | 99.20 | to verify |
| LinkAlign | EMNLP 2025 | Prompting | GPT-4 (PDF also says DeepSeek) | 61.60 | — | 79.40 | to verify |
| JOLT-SQL | EMNLP 2025 | Fine-tuning | Qwen2.5-Coder-14B | 64.90 | 75.12 | 96.68 | to verify |
| GenLink | EMNLP 2025 | Fine-tuning | several 7–8B models | 67.34 | — | 94.56–97.22 | count-based |
| AutoLink | AAAI 2026 | Prompting | DeepSeek | 68.71 | — | 97.40 | strict |
| BiSchemaLink | EACL 2026 | Prompting | Gemini 2.0-Flash | 57.80 | — | 90.60 | to verify |
| SchemaGraphSQL | EACL 2026 | Prompting | Gemini 2.5-Flash | 62.91 | 86.21 | 95.71 | to verify |
| LiteSQL | EACL 2026 | Fine-tuning + RL | Qwen2.5-Coder | 72.10 | — | 82.31 | to verify |
| Graph-Link | ICML 2026 | Prompting | Qwen3-max | 68.50 | 70.40 | 95.90 | to verify |
| **SlayQL (ours)** | — | Prompting | deepseek-v4-flash | R1 and v1.8 | from runs | from runs | table, column and strict (all three) |

Spider 2.0-Lite rows: AutoLink (strict recall 91.20), Graph-Link (P 69.7 / R 91.30), SchemaGraphSQL (P 59.88 / R 47.37), SlayQL (O1).

**Always show precision and schema size next to recall.** SlayQL's near-100% BIRD recall comes from keeping almost everything.

#### C. Spider 2.0-Lite execution accuracy (context only)

| Method | Venue | Training | Backbone | EX |
|---|---|---|---|---|
| AST-SQL | ICML 2026 | RL | Qwen2.5-Coder / OmniSQL-7B | 8.90 / 14.10 |
| Arctic-Text2SQL-R1-32B | ACL 2026 | RL | 32B | 16.30 |
| LinkAlign | EMNLP 2025 | Prompting | DeepSeek | 33.09 |
| AutoLink | AAAI 2026 | Prompting | DeepSeek | 34.92 |
| VET | ACL 2026 | Prompting | DeepSeek-Chat | 37.04 |
| **SlayQL (ours)** | — | Prompting | deepseek-v4-flash | **45.89** (251/547) |
| PExA | ACL 2026 | Prompting | to verify | 46.60 |
| SquRL | ICML 2026 | RL | to verify | 49.18 |

**Framing:** SlayQL is third in this list and among the strongest prompting-based methods, **but on a newer backbone**. The same-model comparison (40.4% vs 39.9% on 178 questions) shows that most of the gap to AutoLink's reported 34.92 comes from the model. The paper must say this.

#### D. Token budgets (context only)

The linker-only table (page 4 of the PDF; BIRD; Qwen3-max generator; cite its source paper, likely Graph-Link):

| Method | EX | Tokens/question |
|---|---|---|
| Hybrid (BM25 + vector) | 29.4 | ~8,500 |
| Full schema (no linking) | 45.7 | ~55,300 |
| DIN-SQL linker | 52.4 | ~33,200 |
| MAC-SQL linker | 54.8 | ~15,800 |
| RSL-SQL linker | 63.4 | ~48,100 |
| MCS-SQL linker | 66.0 | ~63,800 |
| Graph-Link | 68.5 | ~20,800 |

SlayQL **cannot** go in this table without rerunning with Qwen3-max (out of scope this week; possible for PAKDD or DASFAA). Use it to show typical token budgets, and give SlayQL's own curve (F2) and the same-model AutoLink token comparison.

#### E. Spider 1.0 (appendix only)

Published Spider 1.0 EX in the PDF is 70.6–89.75, against our 65.39. **Keep Spider 1.0 EX out of the main paper.** If used, report only linking recall, next to PET-SQL (86.40), JOLT-SQL (98.58), LinkAlign (87.30) and LiteSQL (99.16), with definitions labelled and the split (dev or test) checked.

#### F. Related work only (cite, no numbers)

- **Prompting pipelines:** DAIL-SQL, C3, DIN-SQL, PET-SQL, MAC-SQL, MCS-SQL, CHESS, CHASE-SQL, Alpha-SQL, Dialect-SQL, Safe-SQL, MCTS-SQL, DPC, GBV-SQL, PV-SQL, R3-SQL, VET, PExA.
- **Training-based (fine-tuning or RL):** OmniSQL, Reasoning-SQL, JOLT-SQL, GenLink, LiteSQL, AST-SQL, SquRL, MARS-SQL, SQL-Trail, SDE-SQL, Arctic-Text2SQL-R1, ReEx, EXPO-SQL, XiYan-SQL.
- **Positioning sentence:** training-based methods lead the leaderboards but need fine-tuning; SlayQL is training-free and studies the linking–cost trade-off at inference time.

### 5.5 Problems in `Comparisons.pdf` to fix before quoting

- **PET-SQL:** the year is 2004; it should be 2024.
- **LinkAlign:** the name says "(DeepSeek)" but the BIRD row lists GPT-4. Check the backbone per dataset.
- **Page 4 model sizes:** "Qwen3-max (95B)" and "GLM4.7 (32B)" look wrong (GLM-4.7 is a mixture-of-experts model with about 32B *active* parameters). Check the source.
- **Missing backbones:** most rows on pages 5–6 have none.
- **Unclear recall level:** Spider 2.0-Lite P/R for Graph-Link and SchemaGraphSQL doesn't say whether it is table- or column-level.
- **Page 3** is an empty table; remove it.

---

## 6. Datasets and evaluation protocol

| Dataset | Questions | Role | Notes |
|---|---|---|---|
| **BIRD dev** | 1,534 | All new runs | Local SQLite. Difficulty labels (simple, moderate, challenging) come from `dev/dev_20240627/dev.json`, joined on the source ID. |
| **Spider 2.0-Lite** | 547 (EX); 250 with gold SQL (linking); 80 paired with AutoLink | Large-schema evidence | **No new runs:** warehouse access was withdrawn by the benchmark maintainers. State this in the setup and limitations sections. |
| Spider 1.0 test | 2,147 | Appendix only | Existing k=3 run |

**Denominators (always fixed):**
- **BIRD:** every EX is out of **1,534**. Missing or failed predictions count as wrong.
- **Spider 2.0-Lite EX:** out of **547**. This gives 45.89%, not the 47.63% out of 527 evaluable.
- **Linking metrics:** averaged over instances where gold SQL could be parsed. Report the count (e.g. "n = 250").

**Gold schema for linking:** tables and columns referenced in the gold SQL, extracted with `sqlglot`. On BIRD this is done by `run/evaluate_dataset.py`; on Spider 2.0-Lite we do it in O1.

---

## 7. Metrics (definitions)

### 7.1 Accuracy

| Metric | Definition |
|---|---|
| **EX (execution accuracy)** | Share of questions whose predicted SQL returns the same result set as the gold SQL (strict set comparison, `evaluate_dataset.py`). Fixed denominator. |
| **EX by difficulty** | EX separately for BIRD simple, moderate and challenging questions |
| **Failure rate** | Share of questions with no prediction or an execution error |

### 7.2 Schema linking

For each question, *G* is the set of gold items and *P* the set of items in the linked schema. We compute this at **table level** and at **column level**.

| Metric | Definition | Why it matters |
|---|---|---|
| **Precision** | \|P ∩ G\| / \|P\| | How much of the linked schema is actually needed (1 − noise) |
| **Recall** | \|P ∩ G\| / \|G\| | How much of what is needed was kept |
| **F1** | Harmonic mean of precision and recall | Single summary |
| **Strict recall** | 1 if G ⊆ P, else 0, averaged over questions | Share of questions where **nothing** needed was lost. Same definition as AutoLink. |
| **Schema reduction** | 1 − (linked-schema tokens / full-schema tokens) | How much the prompt shrinks |
| **Items kept** | Average \|P\| (tables and columns) | Makes the size of the linked schema visible |

We report **macro** averages (mean over questions) as primary and **micro** (pooled counts) in the appendix. Token counts use `tiktoken` (`cl100k_base`), and we say so in the paper, because DeepSeek's own tokenizer differs.

### 7.3 Budget and cost

| Metric | Definition |
|---|---|
| **Tokens per question** | (prompt + completion tokens) / questions, overall and **by stage**: linking (schema completion), generation, revision, selection |
| **Cost per question** | OpenRouter cost / questions, in USD |
| **Tokens per correct answer** | Total tokens / number of correct questions: what one correct answer costs |
| **Exploration turns** | Average completion-agent turns per question (shows IT-EE at work) |
| **API calls per question** | Calls / questions |
| **Latency** | Median (p50) and 95th percentile (p95) seconds per call |

### 7.4 Candidates and selection

| Metric | Definition |
|---|---|
| **oracle@k** | Share of questions where at least one of the first k candidates is correct: an upper bound for a perfect selector |
| **vote@k** | EX when choosing the most common result among the first k candidates |
| **Selection regret** | Questions where a correct candidate existed but was not selected |
| **Selection accuracy given oracle** | EX / oracle: how often the selector finds the correct candidate when one exists |

### 7.5 Trade-off summary

| Metric | Definition |
|---|---|
| **Pareto frontier** | Settings where no other setting is both more accurate and cheaper. Drawn on the EX vs tokens-per-question plot (F2). |
| **Accuracy at matched budget** | Of two settings with similar tokens (±10%), which has the higher EX |
| **Relative saving** | Token saving vs R1 (%) against the EX change vs R1 (percentage points) |

---

## 8. How we compare accuracy fairly

### 8.1 Rules

1. **Same model, same questions, same denominator** for every "better or worse" statement. Internal comparisons meet this by design.
2. **Paired comparisons:** every system answers the same questions, so we compare per question, not only the totals.
3. **Report uncertainty:** every EX and linking number has a 95% confidence interval.
4. **Test differences:**
   - **McNemar's test** for paired EX (correct/incorrect per question).
   - **Paired bootstrap** (10,000 resamples) for differences in linking metrics and tokens.
5. **Correct for multiple tests:** the four ablations (R2–R5 vs R1) use a Holm–Bonferroni correction.
6. **Reported numbers are never ranked against ours.** They appear in separate, labelled context tables (Section 5.4).
7. **No cherry-picking:** report every run in the appendix, including failed or weak ones.

### 8.2 What size of difference is meaningful

| Setting | Questions | Approximate 95% CI on one EX value | Practical reading |
|---|---|---|---|
| BIRD dev | 1,534 | about ±2.5 points (at EX ≈ 55%) | Paired differences smaller than about 2 points are unlikely to be significant; use McNemar for the exact answer |
| Spider 2.0-Lite full | 547 | about ±4.2 points | 45.89% is 41.7–50.1%; compare with published numbers loosely |
| Spider 2.0-Lite 178 subset | 178 | about ±7.3 points | 40.4% vs 39.9% is **no difference** |
| Spider 2.0-Lite paired linking | 80 | Large for EX; better for per-instance recall | Use this for linking metrics, not EX |

### 8.3 How each comparison is reported

| Comparison | Reported as |
|---|---|
| Ablation (R2–R5 vs R1) | ΔEX in points, [95% CI], McNemar p (Holm-adjusted); Δ recall and Δ precision [CI]; Δ tokens per question (%) |
| Budget sweep (R6–R10) | Points on the EX vs tokens plot, with CIs; Pareto frontier; one row per setting in the appendix |
| SlayQL vs AutoLink (Spider 2.0-Lite, paired) | Mean difference in table/column recall, precision and strict recall [bootstrap CI]; tokens per question for both; EX on 178 for both |
| v1.0 vs v1.8 (k=5) | ΔEX [CI], McNemar p; Δ oracle; Δ cost |
| SlayQL vs published | Context table with backbone, training type and metric definition; **no significance claims** |

---

## 9. Experiments

### 9.1 Fixed settings (do not change during the week)

| Item | Value | Reason |
|---|---|---|
| Pipeline version | **SlayQL v1.8** (`run/research_suite_v18.py`) | The only version with a full BIRD dev result (56.19%) |
| Model | `deepseek/deepseek-v4-flash` via OpenRouter (`run/.env`) | Same model as the v1.8 full run; its usage logs confirm 13,281 calls to it |
| Dataset | BIRD dev, full, 1,534 questions | Local, no external access needed |
| Candidates | `--num-candidates 1` (v1.8 generates 2 SQL per requested candidate) | Isolates linking effects and cuts each run to about 3–5 hours |
| Seed | 20260813 (default) | Same order and sampling for every run |
| Workers | 4 per run, at most 2 runs at once | OpenRouter rate limits and GPU memory |
| Evaluator | `run/evaluate_dataset.py` | Same as all previous BIRD numbers |

**Implementation facts confirmed in the code:**
- All switches are environment variables, and the pipeline passes the environment to every stage (`env = os.environ.copy()` in `dataset_pipeline.py`).
- `SLAYQL_TOP_N` sets how many columns are retrieved at first (default 100).
- `ABLATION_ITEE_THRESHOLD` (default 0.4) sets the entropy threshold. A higher value means more questions get the minimum exploration budget, so fewer tokens.
- IT-EE's `ComplexityAnalyzer` forces the full budget for questions with temporal, aggregation or structural signals. This may limit how much the threshold changes anything (see O7 and Scenario C).
- v1.8 applies a schema-focus cap of **8 tables / 72 columns**, and no switch turns it off.
- The Spider 2.0-Lite 45.89% run used the older generation stack (`main.sh` / `sql_gen.sh`) with the **same linking scripts** (`retrieve_topk_schema.py`, `complete_schema.py`). The paper must say "same linking module, different generation stack".

### 9.2 Existing results reused

| Result | Location | Use |
|---|---|---|
| BIRD v1.0, k=5: EX 49.15%, oracle 61.73%, $5.24 | `run/bird_dev_full/` | Base pipeline; candidate-budget curve |
| BIRD v1.8, k=5: EX 56.19%, oracle 68.77%, $10.10 | `run/bird_dev_v18_full/` | Full-system row; candidate-budget curve; selection regret |
| Spider 1.0 test, k=3: EX 65.39%, $2.92 | `run/spider1_test_full_3cand/` | Appendix |
| Spider 2.0-Lite full: 251/547 = 45.89% | `run/log_spider2_full_slayql/` | Large-schema accuracy and linking |
| Spider 2.0-Lite 178 subset, AutoLink and SlayQL, same model | `run/log_subset_diverse_20_evaluation_autolink_baseline_v2/`, `run/log_subset_diverse_20_evaluation_slayql_ccase/` | Paired linking and token comparison |

### 9.3 Offline analyses (no API cost)

| ID | Analysis | Method | Output | Owner |
|---|---|---|---|---|
| **O1** | **Spider 2.0-Lite linking** | Parse gold SQL (`evaluation_suite/gold/sql/`, 256 files) with `sqlglot` in the right dialect; parse linked tables and columns from `final_schema_prompts/{id}.txt`; compute Section 7.2 metrics at table level (primary) and column level (best effort); measure full-schema tokens from `run/documents/` | Linking metrics on about 250 instances; paired SlayQL vs AutoLink on 80; schema reduction; average database size | B |
| **O2** | **Token and cost accounting** | Read `usage/`, `tool_calls/` and `aggregates/summary_metrics.json` for every run. Recount the Spider 2.0-Lite full run (the current total covers only 187 of 547 queries). | One row per run with Section 7.3 metrics | C |
| **O3** | **Candidate-budget curve** | From the v1.0 and v1.8 per-question evaluations and candidates, compute oracle@k and vote@k for k = 1…5 | Data for F3; H3c | C |
| **O4** | **Old 178-question ablation** | Re-score every variant on the questions that all variants completed. Inspect error files for no-RBP (2.25%) and no-BM25 (1.69%). If they crashed, record them as failed runs, not component effects. | Appendix note (the BIRD ablation replaces it in the main paper) | B |
| **O5** | **Statistics script** | Bootstrap CIs, McNemar, Holm correction (Section 8) | Reusable script run on every comparison | B |
| **O6** | **Error analysis** | Sample 100 wrong answers from R1 and 50 from Spider 2.0-Lite. Label each: linking miss (join key, value column, projection column, aggregation column), generation error, or selection error (a correct candidate existed). | Error table (T4) | A |
| **O7** | **IT-EE activation** | From R1 logs, count how many questions got the minimum budget vs the full budget, and how often the complexity override fired | Explains R8/R9 results (Scenario C) | A |

### 9.4 New BIRD dev runs (v1.8, k=1, all 1,534 questions)

| ID | Variant | Setting | Tests | Expected outcome if the hypothesis holds | Est. time |
|---|---|---|---|---|---|
| **R0** | Smoke tests (5 questions per switch) | Section 14.2 | The switches work | Linked schema or turns change | 30 min |
| **R1** | **Reference** | none | Baseline | — | 3–5 h |
| **R2** | No RBP | `ABLATION_NO_RBP=1` | H2a | Lower recall, mostly on multi-table questions | 3–5 h |
| **R3** | No IT-EE (always 10 turns) | `ABLATION_NO_ITEE=1` | H2b, H3b | More tokens; EX not significantly higher | 4–6 h |
| **R4** | No BM25 | `ABLATION_NO_BM25=1` | H2c | Lower EX on value questions | 3–5 h |
| **R5** | No QOC | `ABLATION_NO_QOC=1` | H2d | Lower EX, more format errors | 3–5 h |
| **R6** | Retrieval `top_n` = 20 | `SLAYQL_TOP_N=20` | H3a | Fewer tokens, higher precision, some recall loss | 3–5 h |
| **R7** | Retrieval `top_n` = 50 | `SLAYQL_TOP_N=50` | H3a | Between R6 and R1 | 3–5 h |
| **R8** | IT-EE threshold 0.2 (generous) | `ABLATION_ITEE_THRESHOLD=0.2` | H3b | More turns and tokens than R1 | 3–5 h |
| **R9** | IT-EE threshold 0.7 (frugal) | `ABLATION_ITEE_THRESHOLD=0.7` | H3b | Fewer turns and tokens than R1 | 3–5 h |
| **R10** | Retrieval unpruned (optional) | `SLAYQL_TOP_N=10000` | RQ1 upper bound | Recall ≈ 100%, most tokens. The 8-table / 72-column cap still applies; label it "retrieval-unpruned". | 3–5 h |
| **R11** | Second backbone (optional) | `MODEL_NAME=<second model>`, `--mode subset20` | Generalisation | Same ranking of settings as with DeepSeek; compare with R1 on the same IDs | 1–2 h |

**Priority if time runs short:** R1 > R3 > R6 > R2 > R4 > R9 > R7 > R5 > R8 > R10 > R11.

**Estimated total:** 35–50 hours of compute; about $25–40.

---

## 10. Scenarios: what we do if the results are not strong enough

We will know which scenario applies by day 3 (Section 13). Each one still leads to a submittable paper; the framing changes.

### Scenario A: Pruning hurts accuracy on BIRD (R6/R7 lose a lot of EX)

- **What it means:** BIRD schemas are too small for pruning to pay off; keeping everything is cheap enough.
- **Reframe:** "linking is a large-schema problem". Put the linking story on Spider 2.0-Lite (O1: schema reduction with recall) and present BIRD as the control case showing where pruning does not help.
- **Claim instead:** the value of linking depends on schema size, shown by measured reduction vs recall on both benchmarks.
- **Still report:** the R6/R7 numbers, as the evidence for this claim.

### Scenario B: SlayQL links worse than AutoLink on the paired Spider 2.0-Lite instances

- **Check first:** whether SlayQL uses fewer tokens or a smaller schema. If so, frame it as a **cost trade-off**: "X% of AutoLink's recall at Y% of its tokens".
- **If SlayQL is worse on both recall and cost:** report it honestly. The paper becomes a measurement study: consistent linking metrics and costs for two agentic linkers on enterprise schemas, plus where each one misses (O6).
- **Do not:** hide AutoLink's row or switch to a friendlier metric after seeing the numbers.

### Scenario C: The budget controls do not change tokens (R8/R9 ≈ R1)

- **Likely cause:** IT-EE's complexity override gives the full budget to most BIRD questions, so the threshold rarely matters. O7 will show this.
- **Reframe:** "adaptive budgets only save tokens when the router lets them act". Report the share of questions routed to the minimum budget and what R3 (no IT-EE) costs.
- **Use the other budget axes:** retrieval size (R6/R7) and candidate count (O3) still give trade-off curves.

### Scenario D: The ablations show no significant differences

- **What it means:** on BIRD, with k=1, the components are redundant, or their effects are below what 1,534 questions can detect (about 2 points).
- **Reframe:** report the **confidence intervals** as a finding: "no component changes EX by more than X points on small schemas", plus any **token** differences, which are often significant even when EX is not.
- **Support with Spider 2.0-Lite:** the old 178-question ablation (O4) as a limited appendix note, only if O4 shows it is valid.

### Scenario E: Both linking and budget results are weak

**Minimum viable paper**, a measurement and analysis paper:
1. Consistent linking metrics (precision, recall, strict recall, schema size) on BIRD and Spider 2.0-Lite.
2. Where the tokens go, by stage (O2).
3. The bottleneck finding: on BIRD, the correct SQL is generated for 68.77% of questions but selected for only 56.19% (193 questions lost to selection), while linking recall is near 100%.
4. The candidate-budget curve (O3).
5. The error analysis (O6).

**Venue adjustment:** if the supervisor judges this too thin for ARR, submit the stronger version to **PAKDD (20 Nov)** or **DASFAA (25 Nov)**, using the extra 5–7 weeks for the Qwen3-max linker-only row (Section 5.4 D) and a second backbone. The **EACL Student Research Workshop (15 Dec)** is the last fallback.

### Scenario F: Runs fail or do not finish

- Resume with the same run ID (checkpoints).
- Drop runs from the bottom of the priority list and list the dropped ones in the limitations section.
- **Minimum set of runs:** R1, R3, R6, together with all offline analyses.

### Scenario G: Gold SQL parsing fails for many Spider 2.0-Lite queries

- Report **table-level** linking as primary (table names are much easier to extract than columns).
- State how many instances parsed (e.g. "n = 212 of 256").
- Keep column-level results in the appendix, or drop them.

---

## 11. Paper outline, tables and figures

### 11.1 Sections (4 pages)

| Section | Length | Content |
|---|---|---|
| 1. Introduction | 0.5 page | The problem (Section 2.1); the gap (2.2); RQ1–RQ3; the contributions (Section 3); a one-line headline result |
| 2. Pipeline | 0.5 page | Retrieval, RBP, IT-EE, BM25, QOC, generation and selection; F1 with tokens per stage |
| 3. Setup | 0.5 page | Datasets and denominators (Section 6); model, k, seed; metrics (Section 7); statistics (Section 8); the Spider 2.0-Lite access statement |
| 4. Results | 1.75 pages | RQ1: T1 + Spider 2.0-Lite paired comparison. RQ2: T2 ablation. RQ3: F2 budget curve + F3 candidate curve |
| 5. Analysis | 0.5 page | Error analysis (T4); where accuracy is lost on small vs large schemas; selection regret |
| 6. Related work | 0.25 page | Groups from Section 5.4 F |
| Limitations | (not counted) | One main backbone; one seed; offline Spider 2.0-Lite analysis on 250 of 547 instances; the schema-focus cap; BIRD schemas are small; reported baselines use other models |
| Appendix | (not counted) | Full run table, per-difficulty EX, micro metrics, Spider 1.0, old ablation note, run commands |

### 11.2 Tables

| Table | Rows | Columns | Source |
|---|---|---|---|
| **T1** Linking quality | BIRD: SlayQL R1, R10, v1.8; Spider 2.0-Lite: SlayQL, AutoLink (reproduced); reported linkers (Section 5.4 B) in a separate block | Backbone, training type, reported/reproduced, table P/R/F1, column P/R/F1, strict recall, items kept, schema tokens, recall definition | R1, R10, O1, 5.4 B |
| **T2** Ablation | R1, R2, R3, R4, R5 | EX [CI], ΔEX, McNemar p (Holm), table/column recall and precision, tokens/q, $/q, turns/q | R1–R5, O2, O5 |
| **T3** Spider 2.0-Lite | SlayQL vs AutoLink (same model, paired); published EX (Section 5.4 C) as context | Recall, precision, strict recall [CI], tokens/q, EX (178 and 547) | O1, O2 |
| **T4** Error analysis | Error categories | Count and share for BIRD and Spider 2.0-Lite | O6 |
| A1 (appendix) | All runs | Every metric in Section 7 | All |

### 11.3 Figures

| Figure | Content | Source |
|---|---|---|
| **F1** | Pipeline diagram with average tokens per stage | O2 |
| **F2** | EX (y) vs tokens per question (x), one point per setting (R1, R3, R6–R10), 95% CI bars, Pareto frontier marked. A second panel shows column recall vs tokens. | Budget runs |
| **F3** | oracle@k, vote@k and selected EX vs k (v1.0 and v1.8) | O3 |

---

## 12. Claims we may and may not make

### 12.1 Allowed (only if the numbers support them)

- Linking quality and cost on small vs large schemas, with precision, recall, strict recall and schema reduction.
- The effect of each component under a fixed model, question set and denominator, with CIs.
- Accuracy–token trade-offs for retrieval size, exploration budget and candidate count.
- Spider 2.0-Lite 45.89% (251/547) with the backbone stated, and that further runs were impossible because access was withdrawn.
- On BIRD, candidate selection, not linking, is the main remaining gap.

### 12.2 Not allowed

- State of the art on any benchmark.
- "Every module is necessary" unless the ablation CIs support it.
- Ranking SlayQL against published numbers that use a different backbone or a different recall definition.
- Any number that does not come from the run folders in this plan, and any figure from archived documents that contain unmeasured numbers.

---

## 13. Schedule

Roles:
- **A:** runs, monitoring, O6, O7.
- **B:** O1, O4, O5 (Spider 2.0-Lite and statistics).
- **C:** O2, O3, figures, related work, checking published numbers.

The supervisor reviews at the checkpoints.

| Day | Date | Runs (A) | Offline and writing (B, C) | Checkpoint |
|---|---|---|---|---|
| 0 | Sat 26 Sep | R0 smoke tests; start **R1** in the evening | B: O1 parser. C: O2. Supervisor: confirm ARR service contributor | Smoke tests pass |
| 1 | Sun 27 Sep | Start **R3** and **R6** | B: O1 table-level results. C: finish O2, start O3 | R1 complete and sensible |
| 2 | Mon 28 Sep | Start **R2** and **R9** | B: O1 column-level + paired AutoLink. C: O3 curves. A: O7 on R1 | **Scenario check:** A (R6) and B (O1) |
| 3 | Tue 29 Sep | Start **R4** and **R7** | B: O5 script, O4. C: verify all Section 5.4 numbers against original papers | **Scenario check:** C (R9 vs R1) |
| 4 | Wed 30 Sep | Start **R5** and **R8** | A: O6 error analysis. B: run O5 on finished runs | — |
| 5 | Thu 1 Oct | Reruns; optional **R10** and **R11** | C: F1–F3 | Core runs complete |
| 6 | Fri 2 Oct | Optional runs finish | B: final statistics. Everyone: fill T1–T4 | **Results frozen**; scenario chosen (Section 10) |
| 7 | Sat 3 Oct | — | **Write the full draft (1 day)** | Draft to supervisor |
| 8–10 | 4–6 Oct | One targeted rerun at most, if needed | Revise from supervisor feedback | Revised draft |
| 11–14 | 7–10 Oct | — | Polish, anonymise, limitations, appendix, checklist | Final PDF by 10 Oct |
| 15 | Sun 11 Oct | — | **Submit one day early** | Submitted |
| 16 | Mon 12 Oct | — | Hard deadline (AoE). All authors register as reviewers within 48 h | — |

---

## 14. Run protocol and commands

### 14.0 Code changes required before R1 (checked 26 Sep)

The pipeline logic needs no changes; the switches already work. Two small fixes to the run harness are needed:

| # | Problem | Consequence | Fix | Size |
|---|---|---|---|---|
| 1 | The v1.8 run config (`research_suite._resolved_config`) records **no environment settings**: not `ABLATION_*`, `SLAYQL_TOP_N` or `MODEL_NAME` (`bird_dev_v18_full/resolved_config.json` has no `environment` field). `dataset_pipeline.resolved_config` records some, but misses `ABLATION_NO_RBP`, `ABLATION_NO_ITEE` and `ABLATION_NO_QOC`. | A run folder does not say which variant it is, so results can't be traced to their setting. A resume with a leftover variable would not be detected. | Add an `environment` block with all `ABLATION_*`, `SLAYQL_TOP_N`, `MODEL_NAME` and `OPENAI_BASE_URL` values to `research_suite._resolved_config` (it is then part of the config hash), and add the three missing keys to `dataset_pipeline.resolved_config` | ~10 lines |
| 2 | `_prompt_bird_root` in `dataset_pipeline.py` **always asks two questions** (the BIRD directory and "Continue? [y/N]"), even when `--bird-root` is given. | Runs can't start unattended or with output redirected to a log | Skip the prompts when `--bird-root` is given and `SLAYQL_NONINTERACTIVE=1`. Workaround without code: pipe the answers, `"", "y" \| python research_suite_v18.py ...` | ~5 lines |

**Environment notes for this machine:**
- **GPU:** a GTX 1650 with 4 GB (not the RTX 4060 in `STATUS.md`). Stagger parallel runs so only one is in its embedding or retrieval stage at a time. If memory errors appear, run one at a time.
- **Embedding model:** `run/model_manager.py` uses `hf_cache/` in the repo, which currently has no model. The first run downloads it (needs internet).
- **BIRD data:** pass `--bird-root ..\dev\dev_20240627` (contains `dev.json`, `dev_tables.json` and `dev_databases/`).

**Analysis code to write (new scripts; no pipeline changes):**

| Script | For | Effort |
|---|---|---|
| Spider 2.0-Lite linking evaluator (gold SQL parsing with `sqlglot`, schema-prompt parsing, metrics, schema tokens) | O1 | ~0.5–1 day, the largest task |
| Run aggregator (EX, linking, tokens by stage, cost, turns → one CSV) | O2, T1–T2 | ~2 h |
| oracle@k and vote@k from `evaluation/*.json` (`correct_candidate_ids`) and `candidates/` | O3, F3 | ~2 h |
| Statistics (bootstrap CIs, McNemar, Holm) | O5 | ~2 h |
| IT-EE activation from `initial_candidates.json` (`dynamic_t_max`, `entropy` are stored per question) | O7 | ~1 h |
| BIRD difficulty join (from `dev.json` via source ID) | EX by difficulty | ~1 h |
| Figures F2 and F3 | Paper | ~2 h |

### 14.1 Rules

1. **One run ID per variant** (`bird_dev_v18_k1_<variant>`). Never reuse one; the pipeline resumes from checkpoints in the run folder.
2. **Set and clear environment variables per run.** A leftover `ABLATION_*` variable silently contaminates the next run.
3. **At most 2 runs at once**, with starts staggered by about 30 minutes so retrieval stages do not compete for the GPU.
4. **Log everything** to `run/logs_pub/<run_id>.log`.
5. **Resume a failed run** by rerunning the identical command. Record reruns in Section 14.4.
6. **Windows:** stopping the terminal does not stop Python. Use `Get-Process python* | Stop-Process -Force` only when no other run is active.
7. **No pipeline code changes** after R1 starts. If one is unavoidable, restart the affected runs.

### 14.2 Smoke tests (R0)

```powershell
cd run
python research_suite_v18.py run --dataset bird --split dev --mode smoke --bird-root ..\dev\dev_20240627 --run-id smoke_ref --num-candidates 1 --workers 4
$env:ABLATION_NO_RBP = "1"
python research_suite_v18.py run --dataset bird --split dev --mode smoke --bird-root ..\dev\dev_20240627 --run-id smoke_no_rbp --num-candidates 1 --workers 4
Remove-Item Env:ABLATION_NO_RBP
# repeat for ABLATION_NO_ITEE, ABLATION_NO_BM25, ABLATION_NO_QOC, SLAYQL_TOP_N=20, ABLATION_ITEE_THRESHOLD=0.7
```

**Pass criteria:**
- the log prints the matching `[ABLATION]` line;
- `final_schema_prompts/` differs from `smoke_ref` for the RBP, TOP_N and BM25 variants;
- turn counts differ for the IT-EE variants.

Also check whether the local asset stage (documents and embeddings) is rebuilt for every run. If it is slow, copy the assets from `bird_dev_v18_full/` into each new run folder before starting.

### 14.3 Full-run template

```powershell
cd run
$env:ABLATION_NO_RBP = "1"          # or the setting for this run; none for R1
$env:SLAYQL_NONINTERACTIVE = "1"     # after fix 2 in Section 14.0
python research_suite_v18.py run --dataset bird --split dev --mode full --bird-root ..\dev\dev_20240627 `
  --run-id bird_dev_v18_k1_no_rbp --num-candidates 1 --workers 4 --skip-subset-gate `
  *> logs_pub/bird_dev_v18_k1_no_rbp.log
Remove-Item Env:ABLATION_NO_RBP
```

Each run writes `aggregates/summary_metrics.json` (EX, linking, usage) and per-question results in `evaluation/`.

### 14.4 Run log (fill in as you go)

| Run | Run ID | Started | Finished | Reruns | EX | Table P/R | Col P/R | Tokens/q | $ | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | bird_dev_v18_k1_ref | | | | | | | | | |
| R2 | bird_dev_v18_k1_no_rbp | | | | | | | | | |
| R3 | bird_dev_v18_k1_no_itee | | | | | | | | | |
| R4 | bird_dev_v18_k1_no_bm25 | | | | | | | | | |
| R5 | bird_dev_v18_k1_no_qoc | | | | | | | | | |
| R6 | bird_dev_v18_k1_topn20 | | | | | | | | | |
| R7 | bird_dev_v18_k1_topn50 | | | | | | | | | |
| R8 | bird_dev_v18_k1_itee02 | | | | | | | | | |
| R9 | bird_dev_v18_k1_itee07 | | | | | | | | | |
| R10 | bird_dev_v18_k1_topn10000 | | | | | | | | | |
| R11 | bird_dev_v18_k1_<model>_subset20 | | | | | | | | | |

---

## 15. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| OpenRouter outage or rate limits | Medium | At most 2 parallel runs; resume with the same run ID; start early |
| Ablations show no significant effect | Medium | Scenario D |
| Budget controls do not change tokens | Medium | Scenario C; O7 explains why |
| Gold SQL parsing fails | Medium | Scenario G |
| SlayQL links worse than AutoLink | Medium | Scenario B |
| ARR review not guaranteed without a qualified service contributor | High unless handled | Supervisor registers as service contributor this week |
| Missing OpenReview profiles | Low | Every author completes OpenReview with ORCID by 5 Oct |
| Published numbers in `Comparisons.pdf` are wrong | Medium | Day 3 verification against the original papers |
| Team runs out of time | Medium | Draft on 3 Oct regardless; later days are buffer |

---

## 16. Submission checklist (ARR)

- [ ] Supervisor confirmed as the qualified service contributor
- [ ] All authors: OpenReview profile with ORCID, affiliation history, DBLP link if any
- [ ] Anonymised PDF; anonymous repository link only
- [ ] Limitations section; responsible research checklist filled in
- [ ] Every number traceable to a run folder and run ID (appendix)
- [ ] Model ID, seed, k and number of questions in every table caption
- [ ] Every published number checked against its original paper (backbone, split, recall definition)
- [ ] CIs and significance tests on every internal comparison
- [ ] All authors register as reviewers within 48 hours of submission
- [ ] Code, configs and run commands archived for release after review

---

## 17. Out of scope this cycle

- New pipeline designs, v1.9 full runs, or new Spider 2.0-Lite runs
- The slayql-UI trust layer (a separate paper)
- The Qwen3-max linker-only protocol from page 4 of `Comparisons.pdf` (possible for PAKDD or DASFAA)
- Spider 1.0 accuracy in the main paper

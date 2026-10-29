# C-CaSE / SlayQL-Lite: Scalable Schema Exploration & Value-Grounded Text-to-SQL at Scale

<p align="center">
  | <a href="https://arxiv.org/abs/2511.17190"><b>AutoLink Paper (arXiv)</b></a> |
</p>

## Overview

This repository is modified and extended by **Kian Lok Chin (Monash University Malaysia)** and the **MDS06 FYP Group** to advance baseline testing, schema linking research, component ablation, and scalable evaluation on the **Spider 2.0-Lite** benchmark.

> [!NOTE]
> ### 👨‍💻 Primary Research & Project Leadership
> **All research, architectural design, C-CaSE/SlayQL framework implementation, ablation study pipelines, and benchmark evaluations were majorly conducted by Kian Lok Chin throughout the semester break from 1 June 2026 to 24 July 2026.**

> [!IMPORTANT]
> ### ⚠️ Important Notes for FYP Group Members (MDS06)
> 1. **Pre-processed Embeddings:** You do **not** need to re-run document generation or embedding creation. Use pre-processed `embeddings/` and `documents/` folders inside `run/`.
> 2. **Credentials:** Credentials are required for both the AutoLink agent and the Evaluation suite (`run/bigquery_credentials/`, `run/snowflake_credential/`, and `evaluation_suite/`).
> 3. **Local Databases:** SQLite evaluation requires local `.sqlite` databases stored in `run/resource/databases/spider2-localdb`.
> 4. **API Configuration:** Put `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `MODEL_NAME` in `run/.env`. The pipeline uses the OpenAI Python client, so an OpenAI-compatible host works without code changes. For Together, use `OPENAI_BASE_URL=https://api.together.ai/v1` and that host's model id. Do not commit `run/.env`.

---

## 🏛️ Executive Summary & Master System Vision

Text-to-SQL over enterprise-scale databases presents severe challenges for Large Language Models (LLMs). Enterprise schemas often contain hundreds of tables, tens of thousands of columns, ambiguous string values, and multi-hop foreign key relationships.

The **AutoLink** baseline introduced an agentic 10-turn exploration framework over dense vector column retrievals. However, AutoLink suffers from **schema join blindness**, **value entity misattribution**, **runaway API token costs**, and **unconstrained formatting parser traps**.

This document details the technical evolution of **C-CaSE / SlayQL** across local release tags (`AutoLink`, `c-case-v1`, `v1.0.0-slayql-lite`), commit milestones (`af6bad0`, `a72cce2`, `3b53c20`, `8770692`, `475ce87`, `b015e42`, `02599b2`, `251c7bb`, `5932669`, `ba00dc2`, `2b1719f`), and research branches (`slayql-1`, `slayql-2`, `slayql-lite`).

Important Git correction: the project history is **not** a single linear chain from `AutoLink` to `c-case-v1` to `slayql-1` to `slayql-2` to `slayql-lite`. Local Git shows parallel work from the `AutoLink` baseline that was later integrated into `main`. The `v1.0.0-slayql-lite` annotated tag resolves to commit `02599b2`; `251c7bb` is a post-release commit.

The local artifacts support the SlayQL-Lite headline result of **40.45% EX (72/178)** on Spider 2.0-Lite. The baseline denominator depends on which comparison artifact is used: `run/comparison_report.md` reports **71/178 (39.89%)**, while `run/csv_only_comparison_report.md` reports **67/178 (37.64%)**.

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                          COMPLETE ARCHITECTURAL EVOLUTION TRAJECTORY                      │
└───────────────────────────────────────────────────────────────────────────────────────────┘

  [Tag: AutoLink] ──┬──► [Tag: c-case-v1] ──► [Commit: 3b53c20] ────────────────┐
                    │                                                           │
                    └──► [Branch: slayql-1] ──► [Branch: slayql-2]              │
                         │                                                       │
                         └──► [Tag: v1.0.0-slayql-lite @ 02599b2] ──► [slayql-lite] ──► [main]

  • AutoLink: af6bad0 baseline snapshot
  • c-case-v1: a72cce2 evaluation/infrastructure tag, not c-case-op-1 branch tip
  • slayql-1: 8770692/475ce87 RBP + BM25 value grounding line
  • slayql-2: b015e42 SGSA semantic-assertion validation experiment
  • v1.0.0-slayql-lite: annotated release tag targeting 02599b2
  • post-release: 251c7bb/5932669/ba00dc2 operational and documentation updates
```

---

## 📜 1. Master Version & Release History

| Version / Ref | Branch / Type | Key Commit | Verified Milestone & Focus | Benchmark Evidence |
|---|---|---|---|---|
| **`AutoLink`** | tag / `c-case-op-1` branch | `af6bad0` | **Initial Baseline Snapshot**: AutoLink-derived starting point. | Later comparison artifacts report baseline results; do not infer a unique benchmark score from the tag alone. |
| **`c-case-v1`** | tag | `a72cce2` | **Evaluation & Infrastructure**: comparison tools, subset evaluation wrapper, credential/load handling, and multi-provider execution support in repo code. | `c-case-op-1` does **not** point here; it still points to `af6bad0`. |
| **`SlayQL v2`** | main-line commit | `3b53c20` | **Schema Engine / SQL Revision Work**: adds `run/slayql2_schema_engine.py`, scratch schema tools, config, SQL generation, and SQL revision changes. | Real milestone present in Git; omitted by the earlier report. |
| **`slayql-1`** | branch | `8770692` | **RBP + Value Grounding Pipeline**: introduces graph propagation and value-grounding support. | Implementation supported by committed files. |
| **`slayql-1`** | branch tip | `475ce87` | **Enhanced Value Grounding**: stop-word filtering, numeric thresholding, capped hint injection, and RBP refinements. | Implementation supported by committed files. |
| **`slayql-2`** | branch | `b015e42` | **SGSA Semantic Validation**: Self-Generated Semantic Assertions validator and revision-loop integration. | Committed v2 reports show 27/178 (15.2%), but not because of Steiner/subgraph pruning. |
| **`v1.0.0-slayql-lite`** | annotated release tag | `02599b2` | **SlayQL-Lite Release Snapshot**: release target for the SlayQL-Lite architecture. | Actual annotated tag target. |
| **post-release SlayQL-Lite** | `slayql-lite` history | `251c7bb` | **Production & Automation**: resilient batch retry engine, failed-task tracking, ablation scripts, and handoff docs. | Post-release commit, not the release tag target. |
| **`slayql-lite`** | branch tip | `ba00dc2` | **Documentation Manuscript**: expanded README and project evolution manuscript. | Merged into `main` by `2b1719f`. |
| **`v1.9.0`** | annotated release tag on `main` | `slayql-1` research suite | **SlayQL v1.9 adaptive schema research suite**: BIRD dev pipeline, publication runner, and result tables. Local run `bird_dev_v19_full` scored **904/1534 (58.93% EX)** with 5 candidates. | `run/research_summary.json` in that run; summary tables under `run/pub_results/`. |

---

## Running SlayQL v1.9 on BIRD dev

From the repository root, with `run/.env` filled in and the BIRD dev files under `dev/dev_20240627`:

```powershell
cd C:\path\to\C-CaSE
$env:SLAYQL_NONINTERACTIVE = "1"
powershell -ExecutionPolicy Bypass -File .\run\run_research_suite_v19.ps1 `
  -Command run -Dataset bird -Split dev -Mode full `
  -BirdRoot "C:\path\to\C-CaSE\dev\dev_20240627" `
  -RunId bird_dev_v19_full -SkipSubsetGate
```

`SLAYQL_NONINTERACTIVE=1` skips the BIRD directory prompt. The same run id resumes from checkpoints. Publication smoke and full variant runners are `run/pub_setup.ps1` and `run/pub_run_all.ps1`.

---

## 🔍 2. Phase 0: AutoLink Baseline Architecture & Dissected Bottlenecks

### 2.1 The Baseline Pipeline Execution Flow
The original AutoLink pipeline follows a linear 12-stage execution flow:

$$\text{Query } Q \longrightarrow \text{Dense Retrieval } (\text{BGE-Large}) \longrightarrow \text{Initial Schema Prompt} \longrightarrow \text{Agentic Loop (10 Turns)} \longrightarrow \text{Candidate SQL Gen} \longrightarrow \text{Execution Selection}$$

1. **Document Construction** (`generate_docs.py`): Formats database metadata into column-level text documents.
2. **Dense Retrieval** (`embedding_docs.py`, `retrieve_topk_schema.py`): Computes cosine similarity between query embedding $\mathbf{q} = \text{BGE-Large}(Q)$ and column embeddings $\mathbf{d}_c = \text{BGE-Large}(D_c)$:
   $$\text{Sim}(Q, D_c) = \frac{\mathbf{q} \cdot \mathbf{d}_c}{\|\mathbf{q}\| \|\mathbf{d}_c\|}$$
3. **Agentic Schema Exploration** (`complete_schema.py`): Runs a fixed 10-turn chat loop where the LLM requests additional column definitions.
4. **SQL Generation & Selection** (`sql_generation.py`, `sql_selection.py`): Generates $K=5$ SQL candidates per instance, executes them, clusters identical execution DataFrames, and selects the majority candidate via pairwise LLM voting.

### 2.2 Mathematical & Architectural Failure Modes in Baseline

#### Failure Mode 1: Schema Join Blindness (Disconnected Graphs)
Dense vector retrieval ranks columns independently based on semantic overlap. When a question requires joining `table_a` and `table_c` through an intermediate junction table `bridge_b` whose column names have low semantic similarity to $Q$:
$$\text{Sim}(Q, D_{\text{bridge\_b}}) < \tau_{threshold}$$
`bridge_b` is excluded from top-N retrieval. Consequently, the LLM receives a disconnected schema graph $G = (V, E)$ where no edge path $v_a \rightsquigarrow v_c$ exists in $E$.

#### Failure Mode 2: Entity Value Misattribution
When $Q$ contains string literals (e.g., *"Find applications filed under 'IoT'"*), vector retrieval matches column *descriptions* rather than *cell values*. The LLM cannot determine if `'IoT'` refers to `technology_category`, `abstract_text`, or `short_name`, leading to incorrect `WHERE` clause conditions:
$$\text{WHERE } \text{technology\_category} = \text{'IoT'} \quad (\text{Incorrect; actual value is in } \text{abstract\_text})$$

#### Failure Mode 3: Runaway Token Consumption (Fixed Budget Trap)
AutoLink executes a rigid 10-turn exploration budget for every query. For a dataset of $N=178$ queries and $M=10$ turns:
$$\text{Total Prompt Tokens} = \sum_{i=1}^{N} \sum_{t=1}^{10} |\text{Prompt}_{i, t}| \approx 1.2 \times 10^8 \text{ tokens}$$
For simple queries where the schema was complete at Turn 2, turns 3–10 added 80% redundant API overhead and increased latency by $4\times$.

#### Failure Mode 4: The Silent Execution Trap
Unconstrained system prompts allow the LLM to output arbitrary explanation text:
```
Here is the requested SQL query for your analysis:
SELECT date FROM gsod2009 WHERE ...
I hope this query helps!
```
Regex parsers searching for code blocks fail to isolate clean SQL code, causing null SQL generation files or execution timeouts.

---

## 🛠️ 3. Phase 1: Multi-Provider Evaluation Infrastructure (`c-case-v1`)

To establish reliable benchmarking across heterogeneous database environments, **Tag `c-case-v1`** (`a72cce2`) added evaluation/infrastructure code in this repository, including comparison scripts, a subset evaluation wrapper, credential/load handling, and multi-provider execution support. The wrapper `run/evaluate_subset.py` invokes `../evaluation_suite/evaluate.py`; that `evaluation_suite/` directory is expected as an external/sibling evaluation resource and is not tracked inside this repository snapshot.

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                         MULTI-PROVIDER EVALUATION ARCHITECTURE                            │
└───────────────────────────────────────────────────────────────────────────────────────────┘

                                ┌───────────────────────────┐
                                │   Predicted SQL & Gold    │
                                └─────────────┬─────────────┘
                                              │
                                              ▼
                                ┌───────────────────────────┐
                                │   Dialect Router / Dispatch│
                                └──────┬──────────┬─────────┘
                                       │          │
                 ┌─────────────────────┘          └─────────────────────┐
                 ▼                                                      ▼
   ┌───────────────────────────┐                          ┌───────────────────────────┐
   │    Google BigQuery API    │                          │   Snowflake Connector DB  │
   │  (Credentials Pool / REST)│                          │  (Warehouse Connection)   │
   └─────────────┬─────────────┘                          └─────────────┬─────────────┘
                 │                                                      │
                 └─────────────────────┬────────────────────────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │   Local SQLite Engine Pool│
                         │   (spider2-localdb DBs)   │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │  Execution DataFrame Match│
                         │  (conformal score / EX)   │
                         └───────────────────────────┘
```

### Key Technical Contributions in `c-case-v1`:
1. **Multi-Dialect Execution Engine**: Handles Google BigQuery REST endpoints, Snowflake warehouse sessions, and 32 local SQLite databases concurrently.
2. **Credential Load Balancer**: Distributes BigQuery service account keys across thread pools to bypass GCP quota limits (`403 Quota Exceeded`).
3. **DataFrame Execution Matcher**: Compares predicted Pandas DataFrames against gold execution DataFrames using value-level matching, handling float rounding tolerances (`ROUND(val, 4)`) and column permutation invariance.

---

## 4. Phase 2: SGSA Semantic-Validation Experiment (`slayql-2`)

### 4.1 Corrected SGSA Definition
In **Branch `slayql-2`** (Commit `b015e42`), SGSA means **Self-Generated Semantic Assertions**, not "Sub-Graph Search Algorithm." The branch introduces semantic validation code that parses model-generated assertions, validates execution DataFrames against those assertions, and feeds validation failures into the SQL revision loop.

Verified files on the `slayql-2` branch include:
1. `run/semantic_validator.py`
2. `run/test_semantic_validator.py`
3. `run/sql_execution.py`
4. `run/sql_generation.py`
5. `run/sql_revise.py`

```text
SGSA Semantic Validation Flow

[Generated SQL + semantic assertions]
              |
              v
[Execution result DataFrame]
              |
              v
[SGSA validator]
              |
              v
[Pass] or [Revise SQL with semantic errors]
```

### 4.2 Empirical Result in Committed `slayql-2` Artifacts
The committed `slayql-2` comparison artifacts report a substantial degradation:

| Artifact | Baseline | SGSA Variant (`slayql-2`) | Change |
|---|---:|---:|---:|
| `run/comparison_report_v2.md` at `b015e42` | 67 / 178 (37.6%) | 27 / 178 (15.2%) | -40 |
| `run/csv_only_comparison_report_v2.md` at `b015e42` | 67 / 178 (37.6%) | 27 / 178 (15.2%) | -40 |

### 4.3 Corrected Failure Interpretation
The local Git evidence supports the conclusion that the `slayql-2` SGSA semantic-validation experiment performed worse than the baseline in the committed v2 reports. It does **not** support the earlier explanation that this branch implemented Steiner-tree pruning, destructive subgraph rollback, or an "Over-Pruning Trap."

Correct conclusion:

> SGSA semantic validation was an experimental rollback path that degraded empirical accuracy in the available committed reports. The cause should be described as a semantic-validation/revision-loop failure mode unless separate pruning evidence is added.

---

## ⚡ 5. Phase 3: SlayQL-Lite Production Architecture (`slayql-lite`)

To address the limitations of baseline AutoLink, **SlayQL-Lite** (`v1.0.0-slayql-lite`, annotated tag targeting `02599b2`) introduced a non-destructive 4-module architecture:

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                 SLAYQL-LITE ARCHITECTURE                                  │
└───────────────────────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────┐
                           │    User Question & Database   │
                           └───────────────┬───────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────┐
                           │   1. Dense Retrieval + RBP    │
                           │   (Graph Join Propagation)    │
                           └───────────────┬───────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────┐
                           │   2. BM25 Value Grounder      │
                           │  (Exact Value Hint Injection) │
                           └───────────────┬───────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────┐
                           │   3. Agentic Completion +     │
                           │   IT-EE (Dynamic Early Exit)  │
                           └───────────────┬───────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────┐
                           │   4. SQL Generation + QOC     │
                           │   (Strict Output Contracts)   │
                           └───────────────┬───────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────┐
                           │   5. Execution & Selection    │
                           │  (Pairwise Pair Consistency)  │
                           └───────────────────────────────┘
```

### 5.1 Module 1: Relevance-Based Propagation (RBP)
- **File**: `run/rbp_graph.py` & `run/retrieve_topk_schema.py`
- **Naming note**: The code labels RBP as **Relevance-Based Propagation**.
- **Mathematical Formulation**:
  Let $\mathbf{s}^{(0)} \in \mathbb{R}^{|V|}$ be the initial dense retrieval vector over schema tables $V$. RBP computes a graph random-walk restart with decay factor $\alpha \in (0, 1)$:
  $$\mathbf{s}^{(t+1)} = (1 - \alpha) \mathbf{M} \mathbf{s}^{(t)} + \alpha \mathbf{s}^{(0)}$$
  where $\mathbf{M} = \mathbf{D}^{-1} \mathbf{A}$ is the degree-normalized adjacency matrix of the foreign key graph $(V, E_{\text{fk}})$.
- **Impact**: Automatically elevates scores for intermediate junction tables $v_b \in V_{\text{bridge}}$, ensuring multi-hop foreign key JOIN paths remain intact in prompt contexts.

### 5.2 Module 2: BM25 Value Grounding Engine
- **File**: `run/value_grounder.py` & `run/build_value_indices.py`
- **Mathematical Formulation**:
  For query tokens $q \in Q$ and column value text $D_c$:
  $$\text{Score}_{\text{BM25}}(Q, D_c) = \sum_{q \in Q} \text{IDF}(q) \cdot \frac{f(q, D_c) \cdot (k_1 + 1)}{f(q, D_c) + k_1 \cdot \left(1 - b + b \cdot \frac{|D_c|}{\text{avgdl}}\right)}$$
- **Filtering & Capping Pipeline**:
  1. *Stop-Word & Low-Entropy Filter*: Strips generic terms (`'all'`, `'the'`, `'total'`).
  2. *Numeric Thresholding*: Ignores pure integer string filters unless tagged explicitly.
  3. *Hint Capping*: Current code uses `MAX_HINTS_PER_PROMPT = 3` to prevent prompt inflation.
- **Example Output**:
  ```markdown
  [VALUE GROUNDING HINT]
  Query entity 'internet of things' matched column `abstract_text` in table `patents.publications`.
  ```

### 5.3 Module 3: Iterative Early Exit (IT-EE)
- **File**: `run/complete_schema.py`
- **Code-state caveat**: The current `run/it_ee.py` comments describe a "Safe Exit" refactor where `should_early_exit` is forced to `False`; treat the formula below as the intended IT-EE design, not proof that the current code always exits early.
- **Mathematical Formulation**:
  Let $S^{(t)}$ be the set of schema elements in candidate prompt at exploration turn $t$. IT-EE computes the Jaccard similarity index across consecutive turns:
  $$J(S^{(t)}, S^{(t-1)}) = \frac{|S^{(t)} \cap S^{(t-1)}|}{|S^{(t)} \cup S^{(t-1)}|}$$
  **Early Exit Condition**:
  $$\text{If } J(S^{(t)}, S^{(t-1)}) \ge \theta_{\text{exit}} \quad (\text{where } \theta_{\text{exit}} = 0.95) \text{ for } K=2 \text{ consecutive turns } \longrightarrow \text{EXIT LOOP}$$
- **Impact**: Intended to reduce redundant exploration once candidate schemas stabilize. Local ablation logs show the `w/o IT-EE` run used 20,473,386 total tokens and 189,568 average tokens/query, but the current committed artifacts do not include a complete full-run token summary that independently verifies an exact **~60%** savings claim.

### 5.4 Module 4: Strict Output Contracts (QOC)
- **File**: `run/sql_generation.py`
- **System Prompt Formatting Directive**:
  ```markdown
  📤 Output Format
  You MUST return the final generated SQL query strictly enclosed inside triple-backtick blocks:
  ```sql
  SELECT ...
  ```
  Do NOT add conversational preambles or postscripts inside the code block.
  ```
- **Impact**: Improves regex parseability by requiring SQL code fences; this reduces silent parsing failures but should not be read as a proven absolute guarantee.

---

## 📊 6. Comprehensive Empirical Benchmark & Ablation Analysis

### 6.1 Benchmark Results (Spider 2.0-Lite — 178 Instances)

Evaluated on `subset_diverse_20_evaluation.json` (178 records). Result-source caveat: current local artifacts disagree on the baseline score, so the authoritative artifact must be named when reporting headline numbers.

| Model / Framework | Correct / Denominator (178) | Execution Accuracy % | Evaluable Subset Score (result.csv) | Report Path |
|---|---|---|---|---|
| **AutoLink Baseline** | 71 / 178 | **39.89%** | Not independently verified in current local artifacts | [comparison_report.md](file:///d:/C-CaSE/run/comparison_report.md) |
| **SlayQL-Lite (Enhanced)** | **72 / 178** | **40.45%** | Not independently verified in current local artifacts | [comparison_report.md](file:///d:/C-CaSE/run/comparison_report.md) |
| **AutoLink Baseline (CSV-only artifact)** | 67 / 178 | **37.64%** | Not independently verified in current local artifacts | [csv_only_comparison_report.md](file:///d:/C-CaSE/run/csv_only_comparison_report.md) |
| **SlayQL-Lite (CSV-only artifact)** | **72 / 178** | **40.45%** | Not independently verified in current local artifacts | [csv_only_comparison_report.md](file:///d:/C-CaSE/run/csv_only_comparison_report.md) |

#### Category Breakdown (`run/comparison_report.md`):
- 📈 **Improved** (Baseline ❌ $\rightarrow$ SlayQL ✅): **16 instances**
- 📉 **Degraded** (Baseline ✅ $\rightarrow$ SlayQL ❌): **15 instances**
- 🤝 **Both Correct**: **56 instances**
- ❌ **Both Incorrect**: **91 instances**

---

### 6.2 Leave-One-Out Component Dropout Ablation Suite

To measure the individual contribution of each SlayQL-Lite module, leave-one-out dropout experiments were run. The table below reflects the local `eval_result.txt` summaries that are currently present in the working tree:

| Variant | Module Dropped | Execution Accuracy (EX) | Total Tokens Consumed | Avg Tokens / Query | Empirical Takeaway & Conclusion |
|---|---|---|---|---|---|
| **Full SlayQL-Lite** | None (Reference) | **72 / 178 (40.45%)** | Not reproducible from `run/ablation1_full_slayql` in current tree | Not reproducible from current full-run ablation dir | Accuracy supported by comparison artifacts; full-token summary is not present locally. |
| **w/o RBP** | Relevance-Based Propagation | **4 / 178 (2.25%)** | 17,418,471 | 217,730 | **Severe Collapse (-38.2%)** in the available local run. |
| **w/o BM25** | Value Grounding Hints | **3 / 178 (1.69%)** | 5,652,427 | 171,285 | **Severe Collapse (-38.7%)** in the available local run; token values corrected from `run/ablation1_no_bm25/ablation1_no_bm25/eval_result.txt`. |
| **w/o IT-EE** | Dynamic Early Exit | **78 / 168 (46.43% eval)** | 20,473,386 | 189,568 | Accuracy did not collapse in this partial/evaluable run, but average token usage is high. |
| **w/o QOC** | Strict Output Contracts | *23 / 66 (Incomplete)* | 0 parsed | 0 parsed | Incomplete run; token parser found no token records in the local summary. |

---

### 6.3 Detailed Instance-Level Case Studies

#### Case Study 1: `sf_bq033` (Database: `PATENTS`) — Improved in `run/comparison_report.md` (Baseline ❌ $\rightarrow$ SlayQL ✅)
- **Question**: *"How many U.S. publications related to IoT (where abstract includes 'internet of things') were filed each month from 2008 to 2022, including months with no filings?"*
- **Artifact-grounded note**: `run/comparison_report.md` marks this instance as improved. However, the local artifact does **not** support the earlier claim that the baseline filtered `title`; the baseline SQL also filters `abstract_localized`. This case should be treated as an execution-result/equality improvement example, not as proof of title-vs-abstract value misgrounding.
  ```sql
  -- Baseline artifact also filters abstract_localized:
  AND LOWER(f.value:"text"::VARCHAR) LIKE '%internet of things%'
  ```
- **SlayQL-Lite (✅)**: The SlayQL SQL in the artifact also grounds the phrase through `abstract_localized` while producing the result shape marked correct by the comparison report:
  ```sql
  AND LOWER(f.value:"text"::TEXT) LIKE '%internet of things%'
  ```

#### Case Study 2: `bq392` (Database: `noaa_gsod`) — Both Correct in `run/comparison_report.md`
- **Question**: *"What are the top 3 dates in October 2009 with highest average temperature for station 723758 in YYYY-MM-DD format?"*
- **Artifact-grounded note**: `run/comparison_report.md` marks both the baseline and SlayQL as correct for this instance. It is therefore not valid evidence for a baseline failure. It remains a useful example of the expected BigQuery date formatting pattern:
  ```sql
  SELECT FORMAT_DATE('%Y-%m-%d', DATE(CAST(year AS INT64), CAST(mo AS INT64), CAST(da AS INT64))) AS date
  FROM `bigquery-public-data.noaa_gsod.gsod2009`
  WHERE stn = '723758' AND mo = '10' AND temp != 9999.9
  ORDER BY temp DESC LIMIT 3
  ```

---

## 🔧 7. Engineering & Infrastructure Enhancements

### 7.1 Resilient API Batch Retry Engine
- **Location**: `run/sql_generation.py`
- Added `run_batch()` wrapper with `--max_retries` (default: 5 with exponential backoff & jitter).
- Catches OpenRouter `None` content or timeout errors, records failed tasks in `sql_gen_failed_tasks.json`, and executes a dedicated rerun pass.

### 7.2 Cross-Platform Automation Suite
- **Location**: `run/`
- Created native Windows PowerShell scripts (`ablation1_component_dropout.ps1`, `ablation1_fix_failed.ps1`, `ablation_smoke_test.ps1`, `run_autolink_baseline.ps1`) for Windows 11 environments alongside Linux Bash scripts (`ablation1_component_dropout.sh` through `ablation4_model_agnostic.sh`).

### 7.3 Multi-Encoding Log Parsing
- **Location**: `run/generate_ablation_report.py`
- Implemented multi-encoding reader (`utf-8` and `utf-16`) to parse evaluation logs generated by PowerShell `Out-File` or `Tee-Object`.

### 7.4 System Disk Cache Protection
- **Location**: `run/model_manager.py`
- Redirects HuggingFace transformer model weights (`BAAI/bge-large-en-v1.5`) to `D:\C-CaSE\hf_cache` to prevent system drive `C:` space exhaustion.

---

## 🌿 8. Summary Matrix of Git Releases, Tags & Branches

| Identifier | Type | Commit | Key Technical Innovation / Milestone | Benchmark Evidence |
|---|---|---|---|---|
| **`AutoLink`** | Tag | `af6bad0` | Initial AutoLink baseline snapshot. | Later comparison artifacts report baseline scores. |
| **`c-case-op-1`** | Branch | `af6bad0` | Branch still points to initial commit. | Not the `c-case-v1` tag. |
| **`c-case-v1`** | Tag | `a72cce2` | Evaluation/infrastructure milestone. | Repo wrapper invokes external/sibling `evaluation_suite`. |
| **`SlayQL v2`** | Commit | `3b53c20` | Main-line schema-engine and SQL generation/revision work. | Real Git milestone. |
| **`slayql-1`** | Branch | `475ce87` | Integrated RBP graph propagation + BM25 value grounding. | Implementation supported. |
| **`slayql-2`** | Branch | `b015e42` | SGSA Self-Generated Semantic Assertions validation experiment. | Committed v2 artifacts report 27/178 (15.2%). |
| **`v1.0.0-slayql-lite`** | Annotated release tag | `02599b2` | SlayQL-Lite release snapshot. | Actual release tag target. |
| **post-release SlayQL-Lite** | Commit | `251c7bb` | Resilient batch engine, failed-task tracking, ablation scripts, and handoff docs. | Post-release, not the tag target. |
| **`slayql-lite`** | Branch tip | `ba00dc2` | Documentation/manuscript updates. | Merged into `main` by `2b1719f`. |

---

## 📁 9. Repository Structure

```
- evaluation_suite/                    -- Spider 2.0-Lite Evaluation Suite (external/sibling resource; not tracked in this repo snapshot if absent)
  - gold/                              -- Gold execution results and SQL
  - evaluate.py                        -- Execution accuracy evaluator
  - bigquery_credential.json           -- Credential for BigQuery evaluation
  - snowflake_credential.json          -- Credential for Snowflake evaluation
- run/                                 -- Core SlayQL / AutoLink Logic
  - ablation1_component_dropout.ps1    -- Windows PowerShell Ablation 1 runner
  - ablation1_fix_failed.ps1           -- Windows PowerShell ablation resume tool
  - ablation_smoke_test.ps1            -- 2-instance sanity smoke test (~2 min)
  - ablation1_component_dropout.sh     -- Linux Bash Ablation 1 runner
  - ablation2_scalability.sh           -- Ablation 2 (Scalability sweep)
  - ablation3_hyperparameter.sh        -- Ablation 3 (Hyperparameter tuning)
  - ablation4_model_agnostic.sh        -- Ablation 4 (Model-agnostic evaluation)
  - generate_ablation_report.py        -- Ablation Markdown report generator
  - run_autolink_baseline.ps1          -- Windows Baseline launcher
  - run_autolink_baseline.sh           -- Linux Baseline launcher
  - retrieve_topk_schema.py            -- Dense Retrieval + RBP graph propagation
  - complete_schema.py                 -- Dynamic Agentic Schema Completion (IT-EE)
  - sql_generation.py                  -- Candidate SQL Generation with retry engine & QOC
  - sql_selection.py                   -- Pairwise model voting & execution selection
  - value_grounder.py                  -- BM25 value hint retriever
  - comparison_report.md               -- Side-by-side SQL diff & execution report
  - .env                               -- Environment variables & API keys
STATUS.md                              -- Detailed team handoff documentation
PROJECT_EVOLUTION_REPORT.md            -- Exhaustive technical evolution report
COMMIT_SUMMARY.md                      -- Git commit summary log
```

---

## ⚙️ 10. Environment Setup & Installation

1. **Clone Repository & Switch to `slayql-lite`**:
   ```bash
   git clone https://github.com/MDS06-Monash-2026/C-CaSE.git
   cd C-CaSE
   git checkout slayql-lite
   ```

2. **Python & Dependencies**:
   ```bash
   conda create -n SlayQL python=3.11
   conda activate SlayQL
   pip install -r requirements.txt
   ```

3. **Configure API Credentials**:
   Create or edit `run/.env`:
   ```env
   OPENAI_API_KEY=your_openrouter_or_openai_key
   OPENAI_BASE_URL=https://openrouter.ai/api/v1
   MODEL_NAME=deepseek/deepseek-v4-flash
   ```

4. **Resource Setup**:
   - Place BigQuery & Snowflake credentials into `run/bigquery_credentials/` and `run/snowflake_credential/`.
   - Place SQLite database files into `run/resource/databases/spider2-localdb/`.

---

## 🚀 11. Running the Pipeline

### Option A: Windows (PowerShell)

**Run Sanity Smoke Test (2 instances)**:
```powershell
cd run
.\ablation_smoke_test.ps1
```

**Run Baseline AutoLink**:
```powershell
cd run
.\run_autolink_baseline.ps1
```

**Run Full Ablation 1 Pipeline**:
```powershell
cd run
.\ablation1_component_dropout.ps1
```

### Option B: Linux (Bash)

**Run Baseline Pipeline**:
```bash
cd run
bash run_autolink_baseline.sh
```

**Run Ablation 1 Pipeline**:
```bash
bash ablation1_component_dropout.sh --data_file subset_diverse_20_evaluation.json
```

---

## 📊 12. Evaluating Results & Generating Reports

Once SQL generation and selection complete, run the evaluation script. This command assumes the external/sibling `evaluation_suite/` directory is available at the path shown:

```bash
python evaluation_suite/evaluate.py \
    --result_dir run/log_subset_diverse_20_evaluation_slayql_ccase/sql_selection/final \
    --mode exec_result \
    --gold_dir evaluation_suite/gold \
    --data_file run/subset_diverse_20_evaluation.json
```

To parse token consumption metrics and generate an ablation report:

```bash
python run/generate_ablation_report.py \
    --ablation_type component_dropout \
    --data_file subset_diverse_20_evaluation.json \
    --task r1_lite \
    --variants \
        "Full SlayQL:log_subset_diverse_20_evaluation_slayql_ccase" \
        "w/o IT-EE:ablation1_no_itee" \
        "w/o RBP:ablation1_no_rbp" \
        "w/o BM25:ablation1_no_bm25" \
        "w/o QOC:ablation1_no_qoc" \
    --output_path ablation1_component_dropout_report.md
```

---

## 📜 13. Citation

If you use this codebase or benchmark methodology, please cite the original AutoLink work:

```bibtex
@misc{wang2025autolinkautonomousschemaexploration,
      title={AutoLink: Autonomous Schema Exploration and Expansion for Scalable Schema Linking in Text-to-SQL at Scale}, 
      author={Ziyang Wang and Yuanlei Zheng and Zhenbiao Cao and Xiaojin Zhang and Zhongyu Wei and Pei Fu and Zhenbo Luo and Wei Chen and Xiang Bai},
      year={2025},
      eprint={2511.17190},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2511.17190}, 
}
```

# C-CaSE / SlayQL Repository Technical Briefing Report

**Purpose**: Brief teammates, supervisors, evaluators, or future maintainers on what has been built in this repository, how it is implemented, what results exist, and what caveats must be preserved.  
**Repository checked**: `D:\C-CaSE`  
**Current local branch**: `main`  
**Primary remote**: `https://github.com/MDS06-Monash-2026/C-CaSE`  
**Prepared on**: 2026-07-25  
**Evidence sources**: corrected `README.md`, local Git history, local branch/tag refs, source files under `run/`, result artifacts under `run/`, `STATUS.md`, `COMMIT_SUMMARY.md`, and `ACCURATE_PROJECT_EVOLUTION_REPORT.md`.

---

## 1. Executive Brief

C-CaSE / SlayQL is a Text-to-SQL research codebase built from the AutoLink baseline and extended for Spider 2.0-Lite-style enterprise schema linking. The work focuses on improving schema retrieval, value grounding, SQL generation robustness, evaluation reproducibility, and ablation analysis.

The repository now contains:

1. The original AutoLink-style pipeline for document generation, embedding, schema retrieval, schema completion, SQL generation, SQL revision, execution, and candidate selection.
2. SlayQL-Lite extensions:
   - **RBP**: Relevance-Based Propagation over schema graphs.
   - **BM25 value grounding**: exact value-hint retrieval from database cell values.
   - **IT-EE**: intended iterative/dynamic budget logic, currently with a safe-exit caveat.
   - **QOC**: stricter SQL output formatting contracts.
3. Multi-provider support for:
   - BigQuery
   - Snowflake
   - SQLite local databases
4. Evaluation and comparison tooling:
   - side-by-side SQL comparison reports;
   - CSV-only result comparison reports;
   - subset evaluation wrappers;
   - ablation report generation.
5. Automation scripts for Windows PowerShell and Bash, especially for baseline and Ablation 1.
6. Git history documenting experimental branches:
   - `AutoLink`
   - `c-case-v1`
   - `slayql-1`
   - `slayql-2`
   - `slayql-lite`
   - final integration into `main`.

The strongest local headline result, from `run/comparison_report.md`, is:

| System | Correct / 178 | Accuracy |
|---|---:|---:|
| AutoLink baseline | 71 / 178 | 39.89% |
| SlayQL-Lite / enhanced | 72 / 178 | 40.45% |

However, the repository also contains `run/csv_only_comparison_report.md`, which reports a different baseline:

| System | Correct / 178 | Accuracy |
|---|---:|---:|
| AutoLink baseline, CSV-only artifact | 67 / 178 | 37.64% |
| SlayQL-Lite / enhanced, CSV-only artifact | 72 / 178 | 40.45% |

For any presentation or paper, the exact artifact used must be stated.

---

## 2. Correct Git Evolution

The actual local Git graph is not a single linear chain. `c-case-v1`, `slayql-1`, `slayql-2`, and `slayql-lite` represent related but not strictly linear work from the AutoLink baseline.

### 2.1 Verified Commit Timeline

| Commit | Date | Ref | Meaning |
|---:|---|---|---|
| `af6bad0` | 2026-06-13 | `AutoLink`, `c-case-op-1` | Initial AutoLink baseline snapshot. |
| `a72cce2` | 2026-06-16 | `c-case-v1` | Evaluation/infrastructure milestone. |
| `3b53c20` | 2026-06-17 | main-line commit | SlayQL v2 schema-engine and SQL revision/generation work. |
| `8770692` | 2026-06-22 | slayql branch history | Full RBP graph propagation and value-grounding pipeline support. |
| `475ce87` | 2026-06-23 | `slayql-1` | Enhanced value grounder with stop-word filtering, numeric thresholding, and capped hint injection. |
| `b015e42` | 2026-06-23 | `slayql-2` | SGSA semantic-validation experiment. |
| `02599b2` | 2026-07-24 | `v1.0.0-slayql-lite` | Actual annotated release tag target. |
| `251c7bb` | 2026-07-24 | post-release SlayQL-Lite | Resilient batch engine, ablation scripts, failed-task tracking, and handoff docs. |
| `5932669` | 2026-07-24 | post-release SlayQL-Lite | README architecture, benchmark, and ablation documentation updates. |
| `ba00dc2` | 2026-07-24 | `slayql-lite` | Manuscript-style README and project evolution report updates. |
| `2b1719f` | 2026-07-24 | `main` | Merge of `slayql-lite` into `main`. |

### 2.2 Corrections That Must Be Preserved

| Common Wrong Claim | Correct Version |
|---|---|
| `v1.0.0-slayql-lite` points to `251c7bb`. | It points to `02599b2`. `251c7bb` is post-release. |
| `c-case-v1` is on branch `c-case-op-1`. | `c-case-v1` is a tag at `a72cce2`; `c-case-op-1` still points to `af6bad0`. |
| `slayql-2` implemented Steiner-tree / subgraph pruning. | `slayql-2` implemented SGSA: Self-Generated Semantic Assertions. |
| The history is linear from AutoLink to c-case-v1 to slayql-1 to slayql-2 to slayql-lite. | It contains parallel branches later integrated into `main`. |

---

## 3. Repository Structure and Responsibilities

### 3.1 Top-Level Files

| File | Role |
|---|---|
| `README.md` | Main project overview, setup, corrected evolution summary, results, and usage instructions. |
| `PROJECT_EVOLUTION_REPORT.md` | Older manuscript-style evolution report; useful but contains known inaccuracies. |
| `ACCURATE_PROJECT_EVOLUTION_REPORT.md` | Corrected evidence-backed evolution report created to fix the older report. |
| `STATUS.md` | Handoff/status notes from the ablation work. Some content is historical and should be read with the corrected Git history in mind. |
| `COMMIT_SUMMARY.md` | Summary of recent script, ablation, and robustness changes. |
| `memory.txt` | Longer work-memory/handoff context. |
| `requirements.txt` | Python dependencies. |
| `.gitignore` | Excludes local env files, logs, caches, BM25 indices, and generated ablation artifacts. |

### 3.2 Main `run/` Implementation Areas

| Area | Key Files |
|---|---|
| Metadata/document generation | `generate_docs.py`, `generate_schema.py`, `postprocess.py`, `add_id.py` |
| Embedding and retrieval | `embedding_docs.py`, `retrieve_topk_schema.py`, `model_manager.py` |
| Graph propagation | `rbp_graph.py` |
| Value grounding | `build_value_indices.py`, `value_grounder.py` |
| Schema completion | `complete_schema.py`, `it_ee.py`, `mcp_tools.py` |
| SQL generation | `sql_generation.py`, `config.py` |
| SQL execution / revision | `sql_execution.py`, `sql_revise.py` |
| Candidate selection | `sql_selection.py` |
| Evaluation / comparison | `evaluate_subset.py`, `generate_comparison.py`, `generate_csv_comparison.py`, `compare_outputs.py`, `compare_batch_ex.py` |
| Ablation reporting | `generate_ablation_report.py`, `parse_tokens.py` |
| Automation scripts | `run_autolink_baseline.ps1`, `run_autolink_baseline.sh`, `ablation1_component_dropout.ps1`, `ablation1_component_dropout.sh`, `ablation1_fix_failed.ps1`, `ablation_smoke_test.ps1`, `ablation2_scalability.sh`, `ablation3_hyperparameter.sh`, `ablation4_model_agnostic.sh` |

---

## 4. End-to-End Pipeline

The repository implements a multi-stage pipeline:

```text
Question + database id
        |
        v
Database metadata -> document generation -> BGE embedding/FAISS index
        |
        v
Dense schema retrieval
        |
        v
SlayQL retrieval extensions:
  - RBP schema graph propagation
  - BM25 value hints
  - IT-EE/dynamic budget metadata
        |
        v
Schema completion prompt construction
        |
        v
Final schema prompt generation
        |
        v
SQL candidate generation, usually 5 candidates
        |
        v
SQL execution against BigQuery / Snowflake / SQLite
        |
        v
SQL revision on execution failure
        |
        v
Candidate clustering and selection
        |
        v
External evaluation suite and local comparison reports
```

The handoff notes describe this as a 12-stage pipeline:

| Stage | Purpose |
|---:|---|
| 1 | Build BM25 value indices. |
| 2 | Retrieve top schema elements. |
| 3 | Add IDs / prepare dataset metadata. |
| 4 | Build initial schema prompt. |
| 5 | Complete schema through agentic schema exploration. |
| 6 | Postprocess outputs. |
| 7 | Build final schema prompts. |
| 8 | Generate SQL candidates. |
| 9 | Execute SQL candidates. |
| 10 | Revise failed SQL. |
| 11 | Select final SQL. |
| 12 | Evaluate final results. |

Several scripts use checkpoint files such as `.pipeline_ckpt` so long runs can be resumed.

---

## 5. Baseline AutoLink Components

The baseline stack remains visible in the repo and forms the foundation for SlayQL-Lite.

### 5.1 Metadata Document Construction

**File**: `run/generate_docs.py`

Purpose:

- Walk database resources under:
  - `resource/databases/bigquery`
  - `resource/databases/snowflake`
  - `resource/databases/sqlite`
- Convert metadata into column/table-level textual documents.
- Save provider-specific document JSON files:
  - `documents/bigquery.json`
  - `documents/snowflake.json`
  - `documents/localdb.json`

Implementation characteristics:

- Branches by provider path.
- Uses database metadata files to produce retrieval descriptions.
- Separates BigQuery, Snowflake, and SQLite document generation because their metadata formats and naming patterns differ.

### 5.2 Embedding Construction

**File**: `run/embedding_docs.py`

Purpose:

- Embed schema documents using `BAAI/bge-large-en-v1.5`.
- Store dense vectors in FAISS indexes.
- Save metadata mappings so retrieved vector positions can be mapped back to database/table/column metadata.

Implementation details:

- Uses `SentenceTransformer("BAAI/bge-large-en-v1.5", device="cuda")`.
- Encodes descriptions in batches.
- Converts vectors to `np.float32`.
- Uses FAISS for similarity search.
- Asserts embedding count equals metadata mapping count.

### 5.3 Model Cache Protection

**File**: `run/model_manager.py`

Purpose:

- Prevent repeated HuggingFace downloads from filling the Windows system drive.
- Redirects HuggingFace cache to:

```text
D:\C-CaSE\hf_cache
```

Implementation details:

- Sets `HF_HOME`.
- Sets `HUGGINGFACE_HUB_CACHE`.
- Sets `TRANSFORMERS_CACHE`.
- Provides a `ModelManager` class around loading `BAAI/bge-large-en-v1.5`.

---

## 6. SlayQL-Lite Component 1: RBP Schema Graph Propagation

**Files**:

- `run/rbp_graph.py`
- `run/retrieve_topk_schema.py`

### 6.1 Problem Addressed

Dense vector retrieval ranks columns independently. This can miss low-text-similarity bridge tables that are necessary for valid joins. RBP was added to make schema linking aware of table connectivity.

### 6.2 Implementation

`run/rbp_graph.py` implements **RBP as Relevance-Based Propagation**.

Key functions:

| Function | Purpose |
|---|---|
| `_dynamic_alpha(entropy)` | Computes damping factor based on retrieval entropy. |
| `_extract_query_keywords(query)` | Extracts lightweight keywords from the user query. |
| `_count_table_columns(db_metadata, table_name)` | Measures table size for hub-table handling. |
| `_table_shares_keywords(...)` | Checks whether a table shares meaningful query keywords. |
| `build_schema_graph(db_metadata)` | Builds a NetworkX schema graph from metadata. |
| `propagate_relevance(...)` | Applies RBP scoring over the schema graph. |

### 6.3 How RBP Works

1. Start with dense retrieval scores from the embedding retriever.
2. Build a table-level schema graph from metadata relationships.
3. Compute retrieval entropy:
   - low entropy means the retriever is confident;
   - high entropy means uncertainty and graph propagation should matter more.
4. Choose dynamic alpha:
   - higher alpha keeps dense retrieval dominant;
   - lower alpha allows more propagation through graph neighbors.
5. Propagate table relevance through graph connectivity.
6. Merge propagated table scores with original column-level similarity scores.
7. Return reranked schema elements to the completion/generation stages.

### 6.4 Ablation Hooks

`run/retrieve_topk_schema.py` exposes:

| Flag / Environment | Effect |
|---|---|
| `--no_rbp` / `ABLATION_NO_RBP=1` | Skip graph propagation and use raw cosine similarity. |
| `--rbp_alpha` / `ABLATION_RBP_ALPHA` | Override RBP alpha for hyperparameter experiments. |

### 6.5 Verified Ablation Result

Local ablation summary:

| Variant | Result | Total Tokens | Avg Tokens / Query |
|---|---:|---:|---:|
| `w/o RBP` | 4 / 178, score 0.0225 | 17,418,471 | 217,730 |

Interpretation:

- In the available local run, removing RBP caused severe accuracy collapse.
- This supports RBP as a major architecture component.

---

## 7. SlayQL-Lite Component 2: BM25 Value Grounding

**Files**:

- `run/build_value_indices.py`
- `run/value_grounder.py`
- integrations in `run/complete_schema.py` and `run/sql_generation.py`

### 7.1 Problem Addressed

Text-to-SQL often fails when the question contains literal entities or phrases whose correct database column is ambiguous. Dense schema retrieval is based on metadata text, not actual cell values. BM25 value grounding was added to map query literals to real cell values/columns.

### 7.2 Index Building

**File**: `run/build_value_indices.py`

Key functions:

| Function | Purpose |
|---|---|
| `extract_and_build(corpus, mapping, db_id)` | Builds a BM25 index and stores mapping metadata. |
| `build_sqlite(db_path, db_name)` | Extracts SQLite table values and builds per-database BM25 index. |
| `build_bigquery(db_name, bq_client)` | Samples/collects values for BigQuery-backed databases. |
| `build_snowflake(db_name, sf_conn)` | Samples/collects values for Snowflake-backed databases. |
| `build_all_indices(data_file)` | Builds all needed indices for a dataset. |

Index outputs:

```text
run/bm25_indices/{db_id}_bm25.pkl
```

Empty/failed cases may be marked with small sentinel files.

### 7.3 Value Hint Retrieval

**File**: `run/value_grounder.py`

Key constants and functions:

| Item | Purpose |
|---|---|
| `MAX_HINTS_PER_PROMPT = 3` | Hard cap for injected hints. |
| `extract_literals(query)` | Extracts query literals/entities while filtering bad candidates. |
| `build_db_value_index(...)` | Builds one database-level value index. |
| `get_value_hints(...)` | Retrieves BM25-matched value hints for a question/database. |

Implementation details:

1. Extract quoted strings and likely named entities.
2. Remove stop words, SQL structural words, and short/noisy tokens.
3. Ignore many low-information numeric strings.
4. Load the per-database BM25 pickle.
5. Score each literal against indexed column values.
6. Apply an exact-match bonus when the retrieved value exactly matches the literal.
7. Emit at most 3 hints.

Example hint shape:

```text
[VALUE HINTS — use these to verify column/value existence]
literal -> database.table.column contains matching value
```

### 7.4 Integration Points

`run/complete_schema.py`:

- Injects value hints into schema-completion prompts unless `ABLATION_NO_BM25=1`.

`run/sql_generation.py`:

- Can add value hints during SQL generation.
- Exposes `--no_bm25` for ablations.

### 7.5 Verified Ablation Result

Local ablation summary:

| Variant | Result | Total Tokens | Avg Tokens / Query |
|---|---:|---:|---:|
| `w/o BM25` | 3 / 178, score 0.0169 | 5,652,427 | 171,285 |

Interpretation:

- In the available local run, removing BM25 value hints caused severe accuracy collapse.
- The token values above are from the local `eval_result.txt`, not from older narrative reports.

---

## 8. SlayQL-Lite Component 3: IT-EE / Dynamic Budgeting

**Files**:

- `run/it_ee.py`
- integration in `run/retrieve_topk_schema.py`
- comments and behavior in `run/complete_schema.py`

### 8.1 Problem Addressed

The baseline agentic schema completion loop can spend a fixed number of turns even when the schema is already sufficient. IT-EE was introduced to reduce unnecessary exploration and manage token cost.

### 8.2 Implementation

`run/it_ee.py` includes:

| Function | Purpose |
|---|---|
| `analyze_complexity(query)` | Heuristically detects query complexity. |
| `calculate_retrieval_entropy(similarities, temp)` | Computes entropy over retrieval scores. |
| `determine_budget(...)` | Determines dynamic turn budget and early-exit metadata. |

The intended design:

- easy/low-complexity queries should use lower exploration budget;
- complex/multi-hop queries should retain more budget;
- entropy and query complexity should influence the turn cap.

### 8.3 Important Code-State Caveat

The current `run/it_ee.py` comments describe a "Safe Exit" refactor where `should_early_exit` is forced to `False`. Therefore:

- the design intention is dynamic early exit;
- the current implementation should not be described as always actively exiting early;
- briefing materials should state this caveat.

`run/retrieve_topk_schema.py` still stores `should_early_exit` and `dynamic_t_max` metadata in retrieval caches/status.

### 8.4 Verified Ablation Result

Local ablation summary:

| Variant | Result | Total Tokens | Avg Tokens / Query |
|---|---:|---:|---:|
| `w/o IT-EE` | 78 / 168, score 0.4643 | 20,473,386 | 189,568 |

Interpretation:

- Accuracy did not collapse in the available `w/o IT-EE` run.
- Average token usage is high.
- The repository does not currently contain a complete full-run token summary that independently proves an exact `~60%` token-saving number.

---

## 9. SlayQL-Lite Component 4: QOC Strict Output Contracts

**Files**:

- `run/sql_generation.py`
- prompt strings in `run/config.py`

### 9.1 Problem Addressed

LLM SQL output may include prose, malformed code blocks, or incomplete snippets. SQL parsers and execution steps require extractable SQL. QOC was introduced to make the model output fenced SQL more consistently.

### 9.2 Implementation

The SQL generation prompt asks for output in fenced SQL blocks:

```text
```sql
SELECT ...
```
```

`run/sql_generation.py` then extracts SQL using regex patterns that search for SQL code fences.

### 9.3 Ablation Hook

`run/sql_generation.py` supports:

| Flag / Environment | Effect |
|---|---|
| `--no_qoc` / `ABLATION_NO_QOC=1` | Strip strict SQL-code-fence output instructions from prompts. |

### 9.4 Verified Ablation State

Local ablation summary:

| Variant | Result | Token Parse |
|---|---:|---|
| `w/o QOC` | 23 / 66 partial/incomplete | token parser found 0 token records |

Interpretation:

- The run is incomplete.
- The 23/66 result should not be used as a final paper result.
- QOC should be described as improving parseability, not as an absolute guarantee that parser failures are impossible.

---

## 10. Schema Retrieval and Completion Implementation

### 10.1 Retrieval

**File**: `run/retrieve_topk_schema.py`

Core responsibilities:

1. Load the proper document/embedding set for a database.
2. Run dense retrieval over schema document embeddings.
3. Apply optional graph-aware RBP propagation.
4. Compute complexity/entropy metadata for IT-EE.
5. Cache instance-level retrieval outputs and status.
6. Provide additional retrieval for agentic schema exploration.

Key functions:

| Function | Purpose |
|---|---|
| `get_or_build_schema_graph(db_name, embed_path)` | Loads or builds graph structure for a database. |
| `compute_graph_penalized_score(...)` | Applies shortest-path penalty logic. |
| `_retrieve_with_device_filtered(...)` | Dense retrieval execution with device filtering. |
| `load_instance_cache(...)` / `save_instance_cache(...)` | Per-instance retrieval cache. |
| `get_next_k_results(...)` | Main retrieval entry for top-k schema elements. |
| `retrieve_additional(...)` | Retrieval of extra columns/tables requested later. |
| `retrieve(...)` | Batch retrieval driver. |

Implementation hooks:

- `--no_rbp`
- `--rbp_alpha`
- `--no_itee`

### 10.2 Schema Completion

**File**: `run/complete_schema.py`

Core responsibilities:

1. Load dataset instances.
2. Load provider-specific documents and dialect instructions.
3. Build initial schema context.
4. Inject BM25 value hints when available.
5. Run LLM-guided schema exploration.
6. Execute lightweight SQL probes if needed.
7. Back up and restore per-instance state for resumability.
8. Write final schema-completion artifacts.

Key functions:

| Function | Purpose |
|---|---|
| `get_least_used_credential()` | Rotates BigQuery credentials by usage count. |
| `backup_instance_state(...)` | Saves per-instance state before risky operations. |
| `restore_instance_state(...)` | Restores failed/interrupted instance state. |
| `thread_safe_sql_execution(...)` | Serializes execution calls where needed. |
| `sql_execution(...)` | Executes SQL against BigQuery/Snowflake/SQLite. |
| `remove_column_values(...)` | Removes values from schema text where needed to reduce prompt size/noise. |
| `process_instance_batch(...)` | Handles completion for a batch of tasks. |
| `complete_schema(...)` | Main batch entry point. |

Provider handling:

- BigQuery:
  - uses `google.cloud.bigquery`;
  - rotates credentials from `run/bigquery_credentials/`;
  - retries with alternate credentials on quota failures.
- Snowflake:
  - uses `snowflake.connector`;
  - loads `run/snowflake_credential/snowflake_credential.json`.
- SQLite:
  - uses local database files under the resource directory.

---

## 11. SQL Generation, Revision, and Selection

### 11.1 SQL Generation

**File**: `run/sql_generation.py`

Core responsibilities:

1. Load final schema prompts and dataset questions.
2. Build SQL-generation prompts with dialect instructions.
3. Generate multiple SQL candidates per instance.
4. Inject BM25 hints unless disabled.
5. Enforce or ablate QOC.
6. Retry on transient API/content failures.
7. Save SQL files in expected downstream layout.
8. Record failed tasks for rerun.

Important classes/functions:

| Item | Purpose |
|---|---|
| `Config` | Holds default retry and worker configuration. |
| `TaskGenerationError` | Explicit exception for generation failures. |
| `DataLoader` | Loads input data/schema artifacts. |
| `retry_delay(attempt)` | Exponential backoff/jitter delay calculation. |
| `SQLGenerator` | Main SQL generation client wrapper. |
| `collect_tasks(...)` | Builds candidate-generation task list. |
| `run_task(...)` | Runs one candidate generation task. |
| `run_batch(...)` | Runs a batch with concurrency and retry handling. |
| `save_failed_tasks(...)` | Writes `sql_gen_failed_tasks.json`. |
| `sql_clean(...)` | Extracts and writes clean SQL from model output. |

Robustness additions:

- `--max_retries`, default 5.
- exponential backoff and jitter.
- failed-task tracking in `sql_gen_failed_tasks.json`.
- rerun pass for failed tasks.
- handling for OpenRouter responses with `content=None`.

### 11.2 SQL Revision

**File**: `run/sql_revise.py`

Core responsibilities:

1. Execute candidate SQL.
2. Capture errors or bad results.
3. Ask LLM to revise failed SQL.
4. Re-execute revised SQL.
5. Save revised SQL and result/error artifacts.

Key functions/classes:

| Item | Purpose |
|---|---|
| `query_sqlite(...)` | Executes SQLite SQL. |
| `query_snowflake(...)` | Executes Snowflake SQL. |
| `query_bigquery(...)` | Executes BigQuery SQL with credential retry. |
| `execute_sql(...)` | Provider routing and timeout handling. |
| `thread_safe_sql_execution(...)` | Thread-safe execution wrapper. |
| `SQLReviser` | LLM-based SQL revision loop. |
| `collect_tasks(...)` | Finds SQL candidates requiring revision. |
| `run_task(...)` | Revises one SQL task. |

### 11.3 SQL Selection

**File**: `run/sql_selection.py`

Core responsibilities:

1. Read SQL candidates and execution CSV/error outputs.
2. Cluster candidates by equivalent execution result.
3. Select majority/consistent cluster where possible.
4. Use model voting for tied clusters.
5. Write final selected SQL/result/error artifacts.

Key functions:

| Function | Purpose |
|---|---|
| `read_sql(...)` | Reads SQL safely; returns `None` if missing/bad. |
| `read_csv_safe(...)` | Reads result CSV safely. |
| `build_candidates(...)` | Builds candidate objects from files. |
| `compare_pandas_table(...)` | Compares result tables. |
| `cluster_by_execution(...)` | Groups candidates by execution equivalence. |
| `select_by_consistency(...)` | Selects strongest cluster by consistency. |
| `model_vote(...)` | Pairwise model voting for ties. |
| `dump_final_selection(...)` | Writes final selected output. |
| `process_instance(...)` | Selects one instance. |

Robustness additions:

- handles missing SQL files;
- handles `None` model-vote content;
- avoids crashing when selected SQL is missing;
- supports `--workers`;
- supports `--data_file`.

---

## 12. SGSA Experiment on `slayql-2`

**Branch**: `slayql-2`  
**Commit**: `b015e42`  
**Important correction**: SGSA means **Self-Generated Semantic Assertions**.

The branch introduced semantic validation, not graph pruning.

Files on branch:

- `run/semantic_validator.py`
- `run/test_semantic_validator.py`
- `run/sql_execution.py`
- `run/sql_generation.py`
- `run/sql_revise.py`

Implementation idea:

1. Ask the model to generate semantic assertions alongside SQL.
2. Parse assertions from model output.
3. Execute SQL.
4. Validate the resulting DataFrame against assertions.
5. If validation fails, feed semantic errors into revision.

Committed result artifacts on that branch:

| Artifact | Baseline | SGSA variant |
|---|---:|---:|
| `run/comparison_report_v2.md` at `b015e42` | 67 / 178 | 27 / 178 |
| `run/csv_only_comparison_report_v2.md` at `b015e42` | 67 / 178 | 27 / 178 |

Conclusion:

- SGSA degraded accuracy in the committed v2 reports.
- Do not describe the failure as Steiner-tree pruning or over-pruning unless new evidence is added.

---

## 13. Evaluation and Reporting Stack

### 13.1 External Evaluation Suite

The README now correctly states that `evaluation_suite/` is an external/sibling evaluation resource. The repo contains wrappers that call:

```text
../evaluation_suite/evaluate.py
```

This means the repo alone may not be sufficient to rerun official evaluation unless the sibling evaluation suite and gold files are available.

### 13.2 Subset Evaluation Wrapper

**File**: `run/evaluate_subset.py`

Responsibilities:

- extract deterministic subsets;
- run configured pipeline variants;
- skip cached stages;
- call the external evaluator;
- compute metrics;
- render comparative dashboard matrices.

### 13.3 SQL and CSV Comparison Reports

**Files**:

- `run/generate_comparison.py`
- `run/generate_csv_comparison.py`

Responsibilities:

- load correct IDs from evaluation outputs;
- read selected SQL;
- read generated result CSVs;
- read gold CSVs;
- generate Markdown reports with:
  - summary metrics;
  - improved/degraded/both-correct/both-wrong categories;
  - instance-level SQL and result comparisons.

Current artifacts:

| Artifact | Baseline | SlayQL | Notes |
|---|---:|---:|---|
| `run/comparison_report.md` | 71 / 178 | 72 / 178 | Main SQL side-by-side report currently used in README. |
| `run/csv_only_comparison_report.md` | 67 / 178 | 72 / 178 | CSV-only comparison; baseline differs. |
| `run/comparison_report_autolink.md` | 6 / 178 | 18 / 178 | Different/incomplete context; do not use as headline without explanation. |

### 13.4 Ablation Report Generator

**File**: `run/generate_ablation_report.py`

Capabilities:

1. Parse `eval_result.txt`.
2. Parse token metrics:
   - total input tokens;
   - total output tokens;
   - total tokens used;
   - average tokens/query.
3. Generate Markdown reports for:
   - component dropout;
   - scalability;
   - IT-EE hyperparameter sensitivity;
   - RBP alpha sensitivity;
   - combined hyperparameter analysis;
   - model-agnostic tests.
4. Handle multiple encodings including UTF-8 and UTF-16 variants.

---

## 14. Ablation Work Summary

### 14.1 Component Dropout

The current local ablation evidence is:

| Variant | Accuracy Result | Total Tokens | Avg Tokens / Query | Status |
|---|---:|---:|---:|---|
| Full SlayQL-Lite | 72 / 178 in comparison artifacts | not reproducible from current `ablation1_full_slayql` dir | not reproducible | Accuracy supported; full token summary missing locally. |
| `w/o RBP` | 4 / 178 | 17,418,471 | 217,730 | Complete local summary exists. |
| `w/o BM25` | 3 / 178 | 5,652,427 | 171,285 | Complete local summary exists. |
| `w/o IT-EE` | 78 / 168 | 20,473,386 | 189,568 | Complete local summary exists for 168 evaluated outputs. |
| `w/o QOC` | 23 / 66 | 0 parsed | 0 parsed | Incomplete; not final. |

Interpretation:

- RBP and BM25 appear critical in the available local ablations.
- IT-EE is mainly an efficiency/budget-control component; current evidence does not prove an exact full-run savings percentage.
- QOC still needs a completed run before final claims can be made.

### 14.2 Other Ablation Scripts

Scripts exist for:

| Script | Purpose | Status |
|---|---|---|
| `ablation2_scalability.sh` | Token cost vs. query complexity buckets. | Bash script exists. |
| `ablation3_hyperparameter.sh` | IT-EE threshold and RBP alpha sweep. | Bash script exists. |
| `ablation4_model_agnostic.sh` | Strong/weak model matrix. | Bash script exists. |

Windows `.ps1` ports currently exist for Ablation 1 and smoke/baseline operations, not all later ablations.

---

## 15. Automation and Operational Work

### 15.1 Baseline Runners

| Script | Purpose |
|---|---|
| `run/run_autolink_baseline.ps1` | Windows baseline pipeline runner. |
| `run/run_autolink_baseline.sh` | Bash baseline pipeline runner. |

### 15.2 Ablation 1 Runners

| Script | Purpose |
|---|---|
| `run/ablation1_component_dropout.ps1` | Windows component-dropout runner. |
| `run/ablation1_component_dropout.sh` | Bash component-dropout runner. |
| `run/ablation1_fix_failed.ps1` | Windows resume/fix script for failed/incomplete ablation work. |
| `run/ablation_smoke_test.ps1` | Small quick sanity test. |

### 15.3 Resume and Checkpointing

Operational handoff notes describe:

- `.pipeline_ckpt` checkpoint files;
- stage-skipping when outputs already exist;
- rerun logic for failed SQL generation tasks;
- careful Windows process management because killing a terminal may not kill Python child processes.

### 15.4 Environment Assumptions

Expected environment:

- Python 3.11
- BigQuery credentials under `run/bigquery_credentials/`
- Snowflake credentials under `run/snowflake_credential/`
- SQLite databases under `run/resource/databases/spider2-localdb/`
- `.env` in `run/` with API credentials/model config
- external/sibling `evaluation_suite/`

Dependencies listed in `requirements.txt`:

```text
faiss-cpu
tqdm
sentence_transformers
openai
snowflake
pandas
google-cloud-bigquery
db-dtypes
func_timeout
```

Additional practical dependency from current code:

```text
rank_bm25
```

`rank_bm25` is imported by `value_grounder.py` and `build_value_indices.py`, so it should be included in environment setup if not already installed.

---

## 16. Implementation Details by File

### 16.1 `run/config.py`

Role:

- Central prompt and dialect configuration.
- Contains BigQuery and Snowflake SQL guidance.
- Contains SQL generation and revision prompt strings.
- Holds output-format instructions that QOC uses/ablates.

Important:

- Prompt changes directly affect output parseability and SQL style.
- The `--no_qoc` ablation works by stripping strict SQL-fence instructions from generation prompts.

### 16.2 `run/generate_schema.py`

Role:

- Converts retrieved and completed schema metadata into final schema prompt text.
- Contains utilities for robust JSON handling and malformed JSON repair.
- Truncates long values/nested structures to keep prompts manageable.

Important functions:

- `extract_description`
- `get_parentheses_content`
- `long_value`
- `truncate_nested_dict`
- `process_values`
- `safe_json_loads`
- `generate_schema_prompt`

### 16.3 `run/mcp_tools.py`

Role:

- Provides tool-like helper functions for schema/data exploration.

Important functions:

- `lookup_business_term`
- `dry_run_query`
- `get_shortest_join_path`
- `profile_column_values`
- `execute_tool_call`

These functions support exploration-style prompts and are especially relevant for BigQuery dry-run validation and column profiling.

### 16.4 `run/sql_execution.py`

Role:

- Shared SQL execution utilities.
- Provides credential rotation and provider-specific execution support.

Current caveat:

- SGSA-specific `semantic_validator.py` is not present in current `main`; it is on the `slayql-2` branch.

### 16.5 `run/parse_tokens.py`

Role:

- Parse token consumption metrics from logs.
- Used to append/report token totals for ablation summaries.

### 16.6 `run/test_bq_credentials.py`, `run/test_connections.py`, `test.py`

Role:

- Sanity-check external connections.
- Useful before running expensive pipeline stages.

---

## 17. Results and Evidence Map

### 17.1 Main Comparison Evidence

| Evidence File | What It Shows |
|---|---|
| `run/comparison_report.md` | Baseline 71/178, SlayQL 72/178, 16 improved, 15 degraded, 56 both correct, 91 both incorrect. |
| `run/csv_only_comparison_report.md` | Baseline 67/178, SlayQL 72/178, 14 improved, 9 degraded, 58 both correct, 97 both incorrect. |
| `run/comparison_report_autolink.md` | Baseline 6/178, SlayQL 18/178, likely different/incomplete context. |

### 17.2 Branch Experiment Evidence

| Branch | Evidence | Result |
|---|---|---|
| `slayql-2` | `run/comparison_report_v2.md` at commit `b015e42` | SGSA variant 27/178 vs baseline 67/178. |
| `slayql-2` | `run/csv_only_comparison_report_v2.md` at commit `b015e42` | SGSA variant 27/178 vs baseline 67/178. |

### 17.3 Ablation Evidence

| Variant | Evidence File |
|---|---|
| `w/o RBP` | `run/ablation1_no_rbp/eval_result.txt` |
| `w/o BM25` | `run/ablation1_no_bm25/ablation1_no_bm25/eval_result.txt` |
| `w/o IT-EE` | `run/ablation1_no_itee/ablation1_no_itee/eval_result.txt` |
| `w/o QOC` | `run/ablation1_no_qoc/ablation1_no_qoc/eval_result.txt` |

---

## 18. What Was Actually Built

This section summarizes the actual engineering output in plain terms.

### 18.1 Baseline Reproduction and Evaluation

Built/maintained:

- baseline AutoLink runner scripts;
- dataset subset files;
- baseline result artifacts;
- side-by-side comparison tools;
- external evaluator wrapper.

Outcome:

- The project can compare AutoLink-style baseline output against SlayQL output on the 178-instance local subset.

### 18.2 Retrieval Improvements

Built:

- dense retrieval with BGE/FAISS;
- graph-aware RBP reranking;
- entropy-aware alpha logic;
- ablation flags for disabling RBP and overriding alpha;
- retrieval caches and status files.

Outcome:

- Retrieval is no longer purely independent column cosine similarity.

### 18.3 Value Grounding

Built:

- BM25 cell-value indexing;
- literal/entity extraction;
- stop-word and noisy-token filtering;
- exact-match value hints;
- prompt hint cap;
- ablation flag for disabling BM25.

Outcome:

- Questions containing real values can inject concrete column/value hints into schema completion and SQL generation.

### 18.4 SQL Robustness

Built:

- strict SQL code-fence prompt instructions;
- SQL extraction/cleaning;
- retry engine;
- failed-task tracking;
- rerun pass for failed generation;
- missing-file and `None` response handling in selection.

Outcome:

- Long batch runs are more resilient to API instability and malformed model responses.

### 18.5 Multi-Provider Execution

Built:

- BigQuery execution with credential rotation and quota fallback;
- Snowflake connector path;
- SQLite local execution;
- dataframe comparison and selection based on execution outputs.

Outcome:

- The same pipeline can target heterogeneous Spider 2.0-Lite database environments.

### 18.6 Ablation Infrastructure

Built:

- component dropout runner;
- no-RBP, no-BM25, no-ITEE, no-QOC toggles;
- ablation report generator;
- token parser;
- smoke test runner;
- scripts for scalability/hyperparameter/model-agnostic studies.

Outcome:

- The project can quantify module contributions, though some ablations remain incomplete or not fully reproducible from current local artifacts.

---

## 19. Known Caveats and Risks

### 19.1 Result Ambiguity

There are multiple result artifacts with different baseline numbers. Always cite the exact artifact:

- `run/comparison_report.md`
- `run/csv_only_comparison_report.md`
- `run/comparison_report_autolink.md`

Do not state "the baseline is X" without naming the artifact.

### 19.2 Full Token Summary Missing

The current `run/ablation1_full_slayql` directory does not contain a reproducible full `eval_result.txt`. Therefore:

- do not claim exact full-run token totals unless the source artifact is restored;
- do not claim exact `~60%` token savings as independently verified by current local files.

### 19.3 `w/o QOC` Incomplete

The `w/o QOC` ablation only has a partial 23/66 result and 0 parsed token metrics. It should not be presented as final.

### 19.4 External Evaluation Suite

The official evaluator is expected outside this repo as `../evaluation_suite/evaluate.py`. Anyone reproducing results needs that sibling directory and gold files.

### 19.5 SGSA Misinterpretation Risk

`slayql-2` must be described as semantic assertions, not subgraph pruning.

### 19.6 Encoding Issues in Existing Reports

Some generated Markdown/log files contain mojibake or PowerShell encoding artifacts. The ablation report generator includes multi-encoding handling, but presentation-ready reports may need cleanup.

---

## 20. How to Brief Others

Use this concise explanation:

> This repo started as an AutoLink baseline for large-scale Text-to-SQL schema linking. We extended it into SlayQL-Lite by adding graph-aware schema propagation, BM25 cell-value grounding, dynamic budget/IT-EE logic, stricter SQL output contracts, resilient SQL generation/retry handling, and ablation/reporting infrastructure. The current local evidence shows SlayQL-Lite reaches 72/178 on the 178-instance Spider 2.0-Lite subset. Depending on the comparison artifact, the baseline is either 71/178 or 67/178, so result claims must cite the exact artifact. RBP and BM25 ablations collapse strongly in the available local runs, supporting them as core components. The `slayql-2` branch was a semantic-assertion experiment that regressed to 27/178 and should not be described as Steiner pruning.

### Recommended Technical Talking Points

1. **Why AutoLink needed extension**:
   - dense retrieval misses join bridges;
   - metadata retrieval does not ground values;
   - fixed exploration budgets waste tokens;
   - model output formatting can break parsers.

2. **What SlayQL-Lite adds**:
   - graph propagation for join-aware schema linking;
   - BM25 value hints from real database contents;
   - dynamic budget metadata for schema exploration;
   - strict output contracts for cleaner SQL extraction;
   - robust retry and failed-task tracking.

3. **How it is implemented**:
   - BGE + FAISS for dense retrieval;
   - NetworkX graph propagation over schema metadata;
   - `rank_bm25` indices over sampled/available cell values;
   - OpenAI/OpenRouter-style chat calls for schema completion, SQL generation, revision, and selection;
   - BigQuery/Snowflake/SQLite execution backends;
   - Markdown report generators and ablation parsers.

4. **What results show**:
   - main artifact: 72/178 vs 71/178;
   - CSV-only artifact: 72/178 vs 67/178;
   - RBP and BM25 are critical in local ablations;
   - IT-EE needs careful framing as efficiency-oriented;
   - QOC ablation is incomplete.

5. **What remains**:
   - finish or rerun `w/o QOC`;
   - restore/generate complete full-run token summary;
   - decide official benchmark artifact;
   - port Ablations 2-4 to PowerShell if Windows execution is required;
   - clean encoding artifacts before publication.

---

## 21. Suggested Next Actions

| Priority | Action | Reason |
|---:|---|---|
| 1 | Decide official benchmark artifact (`comparison_report.md` vs `csv_only_comparison_report.md`). | Prevent conflicting headline claims. |
| 2 | Regenerate/restore full SlayQL-Lite `eval_result.txt` with token metrics. | Needed for defensible token-efficiency claims. |
| 3 | Complete `w/o QOC` ablation. | Current result is partial and should not be final. |
| 4 | Add `rank_bm25` to `requirements.txt` if environment setup should be complete. | Current code imports it but requirements do not list it. |
| 5 | Clean old `PROJECT_EVOLUTION_REPORT.md` or point readers to the accurate report. | Prevent propagation of known Git-history errors. |
| 6 | Add PowerShell ports for Ablations 2-4 if Windows is the primary environment. | Current handoff indicates Windows usage; later ablations are Bash-only. |
| 7 | Normalize encoding in reports/logs intended for submission. | Existing Markdown has mojibake artifacts. |

---

## 22. Appendix: Important Commands

### Run Smoke Test

```powershell
cd D:\C-CaSE\run
.\ablation_smoke_test.ps1
```

### Run Baseline

```powershell
cd D:\C-CaSE\run
.\run_autolink_baseline.ps1
```

### Run Ablation 1

```powershell
cd D:\C-CaSE\run
.\ablation1_component_dropout.ps1
```

### Generate Ablation Report

```powershell
cd D:\C-CaSE\run
python generate_ablation_report.py `
  --ablation_type component_dropout `
  --data_file subset_diverse_20_evaluation.json `
  --task r1_lite `
  --variants `
    "Full SlayQL:log_subset_diverse_20_evaluation_slayql_ccase" `
    "w/o IT-EE:ablation1_no_itee" `
    "w/o RBP:ablation1_no_rbp" `
    "w/o BM25:ablation1_no_bm25" `
    "w/o QOC:ablation1_no_qoc" `
  --output_path ablation1_component_dropout_report.md
```

### Run External Evaluation

This assumes `evaluation_suite/` exists as a sibling/external directory.

```powershell
python evaluation_suite/evaluate.py `
  --result_dir run/log_subset_diverse_20_evaluation_slayql_ccase/sql_selection/final `
  --mode exec_result `
  --gold_dir evaluation_suite/gold `
  --data_file run/subset_diverse_20_evaluation.json
```

---

## 23. Final Briefing Conclusion

The work in this repository is a substantial engineering and research extension of AutoLink into SlayQL-Lite. The main technical contribution is not one single algorithm but an integrated system:

- dense schema retrieval remains the baseline;
- RBP adds graph-aware join propagation;
- BM25 adds real value grounding;
- IT-EE introduces budget-control logic, with a current safe-exit implementation caveat;
- QOC and retry logic make SQL generation/selection more robust;
- multi-provider execution and reporting scripts make results inspectable;
- ablation scripts make component-level analysis possible.

The repo is suitable for briefing as a working research prototype with strong implementation coverage and meaningful local evidence. It should not be briefed as a fully finalized benchmark package until the result-source ambiguity, missing full token summary, and incomplete `w/o QOC` ablation are resolved.


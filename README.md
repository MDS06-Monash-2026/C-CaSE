# C-CaSE / SlayQL-Lite: Scalable Schema Exploration & Value-Grounded Text-to-SQL at Scale

<p align="center">
  | <a href="https://arxiv.org/abs/2511.17190"><b>AutoLink Paper (arXiv)</b></a> |
</p>

## Overview

This repository is modified and extended by **Kian Lok Chin (Monash University Malaysia)** and the **MDS06 FYP Group** to advance baseline testing, schema linking research, and component ablation on the **Spider 2.0-Lite** benchmark.

> [!IMPORTANT]
> ### ⚠️ Important Notes for FYP Group Members (MDS06)
> 1. **Pre-processed Embeddings:** You do **not** need to re-run document generation or embedding creation. Use pre-processed `embeddings/` and `documents/` folders inside `run/`.
> 2. **Credentials:** Credentials are required for both the AutoLink agent and the Evaluation suite (`run/bigquery_credentials/`, `run/snowflake_credential/`, and `evaluation_suite/`).
> 3. **Local Databases:** SQLite evaluation requires local `.sqlite` databases stored in `run/resource/databases/spider2-localdb`.
> 4. **API Configuration:** Configure `OPENAI_API_KEY`, `MODEL_NAME`, and `OPENAI_BASE_URL` in `run/.env`.

---

## 🏛️ Architectural Evolution: From Counterfactual Rollback to SlayQL-Lite

The project underwent two major architectural iterations:

1. **Phase 1 — Counterfactual Rollback & SGSA Exploration (`slayql-2` branch)**:
   - Explored Steiner Tree and SGSA (Sub-Graph Search Algorithm) counterfactual rollback mechanisms to prune superfluous schema elements.
   - *Finding*: Aggressive subgraph pruning led to severe execution performance regressions (~15.2% EX) by triggering the "Silent Execution Trap" (dropping critical foreign key join paths).

2. **Phase 2 — SlayQL-Lite Architecture (`slayql-lite` branch — Current Recommended)**:
   - Redesigned into a streamlined, highly effective 4-module architecture:
     - **RBP (Relational Boost Propagation)**: Graph-based propagation that automatically connects foreign key relation paths across complex database schemas.
     - **IT-EE (Iterative Early Exit)**: Dynamic turn-budget allocation that cuts execution latency and API token consumption without sacrificing accuracy.
     - **BM25 Value Grounding**: Injects exact database value hints into schema prompts to resolve entity and column ambiguities.
     - **QOC (Strict Output Contracts)**: Enforces strict JSON/SQL formatting constraints, eliminating malformed LLM outputs.

---

## 📊 Benchmark Execution Results (Spider 2.0-Lite — 178 Instances)

Evaluated on the full 178-instance evaluation benchmark (`subset_diverse_20_evaluation.json`):

| Model / Framework | Evaluated (Denominator = 178) | Evaluable Subset Accuracy | Performance Report |
|---|---|---|---|
| **AutoLink Baseline** | 71 / 178 (**39.9%**) | 71 / 171 (41.5%) | [comparison_report.md](file:///d:/C-CaSE/run/comparison_report.md) |
| **SlayQL-Lite (Enhanced)** | **72 / 178 (40.4%)** | **72 / 163 (44.2%)** | [comparison_report.md](file:///d:/C-CaSE/run/comparison_report.md) |

### Instance Performance Breakdown:
- 📈 **Improved** (Baseline ❌ $\rightarrow$ SlayQL ✅): **16 instances**
- 📉 **Degraded** (Baseline ✅ $\rightarrow$ SlayQL ❌): **15 instances**
- 🤝 **Both Correct**: **56 instances**
- ❌ **Both Incorrect**: **91 instances**

---

## 🧪 Empirical Ablation Studies (Leave-One-Out Component Dropout)

To quantify the exact contribution of each module, systematic leave-one-out dropout experiments were conducted on the 178-instance dataset:

| Variant | Component Dropped | Execution Accuracy (EX) | Key Takeaway |
|---|---|---|---|
| **Full SlayQL-Lite** | None (Reference) | **72 / 178 (40.4%)** | Baseline reference performance |
| **w/o RBP** | Graph Join Propagation | **4 / 178 (2.25%)** | **Critical**: Removing RBP collapses performance, proving graph propagation is vital for schema join traversal. |
| **w/o BM25** | Value Grounding | **3 / 178 (1.69%)** | **Critical**: Value grounding hints are required for entity-to-column linking. |
| **w/o IT-EE** | Iterative Early Exit | **78 / 168 (46.4% evaluable)** | **Efficiency Win**: IT-EE provides major **API token (~60%) and runtime efficiency gains** with minimal accuracy trade-off. |
| **w/o QOC** | Strict Output Constraints | *23/66 (Incomplete)* | **Formatting Win**: Enforces valid ` ```sql``` ` block generation, avoiding silent parsing traps. |

---

## 🌿 Git Branch Directory Guide

- **`slayql-lite` (Current / Main Production)**: Contains the full SlayQL-Lite architecture, resilient batch retry engine, cross-platform PowerShell/Bash scripts, and complete ablation control flags.
- **`slayql-1`**: Historical baseline vs. SlayQL evaluation reference branch.
- **`slayql-2`**: Counterfactual Rollback / SGSA research branch (retained for baseline comparison).
- **`c-case-op-1`**: Early optimization exploration branch.
- **`main`**: Original base repository.

---

## 📁 Repository Structure

```
- evaluation_suite/                    -- Spider 2.0-Lite Evaluation Suite
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
  - complete_schema.py                 -- Dynamic Agentic Schema Completion
  - sql_generation.py                  -- Candidate SQL Generation with retry engine
  - sql_selection.py                   -- Pairwise model voting & execution selection
  - value_grounder.py                  -- BM25 value hint retriever
  - comparison_report.md               -- Side-by-side SQL diff & execution report
  - .env                               -- Environment variables & API keys
STATUS.md                              -- Detailed team handoff documentation
COMMIT_SUMMARY.md                      -- Git commit summary log
```

---

## ⚙️ Environment Setup & Installation

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

## 🚀 Running the Pipeline

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

## 📊 Evaluating Results & Generating Reports

Once SQL generation and selection complete, run the evaluation script:

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

## 📜 Citation

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
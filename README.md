# AutoLink: Autonomous Schema Exploration and Expansion for Scalable Schema Linking in Text-to-SQL at Scale

<p align="center">
| <a href="https://arxiv.org/abs/2511.17190"><b>arXiv</b></a> |
</p>

## Overview

This repository is modified by **Kian Lok Chin (Monash University Malaysia)** to ease baseline testing and method replication for the MDS06 FYP group.

> [!IMPORTANT]
> ### ⚠️ Important Notes for FYP Group Members (MDS06)
> To save time and avoid configuration issues, please follow these steps:
> 1. **Pre-processed Embeddings:** You do **not** need to run the document generation or embedding scripts. I have already pre-processed these. Contact **Kian Lok** to obtain the `embeddings/` and `documents/` folders to place inside the `run/` directory.
> 2. **Credentials:** You need two sets of credentials (one for the AutoLink agent and one for the Evaluation suite). Contact **Kian Lok** to get the JSON files.
> 3. **Local Databases:** The evaluation requires large `.sqlite` files. Get the `spider2-localdb` zip from **Kian Lok** instead of downloading them from the official repo.
> 4. **Support:** If you face any issues, contact **Kian Lok**.

## Folder Structure  
```
- evaluation_suite/                    -- Spider 2.0-Lite Evaluation Suite
  - gold/                              -- Gold execution results and SQL (DON'T CHANGE)
  - evaluate.py                        -- Main evaluation script
  - bigquery_credential.json            -- Credential for evaluation
  - snowflake_credential.json           -- Credential for evaluation
- run/                                 -- Core logic for AutoLink
  - bigquery_credentials/              -- BigQuery JSON credentials (Agent access)
  - snowflake_credential/              -- Snowflake JSON credentials (Agent access)
  - documents/                         -- Column-level documents [Provided by Kian Lok]
  - embeddings/                        -- Document embeddings [Provided by Kian Lok]
  - resource/                          -- Spider 2.0-Lite resources (DBs, etc.)
  - main.sh                            -- Schema linking entry point
  - sql_gen.sh                         -- SQL generation entry point
  - ...                                -- AutoLink Python scripts
```

## Setting Up Environment
1. **Clone the repository:**
  ```bash
  git clone https://github.com/KLC0317/AutoLink.git
  cd AutoLink
  ```
2. **Create conda environment:**
  ```bash
  conda create -n AutoLink python=3.12
  conda activate AutoLink
  pip install -r requirements.txt
  ```
3. **Configure LLM:**
  Modify `OPENAI_API_KEY`, `MODEL_NAME`, and `OPENAI_BASE_URL` in **both** `run/main.sh` and `run/sql_gen.sh`.

4. **Resource Setup:**
  *   **Local DB:** Unzip and put all `.sqlite` files into `run/resource/databases/spider2-localdb`.
  *   **Credentials:** Place the JSON files provided by Kian Lok into `run/bigquery_credentials/`, `run/snowflake_credential/`, and the root of `evaluation_suite/`.

---

## Running the Code

### 1. Schema Linking
```bash
cd run
bash main.sh
```
This process performs document construction (skipped if pre-processed), initial retrieval, and iterative schema expansion.

### 2. SQL Generation
```bash
bash sql_gen.sh
```
This script generates candidate SQLs, runs self-correction (revision), and selects the final SQL via self-consistency.

---

## Evaluation (Spider 2.0-Lite)

Once the `sql_gen.sh` script completes, it will generate predicted SQL files (typically found in `run/log_path/sql_selection/`). Use the evaluation suite to calculate the execution accuracy.

### Preliminary Setup
Ensure `bigquery_credential.json` and `snowflake_credential.json` are placed inside the `evaluation_suite/` folder.

### Run Evaluation
Navigate to the evaluation directory and point the script to your results:


**Evaluate via CSV Results (if already executed):**
```bash
python evaluation_suite/evaluate.py --result_dir run/log_v3_topn100/sql_selection/final --mode exec_result --gold_dir evaluation_suite/gold
```

*Note: You can test the setup using the `example_submission_folder` provided in the suite.*

---

# Citation
If you find this repo helpful, please cite the original work:
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
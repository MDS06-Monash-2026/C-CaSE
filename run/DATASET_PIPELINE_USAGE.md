# SlayQL v1.1 dataset pipeline

The new entry point keeps every run under a new `run/<run-id>/` directory. It does not write into
`run/log_spider2_full_slayql`, which remains the frozen v1 baseline (251/527 recorded correct,
47.63% over evaluable results).

## Entry points

From the repository root:

```powershell
# Interactive menu with nine standalone dataset/run-size combinations.
.\run\run_dataset_pipeline.ps1

# Explicit command.
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider1 -Split dev -Mode smoke
```

The Python equivalent is:

```powershell
python .\run\dataset_pipeline.py prepare --dataset spider1 --split dev --mode smoke
python .\run\dataset_pipeline.py run --dataset spider1 --split dev --mode smoke
```

`prepare` only validates paths and writes manifests. `run` performs inference and evaluation.
Repeat the same command and run ID to resume; validated completed artifacts are skipped.

## Nine standalone combinations

Each dataset can run independently as `smoke`, `subset20`, or `full`. A standalone 20% or full
run does not require a previous smoke run. The interactive menu exposes all nine combinations:

| Dataset | Smoke | Subset 20 | Full |
|---|---|---|---|
| BIRD | 1 | 2 | 3 |
| Spider 1.0 | 4 | 5 | 6 |
| Spider 2.0-Lite | 7 | 8 | 9 |

Explicit examples:

```powershell
# Any one of these can be run first.
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite -Split dev -Mode smoke
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite -Split dev -Mode subset20
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite -Split dev -Mode full
```

The smoke size remains five by default. Use `-SmokeCount` for a smaller diagnostic smoke.
Backends can be excluded explicitly; both settings are stored in the run manifest and resolved
configuration. For example, this selects three Spider 2.0-Lite instances without Snowflake:

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite -Split dev -Mode smoke `
  -SmokeCount 3 -ExcludeBackend snowflake -RunId spider2_dev_smoke3_no_sf
```

When a backend exclusion is used for smoke mode, selection is round-robin across the remaining
available backends. The example therefore exercises both BigQuery and local SQLite.

Add `-EnforceGates` when a research run must require the original sequence
`smoke -> backend-smoke -> subset20 -> full`:

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider2-lite -Split dev -Mode full -EnforceGates
```

For Spider 2.0-Lite, `subset20` preserves every ID already stored in
`run/subset_diverse_20_evaluation.json`; it does not resample that curated file.
For BIRD and Spider 1.0, `subset20` deterministically selects 20% using the manifest seed.

## BIRD

Every BIRD invocation asks for the dataset directory, lists its immediate contents, and requires
confirmation, even when `-BirdRoot` is supplied or a run is resumed:

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset bird -Split train -Mode smoke -BirdRoot "D:\Downloads\train"
```

The runner recursively resolves `<split>.json`/JSONL, optional gold SQL, and SQLite database files.
The repository-local BIRD dev copy can be selected in the same prompt when running the dev split.

## Spider 1.0

Spider 1.0 is resolved only from `spider_data/spider_data` in this repository:

```powershell
.\run\run_dataset_pipeline.ps1 -Command run -Dataset spider1 -Split dev -Mode smoke
```

## Ablations

The ablation launcher supports `bm25`, `topn`, `candidates`, `rbp`, `itee`, `selector`, `hintcap`,
or `all`. It creates an isolated run and manifest per value, automatically runs all prerequisite
gates up to the requested mode, and writes JSON/Markdown comparisons under `run/ablation_reports/`.

```powershell
# Normalized BM25 thresholds: disabled, .10, .20, .30, .40, .50
.\run\run_ablation.ps1 -Study bm25 -Dataset spider2-lite -Split dev -Mode subset20

# Retrieval depth: 50, 75, 100, 125
.\run\run_ablation.ps1 -Study topn -Dataset spider2-lite -Split dev -Mode subset20

# Other supported examples
.\run\run_ablation.ps1 -Study candidates -Dataset spider1 -Split dev -Mode subset20
.\run\run_ablation.ps1 -Study selector -Dataset bird -Split dev -Mode smoke
```

BM25 traces store the literal, matched field/value, raw and normalized scores, threshold,
exact-match decision, and whether the hint entered the prompt. OpenRouter-compatible response
usage is stored per instance under `usage/` and aggregated only during final evaluation.

## Selector-first and offline replay

The v1.1 selector parses each candidate with SQLGlot and records output grain, projections,
aggregations, grouping, joins, filters, literals, set operations, time constraints, ordering,
limits, `DISTINCT`, and ratio structure. Exact SQL duplicates and equivalent executed results
form one duplicate group, so repetition does not add selector weight. Verification requires both
a close deterministic score and a material structural/result disagreement.

Selection can be replayed against an existing candidate pool without generation or database
execution. Replay writes to a separate directory and disables model verification by default:

```powershell
python .\run\selector_first.py `
  --log_path .\run\log_spider2_full_slayql `
  --data_file .\run\spider2_data.json `
  --num_candidates 5 `
  --offline-replay-output .\run\replay_spider2_v1_1
```

The replay manifest hashes the dataset, available candidate artifacts, selector/evaluator code,
gold assets, Git state, and selector/model configuration. Repeating the command resumes completed
instances. It refuses to continue if the frozen source artifacts or configuration changed.
`--allow-replay-verification` explicitly enables provider calls when a later bounded-verification
experiment is intended.

## Main outputs

Each run contains source/dataset/subset/config manifests, atomic stage and instance checkpoints,
retrieval and candidate artifacts, BM25 traces, selection decisions, provider usage JSONL,
per-instance evaluation records, and `aggregates/summary_metrics.json`. The summary reports
execution accuracy, coverage, SQL exact match, table/column/join schema-linking precision-recall-F1,
strict recall, schema noise, candidate-oracle accuracy, selection regret, provider token usage,
cost, and latency percentiles.

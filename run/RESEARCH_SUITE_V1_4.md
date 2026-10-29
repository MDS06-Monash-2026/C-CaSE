# SlayQL v1.4 Research Suite

v1.4 is a bounded accuracy revision of the v1.3 suite. It keeps the model,
prompt length, turn budget, candidate counts, execution, revision, selector,
evaluation metrics, and checkpoint protocol. The new work is limited to the
failure modes observed in the v1.2/v1.3 subset runs: wrong table/column
grounding, correlated candidates, and noisy value hints.

## What changed

- Query-specific interaction evidence is enabled for v1.4, including a short
  question plan and explicit join-endpoint guidance.
- After final schema completion, `focus_schema.py` keeps the highest-evidence
  tables and columns, always retaining linked join endpoints and key-like
  columns. The stage is deterministic, cached, and checkpointed.
- Retrieval receives a table-balanced precision pass after RBP ordering. It
  understands FAISS distance, similarity, score, and propagated-score fields,
  so the pass is safe across local and Spider2 retrieval artifacts.
- BM25 value grounding rejects strict subphrase matches in v1.4 while still
  admitting exact values. This avoids injecting a plausible value from the
  wrong column; v1.2/v1.3 defaults are unchanged.
- Candidate guidance and selector contract checks explicitly recognize v1.4.
  The five candidate roles and the existing evaluation/selection metrics are
  unchanged.

These changes are deliberately not a claim of a guaranteed target accuracy.
Run the subset and inspect `research_summary.json`, candidate-oracle accuracy,
selection regret, and schema-focus manifests before starting a full run.

## Commands

Run from `D:\SlayQL-v1.1` in PowerShell.

```powershell
# BIRD dev, 20% diverse subset, five candidates
.\C-CaSE\run\run_research_suite_v14.ps1 `
  -Command run -Dataset bird -Split dev -Mode subset20 `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" `
  -RunId v14_bird_dev_subset20 `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\bird_dev_full\aggregates\summary_metrics.json"

# Spider 1.0, three candidates
.\C-CaSE\run\run_research_suite_v14.ps1 `
  -Command run -Dataset spider1 -Split test -Mode subset20 `
  -NumCandidates 3 -RunId v14_spider1_test_subset20

# Spider 2.0-Lite, local + BigQuery only (Snowflake excluded by default)
.\C-CaSE\run\run_research_suite_v14.ps1 `
  -Command run -Dataset spider2-lite -Split test -Mode subset20 `
  -RunId v14_spider2lite_test_subset20
```

After a matching subset is complete, run the full split with the same version
and settings. A full run is gated until its v1.4 subset exists; use
`-SkipSubsetGate` only for an explicit experiment. Rerun the identical command
and run ID after an interruption to resume completed stages and per-instance
artifacts.

## Reading the result

`aggregates/summary_metrics.json` remains the canonical evaluator output.
`research_summary.json` adds target/observed accuracy, candidate-oracle
accuracy, selection regret, usage, and backend exclusions.
`schema_focus_manifest.json` reports selected tables/columns per instance.

The Spider2-Lite summary continues to record the supplied frozen 45.89%
local/BigQuery-only baseline. It does not treat an excluded-Snowflake run as
the complete Spider2 benchmark.

# SlayQL v1.7 Research Suite

SlayQL v1.7 is an API-only extension of v1.6. It does not fine-tune the model or use reinforcement learning. Learning is supplied as training-only prompt demonstrations, while database feedback is used by one selective semantic-repair call.

## Why v1.7 exists

The completed v1.6 BIRD subset reached 130/307 (42.35%) with a 171/307 (55.70%) candidate oracle. The remaining no-oracle failures were concentrated in literal, join, table, ordering, predicate, DISTINCT, aggregation, grouping, and projection mismatches. Schema macro recall was already 99.1%, so adding more schema context was not the primary missing capability.

Two concrete implementation gaps remained:

1. The legacy generation prompt allowed extra output fields and suggested returning both name and ID. This contradicted the v1.6 minimal-projection semantic contract.
2. Execution happened only after all candidates were generated, and revision handled execution errors only. Executable but semantically suspicious SQL received no database-grounded correction.

An offline v1.6 artifact audit found that the v1.7 repair gate selects 62/307 instances (20.2%); 50/62 selected instances were wrong in the completed v1.6 evaluation. Accepted repairs are added as a new candidate and never overwrite the original candidates.

## Architecture

- Training-only prompt learning retrieves two structurally similar examples. It is deterministic, target-overlap checked, and cached per instance. No target `gold_sql` is used.
- Demonstrations are added only to candidates 0 and 2. Other candidates preserve independent route and reasoning diversity.
- Candidate routing, semantic contracts, BM25 value grounding, schema focus, and the full-schema fallback remain from v1.6.
- The generation prompt is corrected only under version 1.7; older run behavior is unchanged.
- Selective semantic revision runs after normal execution-error revision. It triggers only on result disagreement plus material semantic risk, makes at most one API call, executes the proposed SQL, and exposes a validated result as candidate `num_candidates`.
- Selection adds a bounded execution-result consensus signal and retains one evidence-aware verification call for close material disagreements.
- Every prompt-learning and semantic-revision instance has an atomic checkpoint artifact. The model response is cached before repair execution, so an interruption after the API response does not spend the call again.

## BIRD dev subset

Use the BIRD training JSON for prompt learning and the separate BIRD dev directory as the evaluated target:

```powershell
.\C-CaSE\run\run_research_suite_v17.ps1 `
  -Command run -Dataset bird -Split dev -Mode subset20 `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" `
  -DemonstrationFile "D:\Downloads\train\train\train.json" `
  -DemonstrationCount 2 `
  -RunId v17_bird_dev_subset20
```

The loader uses `train_gold.sql` beside `train.json` when SQL is not embedded in the JSON.

## Spider 1.0 subset

Spider 1.0 automatically uses `spider_data/spider_data/train_spider.json` for a dev or test target. Its existing default of three base candidates is preserved.

```powershell
.\C-CaSE\run\run_research_suite_v17.ps1 `
  -Command run -Dataset spider1 -Split dev -Mode subset20 `
  -RunId v17_spider1_dev_subset20
```

## Spider 2.0-Lite subset

No training demonstration source is assumed for Spider 2.0-Lite. Prompt learning records a disabled checkpoint and the remaining v1.7 stages still run. Snowflake remains excluded unless explicitly enabled.

```powershell
.\C-CaSE\run\run_research_suite_v17.ps1 `
  -Command run -Dataset spider2-lite -Split test -Mode subset20 `
  -ExcludeBackend snowflake `
  -RunId v17_spider2lite_test_subset20
```

Re-run the exact same command and run ID to resume. Changing the demonstration file, its contents, count, workers, candidates, seed, or other resolved settings changes the configuration hash and requires a new run ID.

## Outputs

- `prompt_learning/<instance_id>.json`: selected training examples, provenance, and prompt block.
- `semantic_revise/responses/<instance_id>.json`: cached API response for triggered repair.
- `semantic_revise/decisions/<instance_id>.json`: trigger, acceptance, and validation decision.
- `semantic_revise_manifest.json`: total triggered and accepted repairs.
- `selection/<instance_id>.json`: all original candidates plus an accepted semantic candidate.
- `aggregates/summary_metrics.json`: unchanged accuracy, oracle, selection-regret, schema, usage, and cost reporting.

Target accuracies remain research goals, not guaranteed outcomes. The subset result should be compared with v1.6 using the same seed and reference subset before authorizing a full run.

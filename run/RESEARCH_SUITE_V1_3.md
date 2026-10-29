# SlayQL v1.3 Research Suite

v1.3 is a narrow correction to the v1.2 evidence-guided harness. It keeps the
same generation, execution, revision, verification, evaluation, candidate
counts, and checkpoint stages. Run roots and manifests use a distinct
`slayql_v1.3_selective_evidence` version, so old v1.2 results are never mixed
into a v1.3 comparison.

The changes target the observed BIRD gap:

- ordinal and ranking language (`ranked 1st`, `fastest`, `tallest`, and similar)
  now requires ordered SQL and the relevant limit;
- questions asking for a person/entity name are not incorrectly scored as
  scalar aggregates;
- SQLite and cloud interaction evidence uses query-linked fields, a small
  relationship neighborhood, and at most six value probes in the context;
- candidate prompts retain the same five-way role diversity and add a short
  semantic reconciliation check for output columns and ranking.

Recent Text-to-SQL work supports these bounded choices: AutoLink dynamically
expands only linked schema regions, GenLink learns implicit schema relations,
and MCS-SQL combines refined schemas with diverse candidates and confidence
selection. The implementation keeps those ideas deterministic and local to
the existing fixed model-turn budget.

## Subset commands

Run these from `D:\SlayQL-v1.1` in PowerShell. The BIRD root must directly
contain `dev.json` and the corresponding databases.

```powershell
# BIRD dev: five candidates
.\C-CaSE\run\run_research_suite_v13.ps1 `
  -Command run -Dataset bird -Split dev -Mode subset20 `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" `
  -RunId v13_bird_dev_subset20 `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\bird_dev_full\aggregates\summary_metrics.json"

# Spider 1.0: requested three candidates
.\C-CaSE\run\run_research_suite_v13.ps1 `
  -Command run -Dataset spider1 -Split test -Mode subset20 `
  -NumCandidates 3 -RunId v13_spider1_test_subset20

# Spider 2.0-Lite: Snowflake is skipped by default
.\C-CaSE\run\run_research_suite_v13.ps1 `
  -Command run -Dataset spider2-lite -Split test -Mode subset20 `
  -RunId v13_spider2lite_test_subset20
```

Rerun the identical command and run ID after an interruption. The existing
stage and per-instance checkpoints are reused. A full run is accepted only
after the matching v1.3 subset20 run is complete; `-SkipSubsetGate` is an
explicit override.

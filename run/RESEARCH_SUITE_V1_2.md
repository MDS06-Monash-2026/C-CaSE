# SlayQL v1.2 Research Suite

`run_research_suite.ps1` is the reproducible entry point for BIRD, Spider
1.0, and Spider 2.0-Lite. It preserves the v1.1 generation, execution,
revision, selector, and metric artifacts while adding a cached evidence stage,
deterministic subset selection, target reporting, and a full-run gate.

The accuracy-focused changes are intentionally narrow. Interaction evidence is
now injected before schema completion (so the completion agent can use the
relationship/value observations) and appended again to the final generation
prompt. Candidates keep the existing count and turns, but receive deterministic
independent roles: direct schema grounding, join-path verification, filter/value
verification, alternate aggregation, and adversarial semantic review. The v1.2
selector additionally scores candidates against query-linked tables and cached
join edges. These changes target the earlier candidate-oracle, schema-noise,
join, and selection-regret gaps without replacing the v1.1 pipeline.

## Research basis

The evidence-guided design is a deliberately conservative adaptation of recent
agentic Text-to-SQL work: AV-SQL's validated intermediate views, FlexSQL's
flexible schema/value exploration and skills, APEX-SQL's hypothesis checks and
parallel profiling, SQL-Trail's adaptive turn budgeting, and DPC's dual-paradigm
consistency checks. The harness keeps these ideas outside the fixed v1.1 model
turn budget so the comparison remains attributable.

- [AV-SQL (2026)](https://arxiv.org/abs/2604.07041)
- [FlexSQL (2026)](https://arxiv.org/abs/2605.02815)
- [APEX-SQL (2026)](https://arxiv.org/abs/2602.16720)
- [SQL-Trail (ACL 2026)](https://aclanthology.org/2026.acl-long.1677/)
- [DPC (ACL 2026)](https://aclanthology.org/2026.acl-long.313.pdf)

## Recommended sequence

Run a small smoke check first, then the 20% diverse subset, and only then the
full split. The subset uses approximately 20% easy/known-correct examples and
80% harder examples. A reference evaluation can make the easy/hard partition
use measured correctness instead of the difficulty proxy.

```powershell
# BIRD dev (the directory containing dev.json/dev.sql and databases)
.\C-CaSE\run\run_research_suite.ps1 -Command run -Dataset bird -Split dev -Mode smoke `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" -RunId v12_bird_dev_smoke

.\C-CaSE\run\run_research_suite.ps1 -Command run -Dataset bird -Split dev -Mode subset20 `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" -RunId v12_bird_dev_subset20 `
  -ReferenceEvaluation "D:\SlayQL-v1.1\C-CaSE\run\bird_dev_full\aggregates\summary_metrics.json"

.\C-CaSE\run\run_research_suite.ps1 -Command run -Dataset bird -Split dev -Mode full `
  -BirdRoot "D:\SlayQL-v1.1\C-CaSE\dev\dev_20240627" -RunId v12_bird_dev_full
```

For Spider 1.0 use `-Dataset spider1 -Split test` (or `dev` when that split is
available) and pass `-NumCandidates 3` to match the requested comparison. For
Spider 2.0-Lite use `-Dataset spider2-lite`; Snowflake is excluded by default,
so local and BigQuery instances continue while credentials are unavailable.
Use `-AllowSnowflake` only when credentials are restored.

`-Command prepare` creates the normalized dataset and manifests without
starting model inference. `-Mode full` refuses to start until a completed
v1.2 `subset20` run with the same source/configuration is present. The explicit
override is `-SkipSubsetGate`.

## Artifacts and resume behavior

Each run is isolated under `run/<RunId>/`. The existing
`aggregates/summary_metrics.json` remains unchanged. Additional artifacts are:

- `subset_manifest.json`: seed, backend exclusions, selected IDs, and policy.
- `interaction/` and `interaction_context/`: cached database evidence.
- `interaction_manifest.json`: evidence-stage completion record.
- `checkpoints/stages.json`: stage checkpoints used by the v1.1 runner.
- `research_summary.json`: target, observed accuracy, fixed baseline delta,
  candidate oracle, regret, usage, and exclusions.

If a process is interrupted, rerun the same command and `-RunId`; completed
stages and per-instance artifacts are reused. Existing manifests reject changes
to dataset, split, candidates, workers, target, seed, or interaction settings,
which prevents accidental mixing of experiments.

## Spider2 comparison note

When Snowflake is excluded, the research summary records the supplied frozen
45.89% cross-validation baseline as a fixed-denominator comparison. It does not
claim that a local/BigQuery-only run is equivalent to the complete Spider2
benchmark.

# SlayQL v1.2-v1.5 Research Skills

This file is the experiment contract for the evidence-guided harness. It is
deliberately provider-neutral: the existing v1.1 model, prompts, turns, and
evaluation remain the source of truth. v1.3 adds only selective evidence and
ranking/entity contract checks around those same stages. v1.4 adds deterministic
question-grounded schema focus and strict value-hint admission around those
same stages.

v1.5 addresses the measured v1.4 generation-oracle and selection gaps. It adds
relational closure, complementary schema views, semantic-path candidate roles,
and value-aware pairwise selection without changing official evaluation.

## question_contract

- Restate the requested output grain, filters, grouping, ordering, and limit.
- Treat ordinal language (for example, "ranked 1st" or "fastest") as an
  ordering requirement and verify the corresponding limit.
- For entity/name questions, preserve the requested name columns instead of
  collapsing them into an unrelated scalar aggregate.
- Treat literals observed in the interaction evidence as values to verify, not
  as permission to invent a filter.
- Prefer a direct answer over an unnecessary repair or rewrite.

## schema_explorer

- Read the retrieved schema first, then use the cached interaction evidence,
  which is injected before schema completion and retained in the final prompt.
- In v1.3, prioritize fields linked by non-generic question tokens and the
  smallest relevant relationship neighborhood; do not treat every catalog
  edge or sample value as evidence for the query.
- In v1.4, retain linked join endpoints and question-relevant columns after
  completion, but keep a bounded table/column budget. This is a prompt
  precision pass, not a database restriction; the agent can still use its
  normal tools.
- In v1.5, connect question-linked tables with shortest relational paths and
  retain bridge tables plus every join endpoint. The relaxed eight-table focus
  is a recall guard based on v1.4 missing-gold-table failures.
- Reuse admitted BM25 value matches as high-confidence schema seeds. This is a
  deterministic handoff for unquoted entities, not an additional model turn.
- Use declared foreign keys and conservative `_id` links as join candidates.
- For SQLite, sample only query-relevant text fields; for BigQuery/Snowflake,
  use the documented catalog and never require live credentials during subset
  preparation.

## join_verifier

- Require an explicit join path for every multi-table query.
- Check that join columns have compatible roles and that the join does not
  multiply rows unexpectedly.
- If the schema is ambiguous, inspect the database evidence before changing
  the SQL.

## candidate_auditor

- Keep the v1.1 candidate generation and structural selector for comparability.
- Treat each candidate as an independent role: direct grounding, join-path
  verification, value/time verification, alternative aggregation, or adversarial
  semantic review.
- In v1.5, independence means a different reasoning representation: direct
  output contract, relational DDL path, execution-plan decomposition,
  counterfactual table path, or adversarial semantic audit.
- Pairwise v1.5 selection compares unique execution-result groups using result
  column names and a five-row preview. Never expose gold SQL to generation or
  selection.
- Use execution evidence and the selector margin to distinguish a missing good
  candidate from selection regret.
- Do not spend revision calls on syntax that already executes correctly.

## budget_controller

- Interaction evidence is cached per instance and appended once to the existing
  schema prompt; it does not add model turns or enlarge the fixed prompt budget.
- v1.4 rejects strict BM25 subphrase matches unless the database value is an
  exact match. Exact matches remain admissible, and all admissions are recorded
  in the per-instance BM25 trace.
- Do not add unconditional repair/refinement turns in v1.5. Executing SQL is
  already revised by the existing repair stage; measured failures are mainly
  semantic relation/output errors, not syntax errors.
- Re-running a completed stage resumes from `checkpoints/stages.json` and
  instance artifacts.
- Full runs require a completed deterministic `subset20` run unless the user
  explicitly passes `--skip-subset-gate`.

## reporting

- Preserve `aggregates/summary_metrics.json` and all existing metrics.
- Report target accuracy, observed accuracy, candidate oracle accuracy,
  selection regret, usage, and excluded backends in `research_summary.json`.
- Spider2-Lite comparisons with Snowflake excluded must state the fixed
  45.89% cross-validation denominator supplied for the local/BigQuery slice.

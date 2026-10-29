# Lightweight Accuracy Stages

The new stages sit between the existing SLAYQL phases. They do not replace the
existing ablation scripts or silently change baseline output directories.

1. After retrieval, run `prepare-retrieval` and pass its output to schema
   completion. This focuses the schema, records relationship evidence, assigns
   an easy/medium/hard mode, and creates the query contract.
2. After schema completion, run `prepare-generation`. It partitions questions
   by mode and materializes a successfully validated completion draft as
   candidate zero when one is present in the contract.
3. Generate one candidate for `easy.json`, two for `medium.json`, and three for
   `hard.json` with the existing generation command. The counts are also stored
   in `generation_manifest.json`.
4. After execution, run `record-execution`, then `prepare-repair`. The repair
   queue contains both the SQL and a machine-readable semantic error for at
   most one repair attempt with the existing reviser. Run `select` after any
   repaired SQL has been executed. Selection rejects
   hard contract failures before comparing execution consistency and SQL
   simplicity.
5. After official evaluation, run `report` to create one JSONL and CSV row for
   every dataset question, including missing predictions.

Example stage invocation:

```powershell
./lightweight_accuracy_stage.ps1 -Stage prepare-retrieval `
  -InputPath retrieval.json -OutputPath retrieval.prepared.json
```

All paths are explicit so baseline and lightweight artifacts can coexist.

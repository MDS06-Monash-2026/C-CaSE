param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("prepare-retrieval", "prepare-generation", "record-execution", "prepare-repair", "select", "report")]
    [string]$Stage,
    [string]$InputPath,
    [string]$OutputPath,
    [string]$ArtifactRoot = "artifacts/lightweight_accuracy",
    [string]$ContractDir = "artifacts/lightweight_accuracy/contracts",
    [string]$GenerationRoot = "sql_gen",
    [string]$ExecutionRoot = "sql_exec",
    [string]$RepairRoot = "semantic_repair_queue",
    [string]$PredictionDir = "sql_selected",
    [string]$DatasetPath,
    [string]$EvaluationPath
)

$ErrorActionPreference = "Stop"
$RunDir = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Stage) {
    "prepare-retrieval" {
        python "$RunDir/prepare_lightweight_inputs.py" `
            --input $InputPath `
            --output $OutputPath `
            --artifact_root $ArtifactRoot `
            --base_dir $RunDir
    }
    "prepare-generation" {
        python "$RunDir/prepare_generation_inputs.py" `
            --input $InputPath `
            --output_root $OutputPath `
            --contract_dir $ContractDir `
            --generation_root $GenerationRoot
    }
    "record-execution" {
        python "$RunDir/record_execution_artifacts.py" `
            --execution_root $ExecutionRoot `
            --artifact_root $ArtifactRoot
    }
    "prepare-repair" {
        python "$RunDir/prepare_semantic_repairs.py" `
            --sql_root $GenerationRoot `
            --execution_root $ExecutionRoot `
            --contract_dir $ContractDir `
            --output_root $RepairRoot
    }
    "select" {
        python "$RunDir/select_lightweight_sql.py" `
            --sql_root $GenerationRoot `
            --execution_root $ExecutionRoot `
            --contract_dir $ContractDir `
            --output_dir $PredictionDir `
            --artifact_root $ArtifactRoot
    }
    "report" {
        python "$RunDir/build_question_report.py" `
            --dataset $DatasetPath `
            --evaluation $EvaluationPath `
            --prediction_dir $PredictionDir `
            --artifact_root $ArtifactRoot `
            --output_jsonl "$OutputPath/questions.jsonl" `
            --output_csv "$OutputPath/questions.csv"
    }
}

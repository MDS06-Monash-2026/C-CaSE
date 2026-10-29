"""SlayQL v1.2-v1.9 research-suite harness.

The harness keeps the v1.1 inference and evaluation artifacts, but adds:
query-specific interaction evidence, a deterministic diverse subset gate,
target/baseline reporting, and automatic Snowflake exclusion when credentials
are unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

import dataset_pipeline as v11
from artifact_store import atomic_write_json
from prompt_learning import demonstration_fingerprint
from research_subset import select_subset


RUN_DIR = Path(__file__).resolve().parent
SUITE_VERSION = os.environ.get("SLAYQL_RESEARCH_SUITE_VERSION", "1.2")
if SUITE_VERSION not in {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
    raise ValueError(f"Unsupported research suite version: {SUITE_VERSION}")
RESEARCH_VERSION = (
    "slayql_v1.9_adaptive_schema_projection" if SUITE_VERSION == "1.9" else
    "slayql_v1.8_answer_plan_tournament" if SUITE_VERSION == "1.8" else
    "slayql_v1.7_prompt_learning_execution_repair" if SUITE_VERSION == "1.7" else
    "slayql_v1.6_semantic_routes" if SUITE_VERSION == "1.6" else
    "slayql_v1.5_relational_multipath" if SUITE_VERSION == "1.5" else
    "slayql_v1.4_grounded_planning" if SUITE_VERSION == "1.4" else
    "slayql_v1.3_selective_evidence" if SUITE_VERSION == "1.3"
    else "slayql_v1.2_evidence_guided"
)
ARCHITECTURE_REVISION = (
    "adaptive_schema_plan_projection_regeneration_r9" if SUITE_VERSION == "1.9" else
    "answer_plan_cardinality_tournament_safe_repair_r8" if SUITE_VERSION == "1.8" else
    "leakage_safe_prompt_learning_execution_grounded_candidate_r7" if SUITE_VERSION == "1.7" else
    "semantic_contract_candidate_routing_single_judge_r6" if SUITE_VERSION == "1.6" else
    "relational_closure_dual_view_value_tournament_r5" if SUITE_VERSION == "1.5" else
    "balanced_retrieval_schema_focus_strict_values_r4" if SUITE_VERSION == "1.4" else
    "selective_interaction_ordinal_contract_r3" if SUITE_VERSION == "1.3"
    else "evidence_before_completion_candidate_roles_r2"
)
TARGETS = {"bird": 0.75, "spider1": 0.80, "spider2-lite": 0.52}
BASELINES = {"spider2-lite": {"fixed_denominator_accuracy": 0.4589, "label": "SlayQL v1 frozen cross-validation"}}


def _canonical_dataset(value: str) -> str:
    normalized = value.lower().replace("_", "-")
    return "spider2-lite" if normalized in {"spider2", "spider2-lite", "spider2.0-lite"} else "spider1" if normalized == "spider1.0" else normalized


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _candidate_default(dataset: str) -> int:
    return {"bird": 5, "spider1": 3, "spider2-lite": 5}[dataset]


def _resolve_demonstration_file(args: argparse.Namespace, dataset: str) -> Optional[str]:
    if args.demonstration_file:
        return str(Path(args.demonstration_file).expanduser().resolve())
    if SUITE_VERSION in {"1.7", "1.8", "1.9"} and dataset == "spider1" and args.split != "train":
        source = v11.REPO_ROOT / "spider_data" / "spider_data" / "train_spider.json"
        if source.is_file():
            return str(source.resolve())
    return None


def _resolved_config(args: argparse.Namespace, dataset: str, excluded: Sequence[str], candidates: int) -> Dict[str, Any]:
    target_accuracy = args.target_accuracy if args.target_accuracy is not None else TARGETS[dataset]
    v17 = SUITE_VERSION == "1.7"
    v18 = SUITE_VERSION == "1.8"
    v19 = SUITE_VERSION == "1.9"
    config = {
        "schema_version": SUITE_VERSION,
        "research_version": RESEARCH_VERSION,
        "architecture_revision": ARCHITECTURE_REVISION,
        "dataset": dataset,
        "split": args.split,
        "seed": args.seed,
        "smoke_count": args.smoke_count,
        "excluded_backends": sorted(set(excluded)),
        "num_candidates": candidates,
        "workers": args.workers,
        "target_accuracy": target_accuracy,
        "interaction_context": {
            "enabled": True, "max_context_chars": args.max_interaction_chars,
            "mode": "adaptive_schema_plan_regeneration" if v19 else "answer_plan_execution_grounded_tournament" if v18 else "prompt_learning_execution_grounded_repair" if v17 else (
                "semantic_contract_relational_routes" if SUITE_VERSION == "1.6" else (
                "relational_closure" if SUITE_VERSION == "1.5" else (
                "grounded_question_plan" if SUITE_VERSION == "1.4" else (
                "selective_query_linked" if SUITE_VERSION == "1.3" else "broad_query_evidence"
                )
            ))),
        },
        "schema_focus": {
            "enabled": SUITE_VERSION in {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9"},
            "max_tables": 8 if SUITE_VERSION in {"1.5", "1.6", "1.7", "1.8", "1.9"} else 5,
            "max_columns_per_table": 16 if SUITE_VERSION in {"1.5", "1.6", "1.7", "1.8", "1.9"} else 12,
            "max_columns_total": 72 if SUITE_VERSION in {"1.5", "1.6", "1.7", "1.8", "1.9"} else 48,
            "method": (
                "bidirectional_adaptive_schema_beam" if v19 else "question_links_plus_relational_closure_answer_plan" if v18 else "question_links_plus_relational_closure" if SUITE_VERSION in {"1.5", "1.6", "1.7"}
                else "question_linked_columns_plus_join_endpoints"
            ),
        },
        "value_grounding": {
            "strict_subphrase_rejection": SUITE_VERSION in {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9"},
            "exact_match_override": True,
            "schema_seed_handoff": SUITE_VERSION in {"1.5", "1.6", "1.7", "1.8", "1.9"},
        },
        "candidate_guidance": (
            "adaptive_schema_plan_unit_tests" if v19 else "measured_answer_plan_relation_routes" if v18 else "deterministic_relation_routes_with_full_fallback" if SUITE_VERSION in {"1.6", "1.7"} else (
            "relational_multi_path_dual_schema_views" if SUITE_VERSION == "1.5"
            else "deterministic_independent_roles"
        )),
        "semantic_contract": {
            "enabled": SUITE_VERSION in {"1.6", "1.7", "1.8", "1.9"},
            "source": "deterministic_question_and_dataset_evidence",
            "shared_by": ["generation", "selection"],
        },
        "candidate_routing": {
            "enabled": SUITE_VERSION in {"1.6", "1.7", "1.8", "1.9"},
            "full_schema_fallback_candidate": 2,
            "max_relation_hypotheses": 4,
        },
        "subset_policy": "difficulty_or_reference_stratified_20_easy_80_hard",
        "selection": (
            "contract_gated_top2_conditional_regeneration" if v19 else "pairwise_result_tournament_with_plan_guard" if v18 else "consensus_aware_single_contract_verification" if v17 else (
            "single_contract_result_verification" if SUITE_VERSION == "1.6" else (
            "value_aware_pairwise_result_tournament" if SUITE_VERSION == "1.5"
            else "v1.1_selector_first_structural_plus_interaction_grounding"
        ))),
    }
    if v19:
        config["selection_parameters"] = {
            "tournament_size": 2,
            "tournament_margin": 0.18,
            "repair_penalty": 0.12,
            "answer_plan_weight": 0.16,
            "physical_projection_gate": True,
            "conditional_regeneration": True,
        }
    elif v18:
        config["selection_parameters"] = {
            "tournament_size": 4,
            "tournament_margin": 0.20,
            "repair_penalty": 0.20,
            "answer_plan_weight": 0.14,
        }
    if v17 or v18 or v19:
        config["prompt_learning"] = {
            "enabled": bool(args.demonstration_file),
            "method": "training_only_structural_retrieval_answer_plan" if v18 or v19 else "training_only_structural_retrieval",
            "count": args.demonstration_count,
            "generation_candidates": [0, 2],
            "source": demonstration_fingerprint(args.demonstration_file),
        }
        config["semantic_revision"] = {
            "enabled": True,
            "method": "adaptive_schema_failure_regeneration" if v19 else "strict_non_destructive_plan_repair" if v18 else "selective_execution_grounded_extra_candidate",
            "max_repairs_per_instance": 1,
            "overwrites_original_candidates": False,
            "selection_requires_contract_improvement": v18 or v19,
        }
    # Experiment switches and the model are part of the run identity, so a run
    # folder records which variant produced it and a resume with different
    # settings is rejected by the config hash check.
    experiment_keys = (
        "ABLATION_NO_RBP", "ABLATION_NO_ITEE", "ABLATION_NO_BM25", "ABLATION_NO_QOC",
        "ABLATION_ITEE_THRESHOLD", "ABLATION_RBP_ALPHA", "SLAYQL_TOP_N",
        "MODEL_NAME", "OPENAI_BASE_URL", "SLAYQL_API_TIMEOUT",
    )
    config["environment"] = {key: os.environ[key] for key in experiment_keys if os.environ.get(key)}
    config["config_hash"] = _hash_payload(config)
    return config


def _source_hash(source_manifest: Dict[str, Any]) -> str:
    return _hash_payload(source_manifest.get("source_hashes", source_manifest))


def _completed_subset_exists(dataset: str, split: str, source_hash: str, config_hash: str) -> Optional[Path]:
    for candidate in sorted(RUN_DIR.iterdir()):
        manifest_path = candidate / "run_manifest.json"
        summary_path = candidate / "aggregates" / "summary_metrics.json"
        if not manifest_path.exists() or not summary_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            manifest.get("research_version") == RESEARCH_VERSION
            and manifest.get("dataset") == dataset
            and manifest.get("split") == split
            and manifest.get("mode") == "subset20"
            and manifest.get("source_hash") == source_hash
            and manifest.get("config_hash") == config_hash
            and manifest.get("status") == "complete"
        ):
            return candidate
    return None


def _write_research_summary(run_root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    summary_path = run_root / "aggregates" / "summary_metrics.json"
    if not summary_path.exists():
        result = {
            "schema_version": SUITE_VERSION, "status": "evaluation_incomplete",
            "dataset": manifest["dataset"], "target_accuracy": manifest["target_accuracy"],
        }
        atomic_write_json(str(run_root / "research_summary.json"), result)
        return result
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    accuracy = float(summary.get("fixed_denominator_accuracy", summary.get("execution_accuracy", 0.0)))
    baseline = BASELINES.get(manifest["dataset"])
    result = {
        "schema_version": SUITE_VERSION,
        "research_version": manifest.get("research_version"),
        "dataset": manifest["dataset"], "split": manifest["split"], "mode": manifest["mode"],
        "run_root": str(run_root.resolve()), "target_accuracy": manifest["target_accuracy"],
        "observed_accuracy": accuracy, "target_reached": accuracy >= manifest["target_accuracy"],
        "summary_metrics": str(summary_path.resolve()),
        "baseline": baseline,
        "baseline_delta": accuracy - float(baseline["fixed_denominator_accuracy"]) if baseline else None,
        "excluded_backends": manifest.get("excluded_backends", []),
        "subset_policy": manifest.get("subset_policy"),
        "record_count": summary.get("expected"),
        "correct": summary.get("correct"),
        "evaluable": summary.get("evaluable"),
        "candidate_oracle_accuracy": summary.get("candidate_oracle_accuracy"),
        "selection_regret": summary.get("selection_regret"),
        "usage": summary.get("usage"),
    }
    atomic_write_json(str(run_root / "research_summary.json"), result)
    return result


def prepare_run(args: argparse.Namespace) -> tuple[Path, Dict[str, Any], Dict[str, Dict[str, Any]]]:
    dataset = _canonical_dataset(args.dataset)
    if dataset not in TARGETS:
        raise ValueError(f"Unsupported research dataset: {args.dataset}")
    if args.target_accuracy is not None and not 0.0 <= args.target_accuracy <= 1.0:
        raise ValueError("target-accuracy must be between 0 and 1")
    if args.max_interaction_chars < 512:
        raise ValueError("max-interaction-chars must be at least 512")
    if not 1 <= args.demonstration_count <= 5:
        raise ValueError("demonstration-count must be between 1 and 5")
    args.demonstration_file = _resolve_demonstration_file(args, dataset)
    excluded = list(args.exclude_backend or [])
    if dataset == "spider2-lite" and not args.allow_snowflake and "snowflake" not in {value.lower() for value in excluded}:
        excluded.append("snowflake")
    candidates = args.num_candidates or _candidate_default(dataset)
    if candidates < 1:
        raise ValueError("num-candidates must be at least 1")
    config = _resolved_config(args, dataset, excluded, candidates)
    run_id = args.run_id or f"research_v{SUITE_VERSION.replace('.', '')}_{dataset}_{args.split}_{args.mode}"
    run_root = (RUN_DIR / run_id).resolve()
    existing_path = run_root / "run_manifest.json"

    if existing_path.exists():
        manifest = json.loads(existing_path.read_text(encoding="utf-8"))
        if manifest.get("research_version") != RESEARCH_VERSION:
            raise RuntimeError(f"Run ID belongs to another pipeline: {existing_path}")
        if (manifest.get("dataset"), manifest.get("split"), manifest.get("mode")) != (dataset, args.split, args.mode):
            raise RuntimeError(f"Existing run manifest conflicts with requested configuration: {existing_path}")
        if manifest.get("config_hash") != config["config_hash"]:
            raise RuntimeError("Existing run configuration differs; resume with the original candidates/workers/settings")
        records = json.loads((run_root / "dataset.json").read_text(encoding="utf-8"))
        print(f"Resuming SlayQL v{SUITE_VERSION} run: {run_root}", flush=True)
        return run_root, manifest, records

    records, source_manifest = v11.normalize_dataset(dataset, args.split, args.bird_root)
    if args.mode == "full" and not args.skip_subset_gate:
        source_hash = _source_hash(source_manifest)
        if _completed_subset_exists(dataset, args.split, source_hash, config["config_hash"]) is None:
            raise RuntimeError(
                f"Full run is gated until a completed v{SUITE_VERSION} subset20 run exists. "
                "Run the subset first, or pass --skip-subset-gate for an explicit override."
            )
    selected, subset_manifest = select_subset(
        records, args.mode, args.seed, args.smoke_count, excluded, args.reference_evaluation
    )
    run_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(run_root / "dataset.json"), selected)
    atomic_write_json(str(run_root / "dataset_manifest.json"), source_manifest)
    atomic_write_json(str(run_root / "subset_manifest.json"), subset_manifest)
    manifest = {
        "schema_version": SUITE_VERSION, "research_version": RESEARCH_VERSION,
        "architecture_revision": config["architecture_revision"],
        "dataset": dataset, "split": args.split, "mode": args.mode,
        "run_root": str(run_root.resolve()), "source": source_manifest,
        "source_hash": _source_hash(source_manifest), "record_count": len(selected),
        "instance_ids": sorted(selected), "dataset_file": str((run_root / "dataset.json").resolve()),
        "subset_manifest": str((run_root / "subset_manifest.json").resolve()),
        "seed": args.seed, "smoke_count": args.smoke_count,
        "excluded_backends": sorted(set(excluded)), "num_candidates": candidates,
        "workers": args.workers, "target_accuracy": (
            args.target_accuracy if args.target_accuracy is not None else TARGETS[dataset]
        ),
        "subset_policy": subset_manifest.get("selection_policy"),
        "reference_evaluation": args.reference_evaluation,
        "config_hash": config["config_hash"], "resolved_config": str((run_root / "resolved_config.json").resolve()),
        "status": "prepared",
    }
    atomic_write_json(str(run_root / "resolved_config.json"), config)
    atomic_write_json(str(run_root / "run_manifest.json"), manifest)
    if dataset != "spider2-lite":
        v11.validate_local_assets(selected)
    return run_root, manifest, selected


def run(args: argparse.Namespace) -> Dict[str, Any]:
    run_root, manifest, records = prepare_run(args)
    if args.command == "prepare":
        print(json.dumps({"run_root": str(run_root), "records": len(records), "manifest": manifest}, indent=2), flush=True)
        return manifest
    previous = os.environ.get("SLAYQL_RESEARCH_VERSION")
    previous_context_chars = os.environ.get("SLAYQL_RESEARCH_INTERACTION_CHARS")
    previous_compact = os.environ.get("SLAYQL_RESEARCH_COMPACT_INTERACTION")
    previous_bm25_strict = os.environ.get("SLAYQL_BM25_STRICT")
    previous_demonstration = os.environ.get("SLAYQL_DEMONSTRATION_FILE")
    previous_demonstration_count = os.environ.get("SLAYQL_DEMONSTRATION_COUNT")
    previous_tournament_size = os.environ.get("SLAYQL_SELECTOR_TOURNAMENT_SIZE")
    previous_tournament_margin = os.environ.get("SLAYQL_SELECTOR_TOURNAMENT_MARGIN")
    previous_repair_penalty = os.environ.get("SLAYQL_SELECTOR_REPAIR_PENALTY")
    previous_answer_plan_weight = os.environ.get("SLAYQL_SELECTOR_W_ANSWER_PLAN")
    os.environ["SLAYQL_RESEARCH_VERSION"] = SUITE_VERSION
    os.environ["SLAYQL_RESEARCH_INTERACTION_CHARS"] = str(args.max_interaction_chars)
    if SUITE_VERSION in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        os.environ["SLAYQL_RESEARCH_COMPACT_INTERACTION"] = "1"
    if SUITE_VERSION in {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        os.environ["SLAYQL_BM25_STRICT"] = "1"
    if SUITE_VERSION in {"1.7", "1.8", "1.9"}:
        if args.demonstration_file:
            os.environ["SLAYQL_DEMONSTRATION_FILE"] = args.demonstration_file
        else:
            os.environ.pop("SLAYQL_DEMONSTRATION_FILE", None)
        os.environ["SLAYQL_DEMONSTRATION_COUNT"] = str(args.demonstration_count)
    if SUITE_VERSION == "1.9":
        os.environ.setdefault("SLAYQL_SELECTOR_TOURNAMENT_SIZE", "2")
        os.environ.setdefault("SLAYQL_SELECTOR_TOURNAMENT_MARGIN", "0.18")
        os.environ.setdefault("SLAYQL_SELECTOR_REPAIR_PENALTY", "0.12")
        os.environ.setdefault("SLAYQL_SELECTOR_W_ANSWER_PLAN", "0.16")
    elif SUITE_VERSION == "1.8":
        os.environ.setdefault("SLAYQL_SELECTOR_TOURNAMENT_SIZE", "4")
        os.environ.setdefault("SLAYQL_SELECTOR_TOURNAMENT_MARGIN", "0.20")
        os.environ.setdefault("SLAYQL_SELECTOR_REPAIR_PENALTY", "0.20")
        os.environ.setdefault("SLAYQL_SELECTOR_W_ANSWER_PLAN", "0.14")
    try:
        v11.run_inference(run_root, manifest["dataset"], records, manifest["num_candidates"], manifest["workers"])
    finally:
        if previous is None:
            os.environ.pop("SLAYQL_RESEARCH_VERSION", None)
        else:
            os.environ["SLAYQL_RESEARCH_VERSION"] = previous
        if previous_context_chars is None:
            os.environ.pop("SLAYQL_RESEARCH_INTERACTION_CHARS", None)
        else:
            os.environ["SLAYQL_RESEARCH_INTERACTION_CHARS"] = previous_context_chars
        if previous_compact is None:
            os.environ.pop("SLAYQL_RESEARCH_COMPACT_INTERACTION", None)
        else:
            os.environ["SLAYQL_RESEARCH_COMPACT_INTERACTION"] = previous_compact
        if previous_bm25_strict is None:
            os.environ.pop("SLAYQL_BM25_STRICT", None)
        else:
            os.environ["SLAYQL_BM25_STRICT"] = previous_bm25_strict
        if previous_demonstration is None:
            os.environ.pop("SLAYQL_DEMONSTRATION_FILE", None)
        else:
            os.environ["SLAYQL_DEMONSTRATION_FILE"] = previous_demonstration
        if previous_demonstration_count is None:
            os.environ.pop("SLAYQL_DEMONSTRATION_COUNT", None)
        else:
            os.environ["SLAYQL_DEMONSTRATION_COUNT"] = previous_demonstration_count
        for key, value in (
            ("SLAYQL_SELECTOR_TOURNAMENT_SIZE", previous_tournament_size),
            ("SLAYQL_SELECTOR_TOURNAMENT_MARGIN", previous_tournament_margin),
            ("SLAYQL_SELECTOR_REPAIR_PENALTY", previous_repair_penalty),
            ("SLAYQL_SELECTOR_W_ANSWER_PLAN", previous_answer_plan_weight),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    v11.write_integrity_reports(run_root, manifest, records)
    manifest["status"] = "complete" if (run_root / "aggregates" / "summary_metrics.json").exists() else "incomplete"
    atomic_write_json(str(run_root / "run_manifest.json"), manifest)
    result = _write_research_summary(run_root, manifest)
    print(f"Research suite finished: {run_root}", flush=True)
    print(f"Target {manifest['target_accuracy']:.2%}; observed {result.get('observed_accuracy', 0.0):.2%}", flush=True)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"SlayQL v{SUITE_VERSION} research suite")
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--dataset", choices=("bird", "spider1", "spider1.0", "spider2", "spider2-lite"), required=True)
    parser.add_argument("--split", choices=("dev", "train", "test"), default="dev")
    parser.add_argument("--mode", choices=("smoke", "subset20", "full"), default="subset20")
    parser.add_argument("--bird-root")
    parser.add_argument("--run-id")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--smoke-count", type=int, default=5)
    parser.add_argument("--exclude-backend", action="append", default=[])
    parser.add_argument("--allow-snowflake", action="store_true")
    parser.add_argument("--num-candidates", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reference-evaluation")
    parser.add_argument("--target-accuracy", type=float)
    parser.add_argument("--skip-subset-gate", action="store_true")
    parser.add_argument("--max-interaction-chars", type=int, default=12000)
    parser.add_argument("--demonstration-file")
    parser.add_argument("--demonstration-count", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args)


if __name__ == "__main__":
    main()

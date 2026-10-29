from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = REPO_ROOT / "run" / "log_spider2_full_slayql"
FINAL_ROOT = BASELINE_ROOT / "sql_selection" / "final"
EVAL_RESULT = BASELINE_ROOT / "eval_result.txt"


def test_v1_baseline_has_one_final_folder_per_question():
    folders = [path for path in FINAL_ROOT.iterdir() if path.is_dir()]

    assert len(folders) == 547


def test_v1_baseline_result_coverage_is_preserved():
    folders = [path for path in FINAL_ROOT.iterdir() if path.is_dir()]
    result_count = sum((path / "result.csv").is_file() for path in folders)
    error_count = sum((path / "error.txt").is_file() for path in folders)

    assert result_count == 527
    assert error_count == 20


def test_v1_baseline_recorded_score_is_preserved():
    report = EVAL_RESULT.read_text(encoding="utf-8")

    assert re.search(r"Results:\s*251/527\s+correct\.\s+Score:\s*0\.4763", report)

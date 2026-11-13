from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "ci_timing_report.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_timing_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample() -> dict[str, Any]:
    return {
        "run": {
            "id": 1,
            "head_sha": "a" * 40,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
            "run_started_at": "2026-09-14T12:00:00Z",
            "updated_at": "2026-09-14T12:20:00Z",
        },
        "jobs": [
            {
                "id": 2,
                "run_id": 1,
                "head_sha": "a" * 40,
                "run_attempt": 1,
                "name": "test",
                "conclusion": "success",
                "created_at": "2026-09-14T12:00:00Z",
                "started_at": "2026-09-14T12:10:00Z",
                "completed_at": "2026-09-14T12:15:00Z",
                "steps": [
                    {
                        "name": "pytest",
                        "conclusion": "success",
                        "started_at": "2026-09-14T12:11:00Z",
                        "completed_at": "2026-09-14T12:15:00Z",
                    }
                ],
            }
        ],
    }


def test_wait_is_not_execution(sample: dict[str, Any]) -> None:
    result = load_script().analyze(sample)
    assert result["jobs"][0]["pre_start_seconds"] == 600
    assert result["jobs"][0]["execution_seconds"] == 300
    assert result["jobs"][0]["steps"][0]["execution_seconds"] == 240
    assert result["billing"] == "NOT_INFERRED"


def test_skipped_is_not_a_zero_cost_pass(sample: dict[str, Any]) -> None:
    sample["jobs"][0]["conclusion"] = "skipped"
    assert load_script().analyze(sample)["jobs"][0]["execution_seconds"] is None


def test_missing_timing_is_preserved(sample: dict[str, Any]) -> None:
    sample["jobs"][0]["completed_at"] = None
    assert load_script().analyze(sample)["missing_job_timing_count"] == 1


def test_duplicate_pages_are_rejected(sample: dict[str, Any]) -> None:
    sample["jobs"].append(copy.deepcopy(sample["jobs"][0]))
    with pytest.raises(ValueError, match="DUPLICATE_JOB_PAGE"):
        load_script().analyze(sample)


def test_mixed_sha_is_rejected(sample: dict[str, Any]) -> None:
    sample["jobs"][0]["head_sha"] = "b" * 40
    with pytest.raises(ValueError, match="JOB_RUN_MISMATCH"):
        load_script().analyze(sample)


def test_inflight_run_is_rejected(sample: dict[str, Any]) -> None:
    sample["run"]["status"] = "in_progress"
    with pytest.raises(ValueError, match="RUN_NOT_COMPLETED"):
        load_script().analyze(sample)


def test_negative_duration_is_rejected() -> None:
    with pytest.raises(ValueError, match="NEGATIVE_DURATION"):
        load_script().elapsed("2026-09-14T12:20:00Z", "2026-09-14T12:00:00Z")


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="NAIVE_TIMESTAMP"):
        load_script().elapsed("2026-09-14T12:00:00", "2026-09-14T12:10:00")

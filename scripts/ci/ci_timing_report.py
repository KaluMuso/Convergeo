#!/usr/bin/env python3
"""Analyze saved GitHub run/job JSON without inferring a speedup or billing."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


def at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return stamp


def elapsed(start: Any, end: Any) -> float | None:
    if start is None or end is None:
        return None
    duration = (at(end) - at(start)).total_seconds()
    if duration < 0:
        raise ValueError("NEGATIVE_DURATION")
    return duration


def analyze(sample: dict[str, Any]) -> dict[str, Any]:
    run = sample["run"]
    if run.get("status") != "completed":
        raise ValueError("RUN_NOT_COMPLETED")
    jobs = sample["jobs"]
    ids = [job["id"] for job in jobs]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_JOB_PAGE")
    result: dict[str, Any] = {
        "run_id": run["id"],
        "head_sha": run["head_sha"],
        "attempt": run["run_attempt"],
        "conclusion": run.get("conclusion"),
        "run_elapsed_seconds": elapsed(run.get("run_started_at"), run.get("updated_at")),
        "jobs": [],
        "billing": "NOT_INFERRED",
    }
    for job in jobs:
        if job.get("run_id") != run["id"] or job.get("head_sha") != run["head_sha"]:
            raise ValueError("JOB_RUN_MISMATCH")
        duration = elapsed(job.get("started_at"), job.get("completed_at"))
        if job.get("conclusion") == "skipped":
            duration = None
        row = {
            "job_id": job["id"],
            "name": job["name"],
            "conclusion": job.get("conclusion"),
            "source_attempt": job.get("run_attempt"),
            "pre_start_seconds": elapsed(job.get("created_at"), job.get("started_at")),
            "execution_seconds": duration,
            "steps": [],
        }
        for step in job.get("steps") or []:
            row["steps"].append(
                {
                    "name": step["name"],
                    "conclusion": step.get("conclusion"),
                    "execution_seconds": (
                        None
                        if step.get("conclusion") == "skipped"
                        else elapsed(step.get("started_at"), step.get("completed_at"))
                    ),
                }
            )
        result["jobs"].append(row)
    result["observed_job_execution_seconds"] = sum(
        job["execution_seconds"]
        for job in result["jobs"]
        if job["execution_seconds"] is not None
    )
    result["missing_job_timing_count"] = sum(
        job["execution_seconds"] is None and job["conclusion"] != "skipped"
        for job in result["jobs"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        samples = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(samples, list) or not samples:
            raise ValueError("EMPTY_SAMPLE_SET")
        runs = [analyze(sample) for sample in samples]
        times = [
            run["run_elapsed_seconds"]
            for run in runs
            if run["run_elapsed_seconds"] is not None
        ]
        output = {
            "runs": runs,
            "median_elapsed_seconds": statistics.median(times) if times else None,
            "comparison": "OBSERVATIONAL_BASELINE_NOT_A_BEFORE_AFTER_EXPERIMENT",
        }
        args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    except (ValueError, TypeError, KeyError, OSError):
        print("FAIL: invalid or incomplete timing input; no result written by this execution.")
        return 1
    print(f"Analyzed {len(runs)} completed runs. No measured speedup is implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def record(
    role: str, operation: str, event: str, time: int, error: str = "none"
) -> dict[str, object]:
    return {
        "version": 1,
        "role": role,
        "operation": operation,
        "event": event,
        "error": error,
        "time": time,
    }


def write_rows(tmp_path: Path, role: str, rows: list[dict[str, object]], ordinal: int = 1) -> Path:
    path = tmp_path / f"private-lifecycle-{role}-{ordinal}-0.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    path.chmod(0o600)
    return path


def capture(tmp_path: Path, *, recursive_json_decoder: bool = False) -> dict[str, Any]:
    shell = (ROOT / "scripts/qa/run-cart-response-drill.sh").read_text()
    script = shell.split('if ! python3 - "$drill_output" "$drill_phase"', 1)[1]
    script = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    if recursive_json_decoder:
        # New CPython C decoders can parse this nesting iteratively. Exercise
        # the RecursionError containment using the stdlib recursive decoder in
        # this isolated fixture only; never change the production parser.
        script = (
            "import json\nfrom json.scanner import py_make_scanner\n"
            "decoder = json.JSONDecoder()\ndecoder.scan_once = py_make_scanner(decoder)\n"
            "json.loads = decoder.decode\n" + script
        )
    result = subprocess.run(
        [sys.executable, "-", str(tmp_path), "evidence_and_cleanup", "1", "running", "running"],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    assert result.stdout.startswith("cart-drill-native-error-summary: ")
    output = (tmp_path / "diagnostics.json").read_text()
    assert "PRIVATE" not in output + result.stdout
    value: dict[str, Any] = json.loads(output)["request_lifecycle"]
    assert len(json.dumps(value)) < 4096
    return value


def complete(tmp_path: Path) -> tuple[Path, Path]:
    sdk = write_rows(
        tmp_path,
        "sdk",
        [
            record("sdk", "observer", "ready", 1),
            record("sdk", "pdp", "begin", 1_000_000),
            record("sdk", "pdp", "created", 1_001_000),
            record("sdk", "pdp", "sent", 1_002_000),
            record("sdk", "pdp", "headers", 2_000_000),
            record("sdk", "pdp", "end", 3_000_000),
            record("sdk", "pdp", "settle", 16_002_000),
        ],
    )
    customer = write_rows(
        tmp_path,
        "customer",
        [
            record("customer", "observer", "ready", 1),
            record("customer", "compiler", "compile_ready", 2),
            record("customer", "pdp", "received", 1_003_000),
            record("customer", "compiler", "compile_begin", 1_004_000),
            record("customer", "compiler", "compile_settled", 1_010_000),
            record("customer", "product", "created", 1_100_000),
            record("customer", "product", "headers", 1_200_000),
            record("customer", "product", "end", 1_300_000),
            record("customer", "pdp", "finish", 2_999_000),
        ],
    )
    return sdk, customer


def test_lifecycle_relative_timing_distinguishes_headers_body_and_server_finish(
    tmp_path: Path,
) -> None:
    complete(tmp_path)
    value = capture(tmp_path)
    assert value["coverage"] == "bounded"
    assert value["window_ms"] == 15_002
    assert value["sdk"] == {
        "observer_ready": True,
        "body_scope": "http_incoming_message_end",
        "created": 1,
        "sent": 1,
        "headers": 1,
        "body_end": 1,
        "error": "none",
        "first_headers_ms": 1000,
        "first_body_end_ms": 2000,
    }
    assert value["customer"]["first_finish_ms"] == 1999
    assert value["compiler"] == {
        "observer_ready": True,
        "started": 1,
        "scope": "ensure_page_entry_and_settlement_including_rejections_and_cache_hits",
        "settled": 1,
        "synchronous_errors": 0,
        "pending": 0,
        "first_start_ms": 4,
        "first_settled_ms": 10,
    }
    assert value["ssr_data"]["product"]["pending"] == 0
    assert "time" not in json.dumps(value)


def test_lifecycle_pending_response_and_ssr_remain_separate(tmp_path: Path) -> None:
    sdk, customer = complete(tmp_path)
    sdk_rows = [json.loads(line) for line in sdk.read_text().splitlines()]
    write_rows(tmp_path, "sdk", [r for r in sdk_rows if r["event"] != "end"])
    customer_rows = [json.loads(line) for line in customer.read_text().splitlines()]
    write_rows(
        tmp_path,
        "customer",
        [r for r in customer_rows if r["event"] not in {"finish", "compile_settled", "end"}],
    )
    value = capture(tmp_path)
    assert value["sdk"]["headers"] == 1
    assert value["sdk"]["body_end"] == 0
    assert value["customer"]["finished"] == 0
    assert value["compiler"]["pending"] == 1
    assert value["ssr_data"]["product"]["headers"] == 1
    assert value["ssr_data"]["product"]["pending"] == 1


def test_lifecycle_late_completion_cannot_rewrite_primary_snapshot(tmp_path: Path) -> None:
    sdk, customer = complete(tmp_path)
    sdk_rows = [json.loads(line) for line in sdk.read_text().splitlines()]
    for row in sdk_rows:
        if row["event"] == "end":
            row["time"] = 16_002_001
    sdk_rows.sort(key=lambda row: row["time"])
    write_rows(tmp_path, "sdk", sdk_rows)
    customer_rows = [json.loads(line) for line in customer.read_text().splitlines()]
    for row in customer_rows:
        if row["event"] in {"finish", "compile_settled", "end"}:
            row["time"] = 16_002_001
    customer_rows.sort(key=lambda row: row["time"])
    write_rows(tmp_path, "customer", customer_rows)
    value = capture(tmp_path)
    assert value["sdk"]["body_end"] == 0
    assert value["customer"]["finished"] == 0
    assert value["compiler"]["pending"] == 1
    assert value["ssr_data"]["product"]["pending"] == 1


@pytest.mark.parametrize("missing", ["begin", "settle", "customer_ready", "compiler_ready"])
def test_lifecycle_missing_coverage_is_unknown_not_absent(tmp_path: Path, missing: str) -> None:
    sdk, customer = complete(tmp_path)
    path = sdk if missing in {"begin", "settle"} else customer
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    event = (
        "ready"
        if missing == "customer_ready"
        else "compile_ready"
        if missing == "compiler_ready"
        else missing
    )
    write_rows(
        tmp_path, "sdk" if path == sdk else "customer", [r for r in rows if r["event"] != event]
    )
    assert capture(tmp_path)["coverage"] == "incomplete"


@pytest.mark.parametrize(
    "fault",
    [
        "extra_private",
        "role",
        "operation",
        "event",
        "error",
        "negative",
        "float",
        "boolean",
        "huge",
        "reverse_clock",
        "broken",
        "oversize",
        "many_rows",
        "mode",
        "hardlink",
        "symlink",
        "unknown_filename",
        "many_files",
    ],
)
def test_lifecycle_invalid_or_unsafe_record_never_exports_private_data(
    tmp_path: Path, fault: str
) -> None:
    sdk, _ = complete(tmp_path)
    row = record("sdk", "pdp", "headers", 2_000_000)
    if fault == "extra_private":
        row["cookie"] = "PRIVATE_COOKIE_BODY_PERSON"
    elif fault in {"role", "operation", "event", "error"}:
        row[fault] = "PRIVATE_TOKEN"
    elif fault in {"negative", "float", "boolean", "huge"}:
        row["time"] = {"negative": -1, "float": 1.5, "boolean": True, "huge": 2**54}[fault]
    if fault in {
        "extra_private",
        "role",
        "operation",
        "event",
        "error",
        "negative",
        "float",
        "boolean",
        "huge",
    }:
        sdk.write_text(sdk.read_text() + json.dumps(row) + "\n")
    elif fault == "reverse_clock":
        sdk.write_text(sdk.read_text() + json.dumps(record("sdk", "pdp", "headers", 1)) + "\n")
    elif fault == "broken":
        sdk.write_text("PRIVATE_INVALID_JSON\n")
    elif fault == "oversize":
        sdk.write_text("PRIVATE" * 2000)
    elif fault == "many_rows":
        write_rows(tmp_path, "sdk", [record("sdk", "observer", "ready", 1)] * 33)
    elif fault == "mode":
        sdk.chmod(0o644)
    elif fault == "hardlink":
        os.link(sdk, tmp_path / "PRIVATE_OUTSIDE")
    elif fault == "symlink":
        private = tmp_path / "PRIVATE_OUTSIDE"
        private.write_text("PRIVATE_SECRET_CONTENT")
        sdk.unlink()
        sdk.symlink_to(private)
    elif fault == "unknown_filename":
        sdk.rename(tmp_path / "private-lifecycle-PRIVATE.jsonl")
    else:
        for ordinal in range(2, 10):
            write_rows(tmp_path, "customer", [record("customer", "observer", "ready", 1)], ordinal)
    assert capture(tmp_path)["coverage"] == "incomplete"


@pytest.mark.parametrize("kind", ["limit", "observer_error", "sink_failed"])
def test_lifecycle_sink_limit_and_observer_errors_are_explicit(tmp_path: Path, kind: str) -> None:
    complete(tmp_path)
    if kind == "sink_failed":
        (tmp_path / "private-lifecycle-customer-1-0.jsonl.failed").write_text("PRIVATE_REASON")
    else:
        write_rows(tmp_path, "customer", [record("customer", "observer", kind, 2_000_000)], 2)
    value = capture(tmp_path)
    assert value["coverage"] == "incomplete"
    assert (
        value[
            {
                "limit": "record_limit",
                "observer_error": "observer_error",
                "sink_failed": "sink_failed",
            }[kind]
        ]
        is True
    )


def test_lifecycle_absent_probe_does_not_change_original_failure_or_native_summary(
    tmp_path: Path,
) -> None:
    value = capture(tmp_path)
    assert value == {
        "format": "cart_request_lifecycle_v1",
        "scope": "initial_seeded_pdp_only",
        "coverage": "unavailable",
    }


@pytest.mark.parametrize("kind", ["malformed", "private_role", "unsafe_symlink", "nested_json"])
def test_lifecycle_fault_without_valid_records_is_incomplete(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "private-lifecycle-sdk-1-0.jsonl"
    if kind == "unsafe_symlink":
        outside = tmp_path / "outside"
        outside.write_text("PRIVATE")
        path.symlink_to(outside)
    elif kind == "malformed":
        path.write_text("PRIVATE_NOT_JSON")
        path.chmod(0o600)
    elif kind == "nested_json":
        path.write_text("[" * 1500 + '"PRIVATE"' + "]" * 1500)
        assert path.stat().st_size <= 8192
        path.chmod(0o600)
    else:
        write_rows(tmp_path, "sdk", [record("PRIVATE", "pdp", "begin", 1)])
    value = capture(tmp_path, recursive_json_decoder=kind == "nested_json")
    assert value["coverage"] == "incomplete"
    assert value["read_failed"] or value["invalid_records"]
    if kind == "nested_json":
        assert value["read_failed"] is True


def test_lifecycle_directory_enumeration_is_bounded_and_marks_excess(tmp_path: Path) -> None:
    for ordinal in range(66):
        (tmp_path / f"unrelated-{ordinal}").write_text("PRIVATE")
    value = capture(tmp_path)
    assert value["coverage"] == "incomplete"
    assert value["invalid_records"] is True

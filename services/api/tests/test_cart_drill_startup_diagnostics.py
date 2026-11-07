from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def diagnostics(tmp_path: Path, customer_log: str) -> dict[str, object]:
    shell = (ROOT / "scripts/qa/run-cart-response-drill.sh").read_text()
    marker = (
        'if ! python3 - "$drill_output" "$drill_phase" "$drill_status" '
        '"$drill_api_exit" "$drill_customer_exit"'
    )
    script = shell.split(marker, 1)[1].split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    (tmp_path / "private-customer.log").write_text(customer_log)
    (tmp_path / "private-api.log").write_text("PRIVATE_API_TOKEN /PRIVATE_HOME/key")
    (tmp_path / "private-health-probe.json").write_text(
        json.dumps(
            [
                {"name": "api", "ok": True, "raw": "PRIVATE_HEALTH_PAYLOAD"},
                {"name": "customer", "ok": False, "raw": "PRIVATE_HEALTH_PAYLOAD"},
            ]
        )
    )
    result = subprocess.run(
        [sys.executable, "-", str(tmp_path), "server_startup", "1", "running", "1"],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout == result.stderr == ""
    data: dict[str, object] = json.loads((tmp_path / "diagnostics.json").read_text())
    exported = json.dumps(data)
    assert "PRIVATE_" not in exported
    assert data["exit"] == 1
    assert data["customer_launcher_status"] == "1"
    assert data["latest_health"] == [
        {"name": "api", "ok": True},
        {"name": "customer", "ok": False},
    ]
    return data


def test_commonjs_missing_public_dependency_is_classified_without_raw_trace(tmp_path: Path) -> None:
    data = diagnostics(
        tmp_path,
        "Error: Cannot find module '@vergeo/config'\n"
        "code: 'MODULE_NOT_FOUND'\nRequire stack: /PRIVATE_HOME/project/next.config.ts\n"
        "Authorization: PRIVATE_TOKEN\nhttps://host/?token=PRIVATE_TOKEN",
    )
    assert data["customer_log_categories"] == ["MODULE_NOT_FOUND", "Cannot find module"]
    assert data["customer_missing_module"] == "@vergeo/config"


@pytest.mark.parametrize(
    "marker",
    [
        "ERR_PACKAGE_PATH_NOT_EXPORTED",
        "ERR_REQUIRE_ESM",
        "ERR_UNKNOWN_FILE_EXTENSION",
        "ERR_DLOPEN_FAILED",
        "EPERM",
        "ENOENT",
        "EADDRINUSE",
        "Failed to load next.config",
        "Failed to load SWC binary",
    ],
)
def test_startup_codes_export_only_fixed_categories(tmp_path: Path, marker: str) -> None:
    data = diagnostics(tmp_path, f"{marker}: PRIVATE_TOKEN /PRIVATE_HOME/private-file")
    assert data["customer_log_categories"] == [marker]
    assert data["customer_missing_module"] is None


@pytest.mark.parametrize(
    "module, expected",
    [
        ("/PRIVATE_HOME/node_modules/next/PRIVATE_FILE.js", "unclassified"),
        ("PRIVATE_MODULE_TOKEN", "unclassified"),
        ("next/dist/PRIVATE_FILE.js", "next_internal"),
        ("react", "react"),
    ],
)
def test_missing_module_names_are_whitelisted_or_redacted(
    tmp_path: Path, module: str, expected: str
) -> None:
    data = diagnostics(tmp_path, f"Cannot find module '{module}'\nPRIVATE_TOKEN")
    assert data["customer_missing_module"] == expected


def test_unknown_startup_text_is_not_reported_as_a_cause(tmp_path: Path) -> None:
    data = diagnostics(tmp_path, "PRIVATE_CUSTOMER_ERROR /PRIVATE_HOME/customer")
    assert data["customer_log_categories"] == []
    assert data["customer_missing_module"] is None

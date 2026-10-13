from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def diagnostics(
    tmp_path: Path, customer_log: str, runtime_root: Path | None = None
) -> dict[str, object]:
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
        [
            sys.executable,
            "-",
            str(tmp_path),
            "server_startup",
            "1",
            "running",
            "1",
            *([str(runtime_root)] if runtime_root is not None else []),
        ],
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


@pytest.mark.parametrize("module", ["@swc/core", "@swc/core-linux-x64-gnu", "webpack"])
def test_config_graph_modules_export_only_exact_public_names(tmp_path: Path, module: str) -> None:
    data = diagnostics(tmp_path, f"Cannot find module '{module}'\nPRIVATE_TOKEN")
    assert data["customer_missing_module"] == module
    assert data["customer_missing_module_category"] == "public_module"
    assert data["customer_missing_relative_path"] is None


@pytest.mark.parametrize(
    "module, category",
    [
        ("./PRIVATE_TOKEN", "relative_request"),
        ("../PRIVATE_TOKEN", "relative_request"),
        ("/PRIVATE_HOME/secret", "absolute_request"),
        ("PRIVATE_TOKEN", "unclassified"),
        ("https://host/?token=PRIVATE_TOKEN", "unclassified"),
    ],
)
def test_unknown_requests_export_only_fixed_categories(
    tmp_path: Path, module: str, category: str
) -> None:
    data = diagnostics(tmp_path, f"Cannot find module '{module}'\nPRIVATE_TOKEN", tmp_path)
    assert data["customer_missing_module"] == "unclassified"
    assert data["customer_missing_module_category"] == category
    assert data["customer_missing_relative_path"] is None
    assert data["customer_require_chain"] == []


@pytest.mark.parametrize("stack_format", ["commonjs", "object"])
def test_require_chain_exports_only_owned_fixed_public_paths(
    tmp_path: Path, stack_format: str
) -> None:
    root = tmp_path / "PRIVATE_RUNTIME"
    public = "node_modules/next/dist/build/next-config-ts/require-hook.js"
    paths = [
        str(root / "apps/customer/next.config.compiled.js"),
        str(root / "node_modules/.pnpm/next@15.5.27_PRIVATE_PEER" / public),
        str(root / "PRIVATE_USER_FILE.js"),
        "/PRIVATE_HOME/user-data.json",
        str(root / "apps/customer/../next.config.ts"),
        str(root / "apps/customer/next.config.ts?token=PRIVATE_TOKEN"),
    ]
    if stack_format == "commonjs":
        stack = "Require stack:\n" + "\n".join(f"- {path}" for path in paths)
    else:
        stack = "requireStack: [\n" + "\n".join(f"'{path}'," for path in paths) + "\n]"
    data = diagnostics(tmp_path, "Cannot find module 'PRIVATE_MODULE'\n" + stack, root)
    assert data["customer_missing_module"] == "unclassified"
    assert data["customer_require_chain"] == ["apps/customer/next.config.compiled.js", public]
    assert data["customer_require_chain_format"] == "allowlisted_public_module_relative_v1"


def test_owned_missing_runtime_file_exports_only_a_fixed_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "PRIVATE_RUNTIME"
    path = "apps/customer/lib/api-base-url.ts"
    data = diagnostics(tmp_path, f"Cannot find module '{root / path}'", root)
    assert data["customer_missing_module"] == "unclassified"
    assert data["customer_missing_module_category"] == "public_runtime_file"
    assert data["customer_missing_relative_path"] == path


def test_require_chain_is_deduplicated_and_bounded(tmp_path: Path) -> None:
    paths = [
        "apps/customer/next.config.ts",
        "apps/customer/next.config.compiled.js",
        "apps/customer/lib/api-base-url.ts",
        "packages/config/src/index.ts",
        "packages/config/src/env.ts",
        "packages/config/src/api-base-url.ts",
        "packages/config/src/security-headers.ts",
        "node_modules/@swc/core/index.js",
        "node_modules/@swc/core/binding.js",
    ]
    stack = "Require stack:\n" + "\n".join(f"- {tmp_path / path}" for path in paths * 2)
    data = diagnostics(tmp_path, stack, tmp_path)
    assert data["customer_require_chain"] == paths[:8]
    assert data["customer_missing_module"] is None


def test_large_log_exports_only_bounded_tail_diagnostics(tmp_path: Path) -> None:
    log = "Cannot find module '@vergeo/config'\n" + "PRIVATE_TOKEN\n" * 6000
    data = diagnostics(tmp_path, log + "Cannot find module '@swc/core'\n")
    assert data["customer_log_tail_truncated"] is True
    assert data["customer_missing_module"] == "@swc/core"
    assert len(json.dumps(data)) < 2000


def test_neighboring_runtime_prefix_is_not_an_owned_require_chain(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    outside = tmp_path / "runtime-PRIVATE_OTHER" / "apps/customer/next.config.ts"
    data = diagnostics(tmp_path, f"Require stack:\n- {outside}", root)
    assert data["customer_require_chain"] == []


def test_linked_private_log_is_not_read_for_diagnostics(tmp_path: Path) -> None:
    target = tmp_path / "PRIVATE_SYNTHETIC_LOG"
    target.write_text("PRIVATE_TOKEN")
    (tmp_path / "private-customer.log").symlink_to(target)
    data = diagnostics(tmp_path, "Cannot find module 'react'\nPRIVATE_TOKEN")
    assert data["customer_log_categories"] == []
    assert data["customer_missing_module"] is None
    assert data["customer_require_chain"] == []

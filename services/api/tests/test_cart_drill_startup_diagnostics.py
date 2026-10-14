from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def diagnostics(
    tmp_path: Path,
    customer_log: str,
    runtime_root: Path | None = None,
    customer_status: str = "1",
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
            customer_status,
            *([str(runtime_root)] if runtime_root is not None else []),
        ],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""
    data: dict[str, object] = json.loads((tmp_path / "diagnostics.json").read_text())
    prefix = "cart-drill-native-error-summary: "
    assert result.stdout.startswith(prefix)
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout.removeprefix(prefix)) == data["customer_native_error_summary"]
    assert len(result.stdout) < 2000
    exported = json.dumps(data)
    assert "PRIVATE_" not in exported + result.stdout
    assert data["exit"] == 1
    assert data["customer_launcher_status"] == customer_status
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


@pytest.mark.parametrize("platform", ["gnu", "musl"])
def test_native_relative_miss_is_an_attempt_without_a_binding_error_header(
    tmp_path: Path, platform: str
) -> None:
    data = diagnostics(
        tmp_path,
        f"Error: Cannot find module './swc.linux-x64-{platform}.node'\n"
        "  code: 'MODULE_NOT_FOUND'\nNative platform fallback succeeded\nPRIVATE_TOKEN",
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["state"] == "relative_native_missing_attempt"
    assert summary["native_binding_error_header_observed"] is False
    assert summary["relative_native_missing_attempts"] == [f"swc_linux_x64_{platform}_relative"]
    assert summary["observed_error_codes"] == ["MODULE_NOT_FOUND"]
    assert summary["observed_native_carrier_codes"] == []


def test_nested_native_cause_codes_survive_without_exporting_messages(tmp_path: Path) -> None:
    data = diagnostics(
        tmp_path,
        "Error: Failed to load native binding {\n"
        "  [cause]: [\n"
        "    Error: Cannot find module './swc.linux-x64-gnu.node' {\n"
        "      code: 'MODULE_NOT_FOUND', requireStack: ['/PRIVATE_HOME/config.js']\n"
        "    },\n"
        "    Error: PRIVATE_NATIVE_MESSAGE {\n"
        "      code: 'ERR_SWC_NATIVE_CACHE',\n"
        '      cause: {"message":"PRIVATE_TOKEN", "code":"EACCES",\n'
        '        "cause":{"code":"EPERM", "env":"PRIVATE_ENV"}},\n'
        "      [cause]: {code: 'ERR_SWC_NATIVE_CACHE'}\n"
        "    }\n"
        "  ]\n"
        "}\nAuthorization: PRIVATE_TOKEN\nhttps://host/?token=PRIVATE_TOKEN",
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary == {
        "format": "allowlisted_native_error_v1",
        "scope": "bounded_launcher_tail",
        "state": "native_binding_error_header",
        "native_binding_error_header_observed": True,
        "customer_launcher_failed": True,
        "relative_native_missing_attempts": ["swc_linux_x64_gnu_relative"],
        "observed_error_codes": ["MODULE_NOT_FOUND", "EACCES", "EPERM", "ERR_SWC_NATIVE_CACHE"],
        "observed_native_carrier_codes": ["ERR_SWC_NATIVE_CACHE"],
        "tail_truncated": False,
    }


@pytest.mark.parametrize(
    "code",
    [
        "ERR_SWC_NATIVE_FORMAT",
        "ERR_SWC_NATIVE_INTEGRITY",
        "ERR_SWC_NATIVE_COMPRESSION",
        "ERR_SWC_NATIVE_CACHE",
        "ERR_SWC_NATIVE_CONFIGURATION",
        "ERR_SWC_NATIVE_LOAD",
    ],
)
def test_native_carrier_codes_do_not_imply_a_binding_error_header(
    tmp_path: Path, code: str
) -> None:
    data = diagnostics(tmp_path, f"{{code: '{code}', message: 'PRIVATE_TOKEN'}}")
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["observed_native_carrier_codes"] == [code]
    assert summary["state"] == "native_code_without_binding_error_header"
    assert summary["native_binding_error_header_observed"] is False


@pytest.mark.parametrize(
    "header",
    [
        "Error: Failed to load native binding",
        " ⨯ Error: Failed to load native binding {",
        "  [cause]: Error: Failed to load native binding {",
    ],
)
def test_native_binding_error_header_header_is_separate_from_nested_loader_code(
    tmp_path: Path, header: str
) -> None:
    data = diagnostics(tmp_path, header + "\n  code: 'ERR_DLOPEN_FAILED'\nPRIVATE_TOKEN")
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["native_binding_error_header_observed"] is True
    assert summary["observed_error_codes"] == ["ERR_DLOPEN_FAILED"]


@pytest.mark.parametrize(
    "text",
    [
        "PRIVATE_MESSAGE contains ERR_SWC_NATIVE_CACHE and Failed to load native binding",
        "code: 'ERR_SWC_NATIVE_CACHE_PRIVATE_TOKEN'",
        "code: 'ERR_SWC_NATIVE_CACHE\"",
        '"code\': "ERR_SWC_NATIVE_CACHE"',
        "private_code: 'ERR_SWC_NATIVE_CACHE'",
        "code: ERR_SWC_NATIVE_CACHE",
        "Error: Failed to load native binding PRIVATE_TOKEN",
        "message: 'Error: Failed to load native binding'",
        "code: '" + "X" * 5000 + "ERR_SWC_NATIVE_CACHE'",
    ],
)
def test_malformed_or_unclassified_error_fields_cannot_become_native_cause(
    tmp_path: Path, text: str
) -> None:
    data = diagnostics(tmp_path, text)
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["state"] == "no_classified_native_evidence"
    assert summary["observed_error_codes"] == []
    assert summary["native_binding_error_header_observed"] is False


@pytest.mark.parametrize(
    "module_request",
    [
        "../swc.linux-x64-gnu.node",
        "./swc.linux-x64-gnu.node?token=PRIVATE_TOKEN",
        "./PRIVATE_TOKEN/swc.linux-x64-gnu.node",
        "/PRIVATE_HOME/swc.linux-x64-gnu.node",
        r".\swc.linux-x64-gnu.node",
    ],
)
def test_native_relative_request_categories_require_exact_safe_literals(
    tmp_path: Path, module_request: str
) -> None:
    data = diagnostics(tmp_path, f"Cannot find module '{module_request}'")
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["relative_native_missing_attempts"] == []
    assert summary["state"] == "no_classified_native_evidence"


def test_oversize_nested_error_tail_has_finite_codes_and_safe_job_summary(tmp_path: Path) -> None:
    data = diagnostics(
        tmp_path,
        "Error: Failed to load native binding\ncode: 'ERR_SWC_NATIVE_INTEGRITY'\n"
        + "PRIVATE_TOKEN\n" * 6000
        + "Error: Failed to load native binding {\n"
        + "{[cause]: {code: 'ERR_SWC_NATIVE_CACHE'}, PRIVATE_TOKEN\n" * 1300,
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["tail_truncated"] is True
    assert summary["observed_error_codes"] == ["ERR_SWC_NATIVE_CACHE"]
    # A discarded header cannot be recovered from a tail of repeated causes.
    assert summary["native_binding_error_header_observed"] is False
    assert len(json.dumps(summary)) < 1000


def test_malformed_nesting_preserves_only_recognized_code_fields(tmp_path: Path) -> None:
    data = diagnostics(
        tmp_path,
        "Error: Failed to load native binding {\n"
        + "{[cause]: [" * 500
        + "code: 'ERR_SWC_NATIVE_CACHE', code: 'PRIVATE_CODE', env: 'PRIVATE_TOKEN'",
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["native_binding_error_header_observed"] is True
    assert summary["observed_error_codes"] == ["ERR_SWC_NATIVE_CACHE"]
    assert summary["relative_native_missing_attempts"] == []


def test_earlier_relative_miss_does_not_hide_later_fatal_carrier_code(tmp_path: Path) -> None:
    data = diagnostics(
        tmp_path,
        "Error: Cannot find module './swc.linux-x64-gnu.node'\n"
        "  code: 'MODULE_NOT_FOUND'\n"
        "Error: Failed to load native binding {\n"
        "  [cause]: {code: 'ERR_SWC_NATIVE_CACHE', message: 'PRIVATE_TOKEN'}\n}\n",
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert data["customer_missing_module_category"] == "relative_request"
    assert summary["state"] == "native_binding_error_header"
    assert summary["relative_native_missing_attempts"] == ["swc_linux_x64_gnu_relative"]
    assert summary["observed_error_codes"] == ["MODULE_NOT_FOUND", "ERR_SWC_NATIVE_CACHE"]


def test_all_code_sets_are_finite_despite_duplicate_and_unknown_fields(tmp_path: Path) -> None:
    codes = [
        "MODULE_NOT_FOUND",
        "ERR_MODULE_NOT_FOUND",
        "ERR_DLOPEN_FAILED",
        "EACCES",
        "EPERM",
        "ENOENT",
        "ERR_SWC_NATIVE_FORMAT",
        "ERR_SWC_NATIVE_INTEGRITY",
        "ERR_SWC_NATIVE_COMPRESSION",
        "ERR_SWC_NATIVE_CACHE",
        "ERR_SWC_NATIVE_CONFIGURATION",
        "ERR_SWC_NATIVE_LOAD",
    ]
    data = diagnostics(
        tmp_path,
        "Error: Failed to load native binding {\n"
        + "\n".join(f"  code: '{code}', message: 'PRIVATE_TOKEN'" for code in codes * 20)
        + "\n".join(f"  code: 'PRIVATE_UNKNOWN_{index}'" for index in range(200)),
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["observed_error_codes"] == codes
    assert summary["observed_native_carrier_codes"] == codes[6:]
    assert len(json.dumps(summary)) < 1000


@pytest.mark.parametrize("customer_status", ["running", "0", "unknown", "256", "-1"])
def test_caught_binding_error_header_does_not_prove_terminal_launcher_failure(
    tmp_path: Path, customer_status: str
) -> None:
    data = diagnostics(
        tmp_path,
        "  [cause]: Error: Failed to load native binding {\n"
        "    code: 'ERR_SWC_NATIVE_CACHE'\n  }\nNative fallback succeeded\n",
        customer_status=customer_status,
    )
    summary = data["customer_native_error_summary"]
    assert isinstance(summary, dict)
    assert summary["native_binding_error_header_observed"] is True
    assert summary["customer_launcher_failed"] is False
    assert summary["state"] == "native_binding_error_header"
    assert summary["observed_error_codes"] == ["ERR_SWC_NATIVE_CACHE"]

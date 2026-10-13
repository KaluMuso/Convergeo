from __future__ import annotations

import errno
import importlib.util
import json
import os
import shlex
import stat
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts/qa/cart-response-drill-path-diagnostics.py"
spec = importlib.util.spec_from_file_location("cart_path_diagnostics", HELPER)
assert spec is not None and spec.loader is not None
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def acl(*entries: tuple[int, int, int]) -> bytes:
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)


@pytest.mark.parametrize(
    ("mode", "owner", "group", "expected"),
    [(0o700, 99, 98, (0, "other")), (0o750, 99, 77, (5, "group")), (0o700, 88, 98, (7, "owner"))],
)
def test_mode_access_uses_only_test_identity(
    mode: int, owner: int, group: int, expected: tuple[int, str]
) -> None:
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR | mode, st_uid=owner, st_gid=group)
    with patch.object(os, "getxattr", side_effect=OSError(errno.ENODATA, "private detail")):
        assert diagnostics.access_bits(Path("unused"), metadata, 88, 77) == expected


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([(1, 7, 0), (2, 7, 88), (4, 7, 0), (16, 4, 0), (32, 5, 0)], (4, "acl_test_uid")),
        ([(1, 7, 0), (4, 0, 0), (8, 5, 77), (16, 4, 0), (32, 7, 0)], (4, "acl_test_group")),
        ([(1, 7, 0), (2, 7, 999), (4, 7, 0), (16, 7, 0), (32, 0, 0)], (0, "acl_other")),
    ],
)
def test_acl_masks_and_named_principals_are_respected(
    entries: list[tuple[int, int, int]], expected: tuple[int, str]
) -> None:
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o777, st_uid=99, st_gid=98)
    with patch.object(os, "getxattr", return_value=acl(*entries)):
        assert diagnostics.access_bits(Path("unused"), metadata, 88, 77) == expected


def test_filesystem_without_acl_support_uses_mode_bits() -> None:
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=99, st_gid=98)
    with patch.object(os, "getxattr", side_effect=OSError(errno.ENOTSUP, "private detail")):
        assert diagnostics.access_bits(Path("unused"), metadata, 88, 77) == (0, "other")


def test_unreadable_acl_is_unknown_not_a_confirmed_mode_denial() -> None:
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=99, st_gid=98)
    with patch.object(os, "getxattr", side_effect=OSError(errno.EACCES, "SECRET_HOST_VALUE")):
        assert diagnostics.access_bits(Path("unused"), metadata, 88, 77) == (None, "unavailable")


def test_mount_flags_select_longest_mount_and_do_not_emit_source() -> None:
    table = "\n".join(
        [
            "1 0 0:1 / / rw - ext4 SECRET_DEVICE rw",
            r"2 1 0:2 / /sdk\040private rw,noexec,nosuid,nodev - tmpfs SECRET_MOUNT rw",
        ]
    )
    assert diagnostics.mount_flags(Path("/sdk private/bin/python"), table) == {
        "noexec": True,
        "nosuid": True,
        "nodev": True,
        "ro": False,
    }
    assert diagnostics.mount_flags(Path("/sdk private-other/bin/python"), table)["noexec"] is False


def layout(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "SECRET_HOST_USER"
    private.mkdir(mode=0o700)
    workspace = private / "checkout"
    invocation = workspace / "services/api/.venv/bin/python"
    invocation.parent.mkdir(parents=True)
    sdk = tmp_path / "SECRET_SDK_ENV_VALUE"
    target = sdk / "bin/python3.12"
    target.parent.mkdir(parents=True)
    target.write_text("SECRET_FILE_PAYLOAD")
    target.chmod(0o755)
    invocation.symlink_to(target)
    return workspace, sdk


def test_real_metadata_identifies_private_ancestor_without_host_path_or_payload(
    tmp_path: Path,
) -> None:
    workspace, sdk = layout(tmp_path)
    result = subprocess.run(
        ["python3", str(HELPER), str(workspace), str(sdk), "424242", "424243"],
        capture_output=True,
        text=True,
        env={"PATH": os.defpath, "SECRET_ENV": "SECRET_ENV_VALUE"},
    )
    assert result.returncode == 0, result.stderr
    for private in (
        str(tmp_path),
        "SECRET_HOST_USER",
        "SECRET_SDK_ENV_VALUE",
        "SECRET_FILE_PAYLOAD",
        "SECRET_ENV_VALUE",
        "424243",
    ):
        assert private not in result.stdout
    receipt = json.loads(result.stdout)
    assert receipt["resolved_into_python_sdk"] is True
    row = next(row for row in receipt["paths"] if row["path_alias"] == "workspace:ancestor_up=1")
    assert row["mode"] == "0700"
    assert row["test_uid_search_or_execute"] is False
    assert "workspace:ancestor_up=1" in receipt["permission_denial_candidates"]
    assert receipt["test_uid"] == 424242
    assert (sdk / "bin/python3.12").read_text() == "SECRET_FILE_PAYLOAD"
    assert stat.S_IMODE(workspace.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    ("probe_exit", "diagnostic_failure"), [(0, False), (126, False), (126, True)]
)
def test_shell_collects_only_on_failure_and_preserves_probe_exit(
    tmp_path: Path, probe_exit: int, diagnostic_failure: bool
) -> None:
    workspace, sdk = layout(tmp_path)
    helper_link = workspace / "scripts/qa/cart-response-drill-path-diagnostics.py"
    helper_link.parent.mkdir(parents=True)
    if not diagnostic_failure:
        helper_link.symlink_to(HELPER)
    output = workspace / "e2e/results/cart-response-drill"
    output.mkdir(parents=True)
    shell = (ROOT / "scripts/qa/run-cart-response-drill.sh").read_text()
    block = shell[shell.index("if drill_as_user") : shell.index("drill_phase=server_startup")]
    setup = "\n".join(
        [
            "set -euo pipefail",
            f"drill_root={shlex.quote(str(workspace))}",
            f"drill_output={shlex.quote(str(output))}",
            f"pythonLocation={shlex.quote(str(sdk))}",
            "drill_uid=424242",
            "id() { echo 424243; }",
            f"drill_as_user() {{ return {probe_exit}; }}",
        ]
    )
    result = subprocess.run(["bash", "-c", setup + "\n" + block], capture_output=True, text=True)
    assert result.returncode == probe_exit, result.stderr
    assert (output / "python-path-diagnostics.json").exists() is (probe_exit != 0)
    if diagnostic_failure:
        assert (output / "python-path-diagnostics.json").read_text() == ""


def test_publication_allowlist_keeps_private_probe_log_out_of_artifact() -> None:
    workflow = (ROOT / ".github/workflows/perf.yml").read_text()
    upload = workflow.split("name: Upload cart response drill evidence", 1)[1].split(
        "- name: Stop servers", 1
    )[0]
    assert "e2e/results/cart-response-drill/python-path-diagnostics.json" in upload
    assert "private-python-probe.log" not in upload
    assert "include-hidden-files" not in upload

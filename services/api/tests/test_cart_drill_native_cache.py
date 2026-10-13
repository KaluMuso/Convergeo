from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SHELL = ROOT / "scripts/qa/run-cart-response-drill.sh"


class FixtureOS:
    """Model trusted host ancestors, without changing real OS permissions/UIDs."""

    def __init__(self) -> None:
        self.root_owner = 0
        self.tmp_owner = 0
        self.tmp_mode = stat.S_IFDIR | 0o1777
        self.tmp_identity = (os.stat("/tmp").st_dev, os.stat("/tmp").st_ino)

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)

    def lstat(self, path: str) -> Any:
        if path == "/":
            return types.SimpleNamespace(st_uid=self.root_owner, st_mode=stat.S_IFDIR | 0o755)
        if path == "/tmp":
            return types.SimpleNamespace(st_uid=self.tmp_owner, st_mode=self.tmp_mode)
        return os.lstat(path)

    def fstat(self, descriptor: int) -> Any:
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) == self.tmp_identity:
            return types.SimpleNamespace(st_uid=self.tmp_owner, st_mode=self.tmp_mode)
        return metadata


@pytest.fixture
def guard() -> types.ModuleType:
    shell = SHELL.read_text()
    code = shell.split("# Native cache guard (stdlib only).", 1)[1]
    code = code.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    module = types.ModuleType("_synthetic_native_cache_guard")
    exec(compile(code, str(SHELL), "exec"), module.__dict__)
    module.__dict__["os"] = FixtureOS()
    return module


@pytest.fixture
def allocated(
    guard: types.ModuleType, capsys: pytest.CaptureFixture[str]
) -> Iterator[tuple[types.ModuleType, dict[str, Any]]]:
    guard.allocate(os.geteuid(), os.getegid())
    result = capsys.readouterr()
    assert result.err == ""
    record = guard.parse_record(result.out)
    yield guard, record
    # Only directories/links created by this fixture are removed. No sudo,
    # shared resources, UID changes, native libraries or service processes.
    path = Path(record["path"])
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def test_fresh_private_allocation_and_identity_safe_removal(
    allocated: tuple[types.ModuleType, dict[str, Any]], tmp_path: Path
) -> None:
    guard, record = allocated
    path = Path(record["path"])
    assert path.parent == Path("/tmp")
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert path.stat().st_uid == os.geteuid()
    assert path.stat().st_gid == os.getegid()
    assert guard.verify(record, os.geteuid(), os.getegid()) == str(path)
    outside = tmp_path / "protected"
    outside.mkdir()
    (outside / "keep").write_text("PRIVATE_OUTSIDE_CONTENT")
    (path / "namespace").mkdir()
    (path / "namespace/link").symlink_to(outside, target_is_directory=True)
    (path / "namespace/image.node").write_bytes(b"synthetic; never executed")
    (path / "top-link").symlink_to(outside, target_is_directory=True)
    guard.remove(record, os.geteuid(), os.getegid())
    assert not path.exists()
    assert (outside / "keep").read_text() == "PRIVATE_OUTSIDE_CONTENT"
    with pytest.raises(OSError):
        guard.remove(record, os.geteuid(), os.getegid())


@pytest.mark.parametrize(
    "value",
    [
        "",
        "{",
        "[]",
        "null",
        "PRIVATE_TOKEN" * 100,
        '{"path":"/tmp","device":1,"inode":2}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh/child","device":1,"inode":2}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh/../outside","device":1,"inode":2}',
        '{"path":"tmp/cartdrill-swc.abcdefgh","device":1,"inode":2}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh?token=PRIVATE_TOKEN","device":1,"inode":2}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh","device":true,"inode":2}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh","device":1,"inode":0}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh","device":-1,"inode":2}',
        '{"path":"/tmp/cartdrill-swc.abcdefgh","device":1,"inode":2,"extra":"PRIVATE"}',
    ],
)
def test_malformed_outside_or_nonidentity_records_are_refused(
    guard: types.ModuleType, value: str
) -> None:
    with pytest.raises((ValueError, TypeError)):
        guard.parse_record(value)


@pytest.mark.parametrize("field", ["device", "inode", "uid", "gid", "mode", "missing"])
def test_changed_allocation_metadata_is_refused_without_deletion(
    allocated: tuple[types.ModuleType, dict[str, Any]], field: str
) -> None:
    guard, record = allocated
    path = Path(record["path"])
    changed = dict(record)
    uid, gid = os.geteuid(), os.getegid()
    if field in {"device", "inode"}:
        changed[field] += 1
    elif field == "uid":
        uid += 1
    elif field == "gid":
        gid += 1
    elif field == "mode":
        path.chmod(0o701)
    else:
        path.rmdir()
    with pytest.raises((ValueError, OSError)):
        guard.remove(changed, uid, gid)
    if field != "missing":
        assert path.exists()


@pytest.mark.parametrize("change", ["root_owner", "tmp_owner", "tmp_mode", "tmp_symlink"])
def test_untrusted_parent_is_rejected_before_allocation(
    guard: types.ModuleType, capsys: pytest.CaptureFixture[str], change: str
) -> None:
    if change in {"root_owner", "tmp_owner"}:
        setattr(guard.os, change, 12345)
    else:
        guard.os.tmp_mode = (
            (stat.S_IFLNK | 0o777) if change == "tmp_symlink" else stat.S_IFDIR | 0o777
        )
    with pytest.raises(ValueError):
        guard.allocate(os.geteuid(), os.getegid())
    assert capsys.readouterr().out == ""


def test_different_uid_cannot_allocate(
    guard: types.ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ValueError):
        guard.allocate(os.geteuid() + 1, os.getegid())
    assert capsys.readouterr().out == ""


def test_postallocation_failure_keeps_identity_record_for_exit_cleanup(
    guard: types.ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any) -> None:
        raise ValueError("synthetic validation failure")

    monkeypatch.setattr(guard, "checked_cache", fail)
    with pytest.raises(ValueError):
        guard.allocate(os.geteuid(), os.getegid())
    record = guard.parse_record(capsys.readouterr().out)
    path = Path(record["path"])
    assert (path.stat().st_dev, path.stat().st_ino) == (record["device"], record["inode"])
    path.rmdir()


@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_replaced_allocation_is_never_deleted(
    allocated: tuple[types.ModuleType, dict[str, Any]], tmp_path: Path, replacement: str
) -> None:
    guard, record = allocated
    path = Path(record["path"])
    original = tmp_path / "original"
    path.rename(original)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("PRIVATE_KEEP")
    if replacement == "directory":
        path.mkdir(mode=0o700)
        (path / "keep").write_text("PRIVATE_KEEP")
    else:
        path.symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        guard.remove(record, os.geteuid(), os.getegid())
    assert original.exists()
    assert (outside / "keep").exists()
    assert path.exists()


def test_opened_inode_must_match_the_prechecked_entry(
    allocated: tuple[types.ModuleType, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard, record = allocated
    path = Path(record["path"])
    original = tmp_path / "original"

    def swapped_open(name: str, flags: int, **kwargs: Any) -> int:
        if name == path.name:
            path.rename(original)
            path.mkdir(mode=0o700)
            (path / "keep").write_text("PRIVATE_KEEP")
        return os.open(name, flags, **kwargs)

    monkeypatch.setattr(guard.os, "open", swapped_open, raising=False)
    with pytest.raises(ValueError):
        guard.remove(record, os.geteuid(), os.getegid())
    assert (path / "keep").exists()
    assert original.exists()


@pytest.mark.parametrize("mount_suffix", ["", "/nested"])
def test_mounted_allocation_or_subtree_is_not_traversed(
    allocated: tuple[types.ModuleType, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    mount_suffix: str,
) -> None:
    guard, record = allocated
    path = Path(record["path"])
    (path / "keep").write_text("PRIVATE_KEEP")
    monkeypatch.setattr(guard, "mount_paths", lambda: [str(path) + mount_suffix])
    with pytest.raises(ValueError):
        guard.remove(record, os.geteuid(), os.getegid())
    assert (path / "keep").exists()


def test_cleanup_rechecks_top_identity_after_removing_only_opened_allocation_contents(
    allocated: tuple[types.ModuleType, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard, record = allocated
    path = Path(record["path"])
    (path / "image.node").write_bytes(b"synthetic; never executed")
    original = tmp_path / "original"
    lookups = 0

    def swapped_stat(name: str, **kwargs: Any) -> os.stat_result:
        nonlocal lookups
        if name == path.name:
            lookups += 1
            if lookups == 2:
                path.rename(original)
                path.mkdir(mode=0o700)
                (path / "keep").write_text("PRIVATE_KEEP")
        return os.stat(name, **kwargs)

    monkeypatch.setattr(guard.os, "stat", swapped_stat, raising=False)
    with pytest.raises(ValueError):
        guard.remove(record, os.geteuid(), os.getegid())
    assert (path / "keep").exists()
    assert original.exists()


@pytest.mark.parametrize("stage", ["allocate", "verify", "remove", "PRIVATE_ACTION"])
def test_command_failures_emit_only_fixed_error_text(
    guard: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    monkeypatch.setattr(
        guard,
        "sys",
        types.SimpleNamespace(
            argv=["-", stage, str(os.geteuid()), str(os.getegid()), "PRIVATE_TOKEN /PRIVATE_PATH"],
            stderr=sys.stderr,
        ),
    )
    assert guard.main() == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert result.err == "Private native cache guard failed\n"


@pytest.mark.parametrize("stage", ["verify", "remove"])
def test_command_io_failure_preserves_allocation_and_redacts_exception(
    allocated: tuple[types.ModuleType, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    guard, record = allocated

    def fail(*args: Any) -> None:
        raise OSError("PRIVATE_TOKEN /PRIVATE_CACHE_PATH")

    monkeypatch.setattr(guard, "checked_cache", fail)
    monkeypatch.setattr(
        guard,
        "sys",
        types.SimpleNamespace(
            argv=["-", stage, str(os.geteuid()), str(os.getegid()), json.dumps(record)],
            stderr=sys.stderr,
        ),
    )
    assert guard.main() == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert result.err == "Private native cache guard failed\n"
    assert Path(record["path"]).exists()


def test_actual_guarded_launcher_adds_only_generated_absolute_cache_setting(
    allocated: tuple[types.ModuleType, dict[str, Any]], tmp_path: Path
) -> None:
    _, record = allocated
    project = tmp_path / "runtime/apps/customer"
    project.mkdir(parents=True)
    shell = SHELL.read_text()
    function = (
        "drill_as_user() {"
        + shell.split("drill_as_user() {", 1)[1].split(
            "# No new package, image, database or provider", 1
        )[0]
    )
    trace = tmp_path / "argv"
    script = (
        function
        + f"""
sudo() {{ printf '%s\\0' "$@" > {shlex.quote(str(trace))}; }}
drill_root={shlex.quote(str(tmp_path / "runtime"))}
drill_package_root="$drill_root"; drill_uid=123
drill_swc_cache_root={shlex.quote(record["path"])}
drill_python_library=/public-python/lib; drill_browser_path=/public-browser
SUPABASE_ANON_KEY=synthetic-anon; SUPABASE_SERVICE_ROLE_KEY=synthetic-service
drill_as_user --customer-project /synthetic-node next dev --hostname 127.0.0.1
"""
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == result.stderr == ""
    assert trace.read_bytes().decode().split("\0")[:-1] == [
        "-u",
        "cartdrill",
        "env",
        "-i",
        "PATH=/usr/bin:/bin",
        "CART_DRILL_LOCAL=1",
        "CART_DRILL_UID=123",
        "PYTHONNOUSERSITE=1",
        "PYTHONDONTWRITEBYTECODE=1",
        f"TMPDIR={tmp_path}/runtime/tmp",
        f"XDG_CACHE_HOME={tmp_path}/runtime/cache",
        f"XDG_CONFIG_HOME={tmp_path}/runtime/config",
        "SWC_NATIVE_BINDING_CACHE=" + record["path"],
        "LD_LIBRARY_PATH=/public-python/lib",
        "PLAYWRIGHT_BROWSERS_PATH=/public-browser",
        "SUPABASE_URL=http://127.0.0.1:54321",
        "SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        "SUPABASE_ANON_KEY=synthetic-anon",
        "SUPABASE_SERVICE_ROLE_KEY=synthetic-service",
        "NEXT_PUBLIC_DEPLOYMENT_PLANE=development",
        "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000",
        "NEXT_PUBLIC_SITE_URL=http://127.0.0.1:3000",
        "NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY=synthetic-anon",
        "ENV=development",
        "CORS_ORIGINS=http://127.0.0.1:3000",
        "NEXT_TELEMETRY_DISABLED=1",
        "CI=1",
        "/synthetic-node",
        "next",
        "dev",
        "--hostname",
        "127.0.0.1",
    ]


@pytest.mark.parametrize(
    "pgrep_status, requested, record, remove_status, pkill_status, deleted",
    [
        (1, "true", "tracked", 0, 0, True),
        (0, "true", "tracked", 0, 0, False),
        (2, "true", "tracked", 0, 0, False),
        (1, "true", "", 0, 0, False),
        (1, "true", "tracked", 1, 0, False),
        (1, "true", "tracked", 0, 2, False),
        (1, "false", "", 0, 0, True),
    ],
)
def test_actual_cleanup_requires_stopped_uid_and_deletes_cache_before_user(
    tmp_path: Path,
    pgrep_status: int,
    requested: str,
    record: str,
    remove_status: int,
    pkill_status: int,
    deleted: bool,
) -> None:
    shell = SHELL.read_text()
    functions = shell.split("drill_launcher_status() {", 1)[1].split("trap drill_cleanup EXIT", 1)[
        0
    ]
    functions = "drill_launcher_status() {" + functions
    trace = tmp_path / "trace"
    script = (
        functions
        + f"""
sudo() {{
  case "$1" in
    test) return 1 ;;
    pkill) echo stop >> {shlex.quote(str(trace))}; return {pkill_status} ;;
    pgrep) echo probe >> {shlex.quote(str(trace))}; return {pgrep_status} ;;
    iptables|ip6tables) echo firewall >> {shlex.quote(str(trace))}; return 0 ;;
    userdel) echo userdel >> {shlex.quote(str(trace))}; return 0 ;;
    *) return 99 ;;
  esac
}}
sleep() {{ :; }}
drill_native_cache() {{ echo cache-remove >> {shlex.quote(str(trace))}; return {remove_status}; }}
drill_created=true; drill_uid=1000; drill_v4=true; drill_v6=true
drill_output={shlex.quote(str(tmp_path / "absent"))}; drill_package_root=
drill_api_launcher=; drill_customer_launcher=
drill_swc_cache_requested={requested}; drill_swc_cache_record={shlex.quote(record)}
true
drill_cleanup
"""
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.stdout == result.stderr == ""
    events = trace.read_text().splitlines()
    assert events[0] == "stop"
    assert ("userdel" in events) == deleted
    assert result.returncode == (0 if deleted else 1)
    if "cache-remove" in events:
        assert events[events.index("cache-remove") - 1] == "probe"
        if deleted:
            assert events.index("cache-remove") < events.index("userdel")
    else:
        assert not requested == "true" or not deleted


def test_allocation_follows_installed_hooks_and_preserves_existing_runtime_boundaries() -> None:
    shell = SHELL.read_text()
    assert shell.index("drill_swc_cache_record=$(drill_native_cache allocate)") > shell.rindex(
        "sudo ip6tables -w -C OUTPUT"
    )
    assert shell.index("drill_swc_cache_root=$(drill_native_cache verify)") < shell.index(
        "drill_phase=python_preflight"
    )
    assert "cache_python=(sudo -u cartdrill env -i PATH=/usr/bin:/bin python3)" in shell
    assert 'SWC_NATIVE_BINDING_CACHE="$drill_swc_cache_root"' in shell
    assert "SWC_NATIVE_BINDING_CACHE_SKIP_SECURITY_CHECK" not in shell
    assert "NAPI_RS_FORCE_WASI" not in shell
    assert 'sudo chown -hR "$(id -u):cartdrill" "$drill_package_root"' in shell
    assert 'TMPDIR="$drill_package_root/tmp" XDG_CACHE_HOME="$drill_package_root/cache"' in shell


@pytest.mark.parametrize("action", ["allocate", "verify", "remove"])
def test_cache_wrapper_uses_dedicated_uid_for_private_reads_and_privileged_scoped_removal(
    tmp_path: Path, action: str
) -> None:
    shell = SHELL.read_text()
    function = (
        "drill_native_cache() {"
        + shell.split("drill_native_cache() {", 1)[1].split("drill_launcher_status() {", 1)[0]
    )
    trace = tmp_path / "argv"
    script = (
        function
        + f"""
sudo() {{ printf '%s\\0' "$@" > {shlex.quote(str(trace))}; }}
drill_uid=123; drill_gid=456; drill_swc_cache_record=synthetic-record
drill_native_cache {action}
"""
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == result.stderr == ""
    caller = ["-u", "cartdrill"] if action in {"allocate", "verify"} else []
    assert trace.read_bytes().decode().split("\0")[:-1] == caller + [
        "env",
        "-i",
        "PATH=/usr/bin:/bin",
        "python3",
        "-",
        action,
        "123",
        "456",
        "synthetic-record",
    ]

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "cart_drill_package", ROOT / "scripts/qa/cart-response-drill-package.py"
)
assert spec is not None and spec.loader is not None
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    python = source / "python"
    python.write_bytes(b"verified interpreter bytes")
    python.chmod(0o755)
    plan = package.Plan()
    plan.file(python, "services/api/.venv/bin/python")
    plan.file(b"include-system-site-packages = false\n", "services/api/.venv/pyvenv.cfg")
    code = source / "main.py"
    code.write_bytes(b"verified source bytes")
    plan.file(code, "services/api/app/main.py")
    plan.link("apps/customer/node_modules/example", "services/api/app")
    destination = tmp_path / "stage"
    destination.mkdir()
    blob = hashlib.sha1(b"blob 21\0verified source bytes").hexdigest()
    digest = package.materialize(
        plan, destination, "a" * 40, "3.12.15", {"services/api/app/main.py": blob}, "b" * 40
    )
    return source, destination, digest


def test_independent_copies_and_deterministic_manifest(tmp_path: Path) -> None:
    source, destination, digest = fixture(tmp_path)
    receipt = package.verify(destination, digest)
    assert receipt["source_sha"] == "a" * 40
    assert receipt["source_tree"] == "b" * 40
    repeat = tmp_path / "repeat"
    repeat.mkdir()
    assert fixture(repeat)[2] == digest
    copied = destination / "services/api/.venv/bin/python"
    assert copied.read_bytes() == (source / "python").read_bytes()
    assert copied.stat().st_ino != (source / "python").stat().st_ino
    copied.chmod(0o700)
    assert stat.S_IMODE((source / "python").stat().st_mode) == 0o755
    with pytest.raises(package.PackageInputError):
        package.verify(destination, digest)


@pytest.mark.parametrize(
    "change", ["missing", "unexpected", "bytes", "mode", "manifest", "private_link"]
)
def test_verification_refuses_changed_inventory(tmp_path: Path, change: str) -> None:
    _, destination, digest = fixture(tmp_path)
    path = destination / "services/api/app/main.py"
    if change == "missing":
        path.unlink()
    elif change == "unexpected":
        (destination / "unexpected-input").write_text("extra")
    elif change == "bytes":
        path.write_text("different")
    elif change == "mode":
        path.chmod(0o777)
    elif change == "manifest":
        data = json.loads((destination / "input-manifest.json").read_text())
        data["entries"]["unapproved"] = {"type": "file"}
        (destination / "input-manifest.json").write_bytes(package.canonical(data))
    else:
        link = destination / "apps/customer/node_modules/example"
        link.unlink()
        link.symlink_to(tmp_path / "PRIVATE_HOME")
    with pytest.raises((package.PackageInputError, OSError)):
        package.verify(destination, digest)


def test_unapproved_manifest_entry_is_refused_even_with_a_new_hash(tmp_path: Path) -> None:
    _, destination, _ = fixture(tmp_path)
    path = destination / "unapproved-input"
    path.write_bytes(b"extra")
    path.chmod(0o640)
    data = json.loads((destination / "input-manifest.json").read_text())
    data["entries"]["unapproved-input"] = {
        "type": "file",
        "sha256": package.digest(path),
        "size": 5,
        "mode": "0640",
    }
    manifest = destination / "input-manifest.json"
    manifest.write_bytes(package.canonical(data))
    with pytest.raises(package.PackageInputError, match="unexpected runtime manifest entry"):
        package.verify(destination, package.digest(manifest))


@pytest.mark.parametrize("kind", ["private_link", "missing", "setuid", "fifo", "credential"])
def test_source_plan_refuses_unsafe_inputs(tmp_path: Path, kind: str) -> None:
    plan = package.Plan()
    source = tmp_path / "input"
    if kind == "private_link":
        private = tmp_path / "PRIVATE_HOME"
        private.write_text("must not copy")
        source.symlink_to(private)
    elif kind == "setuid":
        source.write_text("unsafe")
        source.chmod(0o4755)
    elif kind == "fifo":
        os.mkfifo(source)
    elif kind == "credential":
        source.write_text("must not copy")
    with pytest.raises(package.PackageInputError):
        plan.file(source, ".env" if kind == "credential" else "services/api/app/input.py")


def test_tree_refuses_private_directory_symlink_before_copy(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    private = tmp_path / "PRIVATE_HOME"
    private.mkdir()
    (private / "credentials").write_text("must not copy")
    (source / "escape").symlink_to(private, target_is_directory=True)
    with pytest.raises(package.PackageInputError, match="external tree symlink"):
        package.Plan().tree(source, ".runtime/browsers/chromium_headless_shell-1194")


def test_node_closure_keeps_peers_and_installed_optional_native_inputs(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    store = root / "node_modules/.pnpm"
    store.mkdir(parents=True)
    locked: dict[str, dict[str, str]] = {}

    def installed(
        name: str,
        dependencies: dict[str, str] | None = None,
        optional: dict[str, str] | None = None,
        peers: dict[str, str] | None = None,
        version: str = "1.0.0",
    ) -> Path:
        path = store / name.replace("/", "+") / "node_modules" / name
        path.mkdir(parents=True)
        (path / "package.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": version,
                    "dependencies": dependencies or {},
                    "optionalDependencies": optional or {},
                    "peerDependencies": peers or {},
                }
            )
        )
        (path / "native.node").write_bytes(b"verified optional native bytes")
        locked[f"{name}@{version}"] = {}
        slot = root / "node_modules" / name
        slot.parent.mkdir(parents=True, exist_ok=True)
        slot.symlink_to(os.path.relpath(path, slot.parent), target_is_directory=True)
        return path

    for name in package.CONFIG_DEPS:
        installed(name)
    installed("peer")
    installed("native")
    installed("core", optional={"native": "1", "absent-platform": "1"}, peers={"peer": "1"})
    for folder in [
        root / "apps/customer",
        *(root / "packages" / name for name in package.WORKSPACES),
    ]:
        folder.mkdir(parents=True)
        (folder / "package.json").write_text(json.dumps({"dependencies": {"core": "1"}}))
    playwright = root / "e2e/node_modules/@playwright/test"
    playwright.mkdir(parents=True)
    (playwright / "package.json").write_text(
        json.dumps({"name": "@playwright/test", "version": "1.56.1"})
    )
    (root / "pnpm-lock.yaml").write_text(json.dumps({"packages": locked}))
    plan = package.Plan()
    package.node_inputs(plan, root)
    assert any("native/native.node" in name for name in plan.files)
    assert any("peer/native.node" in name for name in plan.files)
    assert all(not Path(link).is_absolute() for link in plan.links.values())
    (root / "node_modules/peer").unlink()
    with pytest.raises(package.PackageInputError, match="required installed Node dependency"):
        package.node_inputs(package.Plan(), root)


def test_python_runtime_extras_resources_record_hashes_and_editable_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "checkout"
    site = root / "services/api/.venv/lib/python3.12/site-packages"
    site.mkdir(parents=True)
    sdk = tmp_path / "sdk"
    (sdk / "bin").mkdir(parents=True)
    (sdk / "bin/python3.12").write_text("verified interpreter")
    for name in ("lib/libpython3.12.so.1.0", "lib/python3.12/site.py", "lib/python3.12/ssl.py"):
        path = sdk / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("verified SDK input")
    (root / "services/api/.venv/bin").mkdir()
    (root / "services/api/.venv/bin/python").symlink_to(sdk / "bin/python3.12")
    lock = """
[[package]]
name="vergeo5-api"
version="0.1.0"
dependencies=[
  {name="driver",extra=["binary"]},
  {name="windows-only",marker="sys_platform == 'win32'"}
]
[[package]]
name="driver"
version="1"
[package.optional-dependencies]
binary=[{name="native"}]
[[package]]
name="native"
version="1"
"""
    (root / "services/api/uv.lock").write_text(lock)
    records = {}
    for name in ("driver", "native"):
        path = site / f"{name}/resource.dat"
        path.parent.mkdir()
        path.write_bytes(b"verified runtime resource")
        hash_value = (
            base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
            .decode()
            .rstrip("=")
        )
        records[name] = f"{name}/resource.dat,sha256={hash_value},{path.stat().st_size}\n"
    distributions = [
        SimpleNamespace(
            metadata={"Name": name}, version="1", read_text=lambda field, name=name: records[name]
        )
        for name in records
    ]
    monkeypatch.setattr(package.importlib.metadata, "distributions", lambda **kwargs: distributions)
    plan = package.Plan()
    package.python_inputs(plan, root, sdk)
    assert "services/api/.venv/lib/python3.12/site-packages/native/resource.dat" in plan.files
    assert (
        "include-system-site-packages = false"
        in plan.files["services/api/.venv/pyvenv.cfg"].decode()
    )
    (site / "native/resource.dat").write_text("modified")
    with pytest.raises(package.PackageInputError, match="RECORD byte identity"):
        package.python_inputs(package.Plan(), root, sdk)
    records["driver"] += "editable.pth,,\n"
    with pytest.raises(package.PackageInputError, match="private Python hook"):
        package.python_inputs(package.Plan(), root, sdk)


def test_runner_preserves_isolation_and_packages_before_any_application_process() -> None:
    shell = (ROOT / "scripts/qa/run-cart-response-drill.sh").read_text()
    assert shell.index("mktemp -d /tmp/cartdrill.") > shell.index("sudo ip6tables -w -C OUTPUT")
    assert shell.index("drill_package_verified=true") < shell.index("drill_phase=python_preflight")
    assert 'sudo chown -hR "$(id -u):cartdrill" "$drill_package_root"' in shell
    assert 'drill_root="$drill_package_root"' in shell
    assert "supabase db" not in shell
    assert (
        "chmod" not in shell[shell.index("drill_source_root=") : shell.index("drill_package_root=")]
    )
    assert (
        "private-api.log"
        not in (ROOT / ".github/workflows/perf.yml")
        .read_text()
        .split("name: Upload cart response drill evidence")[1]
    )

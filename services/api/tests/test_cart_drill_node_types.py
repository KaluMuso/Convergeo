from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "cart_drill_node_types_package", ROOT / "scripts/qa/cart-response-drill-package.py"
)
assert spec is not None and spec.loader is not None
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def graph(tmp_path: Path, *, direct: bool = False) -> tuple[Path, Path]:
    root = tmp_path / "checkout"
    customer = root / "apps/customer"
    customer.mkdir(parents=True)
    (customer / "package.json").write_text('{"name":"customer"}')
    for name in package.WORKSPACES:
        folder = root / "packages" / name
        folder.mkdir(parents=True)
        (folder / "package.json").write_text("{}")
    locked: dict[str, dict[str, str]] = {}

    def installed(name: str, version: str, parent: Path) -> Path:
        path = (
            root
            / "node_modules/.pnpm"
            / f"{name.replace('/', '+')}@{version}"
            / "node_modules"
            / name
        )
        path.mkdir(parents=True)
        (path / "package.json").write_text(json.dumps({"name": name, "version": version}))
        if name == "@types/node":
            (path / "index.d.ts").write_text("verified existing Node declarations")
        slot = parent / "node_modules" / name
        slot.parent.mkdir(parents=True, exist_ok=True)
        slot.symlink_to(os.path.relpath(path, slot.parent), target_is_directory=True)
        locked[f"{name}@{version}"] = {}
        return path

    for name in package.CONFIG_DEPS:
        installed(name, "1.0.0", customer)
    target = installed("@types/node", "22.20.1", root / "packages/config")
    if direct:
        installed("@types/node", "22.20.2", customer)
    playwright = root / "e2e/node_modules/@playwright/test"
    playwright.mkdir(parents=True)
    (playwright / "package.json").write_text('{"name":"@playwright/test","version":"1.56.1"}')
    (root / "pnpm-lock.yaml").write_text(json.dumps({"packages": locked}))
    return root, target


@pytest.mark.parametrize("direct", [False, True])
def test_customer_resolves_verified_node_types_without_a_new_distribution(
    tmp_path: Path, direct: bool
) -> None:
    root, fallback = graph(tmp_path, direct=direct)
    original = (fallback / "index.d.ts").read_bytes()
    plan = package.Plan()
    package.node_inputs(plan, root)
    source = root / "apps/customer/package.json"
    plan.file(source, "apps/customer/package.json")
    interpreter = root / "fixture-python"
    interpreter.write_bytes(b"fixture interpreter")
    interpreter.chmod(0o755)
    plan.file(interpreter, "services/api/.venv/bin/python")
    plan.file(b"include-system-site-packages = false\n", "services/api/.venv/pyvenv.cfg")
    stage = tmp_path / "stage"
    stage.mkdir()
    contents = source.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(contents)).encode() + b"\0" + contents).hexdigest()
    digest = package.materialize(
        plan, stage, "a" * 40, "3.12.15", {"apps/customer/package.json": blob}, "b" * 40
    )
    manifest = package.verify(stage, digest)
    node = shutil.which("node")
    assert node is not None
    script = (
        "const {createRequire}=require('node:module');const fs=require('node:fs');"
        "const req=createRequire(process.argv[1]);"
        "const file=req.resolve('@types/node/package.json');"
        "const metadata=JSON.parse(fs.readFileSync(file));"
        "console.log(JSON.stringify({name:metadata.name,version:metadata.version}));"
    )
    result = subprocess.run(
        [node, "-e", script, str(stage / "apps/customer/package.json")],
        env={"PATH": os.environ["PATH"]},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "name": "@types/node",
        "version": "22.20.2" if direct else "22.20.1",
    }
    alias = "apps/customer/node_modules/@types/node"
    assert manifest["entries"][alias]["type"] == "symlink"
    assert not Path(manifest["entries"][alias]["target"]).is_absolute()
    assert (fallback / "index.d.ts").read_bytes() == original
    assert (stage / alias / "index.d.ts").read_bytes() == original


@pytest.mark.parametrize("change", ["missing", "declaration", "private", "unlocked"])
def test_customer_node_types_reject_missing_private_or_unlocked_inputs(
    tmp_path: Path, change: str
) -> None:
    root, target = graph(tmp_path)
    slot = root / "packages/config/node_modules/@types/node"
    if change == "missing":
        slot.unlink()
    elif change == "declaration":
        (target / "index.d.ts").unlink()
    elif change == "private":
        private = tmp_path / "PRIVATE_HOME"
        private.mkdir()
        (private / "package.json").write_text("must not read or copy")
        slot.unlink()
        slot.symlink_to(private, target_is_directory=True)
    else:
        (target / "package.json").write_text('{"name":"@types/node","version":"22.20.9"}')
    with pytest.raises(package.PackageInputError):
        package.node_inputs(package.Plan(), root)

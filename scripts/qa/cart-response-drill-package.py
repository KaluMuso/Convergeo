"""Package only the disposable drill's installed runtime; never fetch dependencies."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

WORKSPACES = ("analytics", "auth", "config", "i18n", "observability", "types", "ui")
CONFIG_DEPS = (
    "@serwist/next",
    "@tailwindcss/postcss",
    "tailwindcss",
    "typescript",
    "@types/react",
    "@types/react-dom",
)
FIXED = (
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "tsconfig.base.json",
    "services/api/pyproject.toml",
    "services/api/uv.lock",
    "e2e/package.json",
    "e2e/scripts/cart-response-drill.mjs",
    "scripts/qa/cart-response-drill-db.py",
    "scripts/qa/cart-response-drill-package.py",
    "scripts/qa/cart-response-drill-path-diagnostics.py",
)


class PackageInputError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise PackageInputError(reason)


def relative(value: str) -> Path:
    path = Path(value)
    require(
        bool(value) and not path.is_absolute() and ".." not in path.parts, "invalid manifest path"
    )
    require(path.as_posix() == value and value != ".", "noncanonical manifest path")
    return path


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def forbidden(path: Path) -> bool:
    return any(
        part.startswith(".env") or part in {".git", ".ssh", ".aws", ".npmrc", ".pypirc"}
        for part in path.parts
    )


class Plan:
    def __init__(self) -> None:
        self.files: dict[str, Path | bytes] = {}
        self.links: dict[str, str] = {}
        self.public_sdk_hashes: dict[str, str] = {}

    def file(self, source: Path | bytes, target: str) -> None:
        relative(target)
        require(not forbidden(Path(target)), "credential-shaped input refused")
        require(target not in self.links, "conflicting input")
        if isinstance(source, Path):
            require(source.is_file() and not source.is_symlink(), "missing or linked file input")
            require(not source.stat().st_mode & 0o6000, "privileged input mode refused")
            try:
                capability = os.getxattr(source, "security.capability")
            except OSError as error:
                require(error.errno in (61, 95), "input capability metadata unavailable")
            else:
                require(not capability, "privileged input capability refused")
        require(target not in self.files or self.files[target] == source, "conflicting input")
        self.files[target] = source

    def link(self, target: str, destination: str) -> None:
        relative(target)
        relative(destination)
        require(not forbidden(Path(target)), "credential-shaped input refused")
        require(target not in self.files, "conflicting input")
        link = os.path.relpath(destination, Path(target).parent)
        require(target not in self.links or self.links[target] == link, "conflicting link input")
        self.links[target] = link

    def tree(self, source: Path, target: str, *, skip_node_modules: bool = False) -> None:
        require(source.is_dir() and not source.is_symlink(), "missing or linked directory input")
        for current, dirs, files in os.walk(source, followlinks=False):
            base = Path(current)
            dirs[:] = sorted(
                d
                for d in dirs
                if d != "__pycache__"
                and not (skip_node_modules and base == source and d == "node_modules")
            )
            for name in sorted(dirs + files):
                path = base / name
                suffix = path.relative_to(source)
                if path.suffix == ".pyc":
                    continue
                require(not forbidden(suffix), "credential-shaped tree input refused")
                if path.is_symlink():
                    resolved = path.resolve(strict=True)
                    require(
                        resolved == source or source in resolved.parents,
                        "private or external tree symlink refused",
                    )
                    self.link(
                        (Path(target) / suffix).as_posix(),
                        (Path(target) / resolved.relative_to(source)).as_posix(),
                    )
                elif path.is_file() and "__pycache__" not in suffix.parts and path.suffix != ".pyc":
                    self.file(path, (Path(target) / suffix).as_posix())
                else:
                    require(path.is_dir(), "special file input refused")


def node_inputs(plan: Plan, root: Path) -> None:
    from yaml import safe_load

    locked = safe_load((root / "pnpm-lock.yaml").read_text())["packages"]
    seen: set[Path] = set()
    approved = [root / "node_modules/.pnpm", root / "e2e/node_modules"]
    workspace_dirs = {root / "packages" / name for name in WORKSPACES}

    def locate(parent: Path, name: str) -> Path | None:
        require(
            bool(re.fullmatch(r"(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+", name)),
            "invalid dependency name",
        )
        for current in (parent, *parent.parents):
            if current != root and root not in current.parents:
                break
            slot = current / "node_modules" / name
            if slot.exists() or slot.is_symlink():
                return slot
        return None

    def visit(slot: Path) -> None:
        canonical = slot.resolve(strict=True)
        require(
            canonical in workspace_dirs
            or any(base == canonical or base in canonical.parents for base in approved),
            "private or external dependency symlink refused",
        )
        if slot != canonical:
            plan.link(slot.relative_to(root).as_posix(), canonical.relative_to(root).as_posix())
        if canonical in seen:
            return
        seen.add(canonical)
        require(len(seen) <= 1500, "dependency closure limit exceeded")
        data = json.loads((canonical / "package.json").read_text())
        if canonical not in workspace_dirs:
            if root / "e2e/node_modules" in canonical.parents:
                require(
                    data["name"] in {"@playwright/test", "playwright", "playwright-core"}
                    and data["version"] == "1.56.1",
                    "unqualified standalone browser dependency",
                )
            else:
                require(
                    f"{data['name']}@{data['version']}" in locked,
                    f"installed Node version differs from lock: {data['name']}@{data['version']}",
                )
            plan.tree(canonical, canonical.relative_to(root).as_posix(), skip_node_modules=True)
        dependencies = dict(data.get("dependencies", {}))
        optional = data.get("optionalDependencies", {})
        peers = data.get("peerDependencies", {})
        for name in sorted(set(dependencies) | set(optional) | set(peers)):
            dependency = locate(canonical, name)
            can_skip = name in optional or data.get("peerDependenciesMeta", {}).get(name, {}).get(
                "optional", False
            )
            require(
                dependency is not None or can_skip,
                f"required installed Node dependency missing: {name}",
            )
            if dependency is not None:
                visit(dependency)

    for folder in (root / "apps/customer", *sorted(workspace_dirs)):
        data = json.loads((folder / "package.json").read_text())
        names = set(data.get("dependencies", {})) | set(data.get("peerDependencies", {}))
        if folder == root / "apps/customer":
            names.update(CONFIG_DEPS)
        # Next's TypeScript setup and workspace type imports need these installed inputs.
        names.update(
            name
            for name in ("@types/node", "@types/react", "@types/react-dom", "typescript")
            if locate(folder, name) is not None
        )
        for name in sorted(names):
            slot = locate(folder, name)
            require(slot is not None, "required workspace Node input missing")
            visit(slot)
    playwright = locate(root / "e2e", "@playwright/test")
    require(playwright is not None, "installed Playwright input missing")
    require(
        json.loads((playwright / "package.json").read_text())["version"] == "1.56.1",
        "unqualified Playwright version",
    )
    visit(playwright)


def python_inputs(plan: Plan, root: Path, sdk: Path) -> None:
    from packaging.markers import Marker

    site = root / "services/api/.venv/lib/python3.12/site-packages"
    installed = {
        re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower(): d
        for d in importlib.metadata.distributions(path=[str(site)])
    }
    packages = tomllib.loads((root / "services/api/uv.lock").read_text())["package"]
    project = next(p for p in packages if p["name"] == "vergeo5-api")
    queue = list(project["dependencies"])
    seen: set[tuple[str, tuple[str, ...]]] = set()
    distributions: set[str] = set()
    while queue:
        dependency = queue.pop()
        if "marker" in dependency and not Marker(dependency["marker"]).evaluate():
            continue
        name = dependency["name"]
        extras = tuple(sorted(dependency.get("extra", [])))
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        require(name in installed, "required installed Python distribution missing")
        distribution = installed[name]
        candidates = [
            p for p in packages if p["name"] == name and p["version"] == distribution.version
        ]
        require(len(candidates) == 1, "installed Python version differs from lock")
        package = candidates[0]
        queue.extend(package.get("dependencies", []))
        for extra in extras:
            require(
                extra in package.get("optional-dependencies", {}), "Python runtime extra missing"
            )
            queue.extend(package["optional-dependencies"][extra])
        if name in distributions:
            continue
        distributions.add(name)
        record = distribution.read_text("RECORD")
        require(record is not None, "Python RECORD inventory missing")
        for filename, recorded_hash, size in csv.reader(record.splitlines()):
            path = Path(filename)
            # Entry-point scripts and generated bytecode are not module runtime inputs.
            if (
                "__pycache__" in path.parts
                or path.suffix == ".pyc"
                or path.name == "direct_url.json"
            ):
                continue
            if ".." in path.parts:
                require(
                    path.parts[:4] == ("..", "..", "..", "bin"),
                    "escaping Python RECORD input refused",
                )
                continue
            require(
                not path.is_absolute() and path.suffix != ".pth" and path.name != "direct_url.json",
                "editable or private Python hook refused",
            )
            source = site / path
            require(
                source.resolve() == source and source.is_file(),
                "missing or linked Python distribution input",
            )
            if recorded_hash:
                algorithm, expected = recorded_hash.split("=", 1)
                require(algorithm == "sha256", "unsupported Python RECORD hash")
                actual = (
                    base64.urlsafe_b64encode(bytes.fromhex(digest(source))).decode().rstrip("=")
                )
                require(actual == expected, "Python RECORD byte identity failed")
            if size:
                require(source.stat().st_size == int(size), "Python RECORD size differs")
            plan.file(
                source, (Path("services/api/.venv/lib/python3.12/site-packages") / path).as_posix()
            )
    interpreter = (root / "services/api/.venv/bin/python").resolve(strict=True)
    require(
        interpreter.parent == sdk / "bin" and interpreter.name.startswith("python3.12"),
        "private Python interpreter refused",
    )
    plan.file(interpreter, "services/api/.venv/bin/python")
    for alias, path in {
        "library": sdk / "lib/libpython3.12.so.1.0",
        "stdlib_site": sdk / "lib/python3.12/site.py",
        "stdlib_ssl": sdk / "lib/python3.12/ssl.py",
    }.items():
        resolved = path.resolve(strict=True)
        require(
            sdk in resolved.parents and resolved.is_file(), "private or missing SDK input refused"
        )
        plan.public_sdk_hashes[alias] = digest(resolved)
    # Synthetic venv configuration: no editable install, private command or user-site path.
    plan.file(
        f"home = {sdk / 'bin'}\ninclude-system-site-packages = false\n".encode(),
        "services/api/.venv/pyvenv.cfg",
    )


def assemble(root: Path, sdk: Path, node: Path, browser: Path) -> tuple[Plan, dict[str, str], str]:
    plan = Plan()
    tracked: dict[str, tuple[str, str, str]] = {}
    for row in (
        subprocess.check_output(["git", "ls-tree", "-rz", "HEAD"], cwd=root).decode().split("\0")
    ):
        if row:
            metadata, name = row.split("\t", 1)
            mode, kind, sha = metadata.split()
            tracked[name] = mode, kind, sha
    prefixes = (
        "apps/customer/",
        "services/api/app/",
        *(f"packages/{name}/" for name in WORKSPACES),
    )
    selected = {
        name
        for name in tracked
        if name
        and name.startswith(prefixes)
        and not forbidden(Path(name))
        and not any(part in {"tests", "__tests__", "__pycache__"} for part in Path(name).parts)
        and not re.search(r"\.(?:test|spec)\.[^.]+$", name)
    }
    selected.update(FIXED)
    git_blobs = {}
    for name in sorted(selected):
        require(name in tracked, "runtime source missing from accepted Git tree")
        mode, kind, expected_blob = tracked[name]
        require(
            kind == "blob" and mode in ("100644", "100755"),
            "linked or special tracked input refused",
        )
        require(not (root / name).is_symlink(), "linked tracked source refused")
        content = (root / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        require(actual == expected_blob, "runtime source Git identity differs")
        git_blobs[name] = actual
        plan.file(root / name, name)
    for name in (
        "apps/customer/package.json",
        "apps/customer/next.config.ts",
        "apps/customer/postcss.config.mjs",
        "apps/customer/tsconfig.json",
        "apps/customer/next-env.d.ts",
        "apps/customer/.next/BUILD_ID",
        "services/api/app/main.py",
    ):
        require((root / name).is_file(), "required runtime source or head build missing")
        if name == "apps/customer/next-env.d.ts":
            plan.file(root / name, name)
    # A completed production build remains a prerequisite; development regenerates
    # its own cache. Never copy the original whole .next tree or environment caches.
    plan.file(root / "apps/customer/.next/BUILD_ID", "apps/customer/.next/BUILD_ID")
    node_inputs(plan, root)
    python_inputs(plan, root, sdk)
    node = node.resolve(strict=True)
    require(
        str(node).startswith("/opt/hostedtoolcache/node/") and node.name == "node",
        "private Node interpreter refused",
    )
    plan.file(node, ".runtime/bin/node")
    browser = browser.resolve(strict=True)
    bundle = browser.parents[1]
    require(
        bool(re.fullmatch(r"chromium_headless_shell-[0-9]+", bundle.name)),
        "unqualified browser layout",
    )
    plan.tree(bundle, f".runtime/browsers/{bundle.name}")
    return (
        plan,
        git_blobs,
        subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip(),
    )


def canonical(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def inventory(root: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(current) / name
            alias = path.relative_to(root).as_posix()
            if alias == "input-manifest.json":
                require(not path.is_symlink(), "linked manifest refused")
                continue
            if path.is_symlink():
                target = os.readlink(path)
                resolved = path.resolve(strict=True)
                require(
                    not Path(target).is_absolute() and root in resolved.parents,
                    "private or escaping output symlink refused",
                )
                found[alias] = {"type": "symlink", "target": target}
            elif path.is_file():
                found[alias] = {
                    "type": "file",
                    "sha256": digest(path),
                    "size": path.stat().st_size,
                    "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
                }
            else:
                require(path.is_dir(), "special output file refused")
                found[alias] = {
                    "type": "directory",
                    "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
                }
    return found


def verify(root: Path, expected_hash: str, sdk: Path | None = None) -> dict[str, object]:
    require(bool(re.fullmatch(r"[a-f0-9]{64}", expected_hash)), "invalid expected manifest digest")
    manifest_path = root / "input-manifest.json"
    require(
        not manifest_path.is_symlink() and digest(manifest_path) == expected_hash,
        "unexpected manifest entries or digest",
    )
    manifest = json.loads(manifest_path.read_text())
    require(
        set(manifest)
        == {"version", "source_sha", "source_tree", "git_blobs", "public_sdk", "entries"}
        and manifest["version"] == 1,
        "unexpected manifest fields",
    )
    require(
        bool(re.fullmatch(r"[a-f0-9]{40}", manifest["source_sha"]))
        and bool(re.fullmatch(r"[a-f0-9]{40}", manifest["source_tree"])),
        "invalid manifest source identity",
    )
    for alias in manifest["entries"]:
        relative(alias)
        require(not forbidden(Path(alias)), "unexpected private manifest entry")
    non_dirs = {
        alias: entry
        for alias, entry in manifest["entries"].items()
        if entry.get("type") != "directory"
    }
    allowed_roots = (
        "node_modules/.pnpm/",
        "e2e/node_modules/",
        "apps/customer/node_modules/",
        "services/api/.venv/lib/python3.12/site-packages/",
        *(f"packages/{name}/node_modules/" for name in WORKSPACES),
    )
    generated = {
        "apps/customer/next-env.d.ts",
        "apps/customer/.next/BUILD_ID",
        "services/api/.venv/bin/python",
        "services/api/.venv/pyvenv.cfg",
        ".runtime/bin/node",
    }
    for alias, entry in non_dirs.items():
        allowed = (
            alias in manifest["git_blobs"]
            or alias in generated
            or alias.startswith(allowed_roots)
            or bool(re.match(r"^\.runtime/browsers/chromium_headless_shell-[0-9]+/", alias))
        )
        require(allowed, "unexpected runtime manifest entry")
        require(entry.get("type") in ("file", "symlink"), "unexpected manifest file type")
        if entry["type"] == "file":
            require(entry.get("mode") in ("0640", "0750"), "unexpected package permissions")
    parents = {
        parent.as_posix()
        for alias in non_dirs
        for parent in relative(alias).parents
        if parent != Path(".")
    }
    actual_dirs = {
        alias for alias, entry in manifest["entries"].items() if entry.get("type") == "directory"
    }
    # A directory symlink itself replaces a directory entry in the reconstructed graph.
    require(actual_dirs == parents - set(non_dirs), "unexpected manifest directories")
    for alias in actual_dirs:
        require(
            manifest["entries"][alias] == {"type": "directory", "mode": "0750"},
            "unexpected directory permissions",
        )
    for alias, blob in manifest["git_blobs"].items():
        path = relative(alias)
        allowed = alias in FIXED or alias.startswith(
            ("apps/customer/", "services/api/app/", *(f"packages/{name}/" for name in WORKSPACES))
        )
        require(
            allowed and not forbidden(path) and alias in non_dirs,
            "unexpected source manifest entry",
        )
        require(not (root / path).is_symlink(), "linked source manifest entry")
        content = (root / path).read_bytes()
        require(
            hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            == blob,
            "source Git blob differs",
        )
    require(
        inventory(root) == manifest["entries"], "missing, unexpected or modified package inputs"
    )
    if sdk is not None:
        require(
            str(sdk).startswith("/opt/hostedtoolcache/Python/")
            and sdk.name == "x64"
            and sdk.parent.name == manifest["public_sdk"]["version"],
            "public SDK identity differs",
        )
        for alias, path in {
            "library": sdk / "lib/libpython3.12.so.1.0",
            "stdlib_site": sdk / "lib/python3.12/site.py",
            "stdlib_ssl": sdk / "lib/python3.12/ssl.py",
        }.items():
            resolved = path.resolve(strict=True)
            require(
                sdk in resolved.parents
                and digest(resolved) == manifest["public_sdk"]["input_hashes"][alias],
                "public SDK input byte identity differs",
            )
        require(
            digest(sdk / "bin/python3.12") == manifest["public_sdk"]["interpreter_sha256"],
            "public SDK interpreter byte identity differs",
        )
    return manifest


def materialize(
    plan: Plan,
    destination: Path,
    source_sha: str,
    sdk_version: str,
    git_blobs: dict[str, str],
    source_tree: str,
) -> str:
    require(
        destination.is_dir() and not destination.is_symlink() and not list(destination.iterdir()),
        "package destination must be empty",
    )
    require(bool(re.fullmatch(r"[a-f0-9]{40}", source_sha)), "invalid source identity")
    entries: dict[str, dict[str, object]] = {}
    for alias, source in sorted(plan.files.items()):
        target = destination / relative(alias)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, bytes):
            target.write_bytes(source)
            expected = hashlib.sha256(source).hexdigest()
        else:
            expected = digest(source)
            shutil.copyfile(source, target, follow_symlinks=False)
        require(digest(target) == expected, "copied byte identity failed")
        executable = isinstance(source, Path) and bool(source.stat().st_mode & 0o111)
        target.chmod(0o750 if executable else 0o640)
        entries[alias] = {
            "type": "file",
            "sha256": expected,
            "size": target.stat().st_size,
            "mode": "0750" if executable else "0640",
        }
    for alias, link in sorted(plan.links.items()):
        target = destination / relative(alias)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(link)
        entries[alias] = {"type": "symlink", "target": link}
    for current, dirs, _ in os.walk(destination, followlinks=False):
        for name in dirs:
            directory = Path(current) / name
            if not directory.is_symlink():
                directory.chmod(0o750)
                entries[directory.relative_to(destination).as_posix()] = {
                    "type": "directory",
                    "mode": "0750",
                }
    destination.chmod(0o750)
    require(
        inventory(destination) == entries, "actual package differs from reconstructed input plan"
    )
    manifest = {
        "version": 1,
        "source_sha": source_sha,
        "source_tree": source_tree,
        "git_blobs": git_blobs,
        "public_sdk": {
            "version": sdk_version,
            "interpreter_sha256": entries["services/api/.venv/bin/python"]["sha256"],
            "input_hashes": plan.public_sdk_hashes,
            "binding": "validated public setup-python SDK; system and user site disabled",
        },
        "entries": entries,
    }
    manifest_path = destination / "input-manifest.json"
    manifest_path.write_bytes(canonical(manifest))
    manifest_path.chmod(0o640)
    expected_hash = digest(manifest_path)
    verify(destination, expected_hash)
    return expected_hash


def main() -> None:
    if sys.argv[1] == "verify":
        manifest = verify(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
        print(
            json.dumps(
                {
                    "verified": True,
                    "source_sha": manifest["source_sha"],
                    "manifest_sha256": sys.argv[3],
                    "entries": len(manifest["entries"]),
                }
            )
        )
        return
    require(sys.argv[1] == "package", "unknown packaging action")
    root, sdk, node, browser, destination = map(Path, sys.argv[2:7])
    require(
        destination.parent == Path("/tmp") and destination.name.startswith("cartdrill."),
        "non-disposable destination refused",
    )
    require(
        str(sdk).startswith("/opt/hostedtoolcache/Python/") and sdk.name == "x64",
        "private SDK binding refused",
    )
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        == sys.argv[7],
        "source checkout differs",
    )
    plan, blobs, tree = assemble(root, sdk, node, browser)
    print(materialize(plan, destination, sys.argv[7], sdk.parent.name, blobs, tree))


if __name__ == "__main__":
    try:
        main()
    except PackageInputError as error:
        print(f"PackageInputError: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, StopIteration):
        print(
            "PackageInputError: required runtime inventory or filesystem metadata unavailable",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

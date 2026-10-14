"""Capture only genuinely generated types and bounded nonsecret CI provenance."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TYPES_PATH = "packages/types/src/db.ts"
MANIFEST_PATH = "typegen-artifact-manifest.json"
CLI_VERSION = "2.109.1"
META_IMAGE = (
    "ghcr.io/supabase/postgres-meta@sha256:"
    "a84cc713585eea7b401e4a2561ec4a1e48c87083d1c7ecb4502f204bb4391300"
)
META_ALIAS = "public.ecr.aws/supabase/postgres-meta:v0.96.6"
REPAIR_ORDER = ["20261009100000", "20261009110000", "20261009124801", "20261011120000"]
Run = Callable[[list[str], Path], str]


class CaptureError(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CaptureError(code)


def command(args: list[str], cwd: Path) -> str:
    # CLI home discovery works without inheriting user credentials/configuration.
    with tempfile.TemporaryDirectory(prefix="typegen-proof-home-") as tool_home:
        result = subprocess.run(
            args,
            cwd=cwd,
            env={"PATH": os.environ.get("PATH", os.defpath), "HOME": tool_home},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    return result.stdout.rstrip("\r\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def context(root: Path, env: Mapping[str, str], run: Run) -> dict[str, Any]:
    require(env.get("TYPEGEN_GENERATION_OUTCOME") == "success", "generation_not_successful")
    require(env.get("TYPEGEN_RESET_OUTCOME") == "success", "reset_not_successful")
    require(env.get("TYPEGEN_META_OUTCOME") == "success", "qualified_meta_not_successful")
    require(
        env.get("GITHUB_ACTIONS") == "true" and env.get("RUNNER_ENVIRONMENT") == "github-hosted",
        "hosted_identity_required",
    )
    require(env.get("GITHUB_REPOSITORY") == "KaluMuso/Convergeo", "repository_identity_required")
    require(env.get("GITHUB_WORKSPACE") == str(root.resolve()), "workspace_identity_required")
    require(not env.get("SUPABASE_PROJECT_ID"), "remote_project_forbidden")
    require(
        platform.system() == "Linux" and platform.machine() == "x86_64",
        "qualified_platform_required",
    )
    commit = run(["git", "rev-parse", "HEAD"], root)
    tree = run(["git", "rev-parse", "HEAD^{tree}"], root)
    require(
        bool(re.fullmatch(r"[a-f0-9]{40}", commit)) and commit == env.get("GITHUB_SHA"),
        "source_sha_mismatch",
    )
    require(bool(re.fullmatch(r"[a-f0-9]{40}", tree)), "source_tree_invalid")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(bool(re.fullmatch(r"[1-9][0-9]*", env.get(key, ""))), "run_identity_required")
    dirty = run(["git", "status", "--porcelain", "--untracked-files=no"], root)
    require(
        all(line == " M " + TYPES_PATH for line in dirty.splitlines()), "unrelated_tracked_change"
    )
    return {
        "commit": commit,
        "tree": tree,
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": env["GITHUB_RUN_ATTEMPT"],
    }


def inputs(root: Path, run: Run) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tracked: dict[str, tuple[str, str]] = {}
    for row in run(
        ["git", "ls-tree", "-rz", "HEAD", "supabase/migrations", TYPES_PATH], root
    ).split("\0"):
        if not row:
            continue
        metadata, name = row.split("\t", 1)
        mode, kind, identity = metadata.split()
        require(kind == "blob" and mode in {"100644", "100755"}, "linked_or_special_source")
        tracked[name] = (mode, identity)
    files = sorted((root / "supabase/migrations").glob("*.sql"))
    names = {str(path.relative_to(root)) for path in files}
    require(
        names == {name for name in tracked if name.endswith(".sql")}, "migration_inventory_mismatch"
    )
    rows = []
    for path in files:
        name = str(path.relative_to(root))
        require(
            not path.is_symlink() and path.resolve() == root.resolve() / name, "linked_migration"
        )
        data = path.read_bytes()
        version = path.name.split("_", 1)[0]
        require(bool(data) and bool(re.fullmatch(r"[0-9]+", version)), "invalid_migration")
        require(blob(data) == tracked[name][1], "migration_source_mismatch")
        rows.append(
            {
                "path": name,
                "version": version,
                "git_blob": tracked[name][1],
                "sha256": sha256(data),
                "bytes": len(data),
            }
        )
    versions = [row["version"] for row in rows]
    require(
        len(rows) == len(set(versions)) == 118 and versions[-4:] == REPAIR_ORDER,
        "migration_union_or_order_mismatch",
    )
    generated = root / TYPES_PATH
    require(
        not generated.is_symlink() and generated.resolve() == root.resolve() / TYPES_PATH,
        "linked_generated_file",
    )
    data = generated.read_bytes()
    require(0 < len(data) <= 20_000_000, "generated_file_empty_or_oversized")
    text = data.decode("utf-8")
    require("export type Json" in text and "export type Database" in text, "generated_file_invalid")
    require(TYPES_PATH in tracked, "committed_types_missing")
    return rows, {
        "path": TYPES_PATH,
        "sha256": sha256(data),
        "bytes": len(data),
        "git_blob": blob(data),
        "committed_git_blob": tracked[TYPES_PATH][1],
    }


def tools(root: Path, run: Run) -> dict[str, Any]:
    require(run(["supabase", "--version"], root) == CLI_VERSION, "cli_version_mismatch")
    fmt = "{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RepoDigests}}"
    identity, system, architecture, digests = run(
        ["docker", "image", "inspect", "--format", fmt, META_IMAGE], root
    ).split("|", 3)
    require(bool(re.fullmatch(r"sha256:[a-f0-9]{64}", identity)), "meta_image_identity_invalid")
    require(
        system == "linux" and architecture == "amd64" and META_IMAGE in json.loads(digests),
        "meta_digest_or_platform_mismatch",
    )
    require(
        run(["docker", "image", "inspect", "--format", "{{.Id}}", META_ALIAS], root) == identity,
        "meta_alias_mismatch",
    )
    return {
        "supabase_cli": CLI_VERSION,
        "platform": "linux/amd64",
        "postgres_meta_ref": META_IMAGE,
        "postgres_meta_image_id": identity,
        "postgres_meta_alias": META_ALIAS,
        "python": platform.python_version(),
    }


def capture(root: Path, env: Mapping[str, str], run: Run = command) -> dict[str, Any]:
    source = context(root, env, run)
    migrations, generated = inputs(root, run)
    tool_info = tools(root, run)
    result = {
        "version": 1,
        "source": source,
        "tools": tool_info,
        "generation": {
            "local_reset_outcome": "success",
            "qualified_meta_outcome": "success",
            "generation_outcome": "success",
            "authority": "existing local scripts/gen-types.sh step",
            "ledger_scope": (
                "repository inventory and successful full local reset; no independent ledger query"
            ),
        },
        "migration_count": 118,
        "migrations": migrations,
        "generated": generated,
    }
    output = root / MANIFEST_PATH
    require(not output.exists() and not output.is_symlink(), "manifest_already_exists")
    # Exclusive creation only after every source/tool/generated-file check passed.
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    return result


def verify(root: Path, env: Mapping[str, str], run: Run = command) -> None:
    source = context(root, env, run)
    migrations, generated = inputs(root, run)
    output = root / MANIFEST_PATH
    require(not output.is_symlink(), "linked_manifest")
    raw = output.read_text()
    result = json.loads(raw)
    require(raw == json.dumps(result, indent=2) + "\n", "manifest_noncanonical_or_duplicate_keys")
    require(
        set(result)
        == {
            "version",
            "source",
            "tools",
            "generation",
            "migration_count",
            "migrations",
            "generated",
        },
        "manifest_shape_invalid",
    )
    require(result["version"] == 1 and result["source"] == source, "manifest_source_mismatch")
    require(
        result["migration_count"] == 118 and result["migrations"] == migrations,
        "manifest_migration_mismatch",
    )
    require(result["generated"] == generated, "manifest_generated_mismatch")
    require(
        result["generation"]
        == {
            "local_reset_outcome": "success",
            "qualified_meta_outcome": "success",
            "generation_outcome": "success",
            "authority": "existing local scripts/gen-types.sh step",
            "ledger_scope": (
                "repository inventory and successful full local reset; no independent ledger query"
            ),
        },
        "manifest_generation_mismatch",
    )
    recorded = result["tools"]
    require(
        set(recorded)
        == {
            "supabase_cli",
            "platform",
            "postgres_meta_ref",
            "postgres_meta_image_id",
            "postgres_meta_alias",
            "python",
        },
        "manifest_tool_shape_invalid",
    )
    require(
        recorded["supabase_cli"] == CLI_VERSION
        and recorded["platform"] == "linux/amd64"
        and recorded["postgres_meta_ref"] == META_IMAGE
        and recorded["postgres_meta_alias"] == META_ALIAS
        and recorded["python"] == platform.python_version()
        and bool(re.fullmatch(r"sha256:[a-f0-9]{64}", recorded["postgres_meta_image_id"])),
        "manifest_tool_identity_invalid",
    )
    require(recorded == tools(root, run), "manifest_actual_tool_mismatch")


def main(argv: list[str]) -> int:
    try:
        require(len(argv) == 2 and argv[1] in {"capture", "verify"}, "invalid_command")
        if argv[1] == "capture":
            capture(ROOT, os.environ)
        else:
            verify(ROOT, os.environ)
    except CaptureError as error:
        print(f"FAIL: typegen artifact {error}", file=sys.stderr)
        return 1
    except Exception:
        # Neither command errors nor file payloads/environment are public diagnostics.
        print("FAIL: typegen artifact input or tool unavailable", file=sys.stderr)
        return 1
    print("PASS: bounded generated-type artifact provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

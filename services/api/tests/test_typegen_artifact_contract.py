from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts/ci/typegen_artifact.py"


@pytest.fixture(scope="module")
def helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("typegen_artifact", HELPER)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Fixture:
    def __init__(self, root: Path, helper: ModuleType) -> None:
        self.root = root
        self.helper = helper
        self.git: dict[str, str] = {}
        self.calls: list[list[str]] = []
        self.fault = ""
        for index in range(114):
            self.file(f"supabase/migrations/{index + 1:04}_fixture.sql", b"select 1;\n")
        for version in helper.REPAIR_ORDER:
            self.file(f"supabase/migrations/{version}_fixture.sql", b"select 1;\n")
        self.file(helper.TYPES_PATH, b"export type Json = null;\nexport type Database = {};\n")
        self.env = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "GITHUB_REPOSITORY": "KaluMuso/Convergeo",
            "GITHUB_WORKSPACE": str(root),
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "TYPEGEN_GENERATION_OUTCOME": "success",
            "TYPEGEN_RESET_OUTCOME": "success",
            "TYPEGEN_META_OUTCOME": "success",
            "GITHUB_TOKEN": "PRIVATE_ENV_SENTINEL",
        }

    def file(self, path: str, data: bytes) -> None:
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        self.git[path] = self.helper.blob(data)

    def run(self, args: list[str], _cwd: Path) -> str:
        self.calls.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return ("a" if args[-1] == "HEAD" else "b") * 40
        if args[:2] == ["git", "status"]:
            return " M " + self.helper.TYPES_PATH if self.fault != "dirty" else " M private-file"
        if args[:2] == ["git", "ls-tree"]:
            return "".join(
                f"100644 blob {identity}\t{path}\0" for path, identity in sorted(self.git.items())
            )
        if args == ["supabase", "--version"]:
            return "latest" if self.fault == "cli" else self.helper.CLI_VERSION
        if args[:3] == ["docker", "image", "inspect"]:
            image = "sha256:" + "c" * 64
            if args[-1] == self.helper.META_ALIAS:
                return "sha256:" + "d" * 64 if self.fault == "alias" else image
            digests = [] if self.fault == "digest" else [self.helper.META_IMAGE]
            architecture = "arm64" if self.fault == "platform" else "amd64"
            return "|".join([image, "linux", architecture, json.dumps(digests)])
        raise AssertionError("unexpected fixture command")


@pytest.fixture
def stage(tmp_path: Path, helper: ModuleType) -> Fixture:
    return Fixture(tmp_path, helper)


def test_successful_generation_capture_is_exact_and_nonsecret(stage: Fixture) -> None:
    h = stage.helper
    d = h.capture(stage.root, stage.env, stage.run)
    assert set(d) == {
        "version",
        "source",
        "tools",
        "generation",
        "migration_count",
        "migrations",
        "generated",
    }
    assert d["migration_count"] == len(d["migrations"]) == 118
    assert [r["version"] for r in d["migrations"]][-4:] == h.REPAIR_ORDER
    assert d["generated"]["path"] == h.TYPES_PATH
    assert "PRIVATE_" not in (stage.root / h.MANIFEST_PATH).read_text()
    assert "GITHUB_TOKEN" not in (stage.root / h.MANIFEST_PATH).read_text()
    h.verify(stage.root, stage.env, stage.run)
    assert all(args[0] in {"git", "supabase", "docker"} for args in stage.calls)
    assert all("pull" not in args and "gen" not in args for args in stage.calls)


@pytest.mark.parametrize(
    "key", ["TYPEGEN_GENERATION_OUTCOME", "TYPEGEN_RESET_OUTCOME", "TYPEGEN_META_OUTCOME"]
)
@pytest.mark.parametrize("outcome", ["failure", "skipped", ""])
def test_missing_success_never_fabricates_manifest(stage: Fixture, key: str, outcome: str) -> None:
    stage.env[key] = outcome
    with pytest.raises(stage.helper.CaptureError):
        stage.helper.capture(stage.root, stage.env, stage.run)
    assert not (stage.root / stage.helper.MANIFEST_PATH).exists()
    assert stage.calls == []


@pytest.mark.parametrize("fault", ["cli", "digest", "platform", "alias", "dirty"])
def test_wrong_source_or_qualified_tool_inputs_fail_closed(stage: Fixture, fault: str) -> None:
    stage.fault = fault
    with pytest.raises(stage.helper.CaptureError):
        stage.helper.capture(stage.root, stage.env, stage.run)
    assert not (stage.root / stage.helper.MANIFEST_PATH).exists()


@pytest.mark.parametrize(
    "fault",
    ["count", "migration_bytes", "empty_types", "missing_types", "linked_types", "remote", "sha"],
)
def test_no_invalid_or_unqualified_generated_file_can_be_captured(
    stage: Fixture, fault: str
) -> None:
    h = stage.helper
    if fault == "count":
        (stage.root / "supabase/migrations/0001_fixture.sql").unlink()
    elif fault == "migration_bytes":
        (stage.root / "supabase/migrations/0001_fixture.sql").write_text("select 2;")
    elif fault == "empty_types":
        (stage.root / h.TYPES_PATH).write_bytes(b"")
    elif fault == "missing_types":
        (stage.root / h.TYPES_PATH).unlink()
    elif fault == "linked_types":
        (stage.root / h.TYPES_PATH).unlink()
        (stage.root / h.TYPES_PATH).symlink_to(stage.root / "private-file")
    elif fault == "remote":
        stage.env["SUPABASE_PROJECT_ID"] = "private-project"
    else:
        stage.env["GITHUB_SHA"] = "d" * 40
    with pytest.raises((h.CaptureError, OSError)):
        h.capture(stage.root, stage.env, stage.run)
    assert not (stage.root / h.MANIFEST_PATH).exists()


@pytest.mark.parametrize(
    "fault", ["file", "source", "extra", "tool", "migration", "python", "image_id", "duplicate"]
)
def test_final_proof_rejects_changed_file_or_unapproved_manifest(
    stage: Fixture, fault: str
) -> None:
    h = stage.helper
    d = h.capture(stage.root, stage.env, stage.run)
    if fault == "file":
        (stage.root / h.TYPES_PATH).write_text("export type Json=null; export type Database={};")
    elif fault == "source":
        d["source"]["commit"] = "d" * 40
    elif fault == "extra":
        d["private"] = "PRIVATE_ENV_SENTINEL"
    elif fault == "tool":
        d["tools"]["supabase_cli"] = "latest"
    elif fault == "migration":
        d["migrations"][0]["sha256"] = "0" * 64
    elif fault == "python":
        d["tools"]["python"] = "PRIVATE_ENV_SENTINEL"
    elif fault == "image_id":
        d["tools"]["postgres_meta_image_id"] = "sha256:" + "d" * 64
    raw = json.dumps(d, indent=2) + "\n"
    if fault == "duplicate":
        raw = raw.replace('"python":', '"python": "PRIVATE_ENV_SENTINEL", "python":', 1)
    (stage.root / h.MANIFEST_PATH).write_text(raw)
    with pytest.raises(h.CaptureError):
        h.verify(stage.root, stage.env, stage.run)


def test_workflow_preserves_reset_preload_and_failing_drift_gate() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job: dict[str, Any] = workflow["jobs"]["db"]
    assert job["needs"] == "migrations"
    steps = job["steps"]
    pin = next(s for s in steps if s["name"] == "Setup Supabase CLI")
    assert pin["with"]["version"] == "2.109.1"
    by_id = {s.get("id"): s for s in steps if "id" in s}
    assert by_id["cart_typegen_reset"]["run"] == "supabase db reset --no-seed"
    assert by_id["cart_typegen_meta"]["run"] == "bash scripts/ci/preload-typegen-meta.sh"
    assert by_id["cart_typegen_generate"]["run"] == "bash scripts/gen-types.sh"
    drift = next(s for s in steps if s["name"] == "Fail on stale committed types")
    assert drift["run"] == "git diff --exit-code packages/types/src/db.ts"
    assert "continue-on-error" not in drift and "if" not in drift
    proof = by_id["cart_typegen_proof"]
    assert proof["if"] == "always()"
    upload = next(s for s in steps if s["name"] == "Upload genuine generated database types")
    for key in ["cart_typegen_generate", "cart_typegen_manifest", "cart_typegen_proof"]:
        assert f"steps.{key}.outcome == 'success'" in upload["if"]
    assert "!cancelled()" in upload["if"]  # Runs despite the blocking drift failure.
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"]["path"].splitlines() == [
        "packages/types/src/db.ts",
        "typegen-artifact-manifest.json",
    ]
    assert upload["with"]["if-no-files-found"] == "error"
    assert "include-hidden-files" not in upload["with"]
    assert (
        steps.index(by_id["cart_typegen_generate"])
        < steps.index(drift)
        < steps.index(proof)
        < steps.index(upload)
    )


def test_command_preserves_porcelain_leading_space(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def mock_run(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert set(kwargs["env"]) == {"PATH", "HOME"}
        owned_home = Path(kwargs["env"]["HOME"])
        assert owned_home.name.startswith("typegen-proof-home-") and owned_home.is_dir()
        assert list(owned_home.iterdir()) == []
        return subprocess.CompletedProcess(
            [], 0, stdout=" M packages/types/src/db.ts\n", stderr="PRIVATE_ERROR"
        )

    monkeypatch.setattr(helper.subprocess, "run", mock_run)
    assert helper.command(["git", "status"], tmp_path) == " M packages/types/src/db.ts"

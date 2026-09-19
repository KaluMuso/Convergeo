"""Execute real selector/verifier functions and workflow probes with offline transports."""

from __future__ import annotations

import ast
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
SHA = "a" * 40
OTHER = "a" * 39 + "b"
PROJECT = "dpadrlxukcjbewpqympu"


def workflow(name: str) -> dict[str, Any]:
    result: dict[str, Any] = yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
    )
    return result


def function(path: str, name: str) -> str:
    source = (ROOT / path).read_text()
    start = source.index(f"{name}() {{")
    return source[start : source.index("\n}\n", start) + 3]


def shell(source: str, env: dict[str, str], stdin: str = "") -> subprocess.CompletedProcess[str]:
    # Do not inherit credentials. Extracted functions have only explicitly supplied transports.
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + source],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], **env},
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def condition(expression: str, values: dict[str, str | bool]) -> bool:
    """Evaluate only the workflow's Boolean subset, not arbitrary expressions."""
    source = expression.replace("${{", "").replace("}}", "").strip()
    for key in sorted(values, key=len, reverse=True):
        source = source.replace(key, repr(values[key]))
    source = source.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    source = re.sub(r"\btrue\b", "True", source)
    source = re.sub(r"\bfalse\b", "False", source)
    tree = ast.parse(source, mode="eval")
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.Constant)
    if not all(isinstance(node, allowed) for node in ast.walk(tree)):
        raise AssertionError("unsupported workflow condition")
    return bool(eval(compile(tree, "<workflow condition>", "eval"), {"__builtins__": {}}, {}))


def fingerprint() -> dict[str, object]:
    return {"env": "production", "git_sha": SHA, "image_tag": SHA, "supabase_project_ref": PROJECT}


class SelectorIdentityTests(unittest.TestCase):
    def select(self, requested: str, commits: list[object]) -> str:
        rows = [
            {"uid": f"dpl_{i}", "state": "READY", "meta": {"githubCommitSha": value}}
            for i, value in enumerate(commits)
        ]
        result = shell(
            function("scripts/ops/vercel_promote.sh", "select_deployment") + "\nselect_deployment",
            {"MASTER_GIT_SHA": requested},
            json.dumps({"deployments": rows}),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_exact_full_sha_is_selected_after_rejected_rows(self) -> None:
        self.assertEqual(self.select(SHA, [OTHER, SHA[:7], None, SHA]), f"dpl_3\t{SHA}")

    def test_missing_short_malformed_and_same_prefix_deployments_are_rejected(self) -> None:
        cases: tuple[object, ...] = (None, "", SHA[:7], SHA[:39], OTHER, "A" * 40, "g" * 40, 123)
        for commit in cases:
            with self.subTest(commit=commit):
                self.assertEqual(self.select(SHA, [commit]), "")

    def test_invalid_requested_sha_cannot_select_even_identical_metadata(self) -> None:
        for requested in ("", SHA[:7], SHA[:39], "A" * 40, "g" * 40, SHA + "\n"):
            with self.subTest(requested=requested):
                self.assertEqual(self.select(requested, [requested]), "")


class LiveVerifierIdentityTests(unittest.TestCase):
    def verify(self, fp: dict[str, object], **expected: str) -> str:
        names = ("set_gate", "json_get", "json_get_string", "check_g1_api", "check_g9")
        source = "\n".join(function("scripts/ops/verify_live.sh", name) for name in names)
        source += """
declare -A GATE_STATUS=() GATE_DETAIL=()
http_code() { printf 200; }
http_body() {
  case "$1" in
    */fingerprint) printf '%s' "$TEST_FINGERPRINT" ;;
    */readyz) printf '{"status":"ok"}' ;;
    *) exit 90 ;;
  esac
}
check_g1_api
check_g9
printf '%s %s' "${GATE_STATUS[G1]}" "${GATE_STATUS[G9]}"
"""
        result = shell(
            source,
            {
                "DRY_RUN": "0",
                "API_BASE_URL": "https://offline.invalid",
                "MASTER_GIT_SHA": SHA,
                "EXPECTED_ENV": "production",
                "EXPECTED_IMAGE_TAG": SHA,
                "EXPECTED_SUPABASE_PROJECT_REF": PROJECT,
                "TEST_FINGERPRINT": json.dumps(fp),
                **expected,
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_exact_identity_passes(self) -> None:
        self.assertEqual(self.verify(fingerprint()), "PASS PASS")

    def test_g9_rejects_same_prefix_short_missing_and_non_string_shas(self) -> None:
        cases: tuple[object, ...] = (OTHER, SHA[:7], "", None, "A" * 40, 1, SHA + "\n")
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(self.verify({**fingerprint(), "git_sha": value}), "PASS FAIL")
        self.assertEqual(self.verify(fingerprint(), MASTER_GIT_SHA=SHA[:7]), "PASS FAIL")

    def test_wrong_missing_or_non_string_image_and_project_fail(self) -> None:
        cases: tuple[tuple[str, object], ...] = (
            ("image_tag", OTHER),
            ("image_tag", SHA[:7]),
            ("image_tag", None),
            ("image_tag", SHA + "\n"),
            ("supabase_project_ref", "iyasmrmbcrvlfxpzescb"),
            ("supabase_project_ref", None),
            ("supabase_project_ref", PROJECT + "\n"),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assertEqual(self.verify({**fingerprint(), field: value}), "FAIL PASS")

    def test_generic_caller_can_bind_a_different_environment_project_and_image(self) -> None:
        self.assertEqual(
            self.verify(
                {
                    **fingerprint(),
                    "env": "staging",
                    "supabase_project_ref": "synthetic-project",
                    "image_tag": OTHER,
                },
                EXPECTED_ENV="staging",
                EXPECTED_SUPABASE_PROJECT_REF="synthetic-project",
                EXPECTED_IMAGE_TAG=OTHER,
            ),
            "PASS PASS",
        )
        self.assertEqual(
            self.verify(
                {"env": "production", "git_sha": SHA},
                EXPECTED_SUPABASE_PROJECT_REF="",
                EXPECTED_IMAGE_TAG="",
            ),
            "PASS PASS",
        )


class WorkflowIdentityExecutionTests(unittest.TestCase):
    def probe(
        self, step: dict[str, Any], fp: dict[str, object]
    ) -> subprocess.CompletedProcess[str]:
        self.assertNotIn("if", step)
        with tempfile.TemporaryDirectory() as directory:
            curl = Path(directory) / "curl"
            curl.write_text(
                f"#!{sys.executable}\n"
                + """import os, sys
from pathlib import Path
args = sys.argv[1:]
assert args == ['-fsS', '--max-time', '30', 'https://offline.invalid/fingerprint',
                '-o', os.environ['RUNNER_TEMP'] + '/fingerprint.json'], args
Path(args[-1]).write_text(os.environ['TEST_FINGERPRINT'])
"""
            )
            curl.chmod(0o755)
            return shell(
                step["run"],
                {
                    "PATH": directory + os.pathsep + os.environ["PATH"],
                    "RUNNER_TEMP": directory,
                    "PROD_API_HOST": "offline.invalid",
                    "WANT_SHA": SHA,
                    "PROD_SUPABASE_PROJECT_REF": PROJECT,
                    "TEST_FINGERPRINT": json.dumps(fp),
                },
            )

    def test_skip_api_with_current_api_passes_and_stale_api_fails_even_without_verify_live(
        self,
    ) -> None:
        jobs = workflow("deploy-production.yml")["jobs"]
        strict = jobs["verify-api-identity"]
        self.assertEqual(set(strict["needs"]), {"guard", "deploy-api"})
        step = next(s for s in strict["steps"] if s.get("name") == "Fingerprint probe")
        self.assertEqual(step["env"]["WANT_SHA"], "${{ inputs.api_image_tag }}")
        self.assertNotIn("inputs.verify_live", strict["if"])
        for skip_api, verify_live in itertools.product((False, True), repeat=2):
            values: dict[str, str | bool] = {
                "needs.guard.result": "success",
                "inputs.skip_api": skip_api,
                "inputs.verify_live": verify_live,
                "needs.deploy-api.result": "skipped" if skip_api else "success",
            }
            with self.subTest(skip_api=skip_api, verify_live=verify_live):
                self.assertTrue(condition(strict["if"], values))
                good = self.probe(step, fingerprint())
                self.assertEqual(good.returncode, 0, good.stderr)
                bad = self.probe(step, {**fingerprint(), "git_sha": OTHER})
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn("git_sha mismatch", bad.stderr)

    def test_failed_guard_deploy_or_unintentional_skip_cannot_pass_identity(self) -> None:
        strict = workflow("deploy-production.yml")["jobs"]["verify-api-identity"]
        for guard, deploy, skip in itertools.product(
            ("success", "failure", "cancelled", "skipped"),
            ("success", "failure", "cancelled", "skipped"),
            (False, True),
        ):
            with self.subTest(guard=guard, deploy=deploy, skip=skip):
                self.assertEqual(
                    condition(
                        strict["if"],
                        {
                            "needs.guard.result": guard,
                            "needs.deploy-api.result": deploy,
                            "inputs.skip_api": skip,
                        },
                    ),
                    guard == "success" and (deploy == "success" or (deploy == "skipped" and skip)),
                )

    def test_both_workflows_use_same_strict_probe_before_success_evidence(self) -> None:
        deploy = workflow("deploy-production.yml")
        frontend = workflow("promote-production-frontends.yml")
        strict = next(
            s
            for s in deploy["jobs"]["verify-api-identity"]["steps"]
            if s.get("name") == "Fingerprint probe"
        )
        steps = frontend["jobs"]["verify"]["steps"]
        probe = next(
            s for s in steps if s.get("name") == "Verify exact production API identity (read-only)"
        )
        evidence = next(s for s in steps if s.get("name") == "Write production release evidence")
        self.assertLess(steps.index(probe), steps.index(evidence))
        self.assertNotIn("if", evidence)
        self.assertNotIn("continue-on-error", probe)
        self.assertEqual(probe["env"]["WANT_SHA"], "${{ needs.guard.outputs.sha }}")
        self.assertEqual(probe["run"], strict["run"])
        for wf in (deploy, frontend):
            self.assertEqual(wf["env"]["PROD_SUPABASE_PROJECT_REF"], PROJECT)
        for step in (strict, probe):
            self.assertEqual(self.probe(step, fingerprint()).returncode, 0)
            for field, value in (
                ("image_tag", OTHER),
                ("supabase_project_ref", "wrong-project"),
                ("env", "staging"),
            ):
                with self.subTest(step=step["name"], field=field):
                    self.assertNotEqual(
                        self.probe(step, {**fingerprint(), field: value}).returncode, 0
                    )

    def test_broader_verifier_requires_strict_success_and_explicit_identity_expectations(
        self,
    ) -> None:
        deploy = workflow("deploy-production.yml")["jobs"]["verify"]
        self.assertIn("verify-api-identity", deploy["needs"])
        self.assertIn("needs.verify-api-identity.result == 'success'", deploy["if"])
        for filename, step_name, expected_sha in (
            ("deploy-production.yml", "verify_live.sh", "${{ inputs.api_image_tag }}"),
            (
                "promote-production-frontends.yml",
                "verify_live.sh (read-only)",
                "${{ needs.guard.outputs.sha }}",
            ),
        ):
            steps = workflow(filename)["jobs"]["verify"]["steps"]
            env = next(s for s in steps if s.get("name") == step_name)["env"]
            self.assertEqual(env["MASTER_GIT_SHA"], expected_sha)
            self.assertEqual(env["EXPECTED_IMAGE_TAG"], expected_sha)
            self.assertEqual(env["EXPECTED_ENV"], "production")
            self.assertEqual(
                env["EXPECTED_SUPABASE_PROJECT_REF"], "${{ env.PROD_SUPABASE_PROJECT_REF }}"
            )

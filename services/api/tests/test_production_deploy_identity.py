"""Hermetic production workflow identity and wiring regressions.

Included by the existing broad Python pytest job; also runnable with unittest.
No application, provider credentials, database or network is required.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/production_deploy_identity.py"
SPEC = importlib.util.spec_from_file_location("production_deploy_identity_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity)
SHA = "a" * 40
PROJECT = "dpadrlxukcjbewpqympu"


def valid_fingerprint() -> dict[str, Any]:
    return {"env": "production", "git_sha": SHA, "image_tag": SHA,
            "supabase_project_ref": PROJECT}


class ProductionIdentityTests(unittest.TestCase):
    def request(self, **overrides: str) -> None:
        values = {"repository": "KaluMuso/Convergeo", "ref": "refs/heads/master",
                  "source_sha": SHA, "image_tag": SHA}
        values.update(overrides)
        identity.validate_request(**values)

    def validate(self, value: object, **overrides: str) -> None:
        values = {"expected_sha": SHA, "expected_project": PROJECT}
        values.update(overrides)
        identity.validate_fingerprint(value, **values)

    def test_exact_request_passes(self) -> None:
        self.request()

    def test_wrong_repository_and_ref_fail(self) -> None:
        for values in ({"repository": "attacker/Convergeo"},
                       {"ref": "refs/heads/staging"}, {"ref": "refs/tags/master"}):
            with self.subTest(values=values), self.assertRaises(identity.ProductionIdentityError):
                self.request(**values)

    def test_request_rejects_short_uppercase_malformed_or_shell_tags(self) -> None:
        for value in ("", "unknown", "latest", SHA[:7], SHA[:12], SHA[:39], SHA + "a",
                      "A" * 40, SHA + "\n", "$(touch /tmp/do-not-run)"):
            with self.subTest(value=value), self.assertRaises(identity.ProductionIdentityError):
                self.request(image_tag=value)

    def test_request_rejects_invalid_source_sha(self) -> None:
        with self.assertRaises(identity.ProductionIdentityError):
            self.request(source_sha=SHA[:7])

    def test_api_and_frontend_candidates_must_match(self) -> None:
        with self.assertRaises(identity.ProductionIdentityError):
            self.request(image_tag="b" * 40)

    def test_exact_fingerprint_passes(self) -> None:
        self.validate(valid_fingerprint())

    def test_unknown_missing_and_non_string_sha_fields_fail(self) -> None:
        cases: tuple[object, ...] = (None, "", "unknown", SHA[:7], True, 123, [], {})
        for field in ("git_sha", "image_tag"):
            for value in cases:
                with self.subTest(field=field, value=value):
                    fp = valid_fingerprint()
                    fp[field] = value
                    with self.assertRaises(identity.ProductionIdentityError):
                        self.validate(fp)
            fp = valid_fingerprint()
            del fp[field]
            with self.assertRaises(identity.ProductionIdentityError):
                self.validate(fp)

    def test_same_seven_and_twelve_character_prefixes_fail(self) -> None:
        for field in ("git_sha", "image_tag"):
            for prefix in (7, 12, 39):
                with self.subTest(field=field, prefix=prefix):
                    fp = valid_fingerprint()
                    fp[field] = "a" * prefix + "b" * (40 - prefix)
                    with self.assertRaises(identity.ProductionIdentityError):
                        self.validate(fp)

    def test_wrong_or_missing_environment_fails(self) -> None:
        for value in (None, "staging", "preview", "development", "Production"):
            with self.subTest(value=value), self.assertRaises(identity.ProductionIdentityError):
                self.validate({**valid_fingerprint(), "env": value})

    def test_wrong_project_fails_even_with_exact_sha(self) -> None:
        with self.assertRaises(identity.ProductionIdentityError):
            self.validate({**valid_fingerprint(), "supabase_project_ref": "iyasmrmbcrvlfxpzescb"})

    def test_expected_project_cannot_be_redirected_to_staging(self) -> None:
        with self.assertRaises(identity.ProductionIdentityError):
            self.validate(valid_fingerprint(), expected_project="iyasmrmbcrvlfxpzescb")

    def test_non_object_fingerprint_fails(self) -> None:
        cases: tuple[object, ...] = (None, [], "text", True, 12)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(identity.ProductionIdentityError):
                self.validate(value)

    def test_duplicate_json_keys_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "fp.json"
            p.write_text('{"git_sha":"unknown","git_sha":"' + SHA + '"}')
            with self.assertRaises(identity.ProductionIdentityError):
                identity.read_fingerprint(p)

    def test_oversized_unreadable_and_malformed_json_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "fp.json"
            with self.assertRaises(identity.ProductionIdentityError):
                identity.read_fingerprint(p)
            for raw in (b"{" , b"\xff", b" " * (identity.MAX_FINGERPRINT_BYTES + 1)):
                p.write_bytes(raw)
                with self.assertRaises(identity.ProductionIdentityError):
                    identity.read_fingerprint(p)

    def test_cli_fingerprint_exit_codes_and_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "fp.json"
            command = [sys.executable, str(SCRIPT), "fingerprint", "--fingerprint-file", str(p),
                       "--expected-sha", SHA, "--expected-project", PROJECT]
            p.write_text(json.dumps(valid_fingerprint()))
            good = subprocess.run(command, capture_output=True, text=True, check=False, timeout=5)
            self.assertEqual(good.returncode, 0, good.stderr)
            p.write_text(json.dumps({**valid_fingerprint(), "git_sha": "secret-sentinel"}))
            bad = subprocess.run(command, capture_output=True, text=True, check=False, timeout=5)
            self.assertEqual(bad.returncode, 1)
            self.assertNotIn("secret-sentinel", bad.stdout + bad.stderr)
            self.assertNotIn("Traceback", bad.stderr)

    def test_cli_request_exit_codes(self) -> None:
        args = [sys.executable, str(SCRIPT), "request", "--repository", "KaluMuso/Convergeo",
                "--ref", "refs/heads/master", "--source-sha", SHA, "--image-tag", SHA]
        self.assertEqual(
            subprocess.run(args, capture_output=True, check=False, timeout=5).returncode, 0
        )
        args[-1] = "b" * 40
        self.assertEqual(
            subprocess.run(args, capture_output=True, check=False, timeout=5).returncode, 1
        )


class ProductionWorkflowContractTests(unittest.TestCase):
    raw: ClassVar[str]
    workflow: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = (ROOT / ".github/workflows/deploy-production.yml").read_text()
        cls.workflow = yaml.load(cls.raw, Loader=yaml.BaseLoader)

    def test_only_manual_trigger_and_no_stale_default(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})
        self.assertNotIn(
            "default", self.workflow["on"]["workflow_dispatch"]["inputs"]["api_image_tag"]
        )

    def test_boolean_conditions_use_typed_inputs(self) -> None:
        jobs = self.workflow["jobs"]
        self.assertEqual(jobs["deploy-api"]["if"], "${{ inputs.skip_api != true }}")
        self.assertIn("inputs.skip_vercel == false", jobs["promote-vercel"]["if"])
        self.assertIn("inputs.verify_live == true", jobs["verify"]["if"])
        self.assertNotIn("github.event.inputs", self.raw)

    def test_guard_is_required_and_uses_environment_arguments(self) -> None:
        jobs = self.workflow["jobs"]
        self.assertEqual(jobs["deploy-api"]["needs"], "guard")
        self.assertEqual(jobs["promote-vercel"]["needs"], ["guard", "verify-api-identity"])
        steps = jobs["guard"]["steps"]
        self.assertEqual(steps[0]["uses"], "actions/checkout@v7")
        run = steps[1]["run"]
        self.assertIn("production_deploy_identity.py request", run)
        self.assertNotIn("${{", run)
        self.assertIn('checkout_sha="$(git rev-parse HEAD)"', run)
        self.assertIn('if [ "$checkout_sha" != "$GITHUB_SHA" ]', run)
        for arg in ("--repository", "--ref", "--source-sha", "--image-tag"):
            self.assertIn(arg, run)

    def test_fingerprint_uses_exact_validator(self) -> None:
        steps = self.workflow["jobs"]["verify-api-identity"]["steps"]
        probe = next(s for s in steps if s.get("name") == "Fingerprint probe")
        self.assertIn("production_deploy_identity.py fingerprint", probe["run"])
        self.assertIn('--expected-project "$PROD_SUPABASE_PROJECT_REF"', probe["run"])
        self.assertNotIn("startswith", self.raw)
        self.assertNotIn("::warning::fingerprint", self.raw)

    def test_verify_cannot_pass_when_guard_failed(self) -> None:
        verify = self.workflow["jobs"]["verify"]
        self.assertIn("guard", verify["needs"])
        self.assertIn("needs.guard.result == 'success'", verify["if"])

    def test_production_approval_and_non_cancelling_lock_preserved(self) -> None:
        jobs = self.workflow["jobs"]
        self.assertEqual(jobs["deploy-api"]["environment"], "production")
        self.assertEqual(jobs["promote-vercel"]["environment"], "production")
        self.assertEqual(self.workflow["concurrency"]["group"], "deploy-production")
        self.assertEqual(self.workflow["concurrency"]["cancel-in-progress"], "false")

    def test_ssh_key_cleanup_is_installed_before_transfer(self) -> None:
        steps = self.workflow["jobs"]["deploy-api"]["steps"]
        step = next(s for s in steps if s.get("name") == "Deploy SHA-tagged image via SSH")
        self.assertLess(step["run"].index("trap 'rm -f /tmp/prod_api_key' EXIT"),
                        step["run"].index("scp -i"))


if __name__ == "__main__":
    unittest.main()

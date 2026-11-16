"""Unit tests for detect_ci_scope.py (CI-SPEED tier selection)."""

from __future__ import annotations

import unittest

from detect_ci_scope import OUTPUTS, classify


def pr(files: list[str] | None, base: str = "release/2026-11-next", head: str = "feat/x"):
    return classify(files, event_name="pull_request", base_ref=base, head_ref=head)


class DetectCiScopeTests(unittest.TestCase):
    def test_push_and_schedule_run_everything(self) -> None:
        for event in ("push", "schedule", "workflow_dispatch"):
            result = classify([], event_name=event)
            self.assertTrue(all(result[k] for k in OUTPUTS if k != "docs_only"), event)
            self.assertFalse(result["docs_only"])

    def test_unknown_diff_fails_open(self) -> None:
        result = pr(None)
        self.assertTrue(all(result[k] for k in OUTPUTS if k != "docs_only"))

    def test_coordinator_review_lane_runs_everything(self) -> None:
        result = pr(["docs/a.md"], head="codex/coordinator-ci-review-1")
        self.assertTrue(result["run_typegen"] and result["run_heavy"])

    def test_docs_only_skips_everything_heavy(self) -> None:
        result = pr(["docs/plan/00-status.md", "README.md", "prompts/x.md"], base="master")
        self.assertTrue(result["docs_only"])
        for key in ("run_js", "run_security", "run_db_light", "run_typegen", "run_heavy", "run_perf"):
            self.assertFalse(result[key], key)
        self.assertTrue(result["run_python"])  # reduced doc-truth run

    def test_docs_txt_is_not_docs_only(self) -> None:
        result = pr(["docs/ops/lenco/f2-required-nodes.txt"])
        self.assertFalse(result["docs_only"])

    def test_empty_diff_is_not_docs_only(self) -> None:
        self.assertFalse(pr([])["docs_only"])

    def test_workflow_or_ci_script_change_runs_everything(self) -> None:
        for path in (".github/workflows/ci.yml", "scripts/ci/run-critical-real-stack.sh",
                     "services/api/uv.lock"):
            result = pr([path])
            self.assertTrue(result["run_typegen"] and result["run_heavy"] and result["run_perf"], path)

    def test_frontend_only_skips_db_and_real_stack(self) -> None:
        result = pr(["apps/customer/app/page.tsx"], base="master")
        self.assertTrue(result["run_js"] and result["run_python"] and result["run_security"])
        for key in ("run_db_light", "run_typegen", "run_heavy"):
            self.assertFalse(result[key], key)
        self.assertTrue(result["run_perf"])  # into master
        self.assertFalse(pr(["apps/customer/app/page.tsx"])["run_perf"])  # into release

    def test_api_into_master_runs_everything(self) -> None:
        result = pr(["services/api/app/services/search/x.py"], base="master")
        for key in OUTPUTS:
            if key != "docs_only":
                self.assertTrue(result[key], key)

    def test_non_money_api_into_release_skips_heavy_and_typegen(self) -> None:
        result = pr(["services/api/app/services/search/x.py"])
        self.assertTrue(result["run_db_light"])
        for key in ("run_typegen", "run_heavy", "run_perf"):
            self.assertFalse(result[key], key)

    def test_money_paths_keep_real_stack_on_release_prs(self) -> None:
        for path in (
            "services/api/app/services/ledger/post.py",
            "services/api/app/services/payments/lenco.py",
            "services/api/app/routers/webhooks_lenco.py",
            "services/api/app/core/auth.py",
            "supabase/migrations/20261101000000_x.sql",
        ):
            result = pr([path])
            self.assertTrue(result["run_heavy"] and result["run_perf"], path)
        self.assertTrue(pr(["supabase/migrations/20261101000000_x.sql"])["run_typegen"])

    def test_unclassified_change_runs_everything(self) -> None:
        self.assertTrue(pr(["Makefile"])["run_heavy"])


if __name__ == "__main__":
    unittest.main()

# Release path for #787 and #797

Checked 2026-11-15 against `origin/release/2026-11-next` at `fa95a058`. Nothing here was merged.

## Summary

| PR   | Branch                        | Base on GitHub                        | Merges cleanly into release?                    | CI on its head                                                     |
| ---- | ----------------------------- | ------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------ |
| #787 | `feat/admin-governance-d1-d5` | `master` (draft, `dirty`)             | No. 16 conflicting files, all mechanical        | No workflow runs on `5febff48`. Only Vercel previews, which failed |
| #797 | `feat/analytics-dashboards`   | `feat/admin-governance-d1-d5` (draft) | No. Same 16 files, plus it inherits all of #787 | 5 failing jobs on `2e6cbd27`                                       |

#797 is stacked on #787 (it contains all 19 of #787's commits plus 41 of its own). It can only land after #787, or together with it.

Note that both PRs target `master`, not the release branch. `release/2026-11-next` is 2 commits ahead of `master`, and `master` is 5 commits ahead of the release branch (PWA icon work and the #790 staging merge). Decide the target first, because it changes which conflicts you see (see step 1).

## #787: conflicts against the release tip

A trial merge (`git merge --no-commit origin/feat/admin-governance-d1-d5`, aborted afterwards) gives these conflicts.

| File                                                                                                                                                                                                                                                                      | Hunks       | Cause                                                                                                                             | Resolution                                                                                                                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.github/workflows/ci.yml`                                                                                                                                                                                                                                                | 1           | `EXPECTED_TYPEGEN_MIGRATION_COUNT` is 158 on release and 160 on #787                                                              | Set to **161** (release's 158 plus #787's 3 new files; see the count note below), then recompute from the directory                                                      |
| `scripts/ci/typegen_artifact.py`                                                                                                                                                                                                                                          | 2           | `MIGRATION_COUNT`, and the pending-repair version list                                                                            | Union of the version lists; recompute the count                                                                                                                          |
| `scripts/ci/run_coordinator_gates.py`                                                                                                                                                                                                                                     | 1           | Hard-coded 158 or 160 inventory size and message                                                                                  | Same count                                                                                                                                                               |
| `scripts/ci/coordinator-gate-inputs.json`                                                                                                                                                                                                                                 | 3           | Migration filename to sha256 map, and hashes of `run_financial_real_stack.py` and `rls/test_matrix.py`                            | Union the migration keys; **regenerate the file hashes** after resolving the code files (do not hand-merge hashes)                                                       |
| `scripts/ci/rehearse_explicit_transaction_profile.py`, `run_financial_real_stack.py`, `test_coordinator_gates.py`, `test_explicit_transaction_boundary.py`, `test_financial_ci_orchestration.py`, `test_synthetic_migration_history.py`, `typegen-synthetic-contract.sql` | 1 to 4 each | #787 ran `ruff format` over the tree, and release carries the #790 CI-script changes plus the notification-center migration       | Take release's side, then re-apply #787's few semantic edits (`git diff e734d051 origin/feat/admin-governance-d1-d5 -- <file>`); re-run `ruff format` last               |
| `services/api/tests/test_schema_convergence.py`                                                                                                                                                                                                                           | 4           | Ordered migration-tail assertions (`actual_versions[-N:]`) and `== 158 / 160`                                                     | Tail order must be: `audit_s1` (100000), `money_dispatch` (120500), `notification_center` (130000), `governance` (163000, 163100). Update the slice length and the total |
| `services/api/tests/test_reconcile_staging_migrations.py`                                                                                                                                                                                                                 | 1           | `PENDING_REPAIR_VERSIONS`                                                                                                         | Union: keep `20261113130000` and add `20261113163000`, `20261113163100`                                                                                                  |
| `services/api/tests/test_typegen_artifact_contract.py`                                                                                                                                                                                                                    | 1           | Count assertion                                                                                                                   | Same count                                                                                                                                                               |
| `services/api/tests/rls/test_matrix.py`                                                                                                                                                                                                                                   | 1           | Release adds `in_app_notifications` and `web_push_subscriptions` entries, #787 adds `privacy_consents`                            | Keep all three entries                                                                                                                                                   |
| `packages/i18n/messages/en/admin.json`                                                                                                                                                                                                                                    | 1           | Release appended `common` and `today` blocks at the end of the file, #787 appended `auditLogUi` and `accountsUi` at the same spot | Keep both sets of blocks; both are plain appends. Check the JSON still parses and that fr/zh have the same keys                                                          |

Count note: release has 158 migration files. #787 adds 3 (`20261113100000`, `20261113163000`, `20261113163100`), so the merged tree is 161, not 160. #787's own branch says 160 because its base was 157 files. Always recompute from the directory (`ls supabase/migrations | wc -l`) instead of trusting either side.

Auto-merged cleanly (no action): `DashboardBoard.tsx`, `admin-nav-capabilities.test.ts`, `PHASE1_NATIVE_REVIEW.md`, `packages/types/src/db.ts`.

### Admin shell compatibility (W4 vs #787)

#787 touches only these admin app files, and none overlap with this branch (`fix/admin-shell-ux`):

- `admin-nav-config.ts` adds the `accounts` and `auditLog` keys.
- `lib/admin-nav-capabilities.ts` and its test.
- `lib/roles-api.ts` adds `user_id` and 6 permission strings.
- `DashboardBoard.tsx`, `api.ts`, `dashboard-truth.ts`, `oversight-list.tsx`.
- New `accounts/` and `audit-log/` pages.

W4 edits `admin-shell.tsx` (not touched by #787), adds new files, `globals.css`, `KycReviewDetail.tsx`, `PendingCanonicalQueue.tsx`, and keys in `shell`, `translations.pages`, `kyc.detail` and `moderation.canonical.dialog` of the admin message files. The nav items render from `ADMIN_NAV_GROUPS`, so #787's new nav entries appear in the new sidebar automatically. W4 also keeps `roles-api.ts` unchanged on purpose (it was edited and then reverted), and it does not change `/admin/me/permissions`, because #787 edits that endpoint and exact-match tests cover it. `admin_kyc.py` is edited in different hunks from #787's formatting-only changes there.

### Migrations

No migration filename in #787 or #797 equals a file on the release branch, so there is no literal collision today. The problems are ordering and shared inventories.

- #787: `20261113100000_admin_money_tables_read_only.sql` sorts before release's `20261113120500` and `20261113130000`. If staging or production already applied those, Supabase will refuse the older version unless pushed with `--include-all`. The repo already tracks this in `PENDING_REPAIR_VERSIONS`, so keep that list in step.
- #787: `20261113163000` and `20261113163100` sit in the same band as `feat/logistics-phase1` (`150000`, `151000`), `feat/web-push-delivery` (`140000`) and `feat/cod-pay-at-door` (`183000`). Whichever of these lands second must not reuse a version, and every one of them edits the same count and tail assertions, so they will conflict with each other the same way.
- #797: seven files `20261113235000` to `20261113235600`. They are already renumbered once (commits `44806390`, `d973acda`). `feat/business-home` uses `233000` and `234000` just before them. No equal versions.
- Cross-branch rule (additive-only after M03): never edit an applied migration. If a rename is needed, do it before the first environment applies it.

If you prefer one clean band after everything else that is pending, renumber like this (git mv, then fix the references listed below):

| Old                                                  | New                                                           |
| ---------------------------------------------------- | ------------------------------------------------------------- |
| `20261113100000_admin_money_tables_read_only.sql`    | `20261117000000_admin_money_tables_read_only.sql`             |
| `20261113163000_admin_direct_writes_read_only.sql`   | `20261115100100_admin_direct_writes_read_only.sql`            |
| `20261113163100_admin_governance_audit_consent.sql`  | `20261115100200_admin_governance_audit_consent.sql`           |
| `20261113235000` to `20261113235600_analytics_*.sql` | `20261115110000` to `20261115110600`, same suffixes and order |

References to update after any rename: `scripts/ci/coordinator-gate-inputs.json` (keys and, if file content changed, hashes), `scripts/ci/typegen_artifact.py`, `services/api/tests/test_schema_convergence.py`, `services/api/tests/test_reconcile_staging_migrations.py`, `scripts/ci/test_synthetic_migration_history.py`, comments inside the SQL that name sibling versions, and `docs/plan/` runbooks (grep for the old version strings).

## #797: failing checks and extra conflicts

Failing on `2e6cbd27`: Python API, Migration replay (fast), Financial real-stack execution, Critical real-stack execution (88 identities), COD production-container smoke.

From the job logs:

1. `tests/test_service_role_import_guard.py::test_service_role_imports_confined_to_allowlist`: `app/routers/admin_analytics.py` and `app/routers/admin_analytics_dashboards.py` import the service-role client directly. Fix by routing them through the approved dependency (`get_supabase_client`) or by adding them to the allowlist with a justification.
2. `tests/test_typegen_artifact_contract.py:97`: asserts `migration_count == 160` while the branch has 167 files. Update to the recomputed count.
3. `tests/test_configurable_admin_roles.py:531`: `len(role_api.service.resource_reads) == reads` fails (1 vs 0), and the fake `RoleDbQuery` has no `insert`, so denied-attempt audit writes fail in the harness. This looks like the #787 and #797 route-permission map disagreeing with the test fake. Re-run after #787 is rebased, then fix the fake or the permission map.
4. The migration replay and real-stack jobs fail on the count and inventory assertions above; confirm after fixing items 1 to 3 rather than assuming.

#797 conflicts: the same 16 files as #787 plus whatever the analytics commits add to the inventories (`test_matrix.py` +40 lines, `test_schema_convergence.py`, `test_reconcile_staging_migrations.py`, `coordinator-gate-inputs.json`). Resolve #787 first; the #797 conflicts then reduce to the count and tail lines.

#787 has not had CI run on `5febff48` at all (draft; only Vercel previews reported, and those failed). Treat its CI status as unknown until it runs.

## Exact steps

Pick the integration target first. These steps assume the release branch. Do all work on a throwaway branch per PR and never force-push.

1. Retarget or sync.
   - If the PRs should land on the release branch: `gh pr edit 787 --base release/2026-11-next`. Then #797 stays based on #787 and is retargeted automatically when #787 merges.
   - If they land on `master` first: merge `origin/master` into the release branch before this work, so both branches start from the same tree.
2. Rebase #787 on the release tip, as a merge to avoid rewriting history:
   ```
   git fetch origin
   git switch -c fix/787-release-sync origin/feat/admin-governance-d1-d5
   git merge origin/release/2026-11-next
   ```
3. Resolve the 16 files using the table above. Order matters:
   1. Python and CI scripts: take release's side, re-apply #787's semantic edits, run `ruff format`.
   2. `test_matrix.py`, `test_schema_convergence.py`, `test_reconcile_staging_migrations.py`: union.
   3. `en/admin.json`: keep both appended blocks.
   4. Recompute counts: `N=$(ls supabase/migrations/*.sql | wc -l)` (expected 161) and write it into `ci.yml`, `typegen_artifact.py`, `run_coordinator_gates.py`, `test_schema_convergence.py`, `test_typegen_artifact_contract.py`.
   5. Regenerate the hashes in `scripts/ci/coordinator-gate-inputs.json` (use the generator the CI script documents, or `sha256sum` each listed file).
4. Decide on the renumbering (previous section). If renumbering, do it in this commit, before anything is applied to an environment.
5. Verify locally, in the foreground:
   ```
   pnpm i && pnpm --filter admin test && pnpm --filter admin typecheck && pnpm --filter admin lint
   cd services/api && uv run ruff check && uv run mypy && uv run pytest tests/test_schema_convergence.py tests/test_typegen_artifact_contract.py tests/test_reconcile_staging_migrations.py tests/test_admin_role_route_matrix.py tests/test_configurable_admin_roles.py tests/test_authz_matrix.py -q
   supabase db reset   # needs the local stack; runs the full replay
   ```
6. Push the sync branch and open it as the PR head (or push to `feat/admin-governance-d1-d5` with a normal merge commit). Wait for the full CI run, since #787 has none today. Do not merge until Migration replay, Python API, both real-stack jobs and the COD smoke are green.
7. #797: `git switch -c fix/797-release-sync origin/feat/analytics-dashboards`, merge the updated #787 branch, then `git merge origin/release/2026-11-next`. Resolve only the count and tail conflicts, fix the three failing tests above, and recompute the counts (expected 168 if #787 is renumbered or not; 158 + 3 + 7).
8. Order of merges: #787, then #797, then this W4 branch (or W4 before #787; the files do not overlap, only `en/admin.json` shares a file and the edits are in different regions).
9. After merge, apply migrations to staging with `supabase db push --include-all` only if `supabase migration list` shows version gaps below the applied tail, and record the repaired versions in `PENDING_REPAIR_VERSIONS`.

Open decisions for the founder: the integration target (master or release), whether to renumber, and whether the two analytics routers should use the approved Supabase dependency or be allowlisted.

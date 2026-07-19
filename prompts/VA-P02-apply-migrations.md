> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VA-P02 — Apply migrations 0051/0053–0056 (staging-first) `[OPS]`

## 1. Context
**Wave 1.** Source: `01-audit-findings.md` DL-3; MR-S01/MR-S11; `release-gates.md` S0/G0. **Depends on VA-P00 (backup) + Wave-0 decisions B-2 (FORCE RLS) and B-3 (role-hook path).**
**Live drift (2026-07-19, verified via `list_migrations`):** applied set ends at `0050` + `20260717100303` (which is `0052_product_relations` under a non-standard version key). **Unapplied on live:** `0051_custom_access_token_role_hook`, `0053_translation_overrides`, `0054_service_reviews`, `0055_service_bookable`, `0056_kyc_integrity`. Repo is complete through `0056`.
**Type:** `[OPS]` — Cursor writes the ordered apply script + verification SQL + evidence doc; the **founder applies to an identifier-distinct STAGING/branch DB** (never prod in this pebble).

## 2. Objective & scope
Apply `0051`, `0053`, `0054`, `0055`, `0056` **in order** to a **staging/branch** database, verify every object, and record the result — so the production apply (VC-P01) is de-risked.
**Non-goals:** **production apply** (that is VC-P01, only after staging PASS + orphan report); **enabling the Auth custom-access-token hook** (VC-P03); the FORCE-RLS migration `0057` (VC-P02). Do not renumber committed migrations.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/migrations-apply.md`
- `scripts/db/verify-0051-0056.sql` (idempotent, read-only object/columns/function checks)
**Guardrail: modify ONLY these files; the migration `.sql` files already exist and must NOT be edited.**

## 4. Implementation spec (runbook)
1. **Confirm VA-P00 backup exists** (timestamp + checksum) before any apply.
2. Reconcile the `0052` version-key skew per **DB-01/MR-S01**: live carries `0052` as `20260717100303`; agree the target `schema_migrations` set with the DBA before applying so the replay does not collide (the repo's `scripts/ci/migration-replay.sh` duplicate-prefix guard is the reference).
3. Apply in order on staging/branch: `0051` → `0053` → `0054` → `0055` → `0056`.
4. Run `scripts/db/verify-0051-0056.sql` and confirm:
   - `0051`: `custom_access_token_hook` (and related) function present.
   - `0053`: `translation_overrides` table present.
   - `0054`: `service_reviews` extensions present.
   - `0055`: `services.bookable` column present.
   - `0056`: KYC integrity trigger `guard_kyc_record_integrity`, its view/columns present; **legacy `kyc pending → submitted`** handled per `impl/kyc-integrity-report.md`.
5. Record staging `schema_migrations` head in the evidence doc.

## 9. Security
- Applied against **staging/branch only**; service-role/DSN never logged. RLS on new tables verified by the RLS matrix job (do not disable RLS to apply).

## 10. Tests / verification (RUN before reporting)
- `scripts/db/verify-0051-0056.sql` returns all-present (paste the boolean result table).
- `bash scripts/ci/migration-replay.sh` (or the CI `migrations`/`db`/`rls` jobs) green on staging.
- Confirm the KYC guard rejects an unauditable privileged mutation (per `test_kyc_integrity.py`).

## 11. Acceptance criteria / DoD
- [ ] Backup (VA-P00) confirmed **before** apply.
- [ ] `0051,0053,0054,0055,0056` applied in order on staging; `schema_migrations` matches the agreed target incl `0056`.
- [ ] All five object checks pass; legacy KYC statuses handled; no data loss.
- [ ] **Production untouched** (prod apply is VC-P01).

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VA-P02 — Apply migrations 0051/0053–0056 (staging-first)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste verify-SQL result + migration-replay/db/rls job status
**EXCERPTS:** the object-check SQL and its output (redacted)
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")

> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VA-P00 — Pre-migration backup artifact `[OPS]`

## 1. Context
**Wave 0 foundation.** Source: `docs/production-readiness/2026-07-19/vision-audit/03-waves-and-phases.md` (VM-A) + `01-audit-findings.md` X-2. Closes the backup-before-DDL rule (`release-gates.md` G7; MR-O04/MR-W04). No dated backup currently exists, and VA-P02 (staging migrations) + VC-P01 (prod `0056`) apply DDL — **a verified backup MUST exist first.** Live DB: Supabase `dpadrlxukcjbewpqympu` (eu-north-1), applied `≤0050` + `20260717100303`(=`0052`).
**Type:** `[OPS]` — Cursor writes the runbook + evidence stub + verification helper; the **founder executes** the dump (dashboard/CLI access) and pastes redacted proof.

## 2. Objective & scope
Produce a **dated, restore-verified logical backup** of the live DB and record the restore point in an evidence doc, so any later migration is reversible.
**Non-goals:** the restore drill itself (VE-P03), authoring the recurring backup workflow (VD-P04), and **any DDL** (this pebble is read/dump only).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/backup-YYYYMMDD.md`
- `scripts/db/backup-verify.sh` (optional helper: `pg_restore --list` + sha256 of a dump path)
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec (runbook the founder executes)
- Take a full logical dump: `pg_dump "$SUPABASE_DB_URL" -Fc -f vergeo5-YYYYMMDD.dump` (custom format), **or** trigger a platform PITR/snapshot and record its id/time.
- **Verify restorable shape without restoring to prod:** `pg_restore --list vergeo5-YYYYMMDD.dump | head` succeeds and shows expected tables; compute `sha256sum`.
- Record in the evidence doc: UTC timestamp, storage location, size, sha256, dump command used, and Supabase project ref. **No secrets, no PII, no connection string** in the doc.
- The timestamp MUST be **before** VA-P02 runs.

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A.

## 9. Security
- Connection string / service-role key **never** logged or committed; `backup-verify.sh` takes a path arg, not a DSN.
- Dump contains PII → stored in access-restricted storage; the evidence doc records location + checksum only.

## 10. Tests / verification (RUN before reporting)
- `bash -n scripts/db/backup-verify.sh` + `shellcheck`.
- `pg_restore --list <dump>` returns a non-empty object list (paste head, redacted).
- sha256 recorded and matches the stored artifact.

## 11. Acceptance criteria / DoD
- [ ] Dated dump exists in restricted storage; timestamp **before** VA-P02.
- [ ] `pg_restore --list` proves restorable shape; sha256 recorded.
- [ ] Evidence doc has location + size + checksum + timestamp; **zero secrets/PII**.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** VA-P00 — Pre-migration backup artifact
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste shellcheck + `pg_restore --list` head (redacted) + sha256
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")

> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VD-P04 — Author + deploy DB backup workflow `[CODE+OPS]`

## 1. Context
**Wave 2.** Source: `01-audit-findings.md` BG-5 / DL-4; MR-W04; `release-gates.md` G7. **The one workflow the docs promise that has no repo artifact:** `infra/n8n/backup-schedule.md` specs a nightly DB dump but **no JSON exists**, and n8n has no backup workflow → backup RPO is unproven. VA-P00 is a one-off manual backup; this makes it recurring.
**Type:** `[CODE+OPS]` — Cursor authors the JSON + `scripts/db-dump.sh` (if absent); the **founder** imports/activates in n8n and confirms one dump.

## 2. Objective & scope
Author and deploy a scheduled nightly logical-dump workflow with a failure-alert branch, and produce one successful dated dump.
**Non-goals:** the restore drill (VE-P03, Wave 4); other workflows.

## 3. Files (create ONLY these)
- `infra/n8n/backup.json`
- `docs/ops/n8n-workflows.md` (add the registry row — this pebble is its sole editor this wave)
- `scripts/db-dump.sh` (only if not already present; else reference it → DEVIATIONS)
**Guardrail: modify ONLY these files.**

## 4. Implementation spec
- **`backup.json`** per `backup-schedule.md`: `scheduleTrigger` cron `0 2 * * *` **Africa/Lusaka** → Execute-Command `scripts/db-dump.sh` → on non-zero exit, a failure-alert branch (WhatsApp Cloud API to founder, mirroring `uptime-alert`/`admin-digest`). Ships `active:false` with credential placeholder per house convention; the founder activates.
- **`scripts/db-dump.sh`:** `pg_dump` (custom format) → gzip + UTC timestamp → upload to OCI Object Storage (document `oci`/rclone env names), **retention prune** per policy, non-zero exit on failure, connection string **never** logged.
- **`docs/ops/n8n-workflows.md`:** add the `backup.json` row (trigger, endpoint/command, purpose, owner `VM-D`) so the registry completeness test (`test_n8n_registry.py`) passes.

## 9. Security
- No secrets in JSON or repo; `infra/.env.example` names only. Dumps contain PII → restricted bucket + encryption noted. Script never echoes the DSN.

## 10. Tests (RUN before reporting)
- `bash -n scripts/db-dump.sh` + `shellcheck`.
- `uv run pytest services/api/tests/test_n8n_registry.py -q` green (registry row present).
- Local dump round-trip against the local Supabase stack (paste redacted output).
- Founder: one successful scheduled/manual run produces a dated artifact; failure branch fires on a forced error.

## 11. Acceptance criteria / DoD (maps to G7 / MR-W04)
- [ ] `backup.json` authored + registered + importable; nightly cron in Africa/Lusaka.
- [ ] `scripts/db-dump.sh` round-trips locally; retention prune implemented; non-zero exit on failure.
- [ ] One dated dump produced; failure-alert branch proven.
- [ ] Registry completeness test green; zero secrets committed.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VD-P04 — Author + deploy DB backup workflow
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste shellcheck + registry test + local dump round-trip
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")

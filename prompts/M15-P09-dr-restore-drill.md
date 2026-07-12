> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (parallel batch 1). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (`git worktree add /tmp/base origin/master`). **⚠ DEFERRED-AC:** the live drill (actually restoring staging from a real dump) needs infra this build env lacks — build the runbook + script + smoke tests + a TEMPLATE drill-log, and mark the live-timing AC as founder/staging-gated. Do NOT block the PR on a real restore.

# M15-P09 — Backup restore drill & DR runbook

## 1. Context

**Grounded against as-built `master`:** Supabase Postgres 16 (managed backups); OCI Always-Free VM (Docker Compose: api, caddy, n8n); Cloudflare + Vercel + Supabase cloud; Lenco payments; migrations `supabase/migrations/NNNN_*.sql` (latest 0029). Money = ngwee; escrow via `post_transaction`. **No live staging DB is reachable from this build env** — so the restore script must be runnable/smoke-testable against a LOCAL Postgres (or a dry-run mode), and the actual staging-restore transcript is a founder/staging step (template it).
Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P09.

## 2. Objective & scope

DR runbook (DB loss, OCI VM loss, Supabase outage, Vercel outage, Lenco outage — RTO/RPO + **exact commands, not prose** per scenario; Lenco-outage degraded mode = COD/pickup continue), a restore-staging script (dump → fresh restore + smoke verify: row counts, migrations current) runnable against local PG or `--dry-run`, and a drill-log (template + a locally-executed dry-run transcript; the real ≤30min staging drill is founder-gated).
**Non-goals:** no app code change, no migration, no live production credentials in the repo (env only).

## 3. Files (create/modify ONLY these)

- **Create:** `docs/ops/runbook-disaster-recovery.md` (per-scenario: trigger, RTO/RPO target, exact restore/failover commands, verification, Lenco-outage degraded-mode = COD+pickup continue) · `scripts/ops/restore-staging.sh` (dump → fresh DB restore → smoke verify: row counts + `migrations current` check; supports `--dry-run` + a `SUPABASE_DB_URL`/local-PG target; NO hardcoded secrets) · `docs/ops/drill-log.md` (drill transcript template + the local dry-run you actually ran, with timings + a clearly-marked "LIVE STAGING DRILL — founder-gated (needs staging + nightly dump)" section)
- **Optional (only if needed to smoke the script):** `scripts/ops/restore-smoke.sql` (invariant queries — row counts, latest migration).
  **Guardrail: nothing else. Docs + ops scripts only. Do NOT touch app code, db.ts, migrations, CI workflows, other pebbles' files.**

## 4. Implementation spec

- **`runbook-disaster-recovery.md`:** one section per scenario with a copy-pasteable command block (Supabase point-in-time restore / `pg_restore`; OCI VM re-provision via docker-compose; Vercel redeploy; Cloudflare failover; Lenco-outage → flip to COD/pickup-only degraded mode). RTO/RPO as numbers. No vague prose — commands.
- **`restore-staging.sh`:** `set -euo pipefail`; take a dump (or accept a dump path), restore into a fresh target DB (`SUPABASE_DB_URL` or a local ephemeral PG), then run smoke assertions: expected tables present, `schema_migrations`/migration count current vs `supabase/migrations/`, non-zero row counts on seed tables. `--dry-run` prints the plan without mutating. Exit non-zero on any smoke failure. Secrets from env only.
- **`drill-log.md`:** the template + your actual LOCAL dry-run run (timestamps, steps, timing) + an explicit founder-gated block for the real staging ≤30min drill (what to run, what to record).

## 5–9. Security etc.

No secrets in repo (env/args only); restore script idempotent + `set -euo pipefail`; smoke assertions fail loudly; Lenco-outage degraded mode documented (COD/pickup continue — money-safe: no escrow release without provider confirmation); the live-timing AC is explicitly founder/staging-gated (not faked).

## 10. Tests (RUN before reporting)

`bash scripts/ops/restore-staging.sh --dry-run` succeeds; if a local Postgres is available, run a real local restore + smoke (paste timings); `bash -n scripts/ops/restore-staging.sh` (syntax); runbook command/link validity check (every command block is a real command, every internal link resolves). If you CANNOT stand up a local PG, run `--dry-run` + `bash -n` and say so.

## 11. Acceptance criteria / DoD

- [ ] Every scenario has exact commands (not prose) + RTO/RPO numbers; Lenco-outage degraded mode defined; restore script smoke-verifies row counts + migrations-current; drill-log has a real local dry-run transcript.
- [ ] **Live staging ≤30min drill clearly marked founder/staging-gated (deferred, not faked);** no secrets in repo; script syntax + dry-run green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P09 — Backup restore drill & DR runbook
**STATUS/FILES/DEVIATIONS** (the scenarios + RTO/RPO; the restore-script smoke assertions; what you ran locally vs what's founder-gated) **/TESTS** (paste dry-run + any local restore timings + bash -n + link check) **/EXCERPTS** the restore-staging.sh smoke-assert block + the Lenco-outage degraded-mode section — nothing else **/QUESTIONS** (state clearly that the live ≤30min staging drill is deferred to the founder with staging access)

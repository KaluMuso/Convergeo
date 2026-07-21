> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY docs + scripts below** — this is an **ops verification pebble**, no app code, no schema. Never print secrets. Foreground blocking only.

# CR-E — Deploy + verify + rollback runbook (close the deploy gap)

## Finding

Per `docs/plan/00-status.md` (2026-07-20) the launch gap is deploy/ops, not features: API `api.vergeo5.com` returned **502**; migrations **0051, 0053–0056** unapplied to live; **n8n workflows 0 active**; `vendor.vergeo5.com` / `admin.vergeo5.com` DNS+Vercel wiring incomplete; staging money-drill + deploy/rollback + observability-capture gates (G0–G9) not PASS. There is no single authoritative, executable path from "master tip" to "verified live + rollback-tested."

## Required fix (runbook + verification scripts, idempotent, read-mostly)

- Author `docs/ops/deploy-verify-runbook.md` — the **single source** for: (1) applying outstanding Supabase migrations to the target env in order (0051, 0053–0056, + any newer) with a pre-apply `supabase db diff` check; (2) deploying the API to OCI (Docker Compose: api/caddy/n8n) and confirming `api.vergeo5.com` returns 200 on `/healthz` + `/readyz`; (3) promoting the three Vercel frontends and confirming DNS for customer/vendor/admin origins; (4) activating the required n8n workflows and confirming they are live; (5) a **rollback** procedure for each (API image, migration, Vercel deployment) with a ≤30-min restore-drill checklist.
- Add `scripts/ops/verify_live.sh` — a **non-destructive** post-deploy verifier that curls the existing health surface (`/healthz`, `/health`, `/readyz`, and **`/fingerprint`** — which returns `env` + `git_sha` + `supabase_project_ref`, so the script can assert **staging ≠ production** and that the deployed `git_sha` matches master tip), checks the applied-migration list matches expected, checks the n8n active-workflow count, and prints a PASS/FAIL matrix mapped to gates G0–G9. Read-only; no writes to prod.
- Cross-link the runbook from `launch-checklist.md §3` (reference only — do not edit the checklist's gate signatures).

## Files (ONLY)

- Add `docs/ops/deploy-verify-runbook.md`
- Add `scripts/ops/verify_live.sh` (+ make it `shellcheck`-clean)
- **Do NOT touch** `launch-checklist.md` gate rows, app code, migrations, infra secrets, or Compose files (reference their paths; don't rewrite them).

## Tests (RUN)

- `shellcheck scripts/ops/verify_live.sh`. Dry-run `verify_live.sh` against staging (or with a mocked base URL) and paste the PASS/FAIL matrix. Confirm the runbook's migration list matches `supabase/migrations/` reality.

## Report

STATUS / FILES / DEVIATIONS / TESTS (paste the verifier matrix + shellcheck) / EXCERPTS (the rollback steps + the gate→check mapping) / QUESTIONS (any gate you cannot verify without live creds).

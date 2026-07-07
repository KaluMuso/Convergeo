> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P06 — CI pipeline

## 1. Context
**Wave 0, pebble 6 of 7 (sequential).** Depends on **M01-P02–P05** (there is now real JS + Python + a Supabase pipeline to gate). Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P06. CI must be green on the repo exactly as it stands after P05.

## 2. Objective & scope
PR-gating GitHub Actions: turbo-affected JS checks, Python checks, Supabase reset + typegen drift check, gitleaks secret scan, dependency audits, concurrency-cancel — plus a stubbed deploy workflow and the required-checks list documented in the README.
**Non-goals:** no real deployment (P07 owns deploy tooling; the workflow job stays a stub), no perf/Lighthouse budgets (M16-P01, Wave 10), no E2E.

## 3. Files (create ONLY these, plus the one README edit)
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml` (stub jobs, `workflow_dispatch` only)
- `.gitleaks.toml`
- `scripts/ci/` (helper scripts the workflows call, e.g. `typegen-drift.sh`)
- **Modify:** `README.md` — fill the "Required CI checks" placeholder section only (P01 left the slot; Wave 0 is sequential so this shared-file edit is safe and sanctioned)
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec
- **ci.yml** (on `pull_request` + push to default; `concurrency` cancel-in-progress per ref; least-privilege `permissions:`):
  1. **js:** pnpm + Node 20 (cached), `pnpm i --frozen-lockfile`, then turbo-affected `lint`, `typecheck`, `test`, `build` (`--filter=...[origin/<default>]` or turbo-affected equivalent).
  2. **python:** uv + Python 3.12, `uv sync`, `uv run ruff check`, `uv run mypy`, `uv run pytest` (workdir `services/api`).
  3. **db:** Supabase CLI, `supabase db reset` (local stack in CI), then `scripts/ci/typegen-drift.sh` — regenerates types and **fails if `packages/types/src/db.ts` is stale** (git diff non-empty).
  4. **secrets:** gitleaks with `.gitleaks.toml` (tuned allowlist for docs/fixtures); fails on any finding.
  5. **audit:** `pnpm audit --audit-level=high` + `uv`/`pip-audit` for the API (fail-on-high wired later by M15-P05 — run as warn/report now, but the job must exist).
- **deploy.yml:** `workflow_dispatch`; stub jobs (`deploy-api-oci`, `deploy-customer-vercel`) that echo TODO and reference secret **names** only (`OCI_SSH_KEY`, `VERCEL_TOKEN`, …). Real deploy logic arrives with P07's `deploy.sh`.
- **README:** required-checks list (job names to mark Required in branch protection).

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A.

## 9. Security
- Workflows: least-privilege `permissions:` (default `contents: read`), `--frozen-lockfile`, no secret values anywhere, no `pull_request_target` foot-guns.
- gitleaks config must not allowlist real secret patterns.

## 10. Tests (RUN / verify before reporting)
- Validate workflows with `actionlint` (or YAML parse if unavailable).
- Fixture tests for `scripts/ci/` helpers (`bash -n` + a stale-types simulation for the drift script).
- **Gitleaks dry run:** plant a dummy AWS-style key in a scratch file on a test branch, show gitleaks catches it, remove it — transcribe the run in the report (per the pebble's AC), do not commit the dummy.
- Confirm every job's commands pass locally against the current repo state (paste outputs).

## 11. Acceptance criteria / DoD
- [ ] CI green on the repo as of P05 (all jobs).
- [ ] Typegen drift check fails when `db.ts` is stale (demonstrated).
- [ ] Planted dummy secret caught by gitleaks (dry run transcribed).
- [ ] deploy.yml is dispatch-only stub, secret names only.
- [ ] Required-checks list in README; least-privilege permissions on workflows.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P06 — CI pipeline
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste actionlint/local-run output + the gitleaks + drift demonstrations
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")

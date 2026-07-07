> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P07 — OCI runtime, deploy, backups & rollback

## 1. Context
**Wave 0, pebble 7 of 7 (sequential) — closes the foundations.** Depends on **M01-P06**. Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P07. Read also: `docs/plan/00-decisions.md` D21 (OCI Always-Free ARM, Cloudflare, Vercel, ≤$50/mo; nightly dump → OCI Object Storage via n8n), D20 (admin separate origin).

## 2. Objective & scope
Committed, reproducible runtime + ops: Docker Compose (api, caddy, n8n; pinned digests), Caddyfile (TLS + baseline security headers), api Dockerfile, `deploy.sh` (tagged deploy + rollback), nightly pg_dump → OCI Object Storage (14-day retention) via n8n, and two runbooks. **No console-clicked config anywhere.**
**Non-goals:** no live cloud provisioning (founder executes runbooks), no real secrets, no admin IP-allowlist hardening (M13-P01 owns the later Caddyfile edit), no full n8n workflow suite (M14).

## 3. Files (create ONLY these)
- `infra/docker-compose.yml`, `infra/Caddyfile`, `infra/.env.example` (names only)
- `services/api/Dockerfile`
- `infra/deploy.sh`
- `infra/backup/pg-dump.sh`, `infra/n8n/backup-nightly.json`
- `docs/ops/runbook-deploy-rollback.md`, `docs/ops/runbook-dns-cloudflare.md`
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec
- **docker-compose.yml:** services `api` (image by tag, healthcheck `/health`, env-file, restart unless-stopped), `caddy` (80/443, Caddyfile + cert volume), `n8n` (persisted volume, behind Caddy). **Pinned image digests** for caddy/n8n; internal network; named volumes; no inline secrets. `docker compose config` must validate.
- **Caddyfile:** blocks for `api.`, `vendor.`, `admin.` hosts (admin = separate origin per D20; a comment marks where M13-P01 will add the allowlist) — automatic TLS, reverse proxy, **baseline security headers** (HSTS, X-Content-Type-Options, frame-ancestors, Referrer-Policy). `caddy validate` must pass.
- **Dockerfile (`services/api/`):** multi-stage (uv build → slim runtime), **non-root user**, `EXPOSE 8000`, uvicorn CMD, `GIT_SHA` build-arg → env (feeds `/health`), `.dockerignore` NOT created here if it requires touching root (inline ignore via build context notes → DEVIATIONS if needed).
- **deploy.sh:** `deploy.sh <tag>` = pull tagged images + `compose up -d` + health-wait; `deploy.sh rollback <tag>` = pin previous tag and re-up. Idempotent, `set -euo pipefail`, no secrets echoed.
- **pg-dump.sh:** nightly logical dump (`DATABASE_URL` from env), gzip + timestamp, upload to OCI Object Storage (document `oci` CLI or rclone env names), **14-day retention prune**, non-zero exit on failure, connection string never logged.
- **backup-nightly.json:** importable n8n workflow — cron (off-peak) → execute `pg-dump.sh` → failure alert placeholder (wired to founder notification in M14).
- **runbook-deploy-rollback.md:** VM bring-up (Always-Free ARM, Docker install), first deploy, tagged rollback, **transcribed staging deploy + rollback exercise** (per AC), RTO/RPO statement, escrow-reconciliation caveat (coordinate M08 recon around any DB restore).
- **runbook-dns-cloudflare.md:** DNS records (api/vendor/admin → OCI proxied; apex/www → Vercel), proxy/WAF-lite/caching posture.

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A. Cloudflare caching posture noted in the DNS runbook.

## 9. Security
- No secrets/values committed — `infra/.env.example` names only; dumps contain PII → bucket access restricted + encryption noted in runbook.
- api container non-root; images digest-pinned; baseline headers on all origins; admin origin separated.
- `pg-dump.sh` / `deploy.sh` never echo credentials.

## 10. Tests (RUN before reporting)
- `docker compose -f infra/docker-compose.yml config` validates.
- `caddy validate --config infra/Caddyfile` passes.
- `bash -n` + `shellcheck` on `deploy.sh`, `pg-dump.sh` (shellcheck runs in CI per pebble spec — if CI wiring needs a `ci.yml` edit, record under DEVIATIONS for the P06 owner).
- `docker build services/api` succeeds; container runs as non-root (`docker inspect`/`whoami`).
- Local dump/restore round-trip of a seeded row using `pg-dump.sh` against the local Supabase stack (paste output).

## 11. Acceptance criteria / DoD
- [ ] `docker compose config` + `caddy validate` pass; api image builds, non-root.
- [ ] `deploy.sh <tag>` and `deploy.sh rollback <tag>` logic complete + transcribed in the runbook (staging exercise or documented dry-run if no staging creds).
- [ ] Backup script round-trips locally; retention prune implemented; n8n workflow importable.
- [ ] Runbooks are copy-pasteable commands, not prose; no console-clicked steps anywhere.
- [ ] Zero secrets committed.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P07 — OCI runtime, deploy, backups & rollback
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste compose/caddy/shellcheck/build + dump round-trip output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")

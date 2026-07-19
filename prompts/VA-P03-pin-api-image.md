> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VA-P03 — Pin & redeploy API image `[OPS]`

## 1. Context
**Wave 1.** Source: `01-audit-findings.md` DL-5; MR-B10; `release-gates.md` G9. **Live drift (07-18/07-19):** the FastAPI container behind Caddy is healthy but its **git SHA / image digest is NOT_AUDITABLE** (OpenAPI reports version `0.1.0`, GHCR manifest needs auth). The KYC-lifecycle admin routes `/admin/kyc/{id}/start-review|suspend|revoke` **returned 404 on the live host** (07-19 fingerprint) — evidence the deployed API predates #293. Host: Hetzner CX23, system Caddy; image `ghcr.io/kalumuso/convergeo-api`.
**Type:** `[OPS]` — Cursor writes the evidence doc (+ a minimal `infra/redeploy-api.sh` fix only if needed); the **founder** reads the GHCR digest and redeploys on the host.

## 2. Objective & scope
Pin the API to the image built from the current `master` tip, redeploy, confirm the KYC-lifecycle routes are live, and **record the image digest** in a release ledger.
**Non-goals:** DB migrations (VA-P02); n8n activation (VM-D); CORS/host config changes beyond redeploy.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/api-image.md`
- `infra/redeploy-api.sh` — **edit only if** a digest-pin fix is required (else leave untouched → note in DEVIATIONS)
**Guardrail: modify ONLY these files.**

## 4. Implementation spec (runbook)
- Read the GHCR digest for `ghcr.io/kalumuso/convergeo-api` corresponding to the `master`-tip build (via authenticated `docker manifest inspect` or the GHCR UI).
- Set `API_IMAGE_TAG` to that digest/tag on the host env; `docker pull` by digest; redeploy via `infra/redeploy-api.sh`; restart behind Caddy.
- Confirm the deployed API now exposes the KYC-lifecycle routes (200, authed) rather than 404.
- Record digest + deploy time in `api-image.md` (the release-ledger row referenced by `release-gates.md` G9).

## 9. Security
- No tokens/DSN echoed. Service-role key stays host-side. Confirm `/internal/*` still require `X-Internal-Token`. Non-root container preserved.

## 10. Tests / verification (RUN before reporting)
```bash
curl -sS -m15 https://api.vergeo5.com/healthz    # {"status":"ok"} via Caddy
curl -sS -m15 https://api.vergeo5.com/readyz
curl -sS -m15 -o /dev/null -w "%{http_code}\n" -X POST https://api.vergeo5.com/admin/kyc/00000000-0000-0000-0000-000000000000/start-review   # 401/403 (route EXISTS) — NOT 404
curl -sS -m15 https://api.vergeo5.com/openapi.json | grep -c "kyc/{"   # KYC lifecycle paths present
```

## 11. Acceptance criteria / DoD
- [ ] Image digest recorded in `api-image.md` (≠ "unknown").
- [ ] `/admin/kyc/{id}/start-review|suspend|revoke` return **401/403 authed** (route present), not 404.
- [ ] `/healthz` + `/readyz` 200 behind Caddy; internal ticks still token-gated.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VA-P03 — Pin & redeploy API image
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste health + KYC-route + openapi grep output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")

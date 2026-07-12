# OWASP Top-10 audit — Vergeo5 API (M15-P05)

Audit of the as-built `master` against the OWASP Top-10 (2021). Each row links to the
code / test evidence that mitigates the risk, or records a **finding** with a fix
reference for a later wave. This wave adds **no app-code fixes** — findings are
documented and, where CI-blocking, pinned with written justification (see A06).

**Enforcement backbone shipped this pebble**

- `services/api/tests/test_authz_matrix.py` — route × role authz matrix: **182 routes ×
  6 personas = 1092 cells**, 100% classified. Anon → 401, wrong-role → 403,
  `/internal/*` → 401 without the shared token, webhooks → ≥400 unsigned, and every
  id-bearing protected route denies an anonymous object reference (IDOR necessary
  condition). Includes a **trip-wire** that fails CI if a new route is dependency-public
  without being registered — catches an endpoint shipped without an authz guard.
- `scripts/security/pentest-lite.sh` — live probe against a running server: authz
  matrix, `/internal` token, webhook-signature, anonymous IDOR, and SSRF/open-redirect;
  non-zero exit on any HIGH finding. Latest run: **314 probes, 0 findings**.
- CI security gates (`.github/workflows/ci.yml`): `deps-audit` now **fails on high**
  (pnpm + pip), `check-headers.mjs` + the authz matrix run in a blocking `security-gates`
  job, and gitleaks stays wired.

Legend: ✅ mitigated (evidence) · ⚠ finding (documented, fix deferred).

| #       | Category                           | Status | Evidence / Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------- | ---------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A01** | Broken Access Control              | ✅     | **Defence in depth, three layers.** DB: RLS on every table, proven by the isolation matrix `services/api/tests/rls/test_matrix.py` (public table × 6 personas × 4 verbs). API guard: `app/core/auth.py` (`get_current_user` verifies the JWT + loads DB-backed roles; `require_role(...)` gates by role — a forged `role` claim without a DB row is 403, see `tests/test_auth_dep.py::test_forged_admin_claim_without_db_role_returns_403`). Route×role: `tests/test_authz_matrix.py` (this pebble). IDOR: owner-scoped lookups return a **uniform 404** for missing-or-non-owned (`app/routers/invoices.py::_not_found`), never distinguishing the two.                                                                      |
| **A02** | Cryptographic Failures             | ✅     | TLS + HSTS (`max-age=63072000; preload`) enforced at every origin — `scripts/ci/check-headers.mjs`, `infra/Caddyfile`, `apps/*/next.config.ts`. JWTs verified against Supabase JWKS with `RS256/ES256` and issuer/audience pinning (`app/core/auth.py::verify_supabase_jwt`). Invoice download links are HMAC-SHA256 signed + short-TTL (`app/routers/invoices.py::sign_invoice_token`/`verify_invoice_token`). Money is integer ngwee; `Decimal` only at the Lenco boundary (no float). Secrets only in env, never repo (A08/gitleaks).                                                                                                                                                                                      |
| **A03** | Injection                          | ✅     | All request bodies/queries validated by Pydantic v2 strict schemas (`app/schemas/`, `app/routers/*`). DB access goes through the Supabase/PostgREST client with parameterised filters — no string-concatenated SQL in `app/`. FTS/trgm queries bind params. Uniform error envelope `{"error":{code,message,details}}` never reflects raw input back as executable content.                                                                                                                                                                                                                                                                                                                                                    |
| **A04** | Insecure Design                    | ✅     | Money/escrow/KYC/dispute transitions run through guarded state-machine functions with an append-only `audit_log` (never raw status UPDATEs) — see `supabase/migrations` + `tests/test_order_state.py`. Payment webhooks are idempotent (Lenco reference = encoded `ord-/pay-/rfd-` ids). Escrow "held → released" ledger orchestration (`tests/test_ledger.py`).                                                                                                                                                                                                                                                                                                                                                              |
| **A05** | Security Misconfiguration          | ✅     | Security headers + strict nonce-CSP (no `unsafe-inline` on `script-src`), per-origin framing, Lenco widget scoped to the customer `checkout/card` route only — statically enforced by `scripts/ci/check-headers.mjs` (wired blocking this pebble). CORS is an explicit allowlist (`app/main.py`, `settings.cors_origin_list`), not `*`. Admin is a separate hardened origin (`infra/Caddyfile` `hardened_edge`). Unhandled errors return a generic 500 with no stack/secret leak (`tests/test_errors.py`).                                                                                                                                                                                                                    |
| **A06** | Vulnerable & Outdated Components   | ⚠      | CI dependency audit is now **blocking on high** — `deps-audit` runs `pnpm audit --audit-level=high` (with a documented advisory allowlist) and `pip-audit` (no `continue-on-error`). **Finding F1 (accepted):** `tmp <0.2.6` path-traversal **HIGH** `GHSA-ph9p-34f9-6g65`, transitive via `@lhci/cli@0.14.0` (Lighthouse CI). Dev/CI-only, never bundled into any shipped app or the API runtime → **no production exposure**. Allowlisted in the CI audit step with justification; remove the allowlist entry when `@lhci/cli` ships a `tmp ≥0.2.6`. Fix ref: `prompts/fixes/M15-P05-bump-lhci-tmp.md`. pip side is clean (0 vulns).                                                                                        |
| **A07** | Identification & Auth Failures     | ✅     | Phone-OTP / email / Google via Supabase Auth; every API request re-verifies the JWT signature + expiry server-side (`app/core/auth.py`, `tests/test_auth_dep.py` covers expired/tampered/missing → 401). OTP abuse throttled (`app/routers/auth_guard.py` `otp-quota`). Rate limiting across mutating endpoints (`app/core/ratelimit.py`; sweep + fuzz in M15-P04). Roles are DB-sourced, not claim-trusted.                                                                                                                                                                                                                                                                                                                  |
| **A08** | Software & Data Integrity Failures | ✅     | Lenco webhooks verify the provider signature before persistence (`app/services/payments/webhook_verify.py`, `app/routers/webhooks_lenco.py`); WhatsApp webhook verifies the challenge token (403 otherwise). Ingestion is idempotent (unique `webhook_events` → 23505 swallow). Secret scanning via gitleaks (`.gitleaks.toml`, CI `secret-scan`). `pnpm i --frozen-lockfile` pins the supply chain.                                                                                                                                                                                                                                                                                                                          |
| **A09** | Logging & Monitoring Failures      | ✅     | Structured JSON logging with per-request correlation ids (`app/logging.py`, `app/middleware.py::RequestIdMiddleware`); every error envelope carries `request_id`. Security-relevant transitions land in `audit_log`. Errors never log secrets/tokens (generic unhandled handler, `tests/test_errors.py`).                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **A10** | Server-Side Request Forgery (SSRF) | ⚠      | Small attack surface: no endpoint fetches an arbitrary user-supplied URL server-side. Media signing targets a fixed Cloudinary host (`app/routers/media.py`); "Ask" retrieval is over the internal index, not user URLs. `pentest-lite.sh` actively probes `/media/sign` + `/ask` with link-local/loopback payloads and public routes for open-redirect (`?next=/redirect=`) — **0 findings**. **Finding F2 (minor hardening):** `POST /webhooks/lenco` returns **500** (not a clean 4xx) when the signature header is absent — the unsigned payload is **not** processed (no access-control impact), but the status should be `400/401` for cleaner observability. Fix ref: `prompts/fixes/M15-P05-webhook-unsigned-4xx.md`. |

## Findings summary

| ID  | Sev  | Category | Status                     | Action                                                                                                                                                                                                                   |
| --- | ---- | -------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| F1  | High | A06      | **Accepted / allowlisted** | `tmp <0.2.6` (`GHSA-ph9p-34f9-6g65`) via `@lhci/cli`; CI/dev-only, no prod exposure. Allowlisted in `deps-audit` with justification. Drop the allowlist when lhci bumps `tmp`. `prompts/fixes/M15-P05-bump-lhci-tmp.md`. |
| F2  | Low  | A10      | **Documented, deferred**   | `/webhooks/lenco` unsigned → 500 instead of 4xx. No access-control impact (payload not processed). App-code fix deferred (this wave adds no app fixes). `prompts/fixes/M15-P05-webhook-unsigned-4xx.md`.                 |

No IDOR, privilege-escalation, or broken-access finding surfaced by the route×role
matrix or the live pen-test: every protected route denies anon (401) and cross-role
(403), and every id-bearing route denies an anonymous object reference.

## Running the checks locally

```bash
# Route × role authz matrix (no DB required)
cd services/api && uv run pytest tests/test_authz_matrix.py -q

# Live pen-test-lite (needs a running local API on BASE_URL)
(cd services/api && uv run uvicorn app.main:app --port 8000 &) ; sleep 3
BASE_URL=http://127.0.0.1:8000 bash scripts/security/pentest-lite.sh

# Security headers manifest check
node scripts/ci/check-headers.mjs

# Dependency audit (as CI runs it)
pnpm audit --audit-level=high ; (cd services/api && uv tool run pip-audit)
```

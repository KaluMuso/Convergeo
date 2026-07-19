# Staging blockers — 2026-07-19

**Source tip:** `cc4a8241d25e4c715903ba4ca161fb95491ff52b` (evidence session); STG-01 infra on PR #300  
**Evidence:** `staging-release-evidence.md`  
**Rule:** Blockers are launch-blocking for STAGING_VERIFIED / real-money enablement.

**STG-01 note (infra/CI only):** Staging pipeline, separation guards, OCI/Vercel/n8n
templates, synthetic seeder, and runbooks landed in PR #300. **SB-01 remains open**
until a real staging Supabase project + API host + secrets are provisioned and
proven distinct from production (see `staging-provisioning-checklist.md`).

---

## P0 blockers (must clear before staging gate PASS)

| ID    | Class               | Blocker                                                                              | Proof                                                                                                                    | Owner              | Unblock action                                                                                                                      |
| ----- | ------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| SB-01 | DEPLOYMENT_REQUIRED | No separable Vergeo5 staging stack (infra code ready; resources not provisioned)     | Supabase has no staging Vergeo5 project; Preview env not wired; n8n still targets prod until staging plane is brought up | founder / ops      | Follow `staging-provisioning-checklist.md` + `Deploy staging` workflow; prove IDs ≠ prod `dpadrlxukcjbewpqympu` / `api.vergeo5.com` |
| SB-02 | BLOCKED_UNSAFE      | Cannot seed synthetic users/orders/payments safely                                   | Only live DB = production `dpadrlxukcjbewpqympu`                                                                         | release eng        | After SB-01, seed `stg-rv-*` fixtures only on staging                                                                               |
| SB-03 | BLOCKED             | Lenco sandbox credentials unavailable                                                | Agent env has no Lenco sandbox secrets; no staging payment endpoint proven                                               | payments / founder | Provide sandbox keys + webhook URL on staging API only                                                                              |
| SB-04 | FAIL                | Migration `0056` not applied on any staging DB (absent staging; also absent on prod) | `schema_migrations` lacks 0056; KYC CHECK still `pending\|approved\|rejected`                                            | db                 | Apply `0051`/`0053`–`0056` per agreed plan on **staging first**                                                                     |
| SB-05 | FAIL                | Live API not proven at tip for KYC lifecycle (#293)                                  | OpenAPI lacks `start-review`/`suspend`/`revoke`; POST → 404                                                              | api                | Deploy API image built from `cc4a824` (or later) to staging; fingerprint digest                                                     |
| SB-06 | FAIL                | Escrow release + ticket n8n workflows missing/inactive                               | MCP: only notification dispatch + payment recon active                                                                   | ops                | Import/activate staging `release-job`, `event-release`, `tickets-issue` (+ auth tokens)                                             |
| SB-07 | FAIL                | No STAGING_VERIFIED payment collection (#274)                                        | payments=0; ledger=0; no sandbox drill                                                                                   | payments           | MoMo+card sandbox → single `CHARGE_RECEIVED` + webhook replay                                                                       |
| SB-08 | FAIL                | No STAGING_VERIFIED release accounting (#294)                                        | cannot run release without SB-01/03/06/07                                                                                | escrow             | Capture-before-release drill; product/service/event; idempotent double-tick                                                         |
| SB-09 | FAIL                | Customer `/en/categories` returns HTTP 500 on tip production deploy                  | `www.vergeo5.com/en/categories` → 500                                                                                    | customer           | Fix categories route; re-verify on staging/prod                                                                                     |
| SB-10 | FAIL                | Backup + restore not proven                                                          | No backup workflow in n8n; drill-log founder-gated; OCI listing NOT_AUDITABLE                                            | ops                | Dated backup artifact + scratch restore PASS in drill-log                                                                           |
| SB-11 | FAIL                | Observability incomplete                                                             | No Vergeo5 Sentry projects; uptime NOT_AUDITABLE                                                                         | ops                | Create projects; ingest test events; wire alerts                                                                                    |
| SB-12 | PARTIAL             | API image digest / rollback artifact incomplete                                      | OpenAPI version `0.1.0` only; GHCR digest not read                                                                       | ops                | Record `API_IMAGE_TAG` + digest; dry-run rollback per `infra/ROLLBACK.md`                                                           |

## P1 / access blockers

| ID    | Class            | Blocker                                                                             | Unblock                                                            |
| ----- | ---------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| SB-13 | BLOCKED_EXTERNAL | Vercel deployment URLs SSO-gated (`vercel.com/sso-api`)                             | Share bypass or dedicated staging domains without SSO for UAT bots |
| SB-14 | BLOCKED          | No staging test users (customer / vendors / KYC reviewer / unauthorized admin-like) | Provision OTP map + role grants on staging only                    |
| SB-15 | BLOCKED          | Cloudflare Access auditor session unavailable for deep admin UI                     | Temporary Access allowlist for staging verifier                    |
| SB-16 | FAIL (env)       | Seller CTA unavailable (`NEXT_PUBLIC_VENDOR_APP_URL` unset/invalid)                 | Set vendor prod/staging URL; redeploy; HTML probe                  |
| SB-17 | OPEN             | Legal counsel sign-off FD-08 absent                                                 | Written artifact (out of eng scope)                                |

## What is _not_ a staging PASS

| Claim                                             | Status                                          |
| ------------------------------------------------- | ----------------------------------------------- |
| Required PRs merged on master                     | TRUE — does **not** clear S1–S7                 |
| Vercel production frontends at `cc4a824`          | TRUE — production deploy ≠ staging verification |
| Unit/integration CODE_COMPLETE for #274/#294/#293 | TRUE — maturity layer only                      |
| Unauthorized admin/internal deny on live API      | Shell PASS — not a money/KYC lifecycle PASS     |

## Dependency order to clear staging

1. **SB-01** separable staging identifiers proven
2. Deploy API tip + apply migrations through **0056** on staging (**SB-04/05**)
3. Activate staging n8n release/tickets (**SB-06**)
4. Sandbox Lenco + synthetic users (**SB-03/14**)
5. Execute S1–S6 drills; attach redacted IDs
6. Backup/restore + Sentry (**SB-10/11**)
7. Fix categories 500 (**SB-09**) and CTA env (**SB-16**) before panel UAT sign-off

Until SB-01–SB-08 clear: **do not** enable real prepaid money or claim STAGING_VERIFIED.

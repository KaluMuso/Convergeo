# Critical Risk Register — Vergeo5 Production Readiness

**Audit date:** 2026-07-18 · **Contract:** `document-audit-contract.md`  
**Rule:** Do **not** mark resolved without direct VERIFIED evidence that the failure mode cannot occur.

Row format: source | fact | target | key | evidence | status | impact | action | owner

---

## R1 — Seller/vendor CTA localhost fallback

| Field              | Value                                                                                                                                                                                           |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | Known risk; PR #268 seller-cta fix; `apps/customer/.../vendor-app.ts`                                                                                                                           |
| extracted fact     | If `NEXT_PUBLIC_VENDOR_APP_URL` unset, production must not emit `localhost:3001`                                                                                                                |
| target             | Customer sell CTAs → vendor onboarding                                                                                                                                                          |
| matching key       | `NEXT_PUBLIC_VENDOR_APP_URL`                                                                                                                                                                    |
| evidence           | Live `/en/sell`: **no** `localhost:3001`; CTAs **disabled** with “Vendor signup is temporarily unavailable”. Code fail-closed in production. Vendor app itself is live at `vendor.vergeo5.com`. |
| status             | **PARTIAL** — localhost failure mode mitigated; **seller acquisition CTA still broken** (env likely unset)                                                                                      |
| impact             | Cannot convert sellers from customer marketing surface                                                                                                                                          |
| recommended action | Set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer` and redeploy; re-verify CTA href                                                                            |
| owner              | Founder / Vercel customer env                                                                                                                                                                   |

---

## R2 — Prepaid MoMo/card checkout fails to create ledger entries

| Field              | Value                                                                                                                                                                                                                                                                                                                   |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | Known money risk; Wave-15 note on ticket escrow gating on `payments.status` without ESCROW_HOLD                                                                                                                                                                                                                         |
| extracted fact     | Successful prepaid collection should post `CHARGE_RECEIVED` / escrow hold legs                                                                                                                                                                                                                                          |
| target             | `payments` success path → `ledger_transactions` / `ledger_postings`                                                                                                                                                                                                                                                     |
| matching key       | `LedgerTemplate.CHARGE_RECEIVED` / `ESCROW_HOLD`                                                                                                                                                                                                                                                                        |
| evidence           | Repo: `transition_payment` / `apply_payment_status` update `payments` + `audit_log` only — **no** `post_transaction`. Grep shows prepaid webhook/initiate paths do not call ledger templates; COD/job_completion/admin/refund/release do. Live: `payments=0`, `ledger_transactions=0` (cannot observe runtime success). |
| status             | **PARTIAL** (strong code evidence of missing hook; **not** runtime-proven with a live paid order)                                                                                                                                                                                                                       |
| impact             | Escrow balances, reconciliation, payouts, liability dashboards wrong/empty after real MoMo/card pay                                                                                                                                                                                                                     |
| recommended action | Trace payment-success → ledger in a **sandbox** checkout; add VERIFIED fixture before real-money launch                                                                                                                                                                                                                 |
| owner              | Payments / M08                                                                                                                                                                                                                                                                                                          |

---

## R3 — n8n workflows missing or inactive (escrow, tickets, backups)

| Field              | Value                                                                                                                                                                                                                                                    |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | `docs/ops/n8n-workflows.md`; known risk list                                                                                                                                                                                                             |
| extracted fact     | Escrow auto-release, ticket issuance, DB backups must run in prod                                                                                                                                                                                        |
| target             | n8n + `/internal/*` ticks                                                                                                                                                                                                                                |
| matching key       | workflow names / `infra/n8n/*.json`                                                                                                                                                                                                                      |
| evidence           | Live n8n: **only 2** workflows active (notification dispatch + payment reconciliation crons). Missing live: `release-job`, `tickets-issue`, `order-jobs`, `event-release`, embeddings, reservation sweeper, digests, backup (only `backup-schedule.md`). |
| status             | **VERIFIED MISSING** for escrow release / ticket issue / most ops; backup **MISSING** as workflow (**NOT_AUDITABLE** whether ad-hoc OCI cron exists)                                                                                                     |
| impact             | Paid tickets may never issue; escrow may never auto-release; backup RPO unproven                                                                                                                                                                         |
| recommended action | Import/activate registry workflows with tokens; prove one tick each; document backup host proof                                                                                                                                                          |
| owner              | Ops / M13–M14 / M10                                                                                                                                                                                                                                      |

---

## R4 — Thin/absent observability & empty admin analytics

| Field              | Value                                                                                                                                                             |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | M16-P06 founder-gated; known risk                                                                                                                                 |
| extracted fact     | Sentry + uptime + admin analytics must observe production                                                                                                         |
| target             | Sentry projects; UptimeRobot; `analytics_events` / admin dashboard                                                                                                |
| matching key       | `SENTRY_DSN` / `NEXT_PUBLIC_SENTRY_DSN`                                                                                                                           |
| evidence           | Sentry org `convergeo-w2` has **no** Vergeo5 projects (only zed\*). Admin dashboard UI exists but analytics/funnel tables are **0** rows. UptimeRobot not probed. |
| status             | **VERIFIED** thin/absent for Sentry projects; analytics streams empty (**PARTIAL** for “implementation incomplete” vs “no traffic”)                               |
| impact             | Production errors/money failures may go unseen; go-live monitoring gate unmet                                                                                     |
| recommended action | Create Sentry projects + set DSNs; configure UptimeRobot; fire test event; confirm admin tiles against non-zero aggregates after traffic                          |
| owner              | Founder / M16-P06                                                                                                                                                 |

---

## R5 — Live demo / seed data

| Field              | Value                                                                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | Status notes; known risk                                                                                                                          |
| extracted fact     | Production must not present demo inventory as real marketplace without disclosure/cleanup                                                         |
| target             | `vendors`, `vendor_listings`, `listing_images`, public catalog                                                                                    |
| matching key       | `demo/%` Cloudinary prefix; vendor slugs                                                                                                          |
| evidence           | 3 demo vendors; 134 listings; **134** `listing_images` with `cloudinary_public_id LIKE 'demo/%'`; catalog API `total=134`; 0 real orders/payments |
| status             | **VERIFIED**                                                                                                                                      |
| impact             | Misleading UX; SEO pollution; wrong trust signal for real-money launch                                                                            |
| recommended action | Label as demo / replace with real vendors / feature-flag public_launch until ready                                                                |
| owner              | Founder / merchandising                                                                                                                           |

---

## R6 — Missing or incomplete product features

| Feature                         | Repo / live signal                                                                     | Status                | Impact                                   |
| ------------------------------- | -------------------------------------------------------------------------------------- | --------------------- | ---------------------------------------- |
| Wishlist                        | Heart labels on cards; SELECTION.md notes affordance-only; no wishlist table/API found | MISSING / PARTIAL     | Expectation gap vs designs               |
| Referrals                       | Explicitly OUT of v1 (`00-decisions.md`)                                               | MISSING (by decision) | Doc conflict if business docs require it |
| Recently viewed                 | No dedicated table/route found                                                         | MISSING               |                                          |
| Reorder                         | No customer reorder flow found                                                         | MISSING               |                                          |
| Saved search                    | No table/route found                                                                   | MISSING               |                                          |
| City guides                     | OUT of v1 / Phase 3 in research                                                        | MISSING (by decision) |                                          |
| Vendor staff RBAC               | Single vendor owner model; no staff roles table                                        | MISSING               | Multi-user vendors blocked               |
| Admin users/roles management UI | `user_roles` service-role only; no admin CRUD UI found                                 | MISSING               | Manual SQL/dashboard role grants         |

Use standard rows in document audits when mapping business docs → these gaps.

---

## R7 — Non-blocking CI gates

| Field              | Value                                                                                                                                                                                                                                                                                                                                                    |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | `.github/workflows/ci.yml`, `perf.yml`, `docs/ops/ci.md`                                                                                                                                                                                                                                                                                                 |
| extracted fact     | Security/quality gates must be blocking on `master`                                                                                                                                                                                                                                                                                                      |
| target             | GitHub Actions required checks                                                                                                                                                                                                                                                                                                                           |
| matching key       | `continue-on-error`                                                                                                                                                                                                                                                                                                                                      |
| evidence           | `secret-scan` has `continue-on-error: true` yet docs list it as required. `i18n-lint` non-blocking. Lighthouse `continue-on-error: true`. `docs/ops/ci.md` still says `deps-audit` informational while workflow claims fail-on-high (**CONFLICT** docs vs YAML). Branch-protection “do not allow bypassing” is founder-gated (not verifiable from code). |
| status             | **VERIFIED** non-blocking jobs exist; branch protection enforcement **NOT_AUDITABLE** from this session                                                                                                                                                                                                                                                  |
| impact             | Defects/secrets can merge despite red/advisory checks                                                                                                                                                                                                                                                                                                    |
| recommended action | Remove `continue-on-error` from secret-scan; align docs; confirm GitHub branch protection UI                                                                                                                                                                                                                                                             |
| owner              | Founder / platform                                                                                                                                                                                                                                                                                                                                       |

---

## R8 — Deployment / commit drift (customer, vendor, admin, API)

| Field              | Value                                                                                                                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source reference   | Known risk                                                                                                                                                                                     |
| extracted fact     | All four runtimes should pin known commits/images                                                                                                                                              |
| target             | Vercel prods + API container                                                                                                                                                                   |
| matching key       | git SHA / `API_IMAGE_TAG`                                                                                                                                                                      |
| evidence           | Customer/vendor/admin production deployments **match** `8cc1fa0`. API SHA/digest **NOT_AUDITABLE**. DB migrations **behind** repo (`0051`/`0053`–`0055` missing; `0052` version key conflict). |
| status             | **PARTIAL** — frontends aligned; API unknown; **DB CONFLICT**                                                                                                                                  |
| impact             | Feature/security fixes in git may be absent from API/DB; audits falsely assume parity                                                                                                          |
| recommended action | Read host `API_IMAGE_TAG`/image digest; apply/reconcile migrations with care; pin and record versions in a release ledger                                                                      |
| owner              | Ops                                                                                                                                                                                            |

---

## Priority release blockers (from this register)

1. **R2** prepaid ledger posting gap (money integrity) — sandbox VERIFIED required
2. **R3** missing n8n escrow release + ticket issuance (+ backup proof)
3. **R8/DB** migration drift before relying on repo-tip features/hooks
4. **R1** seller CTA env (acquisition)
5. **R5** demo catalogue before public real-money positioning
6. **R4** Sentry/uptime before treating staging as observable
7. **R7** CI/branch-protection hardening

Feature gaps in R6 are **product-scope** blockers only if business documents claim they are in v1; otherwise track as roadmap MISSING with decision reference.

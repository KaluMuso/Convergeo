# Panel & Platform Backlogs — Customer · Vendor · Admin · API · DB · Payments · n8n · Ops

**Date:** 2026-07-18 (refresh after PRs #274, #289–#294)  
**Canonical IDs:** `master-reconciliation-register.md` (MR-*)  
**Maturity:** mark each item `OPEN` · `CODE_COMPLETE` · `STAGING_VERIFIED` · `PRODUCTION_VERIFIED`  
**Rule:** Implementation cites evidence + acceptance. No production DB edits without reviewed migration / controlled import. Do not invent founder decisions (`source-conflicts-and-decisions.md`).

**Priority:** P0 = release blocker · P1 = launch quality · P2 = hygiene / post-gate

---

## Status legend for backlog rows

| Status        | Meaning                                                |
| ------------- | ------------------------------------------------------ |
| OPEN          | Not done                                               |
| CODE_COMPLETE | Merged on master; staging/live evidence still required |
| BLOCKED       | Waiting on dependency / founder decision               |
| OUT           | Explicitly out of v1                                   |

---

## Customer panel backlog

**Surface:** `apps/customer` · `www.vergeo5.com`  
**Landed:** PR **#289** (CUST-03/04/07/08/10)

| ID      | Pri | Status                | Title                            | Evidence                          | Remaining work                                                                                                            | Acceptance                                         | Depends on                   |
| ------- | --- | --------------------- | -------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- | ---------------------------- |
| CUST-01 | P1  | OPEN (env)            | Restore seller acquisition CTA   | foundation R1; fail-closed code   | Set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer`; redeploy; HTML probe                 | CTA → vendor prod; no localhost; not “unavailable” | Founder / Vercel             |
| CUST-02 | P1  | BLOCKED               | Demo catalogue disclosure / gate | catalog `total=134`; D25 conflict | Founder FD-04: label **or** exclude demo; no fake seed                                                                    | Cannot mistake for national marketplace            | FD-04 / MR-D01               |
| CUST-03 | P1  | CODE_COMPLETE         | Categories browse entry          | PR #289                           | Deploy customer SHA; re-probe `/en/categories`                                                                            | 200 + navigable Phase-1 roots                      | Deploy                       |
| CUST-04 | P1  | CODE_COMPLETE         | Comparison entry                 | PR #289                           | Deploy; ops multi-listing density optional                                                                                | Compare usable or honest empty                     | Deploy                       |
| CUST-05 | P1  | CODE_COMPLETE (build) | PWA SW delivery                  | #289 emits `sw.js`; live was 404  | Deploy + `GET /sw.js` 200                                                                                                 | Installability check                               | Deploy                       |
| CUST-06 | P1  | OPEN                  | Events Phase-1 discovery UX      | events BL-009                     | Lenses/badges when supply exists                                                                                          | Matches Phase-1; honest empty                      | Events supply + MR-W02       |
| CUST-07 | P1  | CODE_COMPLETE         | Launch copy vs locked decisions  | PR #289 CUST-07                   | Re-probe live hero after deploy                                                                                           | No Yango/own-fleet/Django/Meilisearch claims       | Deploy                       |
| CUST-08 | P0  | CODE_COMPLETE (UI)    | Checkout false-success hardening | PR #289; G4                       | Staging E2E; harden residual checkout `localhost:8000` fallbacks in step-* components; ledger field on status if required | No paid UI without confirmed policy                | MR-B01 staging; API contract |
| CUST-09 | P1  | OPEN                  | Escrow trust UX copy             | CLAUDE.md                         | Wire “paid → held → released” to real statuses                                                                            | Never invent states                                | MR-B01, MR-W01               |
| CUST-10 | P2  | CODE_COMPLETE         | Calendar route                   | PR #289 redirect                  | Deploy + probe                                                                                                            | No dead 404                                        | Deploy                       |
| CUST-11 | P2  | OPEN                  | Lighthouse budgets               | roadmap BL-21                     | Mobile Fast-3G/360px                                                                                                      | Perf≥90 SEO≥95 A11y≥95 or waiver                   | Egress                       |
| CUST-12 | P2  | OUT                   | Wishlist/reorder                 | foundation R6                     | Keep OUT; no half-affordance                                                                                              | Explicit OUT                                       | Product                      |
| CUST-13 | P1  | OPEN                  | Customer storefront KYC badges   | integration §4.4                  | Align `/v/[slug]` to auditable eligibility (not bare `kyc_tier`)                                                          | No verified badge without approved record          | MR-B11 / #293 deploy         |

### Customer verification commands

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -o /tmp/sell.html -w "%{http_code}\n" https://www.vergeo5.com/en/sell
python3 -c 'from pathlib import Path;h=Path("/tmp/sell.html").read_text();print("localhost", "localhost:3001" in h);print("unavailable", "unavailable" in h.lower())'
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/categories
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/compare
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/sw.js
```

---

## Vendor panel backlog

**Surface:** `apps/vendor` · `vendor.vergeo5.com`  
**Landed:** PR **#291** (VEND-01 UI / analytics honesty); API half PR **#293**

| ID      | Pri | Status                 | Title                            | Evidence                  | Remaining work                                              | Acceptance                                  | Depends on              |
| ------- | --- | ---------------------- | -------------------------------- | ------------------------- | ----------------------------------------------------------- | ------------------------------------------- | ----------------------- |
| VEND-01 | P0  | CODE_COMPLETE (UI+API) | KYC tier integrity               | #291 UI; #293 eligibility | Apply `0056`; staging capability drills; prod orphan repair | Privileges only with approved `kyc_records` | MR-S11, ops             |
| VEND-02 | P1  | OPEN                   | Sandbox KYC E2E                  | kyc_records=0             | Upload → under_review → approve                             | One sandbox vendor completes KYC            | Admin + private storage |
| VEND-03 | P1  | PARTIAL                | Listing create UX audit          | product F038              | Test JWT timed attach/quick_list                            | Timing evidence filed                       | Vendor test JWT         |
| VEND-04 | P1  | BLOCKED                | Complete listing modes UI        | API 3/5 modes             | After API unique/MTO                                        | Five flows reachable                        | MR-B06                  |
| VEND-05 | P1  | BLOCKED                | Offline door scanner cache       | events BL-006             | Cache + scan-sync                                           | Offline then sync                           | MR-W02                  |
| VEND-06 | P1  | BLOCKED                | Evidence photos (used goods)     | product RB-PS-007         | Only if FD-06 includes used goods                           | Non-new rejects missing evidence            | MR-S06 / FD-06          |
| VEND-07 | P1  | BLOCKED                | Event organiser publish path     | events empty              | Free RSVP + small paid under beta                           | ≥1 published beta event                     | MR-W02 for paid         |
| VEND-08 | P1  | CODE_COMPLETE (UI)     | Organiser fee / stats honesty    | #291 empty honesty        | Ledger-backed stats after staging money                     | No fabricated GMV                           | MR-B01 staging          |
| VEND-09 | P2  | BLOCKED                | Co-organiser / door roles UX     | events BL-008             | After MR-S09                                                | Door scans only                             | MR-S09                  |
| VEND-10 | P2  | OUT                    | Vendor staff RBAC                | foundation R6             | Stay OUT unless FD-10 ADR                                   | Documented OUT                              | FD-10                   |
| VEND-11 | P1  | OPEN                   | Localhost API fallback residuals | integration §4.3          | Fail-closed production API base on touched clients          | No prod localhost:8000                      | Vendor eng              |

---

## Admin panel backlog

**Surface:** `apps/admin` · Access-gated  
**Landed:** PR **#290** (ADM-06/07 honesty); KYC admin routes PR **#293**

| ID     | Pri           | Status                  | Title                               | Evidence                       | Remaining work                                 | Acceptance                        | Depends on          |
| ------ | ------------- | ----------------------- | ----------------------------------- | ------------------------------ | ---------------------------------------------- | --------------------------------- | ------------------- |
| ADM-01 | P0            | BLOCKED                 | Resolve admin RBAC model            | roadmap F033 vs single `admin` | Founder FD-02                                  | Decision in `00-decisions` or ADR | FD-02               |
| ADM-02 | P0→P1         | OPEN                    | Role grant/revoke UI + audit        | no CRUD UI                     | Only after FD-02/FD-03                         | Grant/revoke audited              | MR-S02              |
| ADM-03 | P0            | CODE_COMPLETE           | KYC review integrity                | #293 guarded transitions       | Apply `0056`; staging drill; orphan report ops | No tier privilege without record  | MR-S11              |
| ADM-04 | P1            | CODE_COMPLETE (empty)   | Moderation queue proven             | #290 empty/scope notes         | Staging merge journey                          | Queue visible; merge idempotent   | Access session      |
| ADM-05 | P1            | OPEN                    | Authenticity report queue           | product RB-PS-013              | Report → flag; policy doc                      | Flag created; policy documented   | Customer report API |
| ADM-06 | P1            | CODE_COMPLETE (honesty) | Analytics tiles vs truth            | #290                           | Traffic + wiring                               | Tiles = aggregates; no fake GMV   | MR-O01              |
| ADM-07 | P1            | CODE_COMPLETE           | Manual dispatch UX fidelity         | #290 D16                       | Deploy + Access smoke                          | No Yango-API framing              | Deploy              |
| ADM-08 | P1            | CODE_COMPLETE (honesty) | Escrow / payout ops visibility      | #290                           | After staging ledger/release                   | Balances match ledger             | MR-B01/B01b, MR-W01 |
| ADM-09 | P2            | OPEN                    | Commission / config verification UI | master BL-11                   | Read-only display                              | Matches locked rates              | DB read             |
| ADM-10 | NOT_AUDITABLE | OPEN                    | Access-approved deep audit          | Cloudflare Access              | Auditor session pack                           | Redacted screenshots              | Access approval     |
| ADM-11 | P1            | OPEN                    | Localhost API fallback residual     | integration §4.2               | Fail-closed admin API base                     | No prod localhost                 | Admin eng           |

---

## API / backend backlog

| ID     | Pri | Status        | Title                                                                   | Acceptance                                     | Depends on            |
| ------ | --- | ------------- | ----------------------------------------------------------------------- | ---------------------------------------------- | --------------------- |
| API-01 | P0  | CODE_COMPLETE | Prepaid collection → `CHARGE_RECEIVED` (#274)                           | STAGING_VERIFIED sandbox MoMo+card             | Lenco sandbox         |
| API-02 | P0  | CODE_COMPLETE | Release accounting capture-before-release (#288/#294)                   | Escrow→0; idempotent double-tick; recon fields | Staging + n8n release |
| API-03 | P0  | CODE_COMPLETE | KYC eligibility + admin lifecycle (#293)                                | Orphans cannot unlock privileges post-`0056`   | MR-S11                |
| API-04 | P0  | OPEN          | Refund/cancel matrix sandbox proof                                      | Cancel→refund+notify                           | Events/money staging  |
| API-05 | P0  | OPEN          | Organiser Tier-1 GMV cap                                                | Over-cap rejected + audit                      | Events config         |
| API-06 | P1  | OPEN          | Listing modes unique/MTO                                                | Five flows OpenAPI+tests                       | Product scope         |
| API-07 | P1  | OPEN          | Search `degraded=false` for common queries                              | Probe evidence                                 | Embeddings/FTS        |
| API-08 | P1  | OPEN          | Payment status contract surfaces ledger/confirmation fields for CUST-08 | Customer cannot infer false paid               | API-01                |
| API-09 | P0  | NOT_AUDITABLE | Record API image digest / git SHA                                       | Release ledger entry                           | Host/GHCR access      |

---

## Database / migrations / RLS backlog

| ID    | Pri   | Status               | Title                                                         | Acceptance                                   | Depends on                                   |
| ----- | ----- | -------------------- | ------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------- |
| DB-01 | P0    | OPEN                 | Reconcile migration drift (`0051`, `0053`–`0055`, `0052` key) | `schema_migrations` matches agreed target    | Backup MR-O04                                |
| DB-02 | P0    | CODE_COMPLETE (file) | Apply `0056_kyc_integrity.sql` staging→prod                   | Trigger/view/columns live; pending→submitted | DB-01 order; API deploy order per KYC report |
| DB-03 | P0→P1 | OPEN                 | Apply/enable `0051` role hook **or** FD-03 exception          | JWT/roles consistent                         | FD-03                                        |
| DB-04 | P0    | OPEN                 | FORCE RLS decision on ticket tier tables                      | force true **or** signed exception           | FD-07                                        |
| DB-05 | P1    | OPEN                 | Apply 0053/0054/0055 when vernacular/services GTM             | Objects present                              | Product timing                               |
| DB-06 | P0    | OPEN                 | Orphaned KYC controlled repair (manual only)                  | Orphan report cleared or ticketed            | DB-02; FD-12                                 |
| DB-07 | P0*   | OPEN                 | `product_class` / condition expand                            | Only if FD-06 claims them                    | FD-06                                        |

---

## Payments backlog

| ID     | Pri | Status        | Title                                                      | Acceptance                           | Depends on      |
| ------ | --- | ------------- | ---------------------------------------------------------- | ------------------------------------ | --------------- |
| PAY-01 | P0  | CODE_COMPLETE | Collection settlement (#274)                               | STAGING_VERIFIED ledger legs         | Sandbox         |
| PAY-02 | P0  | CODE_COMPLETE | Release accounting (#294)                                  | charge→capture→release; recon totals | PAY-01; n8n     |
| PAY-03 | P0  | OPEN          | Webhook idempotency staging proof                          | Single ledger txn on replay          | Sandbox         |
| PAY-04 | P0  | OPEN          | Daily recon mismatch alerting                              | Actionable alert                     | n8n recon       |
| PAY-05 | P0  | BLOCKED       | Zamtel collections posture                                 | UI matches FD-01                     | FD-01           |
| PAY-06 | P0  | OPEN          | No false payment-success (G4) E2E                          | Pending≠success; COD isolated        | CUST-08; PAY-01 |
| PAY-07 | P1  | OPEN          | Soft commission_snapshot immutability hardening (optional) | Trigger or accepted residual         | Payments design |

---

## n8n / automation backlog

| ID     | Pri | Status  | Title                                                  | Acceptance                                                | Depends on             |
| ------ | --- | ------- | ------------------------------------------------------ | --------------------------------------------------------- | ---------------------- |
| N8N-01 | P0  | OPEN    | Activate escrow `release-job` (+ order-jobs as needed) | Active + successful authenticated tick; no double-release | Internal token; PAY-02 |
| N8N-02 | P0  | OPEN    | Activate `tickets-issue` + `event-release`             | Exactly-once ticket issue                                 | Events sandbox         |
| N8N-03 | P1  | OPEN    | Backup workflow **or** host cron proof                 | Dated artifact                                            | OCI access             |
| N8N-04 | P1  | PARTIAL | Keep payment reconciliation; prove failure alert       | Mismatch alerted                                          | Ops                    |
| N8N-05 | P1  | OPEN    | Lifecycle (onboarding/abandoned-cart/review)           | Each fires once in test                                   | Flags                  |
| N8N-06 | P2  | OPEN    | Embeddings / reservation sweeper / digests             | Tick logged                                               | Priority               |

---

## Operational / observability / CI backlog

| ID     | Pri | Status | Title                                                    | Acceptance                 | Depends on     |
| ------ | --- | ------ | -------------------------------------------------------- | -------------------------- | -------------- |
| OPS-01 | P1  | OPEN   | Sentry projects + DSNs (customer/vendor/admin/API)       | Test event per app         | Founder/Sentry |
| OPS-02 | P1  | OPEN   | Uptime monitors on health endpoints                      | Monitors green             | Uptime tool    |
| OPS-03 | P1  | OPEN   | Backup + restore drill                                   | RPO/RTO documented         | N8N-03         |
| OPS-04 | P0  | OPEN   | Staging UAT pack (checkout, KYC, release, tickets)       | Written UAT notes          | Staging env    |
| OPS-05 | P1  | OPEN   | Rollback drill (Vercel + API tag)                        | Time recorded              | Deploy access  |
| OPS-06 | P1  | OPEN   | Make `secret-scan` blocking; confirm branch protection   | Required checks; no bypass | Founder/GitHub |
| OPS-07 | P1  | OPEN   | Deploy panel SHAs (#289–#291) + re-probe foundation URLs | PRODUCTION_VERIFIED probes | Vercel         |
| OPS-08 | P0  | OPEN   | Legal counsel artifact                                   | Written sign-off           | FD-08          |
| OPS-09 | P1  | OPEN   | Pin API image digest in release ledger                   | Digest ≠ unknown           | API-09         |

---

## Cross-panel dependency map

| Dependency              | Owner    | Waiting consumers                                     |
| ----------------------- | -------- | ----------------------------------------------------- |
| PAY-01/02 staging proof | Payments | CUST-08/09, VEND-08, ADM-08, G3/G4                    |
| N8N-01/02               | Ops      | CUST-06, VEND-05/07, ADM-08, events money             |
| DB-01/02 (`0056`)       | DB/Ops   | VEND-01, ADM-03, G12                                  |
| FD-01/02/04/06/07/08    | Founder  | Zamtel, RBAC, demo, catalogue scope, FORCE RLS, legal |
| OPS-01/07               | Platform | All panels error visibility + live honesty            |

---

## Suggested sequencing

1. **Founder decisions** FD-01, FD-02, FD-04, FD-08 (unblock honest scope)
2. **Staging money** PAY-01 → PAY-02 → PAY-03/06 (G3/G4)
3. **n8n** N8N-01 → N8N-02
4. **DB** backup → DB-01 → DB-02 (`0056`) → DB-06 orphans
5. **Deploy panels** OPS-07 + CUST-01 env
6. **Observability/backup** OPS-01/02/03/05
7. **Scope-gated catalogue/events UX** only after FD-06 / money gates

---

_Implementation-ready: one pebble ≈ one row; cite MR-ID / backlog ID in PR titles. Do not declare PRODUCTION_VERIFIED from CODE_COMPLETE alone._

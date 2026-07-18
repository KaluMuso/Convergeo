# Panel & Platform Backlogs — Customer · Vendor · Admin · API · Database · Payments · Workflows · Operations

**Date:** 2026-07-18 (post-implementation refresh)  
**Canonical IDs:** `master-reconciliation-register.md` (MR-*)  
**Master tip:** `d5c2134`  
**Rule:** Every item cites evidence + acceptance criteria. Status separates **code** from **staging** and **production**. Do not list merged work as missing.

**Priority:** P0 = release blocker · P1 = launch quality · P2 = hygiene / post-gate

**Status values:** `OPEN` · `DONE_CODE` · `DONE_STAGING` · `DONE_PROD` · `BLOCKED` · `DEFERRED` · `OUT`

---

## Customer panel backlog

**Surface:** `apps/customer` · `www.vergeo5.com`  
**Merged PR:** [#289](https://github.com/KaluMuso/Convergeo/pull/289) · report: `../implementation/customer-change-report.md`

| ID      | Pri | Status                      | Title                            | Evidence                                                   | Remaining work                                                                                            | Acceptance                                       | Depends on               |
| ------- | --- | --------------------------- | -------------------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------ |
| CUST-01 | P1  | OPEN                        | Restore seller acquisition CTA   | foundation R1; CTA unavailable; fail-closed (no localhost) | Set `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer`; redeploy; HTML probe | CTA href vendor prod; not “unavailable”          | Founder / Vercel env     |
| CUST-02 | P1  | OPEN                        | Demo catalogue disclosure / gate | Public `total=134`; all `demo/` images; sfq E6 vs D25      | Merch decision: label banner **or** exclude demo from public search                                       | Cannot be mistaken for real national marketplace | Founder/merch (MR-D01)   |
| CUST-03 | P1  | DONE_CODE                   | Wire categories browse entry     | product RB-PS-012; #289                                    | Deploy customer tip; re-probe `/en/categories`                                                            | Staging/prod 200 + navigable roots               | Deploy                   |
| CUST-04 | P1  | DONE_CODE                   | Wire comparison entry            | product RB-PS-012; #289                                    | Deploy; exercise ≥2 listings                                                                              | Compare usable; empty state honest               | Deploy + ops seed        |
| CUST-05 | P1  | OPEN                        | PWA service worker delivery      | blueprint BL-P1-01: SW 404 live                            | Deploy tip with serwist; probe SW URL                                                                     | SW 200; installability                           | Customer deploy          |
| CUST-06 | P1  | OPEN                        | Events Phase-1 discovery UX      | events BL-009                                              | Lenses/badges when events>0 or honest empty-state                                                         | Matches Phase-1; empty if 0                      | Supply + MR-W02 for paid |
| CUST-07 | P1  | DONE_CODE                   | Launch copy vs locked decisions  | blueprint BL-P1-06; #289                                   | Deploy; residual copy audit                                                                               | No Yango/own-fleet/Django/Meilisearch claims     | Deploy                   |
| CUST-08 | P0  | DONE_CODE (UI) / OPEN (E2E) | Checkout false-success hardening | foundation R2; #289 UI; MR-B01                             | Sandbox E2E: success only after payment+ledger confirmed                                                  | No “paid” when pending/failed/ledger missing     | API MR-B01 staging       |
| CUST-09 | P1  | OPEN                        | Escrow trust UX copy             | CLAUDE.md; 0 orders                                        | Wire “You paid → Held → Released” to real statuses                                                        | Never invent held/released                       | MR-B01, MR-W01           |
| CUST-10 | P2  | DONE_CODE                   | Calendar route or remove claim   | events F027; #289 redirect                                 | Deploy; confirm no dead nav                                                                               | Calendar → events                                | Deploy                   |
| CUST-11 | P2  | OPEN                        | Lighthouse budgets               | roadmap BL-21                                              | Mobile Fast-3G/360px on critical routes                                                                   | Perf≥90 SEO≥95 A11y≥95 or waiver                 | Egress                   |
| CUST-12 | P2  | OPEN                        | Scope-fence wishlist/reorder     | foundation R6                                              | Hide or mark OUT                                                                                          | No heart implying persistence without API        | Product decision         |

### Customer verification

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -o /tmp/sell.html -w "%{http_code}\n" https://www.vergeo5.com/en/sell
python3 -c 'from pathlib import Path;h=Path("/tmp/sell.html").read_text();print("localhost", "localhost:3001" in h);print("unavailable", "unavailable" in h.lower())'
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/categories
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/compare
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/sw.js
pnpm --filter customer lint && pnpm --filter customer typecheck && pnpm --filter customer test
```

---

## Vendor panel backlog

**Surface:** `apps/vendor` · `vendor.vergeo5.com`  
**Merged PR:** [#291](https://github.com/KaluMuso/Convergeo/pull/291) · API half [#293](https://github.com/KaluMuso/Convergeo/pull/293)  
**Reports:** `../implementation/vendor-change-report.md` · `../implementation/kyc-integrity-report.md`

| ID      | Pri | Status                         | Title                        | Evidence                                           | Remaining work                                                               | Acceptance                                                          | Depends on            |
| ------- | --- | ------------------------------ | ---------------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------- |
| VEND-01 | P0  | DONE_CODE / OPEN (rollout)     | KYC tier integrity           | blueprint BL-P0-05; #291 UI; #293 freeze+`0056`    | Apply `0056` staging→prod; orphan report; controlled repair; re-probe badges | No privilege from bare `kyc_tier`; badge only on auditable approved | DB/ops MR-D02         |
| VEND-02 | P1  | OPEN                           | Sandbox KYC end-to-end       | roadmap BL-13; kyc_records=0                       | NRC/business-reg → review → approve with test vendor                         | One sandbox vendor completes KYC                                    | `0056` + admin review |
| VEND-03 | P1  | OPEN (partial code)            | Listing create UX audit      | product F038 NOT_AUDITABLE; #291 catalogue honesty | Test JWT: attach / new_canonical / quick_list; document unique/MTO gaps      | Timing + field evidence                                             | Vendor test JWT       |
| VEND-04 | P1  | DEFERRED                       | Complete listing modes UI    | product RB-PS-011                                  | After API adds unique/MTO                                                    | Five flows reachable                                                | API MR-B06            |
| VEND-05 | P1  | OPEN                           | Offline door scanner cache   | events BL-006                                      | Cache horizon secrets; queue; scan-sync                                      | Offline then sync; first-scan-wins                                  | MR-W02                |
| VEND-06 | P1  | DEFERRED                       | Evidence photos (used goods) | product RB-PS-007                                  | Before Class D only                                                          | Non-new rejects missing evidence                                    | MR-S06                |
| VEND-07 | P1  | OPEN                           | Event organiser publish path | events F047 empty                                  | Free RSVP + small paid workshop under beta                                   | ≥1 published event in beta                                          | MR-W02 for paid       |
| VEND-08 | P1  | DONE_CODE (UI) / OPEN (ledger) | Fee / stats honesty          | events F018/F041; #291                             | Deploy; prove against real ledger aggregates                                 | No fabricated GMV                                                   | MR-B01 staging        |
| VEND-09 | P2  | DEFERRED                       | Co-organiser / door roles UX | events BL-008                                      | After MR-S09                                                                 | Door scans only                                                     | MR-S09                |
| VEND-10 | P2  | OUT                            | Vendor staff RBAC            | foundation R6; #291                                | Explicitly OUT of v1                                                         | Documented OUT                                                      | —                     |

### Vendor verification

```bash
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://vendor.vergeo5.com/en/health
pnpm --filter vendor lint && pnpm --filter vendor typecheck
curl -sS -m 15 https://api.vergeo5.com/openapi.json | python3 -c 'import sys,json;d=json.load(sys.stdin);print("paths", len(d.get("paths",{})))'
```

---

## Admin panel backlog

**Surface:** `apps/admin` · `admin.vergeo5.com` (Cloudflare Access)  
**Merged PR:** [#290](https://github.com/KaluMuso/Convergeo/pull/290) · KYC APIs [#293](https://github.com/KaluMuso/Convergeo/pull/293)  
**Report:** `../implementation/admin-change-report.md`

| ID     | Pri           | Status                                | Title                               | Evidence                            | Remaining work                                                           | Acceptance                                                   | Depends on          |
| ------ | ------------- | ------------------------------------- | ----------------------------------- | ----------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------ | ------------------- |
| ADM-01 | P0            | OPEN                                  | Resolve admin RBAC model            | roadmap F033 vs single `admin`      | Founder decision: supersede **or** additive roles+RLS+UI                 | Decision in `00-decisions`/ADR; if adopt, authz-matrix green | Founder (MR-A02)    |
| ADM-02 | P0→P1         | OPEN                                  | Role grant/revoke UI + audit        | foundation R6                       | Users/roles management with audit_log                                    | Grant/revoke via UI; JWT matches `user_roles`                | MR-S02 / ADM-01     |
| ADM-03 | P0            | DONE_CODE / OPEN (rollout)            | KYC review integrity                | MR-D02; #293 guarded lifecycle      | Deploy API+admin; apply `0056`; exercise queue; controlled orphan repair | No tier>0 privilege without approved record                  | DB/ops              |
| ADM-04 | P1            | OPEN                                  | Moderation queue proven             | product RB-PS-014; #290 empty-state | Staging: new_canonical → pending → merge/reject                          | Queue visible; merge idempotent                              | Access session      |
| ADM-05 | P1            | OPEN                                  | Authenticity report queue           | product RB-PS-013                   | Customer report → admin flag; cancel-rate policy doc                     | Report creates flag; policy documented                       | Customer report API |
| ADM-06 | P1            | DONE_CODE                             | Analytics tiles vs truth            | foundation R4; #290                 | Deploy; after traffic tiles = SQL                                        | No fake GMV; CSV valid                                       | Deploy + traffic    |
| ADM-07 | P1            | DONE_CODE                             | Manual dispatch UX fidelity         | D16; #290                           | Deploy; spot-check                                                       | No Yango buttons; matches D16                                | Deploy              |
| ADM-08 | P1            | DONE_CODE (honesty) / OPEN (balances) | Escrow / payout ops visibility      | 0 ledger; #290 honesty              | Read-only balances once MR-B01/W01 staging                               | Balances match ledger                                        | MR-B01, MR-W01      |
| ADM-09 | P2            | OPEN                                  | Commission / config verification UI | master BL-11                        | Safe display of category bps + COD cap                                   | Values match locked decisions                                | DB read             |
| ADM-10 | NOT_AUDITABLE | OPEN                                  | Access-approved deep audit          | Cloudflare Access                   | Redacted empty-state screenshots                                         | Audit pack attached                                          | Access approval     |

### Admin verification

```bash
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
# Expect Access challenge (302/403) without token
pnpm --filter admin lint && pnpm --filter admin typecheck
```

---

## API / backend backlog

| ID     | Pri | Status                     | Title                                            | MR             | Remaining                                           | Acceptance                               |
| ------ | --- | -------------------------- | ------------------------------------------------ | -------------- | --------------------------------------------------- | ---------------------------------------- |
| API-01 | P0  | DONE_CODE / OPEN (proof)   | Prepaid collection → `CHARGE_RECEIVED`           | MR-B01 / #274  | Staging MoMo+card + SQL aggregates + webhook replay | Balanced ledger; idempotent; fail-closed |
| API-02 | P0  | DONE_CODE / OPEN (proof)   | Release commission capture before vendor release | MR-B01b / #294 | Staging release tick + recon with MR-W01            | Escrow nets 0; idempotent                |
| API-03 | P0  | DONE_CODE / OPEN (rollout) | KYC eligibility freeze + admin lifecycle         | MR-D02 / #293  | Deploy API image; apply `0056`; orphan report       | Bare tier unlocks nothing                |
| API-04 | P0  | OPEN                       | Organiser Tier-1 GMV cap                         | MR-B04         | Implement/verify config + reject path               | Over-cap rejected + audit                |
| API-05 | P0  | OPEN                       | Refund/cancel matrix sandbox                     | MR-B03         | Cancel → full refund + notify                       | Policy = code                            |
| API-06 | P1  | OPEN                       | Search `degraded=false`                          | MR-B07         | Diagnose embeddings/FTS                             | Common queries healthy                   |
| API-07 | P1  | OPEN                       | Stock reservation E2E                            | MR-B05         | reserve→expire→pay                                  | Atomic unpaid release                    |
| API-08 | P1  | DEFERRED                   | Listing modes unique/MTO                         | MR-B06         | Additive API + validation                           | Five modes                               |
| API-09 | —   | OPEN                       | Record API image digest                          | MR-B10         | Host/`API_IMAGE_TAG` / GHCR                         | Digest in release ledger                 |

---

## Database backlog

| ID    | Pri   | Status   | Title                              | MR            | Remaining                                                      | Acceptance                             |
| ----- | ----- | -------- | ---------------------------------- | ------------- | -------------------------------------------------------------- | -------------------------------------- |
| DB-01 | P0    | OPEN     | Migration reconcile to tip         | MR-S01        | Backup → apply `0051`, `0053`–`0056` in order; fix `0052` skew | `schema_migrations` matches tip        |
| DB-02 | P0    | OPEN     | Apply KYC integrity migration      | MR-D02 / #293 | Staging apply `0056` → prod; no auto-upgrade orphans           | Migration applied; report-only orphans |
| DB-03 | P0→P1 | OPEN     | Role hook enablement               | MR-S02        | Apply `0051` + Auth hook **or** signed exception               | JWT roles consistent                   |
| DB-04 | P0    | OPEN     | FORCE RLS on ticket tier tables    | MR-R01        | Investigate; enable FORCE or exception                         | Decision + SQL evidence                |
| DB-05 | P1    | OPEN     | Service reviews / bookable         | MR-S04        | Apply `0054`/`0055` with services GTM                          | Objects present                        |
| DB-06 | P1    | DEFERRED | `product_class` / condition expand | MR-S05/S06    | Only if Class D/E claimed                                      | Additive + tests                       |
| DB-07 | P1    | OPEN     | Controlled KYC orphan repair       | MR-D02        | Reviewed import/repair plan — **no ad-hoc UPDATE**             | Zero privilege orphans                 |

---

## Payments backlog

| ID     | Pri | Status                   | Title                             | MR                | Remaining                                  | Acceptance                           |
| ------ | --- | ------------------------ | --------------------------------- | ----------------- | ------------------------------------------ | ------------------------------------ |
| PAY-01 | P0  | DONE_CODE / OPEN (proof) | Sandbox MoMo prepaid → ledger     | MR-B01 / #274     | Execute sandbox; attach redacted IDs + SQL | `CHARGE_RECEIVED` + hold balanced    |
| PAY-02 | P0  | DONE_CODE / OPEN (proof) | Sandbox card prepaid → ledger     | MR-B01 / #274     | Same                                       | Same                                 |
| PAY-03 | P0  | DONE_CODE / OPEN (proof) | Release accounting sandbox        | MR-B01b / #294    | Release after deliver/event phase          | Capture then release; escrow 0       |
| PAY-04 | P0  | OPEN                     | False-success ban E2E             | MR-O03 / CUST-08  | Abandon/delay webhook cases                | UI never claims paid early           |
| PAY-05 | P0  | OPEN                     | Zamtel collections decision       | MR-L04 / F9a      | Founder F9a; hide method until ready       | UI matches `zamtel_collections` flag |
| PAY-06 | P1  | OPEN                     | Recon mismatch alerting           | MR-W05            | Force mismatch in sandbox                  | Alert actionable                     |
| PAY-07 | P0  | OPEN                     | Keep prepaid kill-switch until GO | foundation / #266 | Do not enable live prepaid                 | Flag intentional                     |

---

## Workflow backlog (n8n)

| ID    | Pri | Status  | Title                                      | MR         | Remaining                                              | Acceptance                                   |
| ----- | --- | ------- | ------------------------------------------ | ---------- | ------------------------------------------------------ | -------------------------------------------- |
| WF-01 | P0  | OPEN    | Activate escrow `release-job`              | MR-W01     | Import/activate; `X-Internal-Token`; dry-run → sandbox | Active; success execution; no double-release |
| WF-02 | P0  | OPEN    | Activate `tickets-issue` (+ event-release) | MR-W02     | Activate against internal ticks                        | Exactly-once ticket issue                    |
| WF-03 | P1  | OPEN    | Backup schedule workflow or host proof     | MR-W04     | n8n **or** OCI cron evidence                           | Dated artifact within RPO                    |
| WF-04 | P1  | OPEN    | Lifecycle automations                      | MR-W03     | Onboarding / abandoned-cart / review-request           | Each fires once in test                      |
| WF-05 | P2  | OPEN    | Embeddings / reservation sweeper / digests | MR-W06     | Activate as needed                                     | Tick logged                                  |
| WF-06 | P1  | PARTIAL | Keep notification dispatch + payment recon | foundation | Prove failure alerting                                 | Already live (2 workflows)                   |

---

## Operations backlog

| ID     | Pri | Status | Title                           | MR             | Remaining                                           | Acceptance                    |
| ------ | --- | ------ | ------------------------------- | -------------- | --------------------------------------------------- | ----------------------------- |
| OPS-01 | P1  | OPEN   | Sentry projects + DSNs          | MR-O01         | Create customer/vendor/admin/API projects; wire env | Test error visible per app    |
| OPS-02 | P1  | OPEN   | Uptime monitors                 | MR-O02         | `/en/health`, `/healthz`                            | Monitors green                |
| OPS-03 | P1  | OPEN   | Backup + restore drill          | MR-O04         | Scratch restore with evidence                       | RPO/RTO documented            |
| OPS-04 | P1  | OPEN   | Rollback drill                  | G9             | Redeploy prior Vercel + API tag                     | Time recorded                 |
| OPS-05 | P1  | OPEN   | CI secret-scan blocking         | MR-R05         | Remove `continue-on-error`; branch protection       | Merges blocked on hit         |
| OPS-06 | P1  | OPEN   | Deploy panels to tip            | MR-C02/C04/A04 | Vercel customer/vendor/admin → `d5c2134`+           | Live SHA matches intended     |
| OPS-07 | P1  | OPEN   | API deploy with digest recorded | MR-B10         | Deploy image including #274/#293/#294               | Digest in release ledger      |
| OPS-08 | P0  | OPEN   | Legal counsel artifact          | MR-L01 / F4    | Written DPA/NPS escrow sign-off                     | Artifact path recorded        |
| OPS-09 | P2  | OPEN   | Staging pipeline beyond stub    | MR-O05         | Real staging UAT                                    | Journeys pass                 |
| OPS-10 | P2  | OPEN   | Doc SoT banners                 | MR-L02         | Banner on Master Plan / Blueprint / Roadmap         | Engineers cite `00-decisions` |

---

## Cross-panel dependency matrix

| Dependency                      | Owner          | Consumers                      |
| ------------------------------- | -------------- | ------------------------------ |
| MR-B01 / PAY-01–02 (#274 proof) | Payments / API | CUST-08/09, VEND-08, ADM-08    |
| MR-B01b / PAY-03 (#294 proof)   | Payments / API | ADM-08, escrow GO              |
| MR-W01 / WF-01                  | Ops            | CUST-09, ADM-08, real-money GO |
| MR-W02 / WF-02                  | Ops            | CUST-06, VEND-05/07            |
| MR-S01 / DB-01–02               | DB/Ops         | ADM-02/03, VEND-01 rollout     |
| MR-O01 / OPS-01                 | Platform       | All panels                     |
| MR-L01 / OPS-08                 | Founder        | Real-money launch              |
| CUST-01 env                     | Founder        | Seller acquisition             |

---

## Suggested sequencing

See `implementation-wave-plan.md` for exclusive-ownership waves.

**Customer remaining:** CUST-01 → deploy (#289) → CUST-05/02 → CUST-08 E2E → CUST-06  
**Vendor remaining:** DB-02/`0056` → VEND-01 prod → VEND-02 → VEND-03 → VEND-07/05  
**Admin remaining:** ADM-01 decision → ADM-03 rollout → ADM-02 → ADM-04 → ADM-08 balances  
**Platform:** Wave A money proof → Wave B KYC migrate → Wave C deploy → Wave D ops → Wave E founder gates

---

_Integration review (#292): panel merges PASS compile; FAIL go-live until money/ops/legal gates clear._

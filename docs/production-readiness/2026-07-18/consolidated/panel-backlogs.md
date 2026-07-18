# Panel Backlogs — Customer · Vendor · Admin

**Date:** 2026-07-18  
**Canonical IDs:** `master-reconciliation-register.md` (MR-*)  
**Rule:** Every item cites evidence + acceptance criteria. Implementation stays on exclusive panel branches (see `24-hour-workboard.md`). No production DB edits without reviewed migration / controlled import.

**Priority:** P0 = release blocker · P1 = launch quality · P2 = hygiene / post-gate

---

## Customer panel backlog

**Surface:** `apps/customer` · `www.vergeo5.com` · shared packages as needed for customer-only UX  
**Branch suggestion:** `cursor/panel-customer-8f02`

| ID      | Pri | Title                            | Evidence                                                                     | Work                                                                                                                                        | Acceptance criteria                                                          | Depends on                      |
| ------- | --- | -------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------- |
| CUST-01 | P1  | Restore seller acquisition CTA   | foundation R1; `/en/sell` “temporarily unavailable”; no localhost leak       | Confirm `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` on `convergeo-customer`; redeploy; verify HTML                              | CTA href is vendor app; **no** `localhost:3001`; copy not “unavailable”      | Vercel env access (Founder)     |
| CUST-02 | P1  | Demo catalogue disclosure / gate | Public catalog `total=134`; 134 `demo/` images; D25 intent conflict (sfq E6) | Product decision with merch: label demo banner **or** exclude demo from public search while `public_launch=false`; do not seed fake vendors | Public UX cannot be mistaken for real national marketplace; SEO not polluted | Merch decision (MR-D01)         |
| CUST-03 | P1  | Wire categories browse entry     | product RB-PS-012: `/en/categories` 404                                      | Add locale route + taxonomy browse using live categories API                                                                                | `/en/categories` 200; navigable Phase-1 roots                                | None                            |
| CUST-04 | P1  | Wire comparison entry from PDP   | product RB-PS-012: `/en/compare` 404; comparison API PARTIAL                 | Product-page entry to multi-vendor compare; handle ≥2 listings                                                                              | Compare usable for multi-vendor SKU; empty state honest                      | Multi-listing seed (ops)        |
| CUST-05 | P1  | Fix PWA service worker delivery  | blueprint BL-P1-01: manifest 200, SW 404                                     | Fix serwist SW route on customer production                                                                                                 | SW URL 200; installability check passes                                      | Customer deploy                 |
| CUST-06 | P1  | Events Phase-1 discovery UX      | events BL-009: missing Where lens; Tonight+Weekend home; selling-fast        | Implement agreed Phase-1 lenses/badges only when events>0 or behind empty-state                                                             | Browse matches Phase-1 slice; empty state if 0 events                        | Events supply + MR-W02 for paid |
| CUST-07 | P1  | Launch copy vs locked decisions  | blueprint BL-P1-06                                                           | Audit `/en` marketing copy for Yango/own-fleet/direct-telco/Django/Meilisearch claims                                                       | No superseded stack/logistics claims                                         | Copy review                     |
| CUST-08 | P0* | Checkout false-success hardening | foundation R2; MR-B01/O03                                                    | Customer UI must show success **only** after payment+ledger state confirmed by API; failure/pending distinct                                | No “paid” screen when payment pending/failed or ledger missing; E2E sandbox  | API MR-B01                      |
| CUST-09 | P1  | Escrow trust UX copy             | CLAUDE.md escrow UX; 0 orders                                                | Ensure “You paid → Held by Vergeo5 → Released” states wired to real statuses                                                                | States never invent held/released without API status                         | MR-B01, MR-W01                  |
| CUST-10 | P2  | Calendar route or remove claim   | events F027 `/en/calendar` 404                                               | Add route **or** remove nav claim                                                                                                           | No dead nav                                                                  | None                            |
| CUST-11 | P2  | Lighthouse budgets               | roadmap BL-21; perf budgets                                                  | Run mobile Fast-3G/360px Lighthouse on critical routes                                                                                      | Perf≥90 SEO≥95 A11y≥95 or waiver filed                                       | Egress                          |
| CUST-12 | P2  | Scope-fence wishlist/reorder     | foundation R6                                                                | Do not ship half-affordance; hide or mark OUT                                                                                               | No heart that implies persistence without API                                | Product decision                |

\*CUST-08 is P0 for any prepaid go-live; implement with payments panel coordination.

### Customer verification commands

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -o /tmp/sell.html -w "%{http_code}\n" https://www.vergeo5.com/en/sell
python3 -c 'from pathlib import Path;h=Path("/tmp/sell.html").read_text();print("localhost", "localhost:3001" in h);print("unavailable", "unavailable" in h.lower())'
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/categories
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/compare
# SW probe (paths per app):
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/sw.js
pnpm --filter customer lint && pnpm --filter customer typecheck && pnpm --filter customer test
```

---

## Vendor panel backlog

**Surface:** `apps/vendor` · `vendor.vergeo5.com` · vendor-facing API contracts  
**Branch suggestion:** `cursor/panel-vendor-8f02`

| ID      | Pri | Title                                    | Evidence                                          | Work                                                                                                                              | Acceptance criteria                                                             | Depends on                         |
| ------- | --- | ---------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------- |
| VEND-01 | P0  | KYC tier integrity (UI + API contract)   | blueprint BL-P0-05: `kyc_tier=2`, `kyc_records=0` | Stop displaying verified badges without trail; align vendor UI to KYC state machine; coordinate API freeze on tier without record | Badge only when auditable KYC exists; cannot skip Applied→Under Review→Approved | API/admin KYC transitions (MR-D02) |
| VEND-02 | P1  | Sandbox KYC end-to-end                   | roadmap BL-13; kyc_records=0                      | Exercise NRC/business-reg upload → review → approve with test vendor                                                              | One sandbox vendor completes KYC; owner-only edit enforced                      | Private storage; admin review      |
| VEND-03 | P1  | Listing create UX audit (attach <30s)    | product F038 NOT_AUDITABLE                        | With test JWT: attach, new_canonical, quick_list; document gaps for unique/MTO                                                    | Timing + field evidence captured; bugs filed with AC                            | Vendor test JWT                    |
| VEND-04 | P1  | Complete listing modes UI                | product RB-PS-011: API 3/5 modes                  | After API adds `unique` / `made_to_order`, ship vendor forms                                                                      | Five flows reachable; E2E for attach + quick_list null product                  | API MR-B06 / MR-S05                |
| VEND-05 | P1  | Offline door scanner cache               | events BL-006                                     | Cache horizon secrets; queue scans; sync via scan-sync                                                                            | Offline scan succeeds then syncs; first-scan-wins preserved                     | Ticket issuance MR-W02             |
| VEND-06 | P1  | Evidence photo requirements (used goods) | product RB-PS-007                                 | Before Class D: evidence slots; reject stock/demo for non-new                                                                     | Non-new create rejects missing evidence                                         | Schema MR-S06                      |
| VEND-07 | P1  | Event organiser publish path             | events F047 empty; BL-018                         | Organiser create free RSVP + small paid workshop under beta                                                                       | ≥1 published event in beta env                                                  | MR-W02 for paid                    |
| VEND-08 | P1  | Organiser fee / stats honesty            | events F018/F041 NOT_AUDITABLE                    | Fee breakdown + stats only show real aggregates                                                                                   | No fabricated GMV (blueprint Mulenga fiction)                                   | Ledger MR-B01                      |
| VEND-09 | P2  | Co-organiser / door roles UX             | events BL-008                                     | After MR-S09 schema: invite + least privilege                                                                                     | Door scans only; no financials                                                  | MR-S09, auth                       |
| VEND-10 | P2  | Vendor staff RBAC                        | foundation R6                                     | Explicitly OUT of v1 unless decided                                                                                               | Documented OUT or design ADR                                                    | Founder                            |

### Vendor verification commands

```bash
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://vendor.vergeo5.com/en/health
# Authenticated checks require test JWT — do not use production owner sessions for automation.
pnpm --filter vendor lint && pnpm --filter vendor typecheck
# API contract smoke (OpenAPI presence):
curl -sS -m 15 https://api.vergeo5.com/openapi.json | python3 -c 'import sys,json;d=json.load(sys.stdin);print("paths", len(d.get("paths",{})))'
```

---

## Admin panel backlog

**Surface:** `apps/admin` · `admin.vergeo5.com` (Cloudflare Access) · admin API  
**Branch suggestion:** `cursor/panel-admin-8f02`

| ID     | Pri           | Title                               | Evidence                                                  | Work                                                                                                            | Acceptance criteria                                                   | Depends on             |
| ------ | ------------- | ----------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ---------------------- |
| ADM-01 | P0            | Resolve admin RBAC model            | roadmap F033: superadmin/moderator vs live single `admin` | Founder decision: supersede doc **or** additive roles+RLS+UI                                                    | Decision in `00-decisions` or ADR; if adopt, authz-matrix tests green | Founder (MR-A02)       |
| ADM-02 | P0→P1         | Role grant/revoke UI + audit        | foundation R6; no CRUD UI; service-role-only writes       | Admin users/roles management with audit_log; least privilege                                                    | Grant/revoke via UI; JWT/edge gates match `user_roles`                | MR-S02 hook when ready |
| ADM-03 | P0            | KYC review integrity                | MR-D02; kyc_records=0 with tier=2                         | Admin KYC queue only transitions via guarded functions; repair seed badges via controlled plan (not raw UPDATE) | No tier>0 without record; audit trail complete                        | API state machine      |
| ADM-04 | P1            | Moderation queue proven             | product RB-PS-014                                         | Staging: new_canonical → pending_moderation → merge/reject                                                      | Queue visible; merge idempotent; no duplicate canonicals              | Admin Access session   |
| ADM-05 | P1            | Authenticity report queue           | product RB-PS-013                                         | Customer report → admin flag; cancel-rate policy doc                                                            | Report creates flag; ≥10% policy documented                           | Customer report API    |
| ADM-06 | P1            | Analytics tiles vs truth            | foundation R4; analytics=0                                | After events wired: tiles = SQL aggregates; empty-state honest                                                  | No fake GMV; CSV export valid                                         | Traffic + MR-O01       |
| ADM-07 | P1            | Manual dispatch UX fidelity         | D16 manual Lusaka dispatch                                | Ensure delivery admin labels match locked model (no Yango buttons)                                              | Dispatch UI matches D16                                               | None                   |
| ADM-08 | P1            | Escrow / payout ops visibility      | 0 ledger; release workflow missing                        | Read-only escrow status from ledger once MR-B01/W01 land; never invent balances                                 | Balances match ledger postings                                        | MR-B01, MR-W01         |
| ADM-09 | P2            | Commission / config verification UI | master BL-11 rates NOT_AUDITABLE this session             | Safe display of category bps + COD cap; no silent edits                                                         | Values match locked D4/D decisions                                    | DB read                |
| ADM-10 | NOT_AUDITABLE | Access-approved deep audit          | Cloudflare Access                                         | Document empty states with redacted screenshots                                                                 | Audit pack attached                                                   | Access approval        |

### Admin verification commands

```bash
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
# Expect Access challenge (302/403) without token — VERIFIED gate.
pnpm --filter admin lint && pnpm --filter admin typecheck
# After Access session: manual checklist in release-gates.md §Admin route integrity
```

---

## Cross-panel dependencies (do not own on panel branches)

These are owned by **integration/release** or **backend/ops** branches; panels consume contracts only:

| Dependency                       | Owner          | Panels waiting                |
| -------------------------------- | -------------- | ----------------------------- |
| MR-B01 prepaid→ledger            | Payments / API | CUST-08/09, VEND-08, ADM-08   |
| MR-W01/W02 n8n release + tickets | Ops            | CUST-06, VEND-05/07, ADM-08   |
| MR-S01 migration reconcile       | DB/Ops         | ADM-02 (hook), i18n           |
| MR-O01 Sentry                    | Platform       | All panels (error visibility) |
| MR-L01 legal sign-off            | Founder        | Real-money launch             |

---

## Suggested sequencing (per panel)

**Customer:** CUST-01 → CUST-07 → CUST-03/04 → CUST-05 → CUST-02 → CUST-08 (with payments) → CUST-06  
**Vendor:** VEND-01 → VEND-02 → VEND-03 → VEND-07 → VEND-05 → VEND-04/06 (schema-gated)  
**Admin:** ADM-01 decision → ADM-03 → ADM-02 → ADM-04 → ADM-06 → ADM-08

---

_Implementation-ready for Cursor coding sessions: one pebble ≈ one row; cite MR-ID in PR titles (`Mxx-Pxx` or `PR-READINESS: CUST-01`)._

# Executive Summary — blueprint-zambia-vergeo-super-app

**Document:** Blueprint for Zambia's Vergeo super-app (Parts 1–2 TurboScribe transcript)  
**Audit date:** 2026-07-18 · **Mode:** READ-ONLY  
**Directory:** `docs/production-readiness/2026-07-18/document-audits/blueprint-zambia-vergeo-super-app/`

---

## What this document is

A **derivative podcast-style narration** of internal roadmaps, architecture diagrams, and UI wireframes. It is **not** a production data extract and **not** the locked product SoT (`docs/plan/00-decisions.md`). Wireframe metrics (GMV, 840 vendors, 24 events, Mulenga Fashion payout) must be treated as **illustrative**.

---

## Status totals (45 atomic facts)

| Status        | Count  |
| ------------- | ------ |
| VERIFIED      | 6      |
| PARTIAL       | 16     |
| MISSING       | 6      |
| CONFLICT      | 10     |
| NOT_AUDITABLE | 7      |
| **Total**     | **45** |

### VERIFIED (high confidence live match)

- Next.js on Vercel + Cloudflare edge
- Three apps (customer / vendor / admin)
- Custom architecture (not Shopify/WooCommerce)
- Canonical `products` + `vendor_listings`
- Event ticket commission **5%** (`event_tickets` 500 bps)
- `public_launch=false` (invite gate still on)

### Major CONFLICT themes

- **Stack obsolete:** Django, Celery, Upstash Redis, Supabase Realtime notifications vs locked/live **FastAPI + n8n + WhatsApp outbox**
- **Payments:** Direct telco MoMo APIs vs locked **Lenco**; cards downplayed vs implemented card sessions
- **Logistics:** Yango API + own fleet vs locked **manual Lusaka dispatch**
- **Traction fiction:** 840 vendors / 12.4k products / K184k GMV / Mulenga payout vs **3 demo vendors, 134 demo listings, 0 money rows**

### Major MISSING / PARTIAL (launch-relevant)

- Escrow **48h config present** but **n8n auto-release missing**; payments/ledger **0**
- Ticketing APIs present; **0 events/tickets**; issue automation **missing**
- Services RFQ APIs present; **1 demo service**, **0 jobs**
- PWA manifest present; **service worker 404** at probed paths
- KYC tiers on vendors without `kyc_records` trail

---

## Release blocker verdict

**Yes — this document surfaces release blockers** when its trust/money/ticketing claims are treated as launch requirements:

1. **P0 — Unproven prepaid → escrow ledger → release/payout path** (zero money rows; release automation absent).
2. **P0 — Ticket issuance automation absent** while dynamic-QR is a headline claim.
3. **P0 — KYC tier/badge integrity** (`kyc_tier=2` with `kyc_records=0`).
4. **P0 — SoT conflict:** following this transcript’s Django/direct-MoMo/Yango stack would **violate locked decisions** and create security/compliance debt.

Non-blockers if locked decisions hold: City Guides, own logistics network, Tier3 API monetisation, Celery/Redis, 10-province ship-anywhere marketing.

**Demo catalogue + invite gate** mean the environment is **not** a real-money national marketplace yet; citing transcript GMV/vendor projections externally would be a **trust/compliance optics blocker**.

---

## Backlog priority counts

| Priority | Items |
| -------- | ----- |
| P0       | 5     |
| P1       | 8     |
| P2       | 5     |

---

## Assumptions (explicit)

1. Uploaded Part 1 + Part 2 = one logical document (matches 37-page concept PDF).
2. Wireframe numbers are not production master data.
3. Locked decisions outrank this transcript on CONFLICT.
4. Operator SQL aggregates ≠ end-user RLS view.
5. No secrets/PII were read or printed.

---

## NOT_AUDITABLE — access still needed

| Fact theme                           | Needed                                                                         |
| ------------------------------------ | ------------------------------------------------------------------------------ |
| Africa's Talking / OTP live delivery | Confirm SMS provider env **names** + sandbox OTP (no secret paste)             |
| Vendor mobile/desktop UX             | Read-only vendor test JWT                                                      |
| Admin GMV/payout UI empty-state      | Cloudflare Access–approved auditor session                                     |
| Comparison “N vendors” UX            | Public/auth product URL with ≥2 listings                                       |
| Prepaid MoMo/card → ledger proof     | Lenco sandbox end-to-end (mutates sandbox only; out of this read-only session) |
| API image git SHA                    | Host `API_IMAGE_TAG` / GHCR digest                                             |
| 78% mobile statistic                 | Primary research citation                                                      |

---

## Artifacts in this folder

1. `source-document.md`
2. `extracted-facts.json`
3. `reconciliation-matrix.md`
4. `missing-and-conflicting-items.md`
5. `safe-query-log.md`
6. `remediation-backlog.md`
7. `executive-summary.md` (this file)

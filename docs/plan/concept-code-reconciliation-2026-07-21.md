# Concept ↔ Code Reconciliation — 2026-07-21

**Scope:** Assess the three source-of-record concept documents in `docs/concept/` — `Convergeo_Strategic_Master_Plan.pdf`, `Convergeo_Strategy_Bible.pdf`, `Blueprint_for_Zambias_Vergeo_superapp.pdf` — against the current implementation on `master`, and separate **genuine Phase‑1 gaps** from **intentional deferrals** and **already-built strengths**.

**Method:** Vision read from the committed, file-verified distillations (`docs/plan/research/*`, page-counts/dates match the PDFs byte-for-byte; GitHub `master` tree confirmed identical). Implementation state mapped across `apps/*`, `services/api`, `supabase/migrations`, `packages/*`, then each concept differentiator grep-verified in code. This doc does **not** re-litigate the 28 locked decisions (`00-decisions.md`) or the documented deferrals (`product-strategy-gap-audit.md`, `events-strategy-remediation.md`).

---

## 0. Headline

**The code substantially fulfills the Phase‑1 concept.** All 16 mountains (M01–M16) are code-complete and merged; the concept's headline differentiators are not just present but tested. The concept PDFs describe a 5‑year Alibaba-shaped super-app; the team deliberately thin-sliced that into a Phase‑1 launch scope via the locked decisions, and the code matches that scope well.

**The real launch blocker is non-code** (per `docs/production-readiness/2026-07-20/go-no-go-report.md` → NO_GO): escrow legal review (F4, hard NO‑GO), deploy/verify, live Lenco credentials (F9b), and the other founder gates F2/F5/F6/F9a. No amount of feature work moves the launch date until those clear.

---

## 1. Concept differentiators — VERIFIED PRESENT (do not rebuild)

Every headline moat from the Bible/Blueprint/Master-Plan is implemented:

| Concept differentiator                                                                           | Status                          | Evidence                                                                                                              |
| ------------------------------------------------------------------------------------------------ | ------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Escrow trust UX "You paid → Held by Vergeo5 → Released" (the #1 moat vs WhatsApp sellers)        | **Built + tested**              | `home.hero.escrowStep1/2/3`, `home-trust-strip.tsx`, `phase1-locale-render.test.tsx` asserts step2 contains "Vergeo5" |
| Canonical Product + VendorListing + comparison ("7 vendors selling this", sort nearest/cheapest) | **Built**                       | `(shop)/compare/page.tsx`, canonical/listing split in schema (mig 0003), `vendor_listings.py`                         |
| Mobile-money-first (MTN/Airtel USSD push)                                                        | **Built** (rail-gated)          | `services/payments/lenco/*` collection operators mtn/airtel/zamtel; `checkout_payment.py`                             |
| Services RFQ + visible response-time badge ("3–5 reply in an hour")                              | **Built**                       | `services_listings.py` `ResponseTimeTier = fast\|same_day\|slow` from median seconds; `services/post-job`             |
| Events dynamic-QR ticketing (60s HMAC window, PIN backup, transfer, scanner)                     | **Built**                       | `ticket_verify/scan_sync/transfer/wallet.py`, `services/tickets/qr.py`, organiser scan suite                          |
| Progressive-trust KYC on-ramp (Tier1 NRC → Tier2 PACRA → Preferred)                              | **Built**                       | `services/kyc/state_machine.py`, vendor `onboarding/` doc-capture flow, `admin/kyc/[id]`                              |
| WhatsApp-native notifications w/ SMS→email fallback (outbox)                                     | **Built**                       | `services/notifications/*` dispatcher + dedupe + fallback + adapters, `notification_outbox`                           |
| Double-entry escrow ledger, refunds-as-payouts, gapless ZRA invoices                             | **Built**                       | `ledger/engine.py` (sole write path), `refunds/payout_port.py`, `invoicing/` VSDC seam                                |
| Hybrid Postgres search (FTS + pgvector + RRF) + Ask Vergeo RAG                                   | **Built** (ops-fragile, see §3) | `services/search/*` RRF builder, `ask/` retrieve+quota+spend                                                          |
| B2B-lite supplies (MOQ, tier pricing, business-gated) + directory                                | **Built**                       | `(shop)/supplies/page.tsx`, `(shop)/directory/page.tsx`, business-buyer schema (mig 0038)                             |

Money discipline (integer ngwee end-to-end, `Decimal` only at the Lenco boundary, branded `Ngwee` type, shared `formatK()`), RLS breadth (~230 policies, `FORCE ROW LEVEL SECURITY` on money/identity/orders), state machines with audit logs, and pervasive idempotency are all real. E2E covers the money failure paths (`checkout-false-success.spec.ts`, momo/cod/ticket specs).

---

## 2. Genuine gaps INSIDE committed Phase‑1 scope (actionable)

These are small and specific — **not structural.** Cursor prompts in `prompts/fixes/CR-*`.

### 2.1 i18n priority inversion — Bemba/Nyanja behind French AND Chinese → `CR-B`

`packages/i18n/messages/`: **en/fr/zh each = 17 namespaces (complete)**; **bem/nya = 13** — each missing `ai`, `legal`, `vendor`, `admin`. D27 ranks **Bemba/Nyanja ahead of French**, yet French (and a non-public `zh`) got full coverage first. Missing keys **fall back to English by design** (`deep-merge.ts`), so nothing breaks — but Bemba/Nyanja users see English for Ask Vergeo, legal, and the vendor/admin consoles. Customer-visible impact = `ai` + `legal`.

- **Oddity to confirm:** `zh` (Chinese) is fully translated but **not** in `PUBLIC_LOCALES` (`[en,bem,nya,fr]`). Deliberate (Chinese-importer vendor segment per the "Importer/Wholesaler" archetype) or accidental scaffolding? If not intended, the translation effort was misallocated ahead of the mandated African languages.
- **Recommendation:** localize `ai` (+ any customer gaps) into bem/nya now; keep `legal` English until a native speaker reviews it (legal copy in local languages is a liability decision). Do **not** machine-translate legal text.

### 2.2 Commission rates hardcoded on the public "Sell" page → `CR-A`

`apps/customer/.../sell/_components/commission-rates.ts` is a **static mirror** of the `commission_rates` seed (`0008_config.sql`) with `TODO(config): bind to live`. The values are currently correct (match D4: electronics 5, home 8, fashion/beauty 10, services 12, tickets 5, supplies 3, groceries 5, default 8, free 0). **Risk = drift:** the only live readers are **admin-authed** (`admin_config.py list/update_commission_rate`) and a server-side vendor read (`vendor_listings.py`); there is **no public config-read endpoint** for the SSR marketing page. If an admin changes a rate live, the public page silently shows stale rates — a trust/accuracy risk on the exact number that defines the business model.

- **Recommendation:** add a small **public** `GET /public/config/commission-rates` (cacheable, no secrets) and bind the sell page to it; delete the constant.

### 2.3 Search operational fragility → `CR-C`

Embeddings + RRF are built, but recent ops commits ("search degraded probe (CCP-05)") indicate the live path degrades. Concept treats intent-based discovery as core. Harden: explicit FTS-only fallback when the embedding/vector path is unavailable, a health probe, and a degraded-mode banner — so search never returns empty on a partial outage.

### 2.4 RFQ vendor quote-compose — verified in API tests

Vendor quote submission from matched providers is covered by `services/api/tests/test_quotes.py::TestSubmitQuote::test_submit_quote_succeeds_for_matched_provider` (plus contact-strip and rival-isolation cases in the same module). No additional quote-compose work required for launch.

---

## 3. Launch-hardening (non-code-feature, but what actually gates GO)

Not concept gaps, but the true critical path. Prompts `CR-D`, `CR-E`.

- **F4 escrow legal review (hard NO‑GO):** the concept **never addresses who legally holds escrow** (BoZ/NPS-Act e-money/PSP posture). This is the single highest-risk open item. Founder + counsel, not code.
- **Lenco live/sandbox (F9b):** code-complete but never proven against a real Lenco rail. Run the staging money-drill vs Lenco sandbox → `CR-D`.
- **Deploy/verify:** API `api.vergeo5.com` was 502; migrations 0051/0053–0056 unapplied to live; n8n workflows inactive; vendor/admin DNS+Vercel wiring incomplete. Deploy + rollback + observability capture → `CR-E`.

---

## 4. Correctly deferred — DO NOT build now

Re-confirmed as intentional (`00-decisions.md §G`, `product-strategy-gap-audit.md`): product_class A–E enum + variants + IMEI/VIN evidence, price-per-kg normalization, by-weight stock, FX/multi-currency, Meilisearch, PWYW tickets + RRULE recurrence, ticket resale marketplace, multi-warehouse + lot/batch, full B2B (credit/Net-terms/RFQ-broadcast/business accounts/account managers), wallet/financing, POS-light, promoted-listing auctions, referral program, voice/AR search, native app, cross-border, Copperbelt delivery, real-time notification center, multi-dimensional reviews, booking calendars, **video/Clips feed (M17)**. Salaula/used-phones/fresh-produce/alcohol/pharma/live-animals/heavy-materials categories are gated off.

---

## 5. Concept contradictions — already resolved by locked decisions

The distillations flagged ~14 cross-document contradictions; the locked decisions settle nearly all: brand (D1 Vergeo5), vendor fees (D3 free tier + flagged paid), commissions (D4 config table), payout cadence (D5 ≤48h), KYC tiers (D9), payments (D11/D14 Lenco, not DPO), events data model (D24 first-class events), search (D22 Postgres, not Meilisearch), tax (D13 ZRA-ready). No open **concept** contradiction requires a code decision; the open items are the founder gates in §3.

---

## 6. Recommendation

1. Treat feature work as **secondary** — the code fulfills Phase‑1. Put founder bandwidth on F4 (escrow legal) and deploy/verify.
2. Ship the three small code gaps (`CR-A` commission binding, `CR-B` bem/nya customer parity, `CR-C` search resilience) — cheap, and they close real trust/accuracy/quality edges.
3. Run the launch-hardening drills (`CR-D`, `CR-E`) in parallel — they surface deploy reality before public launch.

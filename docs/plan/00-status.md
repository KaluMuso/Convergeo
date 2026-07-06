# Vergeo5 — Project Status

**Updated:** 2026-07-06 · **Mode:** GATED · **Current phase:** Phase 1 ✅ COMPLETE — gate open (approve to start Phase 2)

## Phase gate log

| Phase | Status | Output | Approval |
|-------|--------|--------|----------|
| 0 — Discovery | ✅ CLOSED 2026-07-06 | `00-discovery.md` + `00-decisions.md` (LOCKED) + `research/*` | Founder answered all 28 Qs; delegated items resolved per recommendations |
| 0b — Addendum | ✅ 2026-07-06 | Lenco API distilled (`docs/ops/lenco/`), 6/12 design HTMLs committed, live-prototype screenshot findings, `docs/designs/SELECTION.md` | Founder supplied materials ("continue") |
| 1 — Mountains | ✅ COMPLETE 2026-07-06 — 🟡 AWAITING APPROVAL | `docs/plan/01-mountains.md` (16 mountains, ~141 pebbles est.), `CLAUDE.md` | — |
| 2 — Pebbles & Waves | ▶ next (`Phase 2` after approval) | `docs/plan/02-pebbles/*`, `docs/plan/03-waves.md` | — |
| 3 — Cursor prompts | not started | `prompts/*` | — |
| 4 — Review loop | not started | verdicts logged here | — |

## Lenco integration constraints (recorded 2026-07-06, binding)

Direct MoMo push = MTN+Airtel (Zamtel collections unconfirmed → F9a; Zamtel payouts OK) · cards via hosted widget only (PCI) · no refunds API (refunds = ledger-driven payouts) · no splits/escrow primitives (our double-entry ledger over platform Lenco account) · webhook sig = HMAC-SHA512(raw, SHA256(api-token)) + 30-min reconciliation poller mandatory · amounts decimal-major at boundary, integer ngwee internally. Open Lenco questions F9a–f in `docs/ops/lenco/lenco-api-distilled.md`.

## Locked decisions (full detail: `00-decisions.md`)

Brand **Vergeo5** / vergeo5.com · all 5 verticals thin-sliced into v1 (products, services-RFQ, events+QR tickets, supplies-lite, directory) · free vendor tier at launch, paid tiers feature-flagged · commissions 5/8/10/12/5 (+3% supplies, config-table) · **Lenco** payments+escrow (founder has API access), instant-MoMo payouts, ≤48h promise · COD ≤K500 (⚠ F8 confirm) · Turnover-Tax posture, ZRA/VSDC-ready invoicing · official WhatsApp Cloud API (guide in `docs/ops/`), SMS fallback, **no WAHA** · Lusaka manual-dispatch delivery + nationwide pickup · two-lane returns (faulty=full refund; change-of-mind=vendor-opt-in, fees) · **FastAPI + Supabase** · **Next.js 15 + Tailwind + PWA** · **3 apps in one monorepo** (customer/vendor/admin) · OCI (new account) + Vercel + Supabase cloud + Cloudflare, ≤$50/mo · hybrid search (Postgres FTS + pgvector RRF) = RAG store · "Ask Vergeo" AI tab (guest 3 / free 25 Q/mo, $15 kill-switch) · canonical Product+VendorListing + first-class Event tables · Claude seeds catalog · Cloudinary public media + Supabase Storage private · EN launch with full i18n scaffolding → Bemba/Nyanja → French.

## Blocking items

- None for Phase 1.
- Pre-launch gates: F4 (counsel review of escrow under NPS Act 2026); F5 (WhatsApp number verified); F1/F2 (domain, PACRA returns + company TPIN).
- Design inputs still missing (7 of 12 HTML files + live-prototype audit) — see `docs/designs/SOURCES.md`; needed at Phase 1 start for the design-element selection, not for mountain definition.

## Founder actions open

F1 domain · F2 PACRA returns + company TPIN · ~~F3 Lenco docs~~ ✅ committed+distilled · F4 counsel (launch gate) · F5 Meta/WhatsApp setup · F6 courier MOUs (post-beta) · F7 remaining 6 design files (+ optional prototype-domain allowlist) · F8 confirm COD ≤K500 · **F9 ask Lenco support**: a) Zamtel collections? b) sandbox REST base URL + token c) fee schedule + limits d) bulk transfer spec e) register webhook URLs f) settlement type per rail (details in `docs/ops/lenco/lenco-api-distilled.md`).

## Wave/pebble status

_Begins after Phase 2._

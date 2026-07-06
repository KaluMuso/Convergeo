# Vergeo5 — Project Status

**Updated:** 2026-07-06 · **Mode:** GATED · **Current phase:** Phase 2 ✅ COMPLETE — gate open (approve to start Phase 3 prompts)

## Phase gate log

| Phase | Status | Output | Approval |
|-------|--------|--------|----------|
| 0 — Discovery | ✅ CLOSED 2026-07-06 | `00-discovery.md` + `00-decisions.md` (LOCKED) + `research/*` | Founder answered all 28 Qs |
| 0b — Addendum | ✅ 2026-07-06 | Lenco distilled, 6/12 design HTMLs, `SELECTION.md` | Founder supplied materials |
| 1 — Mountains | ✅ CLOSED 2026-07-06 | `01-mountains.md` (16 mountains), `CLAUDE.md` | Approved by invoking Phase 2 |
| 2 — Pebbles & Waves | ✅ COMPLETE 2026-07-06 — 🟡 AWAITING APPROVAL | `02-pebbles/M01…M16` (**141 pebbles**), `03-waves.md` (**19 waves W0–W18**) | — |
| 3 — Cursor prompts | ▶ next (`Phase 3` after approval) | `prompts/_header.md` + per-pebble prompts, generated **per wave** | — |
| 4 — Review loop | not started | verdicts logged here | — |

## Phase 2 key structural decisions (review these at the gate)

- **19 waves** (W0 sequential foundations → W18 launch QA); exact pebble→wave map in `03-waves.md`, count reconciles 141=141.
- **Conflict-free parallelism via conventions:** router auto-discovery (no `main.py` edits), no ui barrel file (deep imports), one migration file per pebble (numbers assigned at Phase 3 prompt time), per-namespace i18n files placed one-per-wave.
- **Schema freeze after Wave 4** (M03-P01–P08 merged); Wave 5 proves it (full RLS isolation matrix + seed) before any feature wave dispatches.
- **Perf budgets police PRs from Wave 10** (M16-P01 pulled early), not retrofitted.
- **⚙ Intra-wave interface edges** (M08-P04→P03, M08-P10→P09, M09-P06→M08-P08, M10-P04↔P06, M06-P03→P02, M13-P06→M08-P05): dependent pebble codes against merged contracts/stubs; Phase 4 review verifies integration. Flagged in `03-waves.md` §6.
- **M13-P09/M12-P10 dashboards degrade gracefully** for AI-usage data until M06 lands (W15–16).

## Founder-gate overlay for waves

F9b (Lenco sandbox URL/token) **hard-blocks M08-P02 tests → needed before Wave 10** · F9a–f + F5 wanted by W10 · F8 (COD cap) before W9 · F4 counsel + F1/F2 = W18 launch-checklist gates.

## Lenco integration constraints (recorded 2026-07-06, binding)

Direct MoMo push = MTN+Airtel (Zamtel collections unconfirmed → F9a; Zamtel payouts OK) · cards via hosted widget only (PCI) · no refunds API (refunds = ledger-driven payouts) · no splits/escrow primitives (our double-entry ledger over platform Lenco account) · webhook sig = HMAC-SHA512(raw, SHA256(api-token)) + 30-min reconciliation poller mandatory · amounts decimal-major at boundary, integer ngwee internally. Open Lenco questions F9a–f in `docs/ops/lenco/lenco-api-distilled.md`.

## Locked decisions (full detail: `00-decisions.md`)

Brand **Vergeo5** / vergeo5.com · all 5 verticals thin-sliced into v1 · free vendor tier at launch, paid tiers feature-flagged · commissions 5/8/10/12/5 (+3% supplies, config-table) · **Lenco** payments+escrow, instant-MoMo payouts, ≤48h promise · COD ≤K500 (⚠ F8) · Turnover-Tax posture, ZRA/VSDC-ready invoicing · official WhatsApp Cloud API, SMS fallback, **no WAHA** · Lusaka manual-dispatch delivery + nationwide pickup · two-lane returns · **FastAPI + Supabase** · **Next.js 15 + Tailwind + PWA** · **3 apps, one monorepo** · OCI + Vercel + Supabase cloud + Cloudflare ≤$50/mo · hybrid search (FTS + pgvector RRF) = RAG store · "Ask Vergeo" (guest 3 / free 25 Q/mo, $15 kill-switch) · canonical Product+VendorListing + first-class Event tables · Claude seeds catalog · Cloudinary public + Supabase Storage private · EN launch → Bemba/Nyanja → French.

## Founder actions open

F1 domain · F2 PACRA returns + company TPIN · ~~F3 Lenco docs~~ ✅ · F4 counsel (launch gate) · F5 Meta/WhatsApp setup (**by W10**) · F6 courier MOUs (post-beta) · F7 remaining 6 design files (merch variant library only — tokens locked) · F8 confirm COD ≤K500 (**by W9**) · F9 Lenco support a–f (**F9b by W10, hard-blocking**).

## Wave/pebble status

| Wave | Pebbles | Status |
|------|---------|--------|
| W0–W18 | 141 total (map in `03-waves.md`) | ⬜ not dispatched — Phase 3 generates prompts per wave |

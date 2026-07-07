# Vergeo5 — Project Status

**Updated:** 2026-07-07 · **Mode:** GATED · **Current phase:** Phase 4 review loop active ▶ **Wave 0 MERGED & REVIEWED** (PRs #3–#19) · **Wave 1 prompts ready** — batch A (M01-P08 gap-fill ∥ M02-P01 ∥ M02-P02) dispatch now in parallel; batch B (M03-P01 ∥ M03-P07) after M01-P08 merges.

## ⚠ Wave 0 as-built note (2026-07-07)

Wave 0 executed from the **draft-A pebble decomposition** (P02=shared packages, P03=FastAPI, P04=3 app shells, P05=CI, P06=infra, P07=backups) with the canonical header — not the canonical split. Functionally sound; accepted as-built. **Gap:** the canonical Supabase pipeline pebble never ran → filled by `prompts/M01-P08-supabase-pipeline-gapfill.md` (blocks all M03 schema pebbles). Canonical `M01-foundations.md` remains the spec of record for *what exists*; as-built file locations differ (api-client in `packages/config`, envelope includes `request_id`, `/healthz`+`/readyz` instead of `/health`).

## Phase 4 verdicts — Wave 0 (2026-07-07)

| Report | Verdict | Notes |
|---|---|---|
| M01-P01 + fix1 | ✅ APPROVED | packages/config relocation + `@vergeo/ui/*` deep-import alias verified; lint-staged `--config` deviation sound |
| M01-P02 (shared pkgs) | ✅ APPROVED | formatK correct (5 cases); server/public env boundary via `./server` subpath is good practice |
| M01-P03 (FastAPI) | ✅ APPROVED | Envelope+request_id (superset of spec — keep); router auto-discovery in; service-role client documented. 🟢 add `CORS_ORIGINS` to root `.env.example` next time that file is owned |
| M01-P04 (app shells) | ✅ APPROVED w/ fix | 🟡 report claimed admin robots-noindex — **was absent**; `output:"standalone"` also missing on vendor+admin (infra Caddyfile assumes it). Fixed directly on master (<20-line rule): `apps/admin/app/robots.ts`, `output:"standalone"` both apps |
| M01-P05 (CI) | ✅ APPROVED | 🟢 db job (supabase reset + typegen drift) missing — added to M01-P08 scope; runtime-generated i18n eslint config acceptable |
| M01-P06 (infra) | ✅ APPROVED | **Q answered: YES** — defer Caddy rate-limit to Cloudflare edge rules (free) for launch; real enforcement is API-level (M04-P07); keep stock caddy image. 🟢 pin caddy/n8n by digest at deploy; `host.docker.internal` needs `extra_hosts: host-gateway` on Linux — deploy-time TODO |
| M01-P07 (backups) | ✅ APPROVED | Drill PASS; prod-guard good. 🟢 importable n8n JSON (vs schedule doc) lands with M14; compose backup volume noted for P06 owner |

## Phase gate log

| Phase | Status | Output | Approval |
|-------|--------|--------|----------|
| 0 — Discovery | ✅ CLOSED 2026-07-06 | `00-discovery.md` + `00-decisions.md` (LOCKED) + `research/*` | Founder answered all 28 Qs |
| 0b — Addendum | ✅ 2026-07-06 | Lenco distilled, 6/12 design HTMLs, `SELECTION.md` | Founder supplied materials |
| 1 — Mountains | ✅ CLOSED 2026-07-06 | `01-mountains.md` (16 mountains), `CLAUDE.md` | Approved by invoking Phase 2 |
| 2 — Pebbles & Waves | ✅ CLOSED 2026-07-06 | `02-pebbles/M01…M16` (**141 pebbles**), `03-waves.md` (**19 waves W0–W18**) | Approved by merging PR #1 + requesting Phase 3 |
| 3 — Cursor prompts | ◐ IN PROGRESS 2026-07-07 | `prompts/_header.md` + **Wave 0: `M01-P01…P07`** (7/7). Later waves generated per-wave at dispatch. | 🟡 W0 prompts awaiting founder use/review |
| 4 — Review loop | not started | verdicts logged here | — |

> **Session note (2026-07-07):** a parallel session drafted an alternative Phase 2 + W0 prompts from a pre-PR#1 clone (branch `claude/adoring-dirac-a5w0pg`, commit `5192c86`). That duplicate Phase 2 was **discarded** in favor of this merged/approved plan; the W0 prompts were **rewritten against the canonical M01 pebble specs** (router auto-discovery, no barrels, `NNNN_slug.sql`, per-namespace i18n) before merging.

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
| **W0** | M01-P01…P07 (as-built draft-A split) + fix1 | ✅ **MERGED** (PRs #3,#4,#5,#6,#7,#13,#19) · reviewed 2026-07-07, all approved · +micro-fixes on master (admin robots, standalone output) |
| **W0 gap** | M01-P08 Supabase pipeline | 🟨 **prompt ready** (`prompts/M01-P08-supabase-pipeline-gapfill.md`) — dispatch in batch A |
| **W1 batch A** | M01-P08 ∥ M02-P01 (tokens) ∥ M02-P02 (i18n completion) | 🟨 **prompts ready — dispatch all 3 in PARALLEL now** (disjoint files; only M02-P01 touches pnpm-lock) |
| **W1 batch B** | M03-P01 (identity schema) ∥ M03-P07 (config tables) | 🟨 prompts ready — **dispatch after M01-P08 merges**; both regenerate `db.ts` (second-to-merge rebases) |
| W2–W18 | remaining (map in `03-waves.md`) | ⬜ prompts generated per wave |

**Dependabot policy (2026-07-07):** major-version bumps ignored via `dependabot.yml` until M16 launch QA (mid-build major churn risk); majors #14–#18 closed; GitHub-Actions bumps #8–#12 fine to merge when CI is green on them.

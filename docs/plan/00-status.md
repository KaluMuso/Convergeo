# Vergeo5 — Project Status

**Updated:** 2026-07-07 · **Mode:** GATED · **Current phase:** Phase 3 ▶ **Wave 2 prompts ready — dispatch all 7 in PARALLEL from `master`** (`prompts/M02-P03..P06`, `M02-P08`, `M03-P02`, `M03-P03`). Wave 1 merged & reviewed (all ✅). Pre-wave enabler on master: @vergeo/ui test toolchain (react+RTL+jsdom devDeps, `./src/*` wildcard export, jsx react-jsx) so no Wave-2 pebble touches pnpm-lock/package.json; component tests use a `// @vitest-environment jsdom` docblock (no vitest.config.ts — it breaks the snapshot client).

## ⚠ ORCHESTRATION RULE (violated twice — fix in Cursor before Wave 2)

**Cursor MUST branch from and open PRs against `master`.** Wave-1 PRs #20/#21 were merged into the dead ex-default branch `claude/nice-knuth-ijvthu` and #23–#25 targeted it or stacked on each other; Claude converged everything into master manually (merge commits 2026-07-07, all tests green) and closed #22–#25 as absorbed. **`claude/nice-knuth-ijvthu` deleted 2026-07-07** (remote + local); GitHub default branch is `master`. Set Cursor Cloud's base branch to `master` in the dashboard if agents still target the old branch. Also: **batch B pebbles must wait for batch A merges** — running M03-P01/P07 early forced both to bundle duplicate pipeline files, which caused the conflicts.

## Phase 4 verdicts — Wave 1 (2026-07-07)

| Report           | Verdict            | Notes                                                                                                                                |
| ---------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| M01-P08 pipeline | ✅ APPROVED        | PG 15 config kept (Supabase local images skip 16); CI db job is reset/typegen authority                                              |
| M02-P01 tokens   | ✅ APPROVED        | --text-3/--accent decorative-only AA exclusion accepted (SELECTION-conformant); default Tailwind palette removal is a nice hardening |
| M02-P02 i18n     | ✅ APPROVED w/ fix | 🟡 flat dotted keys in common.json rendered raw (next-intl nests on dots) — fixed on master: nested JSON + dot-path resolveMessage   |
| M03-P01 identity | ✅ APPROVED        | FORCE RLS + session_user guard triggers = good judgment; role-escalation matrix 25/25                                                |
| M03-P07 config   | ✅ APPROVED        | platform_config authenticated-select deviation accepted (API reads via service role); placeholder zone fees fine, admin-editable     |

**Convergence fixes applied on master:** db.ts = union of both hand-generated halves (0002+0008, compiles; CI db job regenerates authoritatively) · config.toml PG 15 kept over PG 16 (no Supabase 16 image) · common.json nesting + resolveMessage dot-path walk. Full suite green: 32 tests, typecheck 7/7, lint 4/4.

## Phase gate log

| Phase               | Status                   | Output                                                                                              | Approval                                       |
| ------------------- | ------------------------ | --------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| 0 — Discovery       | ✅ CLOSED 2026-07-06     | `00-discovery.md` + `00-decisions.md` (LOCKED) + `research/*`                                       | Founder answered all 28 Qs                     |
| 0b — Addendum       | ✅ 2026-07-06            | Lenco distilled, 6/12 design HTMLs, `SELECTION.md`                                                  | Founder supplied materials                     |
| 1 — Mountains       | ✅ CLOSED 2026-07-06     | `01-mountains.md` (16 mountains), `CLAUDE.md`                                                       | Approved by invoking Phase 2                   |
| 2 — Pebbles & Waves | ✅ CLOSED 2026-07-06     | `02-pebbles/M01…M16` (**141 pebbles**), `03-waves.md` (**19 waves W0–W18**)                         | Approved by merging PR #1 + requesting Phase 3 |
| 3 — Cursor prompts  | ◐ IN PROGRESS 2026-07-07 | `prompts/_header.md` + **Wave 0: `M01-P01…P07`** (7/7). Later waves generated per-wave at dispatch. | 🟡 W0 prompts awaiting founder use/review      |
| 4 — Review loop     | not started              | verdicts logged here                                                                                | —                                              |

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

| Wave           | Pebbles                                                | Status                                                                                                                                    |
| -------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **W0**         | M01-P01…P07 (as-built draft-A split) + fix1            | ✅ **MERGED** (PRs #3,#4,#5,#6,#7,#13,#19) · reviewed 2026-07-07, all approved · +micro-fixes on master (admin robots, standalone output) |
| **W0 gap**     | M01-P08 Supabase pipeline                              | 🟨 **prompt ready** (`prompts/M01-P08-supabase-pipeline-gapfill.md`) — dispatch in batch A                                                |
| **W1 batch A** | M01-P08 ∥ M02-P01 (tokens) ∥ M02-P02 (i18n completion) | 🟨 **prompts ready — dispatch all 3 in PARALLEL now** (disjoint files; only M02-P01 touches pnpm-lock)                                    |
| **W1 batch B** | M03-P01 (identity schema) ∥ M03-P07 (config tables)    | 🟨 prompts ready — **dispatch after M01-P08 merges**; both regenerate `db.ts` (second-to-merge rebases)                                   |
| W2–W18         | remaining (map in `03-waves.md`)                       | ⬜ prompts generated per wave                                                                                                             |

**Dependabot policy (2026-07-07):** major-version bumps ignored via `dependabot.yml` until M16 launch QA (mid-build major churn risk); majors #14–#18 closed; GitHub-Actions bumps #8–#12 fine to merge when CI is green on them.

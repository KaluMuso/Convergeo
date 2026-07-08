# Vergeo5 — Project Status

**Updated:** 2026-07-08 · **Mode:** GATED · **Current phase:** Phase 4 ▶ **Wave 4 MERGED + reviewed — SCHEMA FREEZE NOW ACTIVE** (all 6 pebbles on `master`: PRs #44,#45,#41,#40,#42,#43). Two deploy-blocking bugs in `0009_search.sql` found via a local PG16 replay and fixed on master (commit `7befd11`). **Migrations are now additive-only.** Next: generate Wave 5 prompts (RLS isolation matrix + seed — proves the freeze) per `03-waves.md`.

> ⚠ **CRITICAL INFRA GAP (found 2026-07-08): there is NO CI. `.github/workflows/` does not exist and never has.** Every "CI `db` job regenerates db.ts / validates migrations" claim in the verdicts below is **false** — nothing was validating migrations or regenerating `db.ts`. This is exactly why `0009`'s two bugs (non-immutable generated column; `search_rrf` bad column ref) merged undetected. **Until a CI pipeline lands, Claude validates migrations by replaying `0001→NNNN` against a throwaway local PG16 cluster** (see Wave-4 verdicts). Standing recommendation: build `.github/workflows/ci.yml` (pnpm/turbo typecheck+test+lint, `uv` pytest+ruff+mypy, and a Postgres migration-replay + `db.ts` drift check) before Wave 5 dispatches. **db.ts is hand-maintained with no authoritative regenerator — treat the merge-order/append rule as load-bearing, not a safety net.**

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

## Phase 4 verdicts — Wave 2 (2026-07-07)

| Report                         | Verdict            | Notes                                                                                                                                                                                                               |
| ------------------------------ | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M02-P03 forms                  | ✅ APPROVED        | 27 tests; OTP paste/auto-advance solid; native inputs, ≥44px                                                                                                                                                        |
| M02-P04 cards/price            | ✅ APPROVED w/ fix | 🟡 inlined a copy of formatK (claimed rootDir blocked workspace import) — **fixed on master**: dropped ui `rootDir` (no-op under noEmit), added `@vergeo/i18n` dep, imported the real formatK. One money path again |
| M02-P05 overlays               | ✅ APPROVED        | 32 tests; focus-trap/scroll-lock/drag-dismiss/toast-queue all covered                                                                                                                                               |
| M02-P06 nav                    | ✅ APPROVED        | 20 tests; config-driven BottomNav, load-more primary, LinkComponent seam                                                                                                                                            |
| M02-P08 media                  | ✅ APPROVED        | 21 tests; `sanitizePublicId` neutralizes protocol smuggling; 360/720/1080 srcset + LQIP                                                                                                                             |
| M03-P02 catalog (0003)         | ✅ APPROVED        | 18 assertions; ≤8-image + status guard triggers; EXPLAIN shows index use; moderation status pinned                                                                                                                  |
| M03-P03 services/events (0004) | ✅ APPROVED        | 17 tests; **quote-privacy proven** (provider A cannot read B's quote); ticket secrets holder/organiser-only; free-RSVP price-0 constraint                                                                           |

**Convergence fixes on master (verified: 123 ui tests, suite 10/10, typecheck 7/7, 3 app builds):**

- **CI db job was broken** — ran `supabase db reset` without `supabase db start` (the failure that forced PR #32's admin-override merge). Added `supabase db start` first.
- **formatK de-duplicated** (M02-P04) — removed the inlined copy, imported `@vergeo/i18n`; removed ui `rootDir`.
- **db.ts** = union of catalog (0003) + services/events (0004) tables (both hand-generated in-cloud; CI db job regenerates authoritatively).

> **Wave-2 orchestration: FIXED.** All 7 PRs (#26,#34,#33,#28,#27,#31,#32) branched from and merged to `master` correctly — the branch-target rule held. One residual: PR #32 needed admin-override due to the CI db-job bug (now fixed) + a db.ts conflict with #31 (resolved by combining table sets).

## Wave-3 grounding audit (2026-07-07)

Before writing the 5 Wave-3 prompts, audited the real merged tree (Workflow harness hit a permission-stream error → done via direct parallel reads). Findings baked into the prompts:

- **M05-P10 duplication caught**: the planned `packages/ui/src/media/url.ts` already exists as merged `cloudinary-url.ts` (M02-P08) → prompt owns ONLY the backend signing endpoint + docs; the existing file IS the D26 seam.
- **M15-P06 flat-key bug caught**: `legal.json` has flat dotted keys (next-intl nests on dots — same class as the `common.json` fix) → prompt must nest it.
- **M04-P01 grounded**: config.toml already has a full `[auth]` section (edit surgically); Africa's Talking → Send SMS Hook (not a built-in provider); profile-bootstrap = migration `0010` (trigger on auth.users); env names reused (`AT_API_KEY` etc.); sole owner of config.toml this wave.
- **Auth seam**: M04-P02 (API auth dependency) not merged → M05-P10 signing authz gates behind a documented, injectable seam.
- **M04-P06 not merged** → M15-P06 privacy page links data-rights to a documented stub route `/{locale}/account/data`.

## Phase 4 verdicts — Wave 3 (2026-07-07)

| Report                | Verdict                   | Notes                                                                                                                                                                                                                                                                                                                                                                                                           |
| --------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M02-P07 preview       | ✅ APPROVED               | 36/36 export-coverage; prod-gate 404s; robots noindex. Its `@vergeo/ui` dep add was lost in a rebase (2 commits) → see fix below                                                                                                                                                                                                                                                                                |
| M03-P04 orders (0005) | ✅ APPROVED               | 17/17; client status-UPDATE denied (both roles); audit trigger on every status change; tickets.order_item_id FK completed; EXPLAIN index use on both hot paths                                                                                                                                                                                                                                                  |
| M04-P01 auth+SMS      | ✅ APPROVED (was PARTIAL) | PARTIAL was only local db-reset env limits (Docker overlayfs) — code verified sound: config.toml auth edits surgical + valid TOML (send_sms hook, google, 3 redirect URLs), `0010` bootstrap idempotent + security-definer, `on conflict (user_id,role)` matches the 0002 unique constraint, edge fn 7/7 with signature verify. **CI db job is the reset validator.** `secrets` (plural) per current CLI — fine |
| M05-P10 media-signing | ✅ APPROVED               | 20 tests; cross-vendor folder injection impossible (server-derived); api_secret never returned; SHA-1 signing golden; authz seam actually verifies Supabase JWT via JWKS (exceeds the stub ask) — TODO-flagged for M04-P02; NO url.ts duplication                                                                                                                                                               |
| M15-P06 legal         | ✅ APPROVED w/ fix        | legal.json fully nested (0 flat keys); 4 pages SSG × 4 locales; footer 4/4. 🟡 two deviations both rooted in the lost M02-P07 dep (relative-path import + i18n workaround) → fixed below                                                                                                                                                                                                                        |

**Convergence fix on master (verified: typecheck 7/7, lint 4/4, test 10/10, customer build 27 SSG routes):**

- **`@vergeo/ui` dependency was undeclared** in `apps/customer/package.json` (M02-P07's add lost in a rebase). The app relied on it transitively via `transpilePackages`+hoisting — worked, but fragile, and forced M15-P06's `../../../../packages/ui/src/footer` relative import. Declared the dep + switched footer to the canonical `@vergeo/ui/src/footer`.
- M15-P06's other deviation (layout loads `legal` via `loadNamespace`+`createTranslator` because `request.ts` only auto-loads `common`) is **accepted as-built** — legal pages/footer are server components; correct. A later i18n pass can make namespace loading route-aware.

> **Wave-3 orchestration: clean.** All 5 branched from + merged to `master`. Grounding audit paid off — the 3 flagged conflicts (M05-P10 url.ts duplicate, M15-P06 flat keys, M04-P01 config clobber) were all pre-empted in the prompts and did not occur.

## Wave-4 grounding + dispatch notes (2026-07-07)

Grounded against merged column names before writing (schema-freeze wave = high stakes):

- **Schema FKs pinned to real names**: money(0006)/trust(0007) FK `checkout_groups`/`orders(id,customer_id,vendor_id,status)`/`order_items(id,order_id,item_kind)`; search(0009) projects `products`/`vendor_listings`/`services`/`events`/`vendors` in their exact publish states.
- **M04-P02 consolidates the media-authz duplicate**: M05-P10 left a full JWKS-verify path in `app/media/authz.py` (TODO-flagged). M04-P02 owns + refactors it onto the new shared `core/auth.py` — one verify path, no duplication. Roles read from `user_roles` (never JWT claims) → forged-admin-claim 403 is the headline test.
- **M04-P03 sole `pnpm-lock` owner** this wave (adds `@supabase/ssr` + `@vergeo/auth`); composes auth with the existing next-intl middleware (locale never dropped); customer browsable logged-out.
- **M12-P11 kept dep-free**: no live config-read client exists yet on the customer app (M04-P03 parallel) → renders the commission table from a single D4-constant module (= 0008 seed) with a `TODO(config)` to bind live later; uses a code fallback for the vendor-app URL instead of touching `.env.example` (M04-P03 owns it).
- **db.ts 3-way overlap** is the only shared file — append-only, no sibling reformatting; CI `db` job regenerates authoritatively; later-merging schema PR combines table sets (same pattern that worked W1/W2).

## Phase 4 verdicts — Wave 4 (2026-07-08) — SCHEMA-FREEZE WAVE

All six merged to `master` (PRs #44 money, #45 trust-ops, #41 search, #40 API-auth, #42 frontend-auth, #43 vendor-pitch). Cursor resolved the 3-way `db.ts` overlap on merge (money + trust + search table sets combined). Full JS/Python suite re-verified green on the merged tree: **typecheck 8/8, test 12/12 (127 ui tests), lint 4/4; API pytest 31/31, ruff + mypy clean.**

| Report                   | Verdict                    | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------ | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M03-P05 money (0006)     | ✅ APPROVED                | 24/24 pgTAP in isolation; zero-sum ledger + `next_invoice_no()` FOR UPDATE + full RLS matrix. Re-verified live: zero-sum rejects imbalance ("got 1 ngwee"), platform-account singleton + vendor_id-required invariants hold                                                                                                                                                                                                                                                                                                             |
| M03-P06 trust-ops (0007) | ✅ APPROVED                | 14/14; verified-purchase trigger (delivered/completed + ownership) + one-review-per-item unique; outbox/audit service-role-only                                                                                                                                                                                                                                                                                                                                                                                                         |
| M03-P08 search (0009)    | ✅ APPROVED **w/ 2 fixes** | Merged PARTIAL (no db reset — no Docker) → **two deploy-blocking bugs found on live replay & fixed on master** (`7befd11`): (1) `tsv` generated column not IMMUTABLE (`array_to_string` STABLE + text-form `to_tsvector`) → IMMUTABLE `search_document_tsv()` helper w/ `'simple'::regconfig`; (2) `search_rrf` `params` CTE omitted `query_embedding` but `vector_lane` referenced `p.query_embedding`. Re-verified: sync trigger projects on publish + removes on unpublish, FTS lane matches, `search_rrf` executes, synonyms seeded |
| M04-P02 API auth         | ✅ APPROVED                | 31/31 pytest incl. forged-admin-claim→403 (roles from `user_roles`, never JWT) + service-role import-guard; media/authz.py consolidated onto `core.auth` (one JWKS path); `test_media.py` still green. Note: `require_vendor_scope` still derives vendor_id from JWT claims (TODO-flagged) — real vendor-ownership check deferred                                                                                                                                                                                                       |
| M04-P03 frontend auth    | ✅ APPROVED                | `@vergeo/auth` (SSR clients/session/roles) + composed middleware in all 3 apps (locale never dropped); 20 tests incl. middleware matrix; sole `pnpm-lock` owner. CI fix: mocked `@supabase/ssr` in node tests. Admin bypass flag non-prod, M13-P01 Cloudflare-Access TODO                                                                                                                                                                                                                                                               |
| M12-P11 vendor pitch     | ✅ APPROVED                | `/sell` SSG × 4 locales (288 B route JS); commission table = single D4 constant module (test-asserted vs 0008 seed) with `TODO(config)`; vendor-app URL via env fallback (no `.env.example` edit); indexable + FAQ JSON-LD                                                                                                                                                                                                                                                                                                              |

**Convergence fix on master (commit `7befd11`, pushed):** the `0009_search.sql` immutability + `search_rrf` fixes above. Editing `0009` in place is correct — a migration that _fails to apply_ cannot be repaired additively, and `0009` had never applied successfully anywhere. Validation method (new, since there is no CI and no Docker): stood up a throwaway local PG16 cluster with a minimal Supabase shim (roles `anon`/`authenticated`/`service_role`/`supabase_admin`, `auth` schema + `auth.users`/`auth.uid()`/`auth.jwt()`, pgvector installed via apt) and replayed `0001→0010` with `ON_ERROR_STOP`, then exercised the risky runtime surfaces (search projection triggers, RRF, ledger zero-sum).

> **Wave-4 orchestration: clean on branch-target** (all 6 → master), **but the CI premise was false** — the "CI validates migrations / regenerates db.ts" assumption that underwrote the whole schema-freeze wave does not exist (see header gap note). Local PG16 replay is the interim validator; a real CI pipeline is the top infra priority before Wave 5.

## Phase gate log

| Phase               | Status                   | Output                                                                           | Approval                                       |
| ------------------- | ------------------------ | -------------------------------------------------------------------------------- | ---------------------------------------------- |
| 0 — Discovery       | ✅ CLOSED 2026-07-06     | `00-discovery.md` + `00-decisions.md` (LOCKED) + `research/*`                    | Founder answered all 28 Qs                     |
| 0b — Addendum       | ✅ 2026-07-06            | Lenco distilled, 6/12 design HTMLs, `SELECTION.md`                               | Founder supplied materials                     |
| 1 — Mountains       | ✅ CLOSED 2026-07-06     | `01-mountains.md` (16 mountains), `CLAUDE.md`                                    | Approved by invoking Phase 2                   |
| 2 — Pebbles & Waves | ✅ CLOSED 2026-07-06     | `02-pebbles/M01…M16` (**141 pebbles**), `03-waves.md` (**19 waves W0–W18**)      | Approved by merging PR #1 + requesting Phase 3 |
| 3 — Cursor prompts  | ◐ IN PROGRESS 2026-07-08 | `prompts/_header.md` + Waves 0–4 dispatched & merged. Wave 5 next.               | Waves 0–4 used + reviewed                      |
| 4 — Review loop     | ◐ IN PROGRESS 2026-07-08 | Waves 0–4 verdicts logged here (all approved; W4 +2 convergence fixes on `0009`) | Rolling per-wave                               |

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

| Wave           | Pebbles                                                                        | Status                                                                                                                                    |
| -------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **W0**         | M01-P01…P07 (as-built draft-A split) + fix1                                    | ✅ **MERGED** (PRs #3,#4,#5,#6,#7,#13,#19) · reviewed 2026-07-07, all approved · +micro-fixes on master (admin robots, standalone output) |
| **W0 gap**     | M01-P08 Supabase pipeline                                                      | 🟨 **prompt ready** (`prompts/M01-P08-supabase-pipeline-gapfill.md`) — dispatch in batch A                                                |
| **W1 batch A** | M01-P08 ∥ M02-P01 (tokens) ∥ M02-P02 (i18n completion)                         | 🟨 **prompts ready — dispatch all 3 in PARALLEL now** (disjoint files; only M02-P01 touches pnpm-lock)                                    |
| **W1 batch B** | M03-P01 (identity schema) ∥ M03-P07 (config tables)                            | ✅ **MERGED**                                                                                                                             |
| **W2**         | M02-P03/04/05/06/08 · M03-P02 (0003) · M03-P03 (0004)                          | ✅ **MERGED** — all approved                                                                                                              |
| **W3**         | M02-P07 · M03-P04 (0005) · M04-P01 (+0010) · M05-P10 · M15-P06                 | ✅ **MERGED** — all approved (+`@vergeo/ui` dep convergence fix)                                                                          |
| **W4**         | M03-P05 (0006) · M03-P06 (0007) · M03-P08 (0009) · M04-P02 · M04-P03 · M12-P11 | ✅ **MERGED — SCHEMA FREEZE ACTIVE**; all approved, +2 `0009` convergence fixes (`7befd11`)                                               |
| **W5**         | RLS isolation matrix + seed (proves the freeze)                                | 🟨 **NEXT — generate prompts** per `03-waves.md`. Recommend CI pipeline lands alongside/before                                            |
| W6–W18         | remaining (map in `03-waves.md`)                                               | ⬜ prompts generated per wave                                                                                                             |

**Dependabot policy (2026-07-07):** major-version bumps ignored via `dependabot.yml` until M16 launch QA (mid-build major churn risk); majors #14–#18 closed; GitHub-Actions bumps #8–#12 fine to merge when CI is green on them.

# Master vs. Documentation — Representation Assessment (2026-07-20)

**Question answered:** *How far is `master` from being a faithful representation of the
expectations in `docs/concept`, `docs/designs`, `docs/ops`, `docs/plan`, and
`docs/production-readiness`?*

**Assessed tree:** `master` @ `1d137ae` (Merge PR #351, 2026-07-20).
**Method:** five parallel area audits (concept, designs, ops, plan, production-readiness),
each verifying documented promises against code/files at HEAD with file-level evidence,
plus a same-day live-state refresh (Vercel deployment SHAs, n8n instance inventory).
Live Supabase state could **not** be re-verified this session (Supabase connector
unauthenticated); last verified live-DB evidence is 2026-07-19.

---

## 1. Headline percentages

Two different questions hide inside "representation", and they score very differently:

| Lens | Score | Meaning |
| ---- | ----- | ------- |
| **A. BUILD** — "does master contain the product the docs describe?" | **≈ 93%** | The v1-scoped product in the concept/plan/designs/ops docs exists in code, tested and CI-green. |
| **B. READINESS** — "is the project in the state the production-readiness corpus says it must reach?" | **≈ 31–40%** | The corpus's prescribed work (45 pebbles, S0–S7 + G0–G22 gates) is only partially executed; **0 gates PASS**; verdict remains **NO-GO for real money / NO-GO for `public_launch`**. |
| **Blended overall** (weights: plan 25, concept 20, designs 15, ops 15, readiness 25) | **≈ 73%** | Only meaningful as a single-number summary; the split above is the real answer. |

### Per-area scores

| Docs area | vs. v1/launch scope | vs. full docs surface | Basis |
| --------- | ------------------- | --------------------- | ----- |
| `docs/plan` (16 mountains, 141 pebbles, Events Wave A/B) | **≈ 99%** | **≈ 91%** | All M01–M16 code-complete; full-surface number deducts M17 (0%, deliberately post-launch), partial bem/nya, 2 unwired components. |
| `docs/concept` (via distillations + document audits) | **≈ 94–95%** | **≈ 45–55%** | 37/41 in-scope capabilities implemented, 3 partial-by-design, 1 absent (video feed). Full-surface number counts the ~24 capability clusters **deliberately deferred by decisions D1–D34/§G** (wallet, referrals, couriers, multi-warehouse, native app, super-app rails…). |
| `docs/designs` (TOKENS/SELECTION/prototypes) | **≈ 93%** | ≈ 93% | Token system a near-exact implementation; every hi-fi + wireframe screen (incl. all four SELECTION §6 "critical gaps") built; residual = dark-mode debt in ~12–14 vendor components + minor deviations. |
| `docs/ops` (21 runbooks/contracts) | **≈ 90% of repo obligations** | **≈ 65%** incl. live-execution ACs | 16/21 docs fully repo-satisfied. The ~35% live-gated slice (drills, Meta submission, creds, pentest run, branch protection) is mostly unexecuted. |
| `docs/production-readiness` (07-18 + 07-19 corpus) | **≈ 43%** of in-repo prescribed pebbles · **≈ 92%** of decisions locked | **≈ 31%** of all 45 pebbles (9 DONE, 10 PARTIAL, 26 OPEN) | Live-ops residual (~24 pebbles) only ~¼ executed; that residual contains **all remaining launch-P0s**. |

**Bottom line:** master is a ~93% faithful build of the documented v1 product — the
platform the docs describe genuinely exists in this repo. What master does *not* yet
represent is the documented **operational end-state**: proven money flows, live
automations, observability, backup/restore, legal sign-off, and the go/no-go evidence
pack. The repo's own thesis (vision-audit §9) still holds at HEAD: the launch-critical
gap is **DEPLOY → VERIFY → OPS → DECISIONS**, not build.

---

## 2. Live-state refresh performed this session (2026-07-20)

| Check | Result | Effect on known gaps |
| ----- | ------ | -------------------- |
| Vercel `convergeo-customer` production | **At master tip `1d137ae`**, READY | **DL-1 closed** (was stuck at `cc4a824` with `/categories` 500 on 07-19). |
| Vercel `convergeo-vendor` production | **At master tip `1d137ae`**, READY | **DL-2 closed for vendor** (admin not directly probed; same git-connected auto-deploy pipeline). |
| n8n live instance | **Only 2 workflows exist, both active** (notification dispatch; payment-reconciliation crons) | **DL-4 fully open** — 17 of 19 committed workflow JSONs (incl. `release-job`, `order-jobs`, `tickets-issue`, `tickets-release`, `event-release`) were never imported; escrow auto-release and ticket issuance **cannot fire in production**. |
| Supabase live DB | **Not verifiable** (connector needs re-auth) | Last evidence (07-19): `0051`/`0053`–`0056` applied directly to prod. Migrations **`0057`–`0062` merged after that evidence** — live application unverified. |
| Direct URL probes (`www.vergeo5.com`, `api.vergeo5.com`) | Blocked by sandbox network policy | API image digest (DL-5/VA-P03) remains unverifiable from here. |
| Open PRs | **#352** (refunds `source_key` + migration `0063`) and **#353** (a separate Cursor-authored gap-analysis doc) unmerged | #352 will move the migration ledger to 0063; #353 overlaps this report's intent. |

---

## 3. What is missing — exact inventory

### 3.1 Genuine build gaps in master (repo-closable)

Ordered roughly by launch relevance. IDs reference the 2026-07-19 vision audit
(`docs/production-readiness/2026-07-19/vision-audit/`).

| # | Gap | Detail / evidence | Ref |
| - | --- | ----------------- | --- |
| 1 | **FORCE RLS migration never written** | D32/B-3 decided "enable", but no migration sets `FORCE ROW LEVEL SECURITY` on `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations`. The planned `0057` slot was consumed by an unrelated fix (`0057_vendor_lifecycle_client_guards.sql`). | VC-P02, FD-07, G0 |
| 2 | **DB-backup n8n workflow JSON absent** | `infra/n8n/` has 19 JSONs; none is a backup. Only `backup-schedule.md` (contract) exists. Blocks the restore drill chain (VE-P03). | VD-P04, BG-5, G7 |
| 3 | **Demo-catalogue exclusion is client-side only** | FD-04 decided "exclude from public search"; only labeling shipped (`_components/demo-listing.ts`). No `demo` filter in `routers/search.py` / `catalog.py`. | VC-P06, G11 |
| 4 | **Two prescribed E2E specs absent** | `e2e/specs/checkout-false-success.spec.ts` (payment pending/failed must never render "paid") and `e2e/specs/critical-path.spec.ts` do not exist; only unit-level coverage. | VB-P07, VE-P07, S6, G4/G16 |
| 5 | **CI security gates still non-blocking** | `secret-scan` is `continue-on-error: true` (`ci.yml:179`); Lighthouse assertions all `warn` + `continue-on-error` (`perf.yml:213-216`, `lighthouserc.json`). | VE-P04, VE-P06, G8/G19 |
| 6 | **RLS test-matrix registry incomplete** | `event_categories`, `product_relations`, `service_reviews` have policies but no rows in `tests/rls/test_matrix.py` EXPECTATIONS. | VC-P04 |
| 7 | **`uptime-alert` inbound webhook unauthenticated** | Webhook node in `infra/n8n/uptime-alert.json` has `options: {}` — no shared secret/HMAC; relies on path obscurity. Money-workflow error-alerting (VD-P06) also absent from the JSONs. | VD-P05/P06 |
| 8 | **Bemba/Nyanja at 8 of 17 namespaces** | `bem`/`nya` are genuine vernacular (not EN stubs) but cover only the Phase-1 purchase journey; missing: admin, ai, auth, directory, events, legal, services, supplies, vendor (+search for bem). `noindex` pending native review (`PHASE1_NATIVE_REVIEW.md`). | VF-P01, BG-1, G18 |
| 9 | **`zh` still in the public locale switcher** | `packages/i18n/src/locales.ts` `LOCALES=["en","bem","nya","fr","zh"]` — NB-1 de-route not done. | VF-P02 |
| 10 | **Two components built but never mounted** | `apps/customer/.../p/[slug]/_components/report-review.tsx` (no importer) and `apps/customer/.../account/jobs/[id]/_components/accept-flow.tsx` (+`complete-confirm.tsx`; page imports only `ServiceReviewForm`). (`claim-banner.tsx`, the third historical orphan, **is** now wired.) | 00-status carried debt #3 |
| 11 | **Search `degraded=true` fix unevidenced** | Live `/search` was observed degraded (embeddings/FTS health) on 07-19; no repo change clearly addresses it. Needs live re-probe. | VF-P04, MR-B07 |
| 12 | **~12–14 vendor components don't dark-theme** | Tailwind default-palette classes (`neutral-*` ×dozens, `emerald-*`, `amber-*`, `red-*`) in `event-form`, `listing-create-flow`, `order-card`, `action-bar`, `payouts-view`, profile editors, etc. Cosmetic. | 00-status UI follow-up (a) |
| 13 | **CSP nonce policy still report-only** | Enforce-mode nonce middleware not landed (documented deferral in `security-headers.md:44-56`). | M15-P03 residual |
| 14 | **M17 "Vergeo Clips" video feed: 0%** | Spec only (`docs/plan/m17-video-feed.md`); zero routes/migrations/tables. **Deliberately post-launch — do not build pre-launch.** | BG-6 |
| 15 | **Doc drift (docs wrong, not code)** | `ci.md` stale (deps-audit now blocking; 5 newer CI jobs undocumented; lists secret-scan as "required" while it can't fail); TOKENS.md missing the dark-mode `--primary`/button-token additions; F7 says "7 design files" vs SOURCES.md's canonical 6; `drill-log.md` local drill pinned at migration ledger 29 vs 62 now. | hygiene |

### 3.2 Live-ops / founder gates (cannot be closed by code in this repo)

This is where the launch actually lives. **0 of 8 S-gates and 0 of 23 G-gates PASS**;
`release-gates.md` verdict is unchanged: **NO-GO real money, NO-GO `public_launch`**.

**Money proof (S1–S6 · VB-P01…P06)** — Lenco **sandbox** MoMo + card charge → `CHARGE_RECEIVED`/escrow-hold ledger legs, webhook replay/idempotency, release accounting (commission-before-vendor-net, escrow→0), refund/cancel matrix, forced reconciliation-mismatch alert. All code-complete and heavily hardened Jul 18–20 (migrations `0059`/`0062`, PRs #333–#351) but **never executed against a live/sandbox target**. Gated on **F9b** (Lenco sandbox/production credentials).

**Automations (S4/G5/G21 · VD-P01…P03)** — import + activate the 17 dormant workflows (escrow release, order jobs, ticket issue/release, event release, 8 lifecycle) on the live n8n; prove idempotent single-tick behaviour. Confirmed still outstanding today.

**Deployment truth (VA-P03)** — pin + record the live API container's GHCR digest; confirm the deployed API serves the `0057`–`0062`-era routes. Also: apply migrations `0057`–`0062` (and `0063` once #352 merges) to the live DB — the 07-19 apply evidence stops at `0056`.

**Observability (G6 · VE-P01/P02)** — Vergeo5 Sentry projects + DSNs (none exist), UptimeRobot monitors, test-event ingestion.

**Trust/authz live halves** — enable the Supabase Auth role hook (`0051` applied, hook **not enabled** — FD-03); manual repair of the 3 orphaned-KYC vendors (FD-12); enable leaked-password protection (VC-P09/G20).

**Ops drills (G7/G9)** — restore drill from a real backup (blocked on gap #2), timed Vercel+API rollback drill, VM isolation plan for the shared host (WAHA + ZedApply co-tenancy, NB-8), and the **go/no-go evidence pack** (VE-P09) that flips `release-gates.md`.

**Founder gates (launch-checklist §4)** — **F2** PACRA + company TPIN · **F4/FD-08** Zambian counsel written sign-off on the escrow flow (NPS Act 2026) — the only FD decision still genuinely open · **F5** Meta/WhatsApp Cloud API activation + 7-template submission · **F6** courier MOUs (post-beta OK) · **F7** upload the 6 remaining design HTMLs (checklist says 7 — stale count) · **F8** confirm COD cap · **F9a** Zamtel collections decision (default: keep off) · **F9b** Lenco credentials. **F1 (domain) is done.**

**Verification proofs (launch-checklist §3)** — E2E green on a deployed target vs Lenco sandbox, ≤30-min restore drill, k6 load p95<500ms @100cc with invariant checks, live Sentry capture + alert fire, deploy+rollback demonstration. All artifacts exist in-repo; none has run live. Note: the corpus records staging-plane provisioning as **BLOCKED_UNSAFE / DEPLOYMENT_REQUIRED** (single live DB, Supabase branching Pro-gated); D30 chose the hybrid live-beta path instead.

### 3.3 Absent but deliberately out of scope (do not count as gaps)

Deferred by locked decisions (D3, D8, D16, D24, D28, D29, D33, D34, §G fence): vendor
subscription billing, full B2B (net-terms, credit, org accounts), wallet/financing,
referrals/loyalty, multi-warehouse + lots, promoted-listing auctions, courier/Yango API,
native Android app, airtime/super-app rails, product classes A–E + variants + used-goods
evidence, PWYW + true recurrence + ticket resale, buyer↔vendor messaging, wishlist/
recently-viewed/saved-search surfaces, admin multi-tier RBAC, auto-suspend enforcement,
Zamtel collections, multi-currency. These explain most of the distance between the
"~94% v1 coverage" and "~50% raw-PDF-vision coverage" numbers.

---

## 4. Reconciliation with the corpus's own tracking

- The 2026-07-19 vision audit's **§1 deployment-lag table**: DL-1 ✅ closed (customer at
  tip), DL-2 ✅ vendor confirmed / admin presumed, DL-3 ✅ closed through `0056` but
  **re-opened for `0057`–`0062`**, DL-4 ❌ open, DL-5 ❌ unverifiable, DL-6 ✅ superseded
  (honest invite-only CTA), DL-7 ❌ open, DL-8 superseded by D30.
- The **fail-closed hardening track** (PRs #333–#351, migrations `0057`–`0062`) sits
  largely *outside* the pebble catalog but materially strengthens VM-B/VM-C code
  correctness (escrow-release fail-closed, COD release, internal-token fail-closed,
  payout cross-worker lock, refund gates/resume, single-settle per checkout,
  item-refund remainder release, T1 GMV cap `0060` = **VF-P06/BG-3 done**).
- The 07-18 scorecard deliberately refuses a readiness percentage while P0s are open;
  its area distribution (Ready 0 · Conditional 7 · Blocked 8) is still accurate at HEAD.

## 5. Suggested next moves (highest leverage first)

1. **Close the four cheap repo blockers**: FORCE-RLS migration (§3.1 #1), `backup.json`
   (#2), API-side demo exclusion (#3), the two E2E specs (#4). Each is small and
   unblocks a named gate.
2. **Apply `0057`–`0062` live + pin the API image digest**, then re-run the categories/
   PDP/KYC-route probes — restores "live == repo" truth.
3. **Import + activate the n8n fleet** (VD-P01…P03) — without it, escrow never
   auto-releases and paid tickets never issue, demo or not.
4. **Run the Lenco sandbox money drill** (VB-P01…P06) the moment F9b credentials exist —
   it is the single largest block of unproven documented behaviour.
5. **Start F4 legal counsel now** (longest external lead time; only genuinely open FD).
6. Flip secret-scan/Lighthouse to blocking, add the 3 RLS-matrix rows, authenticate the
   uptime webhook — one small hardening PR.

---

*Prepared by the project-completion assessment session (branch
`claude/project-completion-assessment-pk5v07`). Companion to — and superseding as of
2026-07-20 — the percentages in `docs/production-readiness/2026-07-19/vision-audit/`.
Note PR #353 contains an independent Cursor-authored gap analysis of the same question;
the two were produced separately.*

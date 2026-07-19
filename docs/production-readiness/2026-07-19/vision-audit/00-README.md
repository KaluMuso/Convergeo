# Vision-to-Codebase Audit & Wave Plan — Vergeo5 / Convergeo

**Date:** 2026-07-19 · **Author role:** Vision/build reconciliation + wave planning
**Master tip audited:** `6841b1e` (merge #301) · **Open PRs at audit:** #302 (draft, live-beta wave 1)
**Live project:** Supabase `dpadrlxukcjbewpqympu` (eu-north-1) · Customer prod Vercel `dpl_9uNb…` @ `cc4a824`

> **This audit extends — it does not replace — the 2026-07-18 production-readiness corpus.** That corpus
> (foundation inventories, six document-audits, MR-register, scorecard, release-gates, wave plan, founder
> decision brief) is the current internal opinion and is cited throughout. Where this audit adds value it is:
> (1) reframing the readiness picture as **vision → code → live** by surface; (2) **fresh live verification**
> on 2026-07-19 (Supabase, n8n, Vercel, GitHub) confirming the fingerprint has **not** drifted; (3) a
> **Mountains → Pebbles → Waves** build plan with Cursor-ready prompts. Read the prior corpus first; this
> sits beside it, not on top of it.

## Deliverables (this folder)

| File | Output | Contents |
| ---- | ------ | -------- |
| `00-README.md` | — | Executive reconciliation, method, fresh live fingerprint, reading guide |
| `01-audit-findings.md` | **Output 1** | Gap table by surface (Customer/Vendor/Admin/Backend/Automations) + deployment-lag vs build-gap split |
| `02-open-questions.md` | **Output 2** | Blocking / Non-blocking questions, each with a default assumption to keep planning unblocked |
| `03-waves-and-phases.md` | **Output 3** | 6 Mountains → Pebbles → Waves, each pebble with a self-contained Cursor prompt |

## The one-paragraph verdict

Vergeo5 is **not a demo shell that needs building — it is a substantially built platform that has never been
verified with real money and is not fully deployed.** Measured against the founding vision (five verticals:
products/services/events/supplies/directory + escrow + KYC + Ask-AI + PWA), the **build is ~90% code-complete**
across all three surfaces and a production-grade FastAPI/Supabase backend (274 endpoints, 71 RLS-enabled tables,
correct integer-ngwee money, idempotent Lenco webhooks, zero-sum ledger, gapless ZRA invoice numbering, RRF+vector
search, ~130 test files with money/authz/state-machine failure paths). The dominant gaps are **not missing
features** — they are **(a) deployment drift** (live ≠ repo: frontends behind master, DB 6 migrations behind,
17 of 19 n8n workflows never deployed, API image SHA unknown), **(b) zero live/staging verification of the
money & KYC paths** (0 payments / 0 orders / 0 ledger rows; CODE_COMPLETE but never STAGING_VERIFIED), and
**(c) ops absence** (no Vergeo5 Sentry, no proven backup/restore, non-blocking CI security gates). Twelve founder
decisions (FD-01…FD-12) remain open, mostly gating *open launch*, a few gating *staging* and *real-money beta*.
The correct posture today is exactly the live flags: **`public_launch=false`, no real money** — an invite/demo
browse. The work ahead is a **prove-and-promote** effort, not a green-field build.

## Method (as executed)

1. **Vision extracted** from committed distillations (`docs/plan/research/*`, `00-discovery.md`, `00-decisions.md`
   D1–D29, `01-mountains.md` M01–M17, product/events/i18n gap-audits) + the six `document-audits/*`. Per
   `CLAUDE.md` and the `/vergeo5` protocol, the raw 30 MB concept PDFs were **not** re-parsed — their canonical
   form is these distillations plus the per-document `extracted-facts.json` / `reconciliation-matrix.md`.
2. **Prior readiness corpus read in full** (`2026-07-18/consolidated/*`, `foundation/*`, `staging/production-go-no-go`,
   `2026-07-19/production/*`). Findings are extended, not re-derived; MR-/FD-/G-IDs are reused.
3. **Codebase mapped** by surface (customer/vendor/admin frontends), backend (FastAPI routers, Supabase migrations,
   payments, ZRA, notifications), and automations (`infra/n8n/*.json`), with independent spot-verification
   (WAHA-clean grep, no-float-money grep, invoicing module, i18n file counts, router counts).
4. **Live systems queried directly on 2026-07-19** — Supabase (`list_migrations`, row/flag snapshot), Vergeo5 n8n
   (`search_workflows`), Vercel (`list_deployments`), GitHub (open PRs, `get_me`).
5. **Live-site walk BLOCKED** — this session's egress policy denies `*.vergeo5.com` at the proxy CONNECT stage
   (403 before origin). This is an **environment limitation, not a site finding**. Live customer/vendor/admin
   behaviour is therefore taken from the 2026-07-18 `production-evidence.md` HTTP probes and the 2026-07-19
   Vercel/DB queries, not a fresh unauthenticated walk. Flagged in Output 2 (NB-6) as a verification I could not
   independently repeat.
6. **Open questions compiled** and reconciled to the documented FD-01…FD-12 rather than inventing new interpretations.

## Fresh live fingerprint — 2026-07-19 (my own queries; confirms 07-18 corpus, no drift)

| Dimension | Live value (2026-07-19) | Source | Δ vs 07-18 |
| --------- | ----------------------- | ------ | ---------- |
| Customer prod deploy | `dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW` @ **`cc4a824`** (#296); newer builds (#297/#301/#302) are `target:null` previews, **not promoted** | Vercel `list_deployments` | same drift; `/en\|fr\|zh/categories` **still 500** in prod |
| DB migrations applied | `0001`–`0050` + `20260717100303` (=`0052`). **`0051`,`0053`,`0054`,`0055`,`0056` NOT applied** | Supabase `list_migrations` | unchanged |
| Money/trust rows | payments **0**, orders **0**, ledger_transactions **0**, tickets **0**, kyc_records **0**, payouts **0**, refunds **0**, disputes **0**, invoices **0**, reconciliation_reports **0** | Supabase SQL | unchanged |
| Catalogue | vendors **3**, vendor_listings **134**, products **150**, categories **74**, services **1**, events **0**, jobs **0** | Supabase SQL | unchanged (demo/seed) |
| Feature flags | `public_launch=false`, `zamtel_collections=false`, `paid_tiers=false`, `abandoned_cart=false`, `wallet=false` | Supabase SQL | unchanged |
| n8n active workflows | **2 of 19**: notification-dispatch (1 min), payment-reconciliation crons (webhook-drain 1m / recon 30m / sweeper 10m / daily 05:00) | n8n `search_workflows` | unchanged |
| i18n coverage | `en`/`fr`/`zh` = 17 namespaces (full); `bem`/`nya` = 1 (notifications only) | repo `packages/i18n/messages` | — |
| Sentry (Vergeo5) | none (org `convergeo-w2` has only unrelated `zed*` projects) | 07-18 `production-evidence` (egress-blocked from re-check) | assumed unchanged |
| API image SHA | NOT_AUDITABLE (GHCR auth required; OpenAPI reports `0.1.0`) | 07-18 evidence | unchanged |

## Three-lens reconciliation (the reframing this audit adds)

The 07-18 scorecard rates every surface **Conditional/Blocked**. That is correct for *real-money launch*, but it
conflates three very different lenses. Separating them is the point of this audit:

| Lens | Question | State | Where the work is |
| ---- | -------- | ----- | ----------------- |
| **BUILD** (vision → code) | Is the feature written? | **~90% complete.** Only M17 video feed unbuilt (post-launch by design). Small real gaps: admin generic user-mgmt UI, Bemba/Nyanja translations (stubs), a few OUT-by-decision product-model items. | Output 1 §Build gaps · Mountain VM-F |
| **DEPLOY** (code → live) | Is the code running in prod? | **Drifted.** Frontends behind master; DB 6 migrations behind; 17/19 workflows off; API SHA unknown. | Output 1 §Deployment lag · Mountain VM-A |
| **VERIFY** (live → proven) | Has it been exercised & observed? | **Near-zero for money/trust.** 0 rows everywhere; CODE_COMPLETE ≠ STAGING_VERIFIED; no Sentry; no backup/restore drill. | Output 1 §Backend/Automations · Mountains VM-B/VM-C/VM-D/VM-E |

## Strategy pivots the task brief should be aware of (task assumptions vs locked reality)

The brief lists "non-negotiables" that have **documented pivots**. None are defects — all are locked decisions —
but planning must use the locked reality, cited:

- **Payments = Lenco only**, not direct MTN/Airtel/Zamtel telco APIs and not DPO (D11). **Zamtel collections OFF**
  (`zamtel_collections=false`, payout-only pending F9a). Card = Lenco hosted widget (no PCI).
- **Languages = EN at launch + i18n scaffolding → Bemba/Nyanja → French → Tonga/Lozi** (D27). The brief's
  "Bemba/Nyanja/Tonga/Lozi" mis-orders this (Tonga/Lozi are 4th; **French is 3rd and already fully translated**).
  Live also ships **`zh` (Chinese)** as a full-fidelity QA/pseudo locale — routable but not a stated market language
  (see Output 2, NB-1).
- **WhatsApp = official Cloud API only; WAHA forbidden even in dev** (D15). The brief's "WAHA → official migration
  path" is a *decided* migration, not a pending one — code is WAHA-clean.
- **Escrow = Lenco-held funds + platform ledger-of-record**, never platform-pooled, for NPS-Act-2026 compliance (D14).
- **v1 ships all five verticals thin** (D2/D29), not a products-only MVP.
- **Admin RBAC = single `admin` role** live (concept wanted superadmin+moderator) — **FD-02 open**.
- **ZRA Smart Invoice = ADDED** (absent from all concept PDFs; surfaced by 2026-07 compliance research). Launch under
  Turnover Tax 5%, **VAT flag OFF**, VSDC fiscalisation a deliberate stub; sequential invoice numbering implemented.
- **NEW in-flight direction (PR #302, 2026-07-19):** a pivot toward a **controlled customer live-beta with staging
  provisioning PAUSED**, superseding the staging-first sequencing in `implementation-wave-plan.md`. Not yet on
  master. Flagged as blocking question **B-7**.

_Reading guide: start at `01-audit-findings.md` for the gap table, `02-open-questions.md` before committing to any
wave, `03-waves-and-phases.md` for the build plan._

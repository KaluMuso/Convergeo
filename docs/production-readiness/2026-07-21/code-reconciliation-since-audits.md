# Code reconciliation — audit corpus vs master (2026-07-21)

**Master tip at write:** `d7891b8` (#400) · **Mode:** GATED · **Purpose:** the
2026-07-18…21 production-readiness corpus (go/no-go, vision audit, implementation
board, live-beta backlog, CCP programme) was written **before** the code-completion
blitz landed. Read literally, those docs overstate the open **code** backlog. This
note re-baselines the _repo-closable_ items against current master so no one
re-dispatches finished work. It changes **no** gate verdicts: the launch-critical
gap is still **DEPLOY + VERIFY + OPS + F4 counsel**, not build.

> This is a code-status reconciliation only. For deploy/verify/money truth use the
> 2026-07-20 `go-no-go-report.md` + `current-implementation-board.md`; for the live
> API/ops fingerprint use `2026-07-21/api-recovery-and-ops.md`.

## 1. Closed since the audits (verified in code on `d7891b8`)

| Audit item(s)                                                | Verdict                             | Evidence                                                                                                                        |
| ------------------------------------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| CCP-01 zh de-route (RC-10 / NB-1)                            | **DONE**                            | `a03447a`; public switcher omits `zh`, `messages/zh` retained                                                                   |
| CCP-02 native-review workflow                                | **DONE** (process doc)              | `b71f202` `PHASE1_NATIVE_REVIEW.md`                                                                                             |
| CCP-03a/b/e bem·nya namespaces                               | **PARTIAL → 13/17**                 | `6ad015a`,`12c27ad`,`9661ce7`; missing `admin`,`ai`,`legal`,`vendor`                                                            |
| CCP-04 orphan UI (RC-09)                                     | **DONE — mounted**                  | `29a1855`; `report-review`→`reviews-section.tsx:156`→PDP; `accept-flow`/`complete-confirm`→`account/jobs/[id]/page.tsx:226,288` |
| CCP-06 vendor dark tokens (RC-12)                            | **DONE**                            | `bc8fe6c`                                                                                                                       |
| CCP-07a CSP nonce report-only (RC-13 pt.1)                   | **DONE**                            | `e0e4e79`; per-request nonce in all 3 middlewares, `Content-Security-Policy-Report-Only`                                        |
| CCP-08 docs drift (SD-06…09)                                 | **DONE**                            | `abcb131`; `00-status.md` header, F7=6 across checklist/decisions/SOURCES                                                       |
| Demo **product** exclusion (RC-04 / FD-04 / G11)             | **DONE for listing/product/vendor** | `#368`; `services/listings/demo.py` image-marker filter                                                                         |
| FORCE RLS launch tables (RC-01 / G0 / D32)                   | **CODE DONE — apply pending**       | `#367` `0064_force_rls_launch_tables.sql` covers all 3 tables; **not yet applied live**                                         |
| Organiser T1 GMV cap (BG-3 / events BL-004)                  | **DONE**                            | `0060`; `events/gmv_cap.py` enforced pre-claim in `tickets/purchase.py:462`, tested                                             |
| Migration `0063` reconcile + `source_key`→`0065` (RC-02)     | **DONE**                            | `390f906` / `#387`                                                                                                              |
| DB backup workflow (BG-5 / MR-W04 / RC-03)                   | **CODE DONE — drill pending**       | `bbe964e` `infra/n8n/backup.json` + dump/watchdog scripts                                                                       |
| CI gate enforcement + ops webhook auth (X-3 / RC-06 / RC-08) | **DONE**                            | `200c8a3`; secret-scan/LHCI/deps-audit/schema-RLS/i18n-completeness blocking; `uptime-alert` authenticated                      |
| Checkout-honesty + critical-path E2E (RC-05 / G4 code)       | **DONE (code)**                     | `36c3e44`                                                                                                                       |
| OG edge bundle >1 MB (promote blocker)                       | **DONE**                            | `2ac18e7`; `opengraph-image.tsx` edge, no i18n/ui/fonts/images                                                                  |
| Conversion fail-closed API base (LB-P0-02/03)                | **DONE for `(shop)`**               | all discovery/checkout clients use `lib/api-base-url.resolveApiBaseUrl`                                                         |
| a11y landmarks/contrast/touch (RC live-beta)                 | **DONE**                            | `b44d5a9`                                                                                                                       |

## 2. Residual repo-closable code backlog (genuinely open)

| ID          | Item                                                               | Why still open                                                                                                                                                                                                                                                                                                                                                                                                | Suggested owner                                                        |
| ----------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **R-1**     | **Demo `service`/`event` discovery leak**                          | `drop_demo_listing_hits` (`services/listings/demo.py:125`) only filters `entity_kind ∈ {listing,product,vendor}` and keys on Cloudinary `demo/` image ids; **services/events are indexed** (`search/__init__.py:217`) but never filtered, and `routers/services_listings.py` has no demo filter. Live probe (07-21) still surfaced `…(demo)` service. Needs a demo **marker** for service/event rows + tests. | Cursor (marker decision below)                                         |
| **R-2**     | **API-base fail-closed sweep (residual)**                          | `(shop)` is fail-closed, but ~22 sites in `apps/customer/app/[locale]/account/**`, `beta`, and **`lib/seo/sitemap-events.ts`** inlined `?? "http://localhost:8000"` (sitemap = public SEO leak if env unset). Vendor/admin verified already clean.                                                                                                                                                            | **DONE — PR #450** (localhost now only in the helper; + sitemap tests) |
| **R-3**     | **bem/nya `admin`/`ai`/`legal`/`vendor` (RC-11 / CCP-03c/d/f)**    | 13/17; `legal`+money strings require human native review (D27), `admin`/`vendor`/`ai` are internal surfaces — **founder scope call** before dispatch.                                                                                                                                                                                                                                                         | Founder decision → Cursor                                              |
| **R-4**     | **CSP enforce (RC-13 / CCP-07b)**                                  | report-only wired; promotion to enforced `script-src` needs a clean RO-violation evidence window (checkout Lenco widget / vendor QR / admin) — phased, do not enforce-first.                                                                                                                                                                                                                                  | Cursor after RO window                                                 |
| ~~**R-5**~~ | ~~RLS test-matrix rows (RC-07)~~                                   | **Correction — already complete on master.** `event_categories`, `product_relations`, `service_reviews`, `embedding_jobs`, `reconciliation_reports` all carry full six-persona `EXPECTATIONS` entries in `tests/rls/test_matrix.py`; the 07-19 audit flag was stale.                                                                                                                                          | — (no action)                                                          |
| **R-6**     | **(optional) `commission_snapshot` immutability trigger (PAY-07)** | defence-in-depth on release math; not gating.                                                                                                                                                                                                                                                                                                                                                                 | Backlog                                                                |

## 3. What this reconciliation does NOT change

- **DEPLOY**: frontends behind master SHA; **migrations `0064`–`0066` not applied live** (FORCE RLS still off on ticket-tier tables live — the top _safety_ gap); API digest unpinned.
- **VERIFY**: money/KYC drills (S1–S6), false-success proof against live/sandbox.
- **OPS**: money-moving n8n unpublished; Sentry projects; restore/rollback/load drills.
- **FOUNDER/LEGAL**: **F4 counsel (only genuinely-open FD)**, F2 PACRA/TPIN, F5 WhatsApp templates, F9b Lenco creds.

Any single open P0 money/security/legal gate keeps real-money at **NO_GO** regardless
of the code progress recorded above.

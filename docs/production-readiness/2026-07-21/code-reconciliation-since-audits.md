# Code reconciliation — audit corpus vs master (2026-07-21)

**Master tip at write:** `dc6e899` (#480) · **Mode:** GATED · **Purpose:** the
2026-07-18…21 production-readiness corpus (go/no-go, vision audit, implementation
board, live-beta backlog, CCP programme) was written **before** the code-completion
blitz landed. Read literally, those docs overstate the open **code** backlog. This
note re-baselines the _repo-closable_ items against current master so no one
re-dispatches finished work. It changes **no** gate verdicts: the launch-critical
gap is still **DEPLOY + VERIFY + OPS + F4 counsel**, not build.

> This is a code-status reconciliation only. For deploy/verify/money truth use the
> 2026-07-20 `go-no-go-report.md` + `current-implementation-board.md`; for the live
> API/ops fingerprint use `2026-07-21/api-recovery-and-ops.md` and
> `post-415-deploy-and-search.md`.

## 1. Closed since the audits (verified in code on `dc6e899`)

| Audit item(s)                                                | Verdict                             | Evidence                                                                                                                      |
| ------------------------------------------------------------ | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| CCP-01 zh de-route (RC-10 / NB-1)                            | **DONE**                            | `a03447a`; public switcher omits `zh`, `messages/zh` retained                                                                 |
| CCP-02 native-review workflow                                | **DONE** (process doc)              | `b71f202` `PHASE1_NATIVE_REVIEW.md`                                                                                           |
| CCP-03a/b/e bem·nya namespaces                               | **PARTIAL → 15/18**                 | `#467` `ai`, `#476` `vendor`; missing `admin`,`legal` (founder-held D27)                                                      |
| CCP-04 orphan UI (RC-09)                                     | **DONE — mounted**                  | `29a1855`; `report-review`→PDP; `accept-flow`/`complete-confirm`→`account/jobs/[id]`; `claim-banner`→`account/tickets`        |
| CCP-06 vendor dark tokens (RC-12)                            | **DONE**                            | `bc8fe6c`                                                                                                                     |
| CCP-07a CSP nonce report-only (RC-13 pt.1)                   | **DONE**                            | `e0e4e79`; per-request nonce in all 3 middlewares, `Content-Security-Policy-Report-Only`                                      |
| CCP-07b CSP report sink (RC-13 pt.2 PR1)                     | **DONE**                            | `#479`; `POST /api/csp-report` + `report-uri`/`report-to` in all 3 apps; evidence runbook in `docs/ops/security-headers.md`   |
| CCP-08 docs drift (SD-06…09)                                 | **DONE**                            | `abcb131`; `00-status.md` header, F7=6 across checklist/decisions/SOURCES                                                     |
| Demo exclusion (RC-04 / FD-04 / G11)                         | **CODE DONE — live verify pending** | `#368` products/listings/vendors; service/event filter in `demo.py` + `services_listings.py`; needs API redeploy + live probe |
| FORCE RLS launch tables (RC-01 / G0 / D32)                   | **CODE DONE — apply pending**       | `#367` `0064_force_rls_launch_tables.sql`; **not yet applied live**                                                           |
| Organiser T1 GMV cap (BG-3 / events BL-004)                  | **DONE**                            | `0060`; `events/gmv_cap.py` enforced pre-claim in `tickets/purchase.py:462`, tested                                           |
| Migration `0063` reconcile + `source_key`→`0065` (RC-02)     | **DONE**                            | `390f906` / `#387`                                                                                                            |
| DB backup workflow (BG-5 / MR-W04 / RC-03)                   | **CODE DONE — drill pending**       | `bbe964e` `infra/n8n/backup.json` + dump/watchdog scripts                                                                     |
| CI gate enforcement + ops webhook auth (X-3 / RC-06 / RC-08) | **DONE**                            | `200c8a3`; secret-scan/LHCI/deps-audit/schema-RLS/i18n-completeness blocking; `uptime-alert` authenticated                    |
| Checkout-honesty + critical-path E2E (RC-05 / G4 code)       | **DONE (code)**                     | `36c3e44`                                                                                                                     |
| OG edge bundle >1 MB (promote blocker)                       | **DONE**                            | `2ac18e7`; `opengraph-image.tsx` edge, no i18n/ui/fonts/images                                                                |
| Conversion fail-closed API base (LB-P0-02/03)                | **DONE**                            | `#462` / #450; account, beta, sitemap, `(shop)` all use `lib/api-base-url` — localhost only in helper + tests                 |
| a11y landmarks/contrast/touch (RC live-beta)                 | **DONE**                            | `b44d5a9`                                                                                                                     |
| Event cancel/reschedule notifications (FIX-K2)               | **DONE**                            | `#462` / #457; `organiser_events.py` + SMS/WhatsApp templates + tests                                                         |
| Nav i18n consolidation + dedup                               | **DONE**                            | `#456`, `#463`; `nav.shop.*` canonical; `catalog.home.nav` removed                                                            |

## 2. Residual repo-closable code backlog (genuinely open)

| ID          | Item                                                    | Why still open                                                                                                                                                                             | Suggested owner                   |
| ----------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------- |
| **R-1**     | **Demo `service`/`event` discovery leak**               | **Code done** (`demo.py` service/event filters + tests); live probe still shows demo service until API redeploy. See `post-415-deploy-and-search.md`.                                      | Founder/Ops redeploy → live probe |
| ~~**R-2**~~ | ~~API-base fail-closed sweep~~                          | **DONE — #462** (account, beta, sitemap; localhost only in helper)                                                                                                                         | —                                 |
| **R-3**     | **bem/nya `admin`/`legal` (RC-11 / CCP-03c/d)**         | **15/18**; `ai` + `vendor` landed (#467, #476); `legal`+money strings require human native review (D27); `admin` founder-held.                                                             | Founder decision → Cursor         |
| **R-4**     | **CSP enforce (RC-13 / CCP-07b PR2)**                   | PR1 report sink **done** (#479); promotion to enforced `script-src` needs a clean RO-violation evidence window (checkout Lenco widget / vendor QR / admin) — phased, do not enforce-first. | Cursor after RO window            |
| ~~**R-5**~~ | ~~RLS test-matrix rows (RC-07)~~                        | **Correction — already complete on master.**                                                                                                                                               | — (no action)                     |
| ~~**R-6**~~ | ~~`commission_snapshot` immutability trigger (PAY-07)~~ | **DONE — `0069_orders_commission_snapshot_immutable.sql`** + RLS trigger test; defence-in-depth on release math.                                                                           | —                                 |

## 3. What this reconciliation does NOT change

- **DEPLOY**: API `git_sha=unknown` until redeploy after #480; frontends may trail tip; **migrations `0064`–`0069` not applied live** (FORCE RLS still off on ticket-tier tables live — the top _safety_ gap).
- **VERIFY**: money/KYC drills (S1–S6), false-success proof against live/sandbox; demo-exclusion + search `degraded=false` probes after API redeploy + embeddings drain.
- **OPS**: money-moving n8n unpublished; Sentry projects; restore/rollback/load drills; CSP evidence window not yet run.
- **FOUNDER/LEGAL**: **F4 counsel (only genuinely-open FD)**, F2 PACRA/TPIN, F5 WhatsApp templates, F9b Lenco creds.

Any single open P0 money/security/legal gate keeps real-money at **NO_GO** regardless
of the code progress recorded above.

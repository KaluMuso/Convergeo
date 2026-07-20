# Vergeo5 / Convergeo — Gap analysis vs GitHub docs expectations

**Date:** 2026-07-20  
**Scope:** `origin/master` (tip includes #350 checkout single-settle + #351 remainder release; #352 source_key uniqueness pending)  
**Doc corpora assessed:**

| Corpus               | Path                         | Role                                                 |
| -------------------- | ---------------------------- | ---------------------------------------------------- |
| Concept              | `docs/concept/`              | Product vision PDFs (use distillations, not re-read) |
| Designs              | `docs/designs/`              | UI fidelity + token selection                        |
| Ops                  | `docs/ops/`                  | Lenco, WhatsApp, CI, DR, n8n                         |
| Plan                 | `docs/plan/`                 | Decisions, mountains, status, launch checklist       |
| Production-readiness | `docs/production-readiness/` | Gates, scorecards, 07-18/07-19 vision audits         |

**Companions:** `docs/plan/00-status.md`, `docs/plan/launch-checklist.md`, `docs/production-readiness/2026-07-19/vision-audit/01-audit-findings.md`.

> **CCP-08 supersession note:** This remains a point-in-time gap analysis. The
> `docs/plan/00-status.md` header no longer claims founder gates are the only
> remaining launch work; use the 2026-07-20 go/no-go report and implementation board
> for current deploy/verify/ops/money-drill truth.

---

## Executive verdict

| Lens                                            | Completion | Confidence                                |
| ----------------------------------------------- | ---------- | ----------------------------------------- |
| **Code / build vs M01–M16 vision**              | **~86%**   | High                                      |
| **Production-ready per GOAL + release-gates**   | **~42%**   | Medium-high                               |
| **Live deployed + verified (browse-safe beta)** | **~48%**   | Medium                                    |
| **Real-money launch ready**                     | **~25%**   | High (hard fail on unverified money path) |

**One-line summary:** The marketplace is largely **built** (141 pebbles / 16 mountains on master). It is **not** a representation of “production-ready” expectations in the readiness docs. The dominant gap is **DEPLOY + VERIFY + OPS + founder/legal gates**, not missing product surfaces. Safe posture today: controlled invite/demo browse with `public_launch=false`. Unsafe: open launch or prepaid customer funds.

---

## How percentages are scored

Each area score is the **minimum** of three lenses (so understatement is intentional):

1. **BUILD** — code exists on `master` matching locked decisions
2. **DEPLOY** — running on live hosts with expected SHAs / migrations / workflows
3. **VERIFY** — exercised with evidence (sandbox drills, staging E2E, live rows)

`CODE_COMPLETE` without `STAGING_VERIFIED` caps an area at ~40–55%.

---

## A) Overall vs each doc corpus

| Corpus                                            | What “done” means                                                                                                     | %                                                   | What’s missing                                                                                            |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Concept** (`docs/concept` → plan distillations) | Multi-vendor ZM commerce: products, services/RFQ, events/tickets, supplies B2B-lite, directory, MoMo escrow, WhatsApp | **78%** product vision in code; **35%** proven live | Live money path; real vendor liquidity; vernacular i18n; M17 video feed (deferred)                        |
| **Designs** (`docs/designs`)                      | Tokens + fidelity to SELECTION; missing HTML sources imported                                                         | **72%**                                             | 6 HTML sources still missing (F7); vendor default-palette leftovers; some desktop polish debt             |
| **Ops** (`docs/ops`)                              | Lenco/WhatsApp/n8n/DR/CI operable                                                                                     | **40%**                                             | Creds/templates (F5/F9); 17/19 n8n workflows dormant; backup restore undemonstrated; API digest unaudited |
| **Plan** (`docs/plan`)                            | Mountains shipped; launch-checklist gates checked                                                                     | **55%**                                             | Status header now points to go/no-go/board; checklist Section 0 unchecked; staging proofs open            |
| **Production-readiness**                          | S0–S7 / G-gates PASS; scorecard green                                                                                 | **22%**                                             | Nearly all S*/G* FAIL or Conditional; money tables still empty                                            |

---

## B) Per-area scorecard (master vs docs)

| Area                         | %      | BUILD                                                               | DEPLOY                                  | VERIFY                               | Missing (concrete)                                                                              |
| ---------------------------- | ------ | ------------------------------------------------------------------- | --------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Customer product surface     | **75** | Strong (~51 locales routes)                                         | Partial (prod SHA lag historically)     | Weak (demo data)                     | Promote latest customer SHA; prove categories/CTA/env; exclude demo catalogue for public launch |
| Vendor product surface       | **70** | Strong (~31 routes)                                                 | Partial                                 | Weak                                 | Live KYC drill; vendor.domain wiring; offline scanner proof                                     |
| Admin product surface        | **65** | Strong (~21 routes)                                                 | Access-gated                            | Unaudited deep UI                    | Access-session probe pack; business/KYC queues with real rows                                   |
| Money / escrow / payments    | **38** | Strong (adapter, ledger, gates, COD, refunds-as-payouts; #350/#351) | Migrations `0057–0062` may lag live     | **Empty** (`payments=0`, `ledger=0`) | S1–S3 sandbox MoMo/card→ledger→release→payout; F9a/F9b                                          |
| Auth / KYC                   | **55** | Strong                                                              | `0051`/`0056` improving live            | `kyc_records=0`                      | S5 submit→approve→caps; F2 PACRA/TPIN                                                           |
| Catalog / listings           | **80** | Strong                                                              | Seeded demo                             | Demo-only                            | Real listings; apply remaining migrations; public_launch posture                                |
| Orders / fulfillment         | **40** | Strong                                                              | Release n8n **off**                     | `orders=0`                           | Activate order/release jobs; staging E2E lifecycle                                              |
| Returns / refunds / disputes | **42** | Strong (+#351 remainder; #352 pending)                              | Unapplied uniqueness on live until #352 | Unexercised                          | Merge #352; live return matrix (MR-B03)                                                         |
| Events / tickets             | **45** | Strong (+ Wave A)                                                   | Ticket/event-release workflows **off**  | `events=0`, `tickets=0`              | Activate tickets-issue/release; paid-ticket exactly-once proof                                  |
| Services / RFQ               | **55** | Strong                                                              | Thin seed                               | `jobs=0`                             | Liquidity + job→escrow→review E2E                                                               |
| Supplies / B2B-lite          | **65** | Strong (D28)                                                        | Gate unexercised                        | `business_buyers` unverified         | Verified buyer path end-to-end                                                                  |
| Search / Ask Vergeo          | **70** | Strong                                                              | Search previously `degraded`            | Quotas/grounding live-unproven       | Embeddings cron; live grounding with real key                                                   |
| Notifications                | **45** | Strong (outbox chain)                                               | **2/19** n8n active                     | No proven WA send                    | F5 Meta templates; activate remaining workflows                                                 |
| Design system / UI polish    | **75** | Strong (`packages/ui`)                                              | —                                       | —                                    | F7 missing HTMLs; vendor palette cleanup                                                        |
| i18n (EN→bem/nya→fr)         | **55** | EN/FR/zh full                                                       | —                                       | bem/nya thin (~8/17 ns)              | Human-reviewed vernacular for checkout/legal                                                    |
| Infra / CI / security        | **50** | CI present                                                          | Secret-scan/LH advisory                 | FORCE RLS gaps                       | FORCE RLS on ticket tiers + `product_relations`; Sentry projects; branch-protection no-bypass   |
| Production-readiness gates   | **20** | Docs/templates exist                                                | —                                       | Almost all FAIL                      | S0–S7, G3–G7, F4 counsel, go/no-go sign-off                                                     |

---

## C) Mountains M01–M16 (plan expectation vs reality)

| Mountain               | Plan expectation           | Code on master                     | Live / verified                                             |
| ---------------------- | -------------------------- | ---------------------------------- | ----------------------------------------------------------- |
| M01 Foundations        | Monorepo, CI, deploy       | Shipped                            | Staging plane incomplete; API digest unaudited              |
| M02 Design system      | Tokens + kit               | Shipped                            | F7 HTML gaps                                                |
| M03 Data / RLS         | Every table FORCE RLS      | Mostly                             | Live migration lag; some tables `relforcerowsecurity=false` |
| M04 Auth               | Phone/email/Google + roles | Shipped                            | Full phone→order unproven                                   |
| M05 Catalog / search   | PLP/PDP/compare/RRF        | Shipped                            | Demo catalogue; search health                               |
| M06 Ask Vergeo         | RAG + quotas               | Shipped                            | Unexercised live                                            |
| M07 Cart / checkout    | MoMo/card/COD              | Shipped                            | 0 checkouts; false-success unproven                         |
| M08 Payments / escrow  | Lenco + ledger + release   | Shipped (+ recent money hardening) | **0 money rows; S1–S3 FAIL**                                |
| M09 Orders             | State machine + pickup     | Shipped                            | 0 orders; release cron off                                  |
| M10 Events / tickets   | QR wallet + escrow timing  | Shipped (+ Wave A)                 | 0 events; issue/release off                                 |
| M11 Services / RFQ     | Jobs + escrow              | Shipped                            | Thin seed                                                   |
| M12 Vendor             | KYC + listings + payouts   | Shipped                            | 0 KYC                                                       |
| M13 Admin              | Queues + Access            | Shipped                            | Deep UI unaudited                                           |
| M14 Notifications      | WA→SMS→email outbox        | Shipped                            | 2/19 workflows live                                         |
| M15 Trust / compliance | Invoices, DPA, DR, OWASP   | Mostly                             | DR/Sentry/FORCE RLS/F4 open; VSDC stub intentional          |
| M16 Launch QA          | E2E, load, beta, checklist | Artifacts shipped                  | Staging proofs unchecked                                    |
| M17 Video feed         | Post-launch                | **Absent**                         | Deferred by design                                          |

---

## D) Top 12 gaps blocking “matches production-readiness docs”

1. **Sandbox money path unverified (S1–S3 / G3)** — code + tests yes; live `payments=0`, `ledger_transactions=0`.
2. **False-success / checkout honesty unproven (S6 / G4)** — pending ≠ paid not proven on staging E2E.
3. **Escrow/ticket automations not live (G5)** — n8n only has notification-dispatch + payment-recon; release/tickets/event-release absent.
4. **Backup + restore undemonstrated (G7)** — no proven ≤30-min restore.
5. **Legal counsel F4 / NPS Act escrow (G13)** — hard real-money gate, unchecked.
6. **Lenco + WhatsApp founder creds (F9b / F5)** — adapters ready; rails/templates not proven.
7. **FORCE RLS (D32 / G0)** — still false on ticket price tiers / instances / `product_relations`.
8. **KYC live drill (S5)** — integrity migrations improving; `kyc_records=0`.
9. **Observability (G6)** — no Vergeo5 Sentry projects / uptime evidence.
10. **Deploy truth + migration lag** — promote apps to intended SHAs; apply master migrations through latest (`0057+` / `0062`; `0063` when #352 merges); pin API GHCR digest.
11. **Vernacular i18n** — bem/nya incomplete vs D27 launch expectation.
12. **Design source completeness (F7)** — 6 HTML designs still missing from `docs/designs`.

---

## E) What _is_ already a good representation of the docs

- Locked stack (D18–D24): FastAPI + Next 15 monorepo + Supabase + Lenco seam + Cloudinary + next-intl scaffolding.
- Integer **ngwee** money discipline + ledger templates + webhook idempotency patterns.
- Full customer / vendor / admin surface area for products, services, events, supplies gate, directory.
- Escrow trust UX scaffolding; COD cap; refunds-as-payouts; recent concurrency/money gates (#350/#351).
- CI corpus (js/python/db/rls/security/money-trigger jobs).
- Ops contracts distilled (`lenco-api-distilled.md`, WhatsApp setup) — bring-up is env, not missing docs.
- Production-readiness **documentation** itself is mature (gates, scorecards, vision audit) — the platform has not yet **passed** those gates.

---

## F) Doc debt (status files that overstate readiness)

| Doc                                         | Issue                                                                                                                                                       |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/plan/00-status.md`                    | Header still “BUILD-OUT COMPLETE / remaining = founder gates”; underplays deploy/verify/ops and ongoing money hardening; migration-lag notes stale vs live. |
| Vision audit `01-audit-findings.md` (07-19) | Partially stale on which migrations are applied; organiser GMV now coded (`0060`); bem/nya better than “notifications only”.                                |
| `launch-checklist.md`                       | Mountain criteria left `[ ]` by design until staging proofs — easy to misread as “nothing built.”                                                           |
| `AGENTS.md`                                 | Still describes flat i18n keys as general state; many namespaces nested.                                                                                    |
| `SOURCES.md`                                | Still accurate: **6 HTML files missing**.                                                                                                                   |

---

## G) Recommended next program (not calendar estimates)

Ordered by gate docs, not feature ambition:

1. **Prove money** — S1–S3 sandbox; record evidence in production-readiness folders.
2. **Activate automations** — release-job, tickets-issue/release, event-release, order-jobs in n8n.
3. **Close deploy truth** — apply migrations through tip; promote Vercel SHAs; pin API image.
4. **FORCE RLS + Sentry + backup drill.**
5. **Founder gates** — F4, F5, F9 (and F2 for vendor onboarding realism).
6. **Merge remaining money PRs** — #352 `source_key` uniqueness (CI fix pushed 2026-07-20).
7. Only then flip `public_launch` / invite capacity.

---

## H) Bottom line for the founder

| Question                                                              | Answer                                                        |
| --------------------------------------------------------------------- | ------------------------------------------------------------- |
| Does master look like the **product** in concept/plan?                | **Mostly yes (~78–86% code).**                                |
| Does master look like the **production-ready bar** in readiness docs? | **No (~42% overall; ~25% real-money).**                       |
| What’s the nature of the gap?                                         | **Prove-and-promote**, not another 141-pebble build.          |
| What must stay closed?                                                | Any open P0 money/security/legal gate = not production-ready. |

_Confidence note: live row counts and n8n workflow counts reflect the 2026-07-19 vision-audit fingerprint plus 2026-07-20 code review; re-probe Supabase/n8n before a go/no-go meeting._

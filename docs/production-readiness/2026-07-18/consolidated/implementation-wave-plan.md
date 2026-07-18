# Implementation Wave Plan — Vergeo5 / Convergeo Production Readiness

**Date:** 2026-07-18  
**Master tip baseline:** `d5c2134`  
**Mode:** Planning register — no production changes from this document alone  
**Supersedes for sequencing:** `24-hour-workboard.md` (keep as historical; use this plan going forward)

**Goal:** Move code-complete money/trust/panel work through **staging-verified** then **production-verified** evidence without inventing founder decisions or seeding fake marketplace scale.

**Overall posture:** **NO-GO** real money / open launch until Waves A–E clear the gates in `release-gates.md`.

---

## Principles

1. **Evidence ladder:** Code-complete ≠ staging-verified ≠ production-verified.
2. **Do not re-list merged work as missing:** #274, #289–#291, #293, #294 are on master.
3. **Exclusive ownership per wave** — one branch/PR theme; avoid cross-panel file collisions.
4. **Founder decisions** (`source-conflicts-and-decisions.md`) are hard stops — agents surface IDs, do not invent.
5. **Additive migrations only;** backup before apply; no ad-hoc production SQL on money/KYC tables.
6. **Prepaid kill-switch stays OFF on production** until Production GO pack is complete.

---

## Already landed (do not rebuild)

| Wave / PR                              | Status      | Remaining                       |
| -------------------------------------- | ----------- | ------------------------------- |
| #274 prepaid `CHARGE_RECEIVED`         | DONE_CODE   | Staging SQL + E2E (Wave A)      |
| #294 release accounting                | DONE_CODE   | Staging release recon (Wave A)  |
| #289 customer honesty routes           | DONE_CODE   | Deploy + probe (Wave C)         |
| #290 admin honesty                     | DONE_CODE   | Deploy + probe (Wave C)         |
| #291 vendor KYC UI honesty             | DONE_CODE   | Deploy + KYC E2E after Wave B   |
| #293 KYC integrity `0056` + API freeze | DONE_CODE   | Apply migrate + repair (Wave B) |
| #292 integration review                | DONE (docs) | Obeyed: FAIL go-live            |

---

## Wave A — Prove money (staging only)

**Objective:** Prove collection → ledger → release accounting with Lenco sandbox. **No production prepaid enablement.**

| Item | Owner          | MR / Gate         | Work                                                                      | Exit criteria                                 |
| ---- | -------------- | ----------------- | ------------------------------------------------------------------------- | --------------------------------------------- |
| A1   | Payments       | MR-B01 / G3       | Sandbox MoMo prepaid → assert `CHARGE_RECEIVED` + escrow legs             | Redacted payment_id + SQL aggregates attached |
| A2   | Payments       | MR-B01 / G3       | Sandbox card prepaid → same                                               | Same                                          |
| A3   | Payments       | MR-O03 / G4       | Abandon + delayed-webhook E2E; UI never false-success                     | CUST-08 E2E log PASS                          |
| A4   | Ops + Payments | MR-W01 / G5       | Activate `release-job` against **staging** API; dry-run then real release | Execution ID; no double-release               |
| A5   | Payments       | MR-B01b / G3      | After deliver/event phase: capture-before-release; escrow nets 0          | Recon summary matches #294 invariants         |
| A6   | Ops            | MR-W05            | Force recon mismatch; confirm alert                                       | Alert evidence                                |
| A7   | Founder        | FD-PREPAID-ENABLE | Confirm production kill-switch remains OFF                                | Flag screenshot / env note                    |

**Branch suggestion:** `cursor/staging-money-proof-<suffix>`  
**Depends on:** F9b sandbox credentials (founder)  
**Does not include:** Production prepaid ON, live payouts, production n8n activate without staging proof

**Wave A PASS ⇒ Staging money drills GO (SG-A…SG-C).** Still NO-GO production real money.

---

## Wave B — KYC integrity rollout

**Objective:** Apply `0056`, prove capability freeze, controlled orphan handling.

| Item | Owner     | MR / Gate       | Work                                                                            | Exit criteria                                          |
| ---- | --------- | --------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------ |
| B0   | Ops       | G7              | Backup before migrate                                                           | Dated artifact                                         |
| B1   | DB        | MR-S01 / G12    | Apply `0056_kyc_integrity.sql` to staging                                       | `schema_migrations` contains 0056                      |
| B2   | API/Admin | MR-D02 / ADM-03 | Staging: submit→under_review→approve; orphan report                             | Lifecycle + report JSON                                |
| B3   | Vendor    | VEND-02         | Staging vendor cannot use bare tier privileges                                  | Capabilities false when orphaned                       |
| B4   | DB        | DB-07           | Controlled repair plan for staging orphans (if any)                             | Reviewed plan executed; no raw privilege UPDATE        |
| B5   | DB        | MR-S01          | Production apply `0056` after staging PASS + backup                             | Prod migration head includes 0056                      |
| B6   | DB/Admin  | MR-D02          | Production orphan report; controlled repair **or** explicit freeze-only posture | Zero privilege from bare tier; repair artifact if used |

**Branch suggestion:** ops/runbook execution (may be no app PR) + `cursor/kyc-rollout-evidence-<suffix>` for evidence docs only  
**Honour:** #293 “DO NOT APPLY FROM PR alone” — staging → production order

**Wave B PASS ⇒ G12 staging PASS; production G12 only after B5/B6.**

---

## Wave C — Deploy panel tip + seller CTA

**Objective:** Production frontends match master tip; seller acquisition unblocked; SW/routes verified.

| Item | Owner        | MR / Gate               | Work                                                | Exit criteria                        |
| ---- | ------------ | ----------------------- | --------------------------------------------------- | ------------------------------------ |
| C1   | Founder      | FD-SELLER-CTA-ENV / G10 | Set `NEXT_PUBLIC_VENDOR_APP_URL` on customer        | Env present (names only in evidence) |
| C2   | Ops          | G1 / G9                 | Deploy customer/vendor/admin to tip ≥ `d5c2134`     | Vercel SHAs recorded                 |
| C3   | Customer     | CUST-03/04/07/10        | Re-probe categories/compare/calendar/copy           | HTTP 200; no dead nav; copy clean    |
| C4   | Customer     | CUST-05 / MR-C04        | Probe SW URL                                        | SW 200                               |
| C5   | Customer     | CUST-01                 | Probe sell CTA                                      | Vendor prod href; not unavailable    |
| C6   | Admin/Vendor | ADM-06/07, VEND-08      | Spot-check empty-state honesty live                 | No fake GMV tiles                    |
| C7   | Ops          | MR-B10 / G9             | Deploy API image with #274/#293/#294; record digest | Digest in release ledger             |

**Branch suggestion:** none required if tip already green — evidence PR `cursor/panel-deploy-evidence-<suffix>`  
**Depends on:** Wave B for KYC admin/vendor production claims; C7 may parallel A after code freeze

---

## Wave D — Ops hardening (workflows, migrations, monitoring, DR)

**Objective:** Clear remaining P0/P1 ops blockers that are not founder-legal.

| Item | Owner    | MR / Gate   | Work                                                               | Exit criteria                                     |
| ---- | -------- | ----------- | ------------------------------------------------------------------ | ------------------------------------------------- |
| D1   | Ops      | MR-W01 / G5 | Activate production `release-job` **only after** Wave A PASS       | Active + sandbox-equivalent prod drill under beta |
| D2   | Ops      | MR-W02 / G5 | Activate `tickets-issue` (+ event-release if selling paid tickets) | Exactly-once issue proof                          |
| D3   | DB       | MR-S01      | Reconcile `0051`, `0053`–`0055` (+ skew 0052) after backup         | Migration head matches agreed target              |
| D4   | Auth     | MR-S02 / G0 | Enable role hook **or** signed manual-grant exception              | Decision + evidence                               |
| D5   | Security | MR-R01 / G0 | FORCE RLS investigation → enable or signed exception               | SQL + note                                        |
| D6   | Platform | MR-O01 / G6 | Create Sentry projects; wire DSNs; fire test errors                | Event links                                       |
| D7   | Platform | MR-O02 / G6 | Uptime monitors on health endpoints                                | Monitors green                                    |
| D8   | Ops      | MR-W04 / G7 | Backup schedule + restore drill                                    | RPO/RTO doc + success                             |
| D9   | Ops      | G9          | Rollback drill (prior Vercel + API tag)                            | Time recorded                                     |
| D10  | CI       | MR-R05 / G8 | Make secret-scan blocking; confirm branch protection               | Screenshot / check required                       |
| D11  | Events   | MR-B04      | Organiser Tier-1 GMV cap verify/implement                          | Over-cap rejected                                 |
| D12  | Payments | MR-B03      | Refund/cancel matrix sandbox                                       | Cancel→refund+notify                              |

**Branch suggestions:** split by owner (`cursor/n8n-release-activate-*`, `cursor/migration-reconcile-*`, `cursor/force-rls-*`) — exclusive files/docs.

---

## Wave E — Founder / business gates

**Objective:** Close decisions Cursor cannot invent. Parallelizable with D once surfaced.

| Item | Decision ID       | Exit criteria                                         | Blocks                |
| ---- | ----------------- | ----------------------------------------------------- | --------------------- |
| E1   | FD-LEGAL / F4     | Written counsel artifact path recorded                | G13, real-money GO    |
| E2   | FD-ZAMTEL / F9a   | Decision recorded; UI matches flag                    | G14                   |
| E3   | FD-ADMIN-ROLES    | ADR or `00-decisions` update                          | G15, ADM-01           |
| E4   | FD-DEMO-MERCH     | Label / exclude / replace plan executed               | G11                   |
| E5   | FD-PUBLIC-LAUNCH  | Remains false until Production GO pack                | Open launch           |
| E6   | FD-PREPAID-ENABLE | Flip only after Production GO                         | Live collections      |
| E7   | FD-SENTRY         | Projects approved                                     | G6                    |
| E8   | FD-ACCESS-AUDITOR | Auditor Access granted; ADM-10 pack                   | Admin deep audit      |
| E9   | PD-* (optional)   | Event type / product class / condition scope recorded | Scope-conditional P0s |

---

## Parallelism map

```text
                    ┌─────────────┐
                    │ Wave A Money│  (staging)
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │ Wave B  │  │ Wave C  │  │ Wave E  │
        │ KYC     │  │ Deploy  │  │ Founder │
        └────┬────┘  └────┬────┘  └────┬────┘
             │            │            │
             └────────────┼────────────┘
                          ▼
                    ┌─────────┐
                    │ Wave D  │  (prod ops; after A for n8n money)
                    └────┬────┘
                         ▼
              Production real-money GO pack
```

- **A ∥ E** (founder decisions) — safe
- **B ∥ C** after A1 credentials available — safe if C does not claim KYC prod until B
- **D1/D2 after A** — required
- **D3 migrations** — after B0 backup; coordinate with B5

---

## Priority board (deduplicated P0)

| Order | Work                                           | Wave | Status now              |
| ----- | ---------------------------------------------- | ---- | ----------------------- |
| 1     | Sandbox prepaid + release proof                | A    | Code DONE; staging FAIL |
| 2     | Activate staging then prod release/tickets n8n | A→D  | MISSING live            |
| 3     | Apply `0056` + KYC freeze proof                | B    | Code DONE; migrate FAIL |
| 4     | Migration reconcile `0051/53–55` + FORCE RLS   | D    | CONFLICT / PARTIAL      |
| 5     | Deploy panels + API digest + seller CTA env    | C    | Undeployed tip          |
| 6     | Sentry / uptime / backup / restore / rollback  | D    | MISSING / NA            |
| 7     | Legal + Zamtel + admin RBAC + demo merch       | E    | OPEN_FOUNDER            |
| 8     | Refund matrix + organiser GMV cap              | D    | OPEN                    |
| —     | Class D/E catalogue                            | —    | DEFERRED unless PD-*    |

---

## Definition of Done per evidence layer

| Layer        | Done means                                                   |
| ------------ | ------------------------------------------------------------ |
| DONE_CODE    | Merged to master; CI green for owned suite                   |
| DONE_STAGING | Staging gates in `release-gates.md` SG-* PASS with artifacts |
| DONE_PROD    | Production gate PASS with release evidence pack filled       |

A MR-ID may only move to **closed** in the master register when the layer required by its acceptance criteria is DONE.

---

## Explicit non-goals this plan

1. Seeding 75–100 / 840 vendors or fake GMV
2. Rebuilding Django / Meilisearch / Celery / DPO / Yango
3. Enabling `public_launch` or production prepaid mid-wave
4. Auto-upgrading KYC orphans without controlled plan
5. Declaring production-ready while G0–G9/G12 production incomplete

---

## Handoff checklist for next coding session

```text
[ ] Read master-reconciliation-register.md §12 (P0 open set)
[ ] Read source-conflicts-and-decisions.md (open FD-*)
[ ] Pick one wave item with exclusive ownership
[ ] Open branch cursor/<descriptive>-<suffix> from master
[ ] Implement or execute evidence only — no drive-by refactors
[ ] Attach evidence paths under docs/production-readiness/2026-07-18/
[ ] Update scorecard change log + gate Current lines
[ ] Do not mark MR closed without staging/prod evidence
```

---

_Related:_ `release-gates.md` · `panel-backlogs.md` · `production-readiness-scorecard.md` · `source-conflicts-and-decisions.md`

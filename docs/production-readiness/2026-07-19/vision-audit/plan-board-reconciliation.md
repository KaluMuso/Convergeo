# Vision-audit plan ⇄ implementation board — reconciliation

**Date:** 2026-07-20 · **Reconciles:** my `2026-07-19/vision-audit/` plan (VA–VF pebbles, G/S gates) against the live `2026-07-20/current-implementation-board.md` (AC/RC/DEP/LIVE/F/L/DD/SD).

## Verdict
The **board is the current source of truth for STATUS.** It is a day-newer re-audit with a live fingerprint (Supabase `list_migrations`, Vercel SHAs, n8n counts) and it already cross-references my pebble IDs and gates. My vision-audit keeps its value as the **decomposition + gate definitions**, but several of its *status* findings are now stale — the board says so explicitly (SD-04, SD-05). Net: adopt the board's taxonomy for "what's left"; use my plan for "what each gate means." No conflict of substance — the board is ahead of, and consistent with, the plan.

## A. Pebble → board crosswalk (status now)

| My pebble | Board ID | Current status | Owner / blocker |
| --------- | -------- | -------------- | --------------- |
| VA-P00 backup artifact | — | ✅ done (Wave 1) | — |
| VA-P01 promote FE | AC-07 | ✅ customer prod @ `b1ea6a3` | — |
| VA-P02 apply 0051/0053–0056 | AC-08, SD-05 | ✅ **superseded** — live now at `0057–0062` too | — |
| VA-P03 pin API image | **DEP-03** | ⛔ DEPLOYMENT_REQUIRED (digest NOT_AUDITABLE; API 502) | founder/host |
| VA-P04 vendor CTA | F-CTA | ~ founder (if still unset); largely resolved by live-beta | founder |
| VB-P01/02 sandbox MoMo/card | **LIVE-01/02** | ⛔ BLOCKED_EXTERNAL (F9b creds + API tip) | founder (Lenco) |
| VB-P03 replay idempotency | LIVE-01 (part) | code ✅; live drill blocked | founder |
| VB-P04 release accounting | **LIVE-03** | code ✅; live drill blocked (release-job inactive) | founder/ops |
| VB-P05 refund · VB-P06 recon | AC-02/AC-03 + LIVE | code ✅ (I verified; #351/#352 merged) | live via DEP-01 |
| VB-P07 false-success E2E | **RC-05** | ✅ **CODE_COMPLETE** — merged `36c3e44` | live = LIVE-06 |
| VC-P01 KYC orphan repair | **F-ORPH** | ⛔ founder ops SQL (guarded; never auto-heal) | founder |
| VC-P02 FORCE RLS (code) | **RC-01** | ⛔ REPO_CLOSABLE (migration) | Cursor/CCP |
| VC-P03 role hook enable | **DEP-04** | ⛔ DEPLOYMENT_REQUIRED (`0051` applied; hook off) | founder ops |
| VC-P04 RLS matrix rows | **RC-07** | ⛔ REPO_CLOSABLE (tests) | Cursor |
| VC-P06 demo exclusion (API) | **RC-04** | ⛔ REPO_CLOSABLE | Cursor |
| VC-P07 admin RBAC (B-4) | DD-08 | deferred (single-admin; no invented roles) | decision |
| VC-P09 leaked-password | **DEP-05** | ⛔ ops checkbox (G20) | founder |
| VD-P01/02/03 activate n8n | **DEP-02** | ⛔ BLOCKED_EXTERNAL (API 502) → then ops import | founder/ops |
| VD-P04 backup workflow | **RC-03** | ✅ **CODE_COMPLETE** — `bbe964e` (script @ `infra/scripts/db-dump.sh`, SSH not Exec-Cmd) | live = LIVE-09 |
| VD-P05 uptime HMAC | **RC-08** | ✅ **CODE_COMPLETE** — constant-time `timingSafeEqual` node | founder activate |
| VD-P06 money-workflow alerting | (in DEP-02) | error-alert node present (live id `LVuHqWgT1tqjYOtc`) | ops import |
| VE-P01/02 Sentry/uptime | **F-SEN/F-UP + LIVE-08** | ⛔ BLOCKED_EXTERNAL (Sentry create 403) | founder |
| VE-P03 restore drill | **LIVE-09** | ⛔ FAIL (local drill only; no approved backup) | founder/ops |
| VE-P04 secret-scan blocking | **RC-06** | ✅ YAML blocking; ⛔ founder branch-protection | founder (F-BP) |
| VE-P07 critical-path E2E | **RC-05** | ✅ merged `36c3e44` | live |
| VE-P09 go/no-go pack | **LIVE-14** | ⛔ LIVE_VERIFICATION_REQUIRED | founder |
| VF-P01 bem/nya i18n | **RC-11** → CCP-02/03 | ⛔ REPO_CLOSABLE (+ native review) | Cursor/founder |
| VF-P02 de-route `zh` | **RC-10** → CCP-01 | ⛔ REPO_CLOSABLE | Cursor |
| VF-P04 search `degraded` | **LIVE-12** → CCP-05 | ⛔ FAIL (API 502; NOT_AUDITABLE) | founder (API) |
| VF-P05/06 scanner/GMV cap | (M10/M-scope) | in master money/ticket hardening | — |

(Tail docs/decision pebbles — VC-P08 legal, VD-P07 SoT banners, VF-P03 admin docs — map to L-01/CCP-08/DD-08.)

## B. What the board surfaced that my 07-19 audit did NOT
1. **RC-02 — a genuinely new P0 repo blocker.** A migration-ledger collision: live `0063` = `revoke_execute_review_reply_guards`, but repo wanted `0063` for `source_key`. Must reconcile (revoke on master + renumber source_key → `0065`) **before** the source_key index can apply live (DEP-01). My audit predates this; it's now the **top repo task**.
2. **Money-hardening PRs landed post-audit** and closed G3 items: AC-01 (#350 checkout single-settle), AC-02 (#351 item-refund remainder), AC-03 (#352 `refunds.source_key`). My "money CODE_COMPLETE" verdict is **confirmed and extended**.
3. **Live migrations advanced past my Wave-1 apply:** `0057–0062` applied live 2026-07-20 (AC-08). My audit stopped at `0056`.
4. **Batch-1 CODE pebbles already built** (what I nearly re-dispatched): VB-P07/VD-P04/VD-P05 = RC-05/RC-03/RC-08 CODE_COMPLETE.

## C. My vision-audit findings now STALE (per board SD-*)
- **SD-04:** DL-1 "categories 500 / customer `cc4a824`" → resolved; prod `b1ea6a3`.
- **SD-05:** DL-3 "unapplied `0051`/`0053–0056`" → applied; residual is the source_key collision (RC-02) + FORCE RLS (RC-01/DEP-07).
- My money-proof framing ("founder just runs the sandbox") understated the blockers: the drills are **BLOCKED_EXTERNAL** on **API 502 + missing Lenco creds (F9b)** — not merely "un-run."

## D. Unified "what's left," by owner (P0 first)
**Repo (Cursor / CCP programme):**
- 🔴 **RC-02** migration-ledger reconcile (revoke + renumber source_key) — *top repo priority; unblocks live refund correctness*
- 🔴 **RC-01** FORCE RLS migration (→ DEP-07 live)
- 🟡 RC-04 demo exclusion · RC-06 CI branch-protection · RC-07 RLS matrix · CCP-01/02/03/05/07 polish
- ✅ RC-03 (backup) · RC-05 (E2E) · RC-08 (uptime) **already done**

**Deploy / ops (founder):** DEP-01 apply source_key (after RC-02) · **DEP-03 pin+recover API (the 502 is the keystone)** · DEP-02 import n8n fleet · DEP-04 role hook · DEP-07 FORCE RLS live.

**Live drills (all gated on API recovery + Lenco creds):** LIVE-01/02/03 money · LIVE-05 KYC · LIVE-06 false-success · LIVE-08 Sentry/uptime · LIVE-09 restore · LIVE-10 rollback · LIVE-14 go/no-go pack.

**Founder external:** 🔴 **F-09b Lenco sandbox+prod creds** (blocks all money) · 🔴 **F-SEN/F-UP** Sentry+uptime (Sentry create 403) · F-02 PACRA/TPIN · F-05 WhatsApp send · F-ORPH orphan repair.

**Legal:** 🔴 **L-01** escrow counsel (NPS Act 2026) — longest external lead; start now.

## E. The keystone insight

> **Update (2026-07-20, post-write):** the **API 502 is RESOLVED** — the founder redeployed `ghcr.io/kalumuso/convergeo-api:latest` with `ENV=production`; `/healthz`, `/readyz`, and `https://api.vergeo5.com/healthz` all return 200. DEP-03 is largely met (record the pinned digest for the audit trail). This clears blocker #1 below, so **DEP-02** (n8n import) and **LIVE-01/02/03/05/06/12** become runnable. ⚠️ **Safety gate still binding:** the host now runs `ENV=production` + `LENCO_ENV=production`, so the S1–S6 money drills must still use **sandbox** Lenco on an **isolated** stack (never this production host), and `public_launch`/prepaid must stay **OFF** until release-gates + L-01 legal pass. Confirm the money kill-switch before any money flow. Blocker #2 (Lenco **sandbox** creds, F-09b) remains.

Two external unlocks collapse most of the LIVE-* backlog:
1. **Recover the API (DEP-03)** — it's returning **502**, which is *why* LIVE-01/02/03/05/06, DEP-02 money ticks, and LIVE-12 search are all NOT_RUN. Nothing money/KYC/false-success can be *verified* live until the API is up and its digest pinned.
2. **Lenco sandbox creds (F-09b)** — no `LENCO_*` on the agent; without them the sandbox money drills can't run even with a healthy API.

Everything else (RC-02/RC-01 repo work, the founder infra, legal) proceeds in parallel, but **API-up + Lenco-creds** is the critical path to earning S1–S6.

## Recommendation
1. Treat `2026-07-20/current-implementation-board.md` as the **live status SoT**; my vision-audit stays the gate/decomposition reference. (Board's CCP-08 already plans SoT-pointer updates — SD-06…09.)
2. Sequence repo work per the board §6: **RC-02 → DEP-01**, then **RC-01 → DEP-07**.
3. Escalate the **API 502 (DEP-03)** and **F-09b Lenco creds** as the two founder items that unblock the entire live-verification chain, and **L-01** as the long-lead legal item.

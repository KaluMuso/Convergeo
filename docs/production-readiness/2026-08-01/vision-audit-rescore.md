# Vision-audit re-score — 2026-08-01 (RC-P02)

**Observation window (UTC):** 2026-08-01T10:50Z–11:20Z
**Observer:** Claude Code session (read-only; no deploy, no config change, no flag flip, no workflow activation, no money action)
**Scores:** the 44 pebbles of `docs/production-readiness/2026-07-19/vision-audit/03-waves-and-phases.md` (VM-A…VM-F)
**Why:** that catalog was written 2026-07-19 and never re-scored. Thirteen days of work has landed against it, and a backlog nobody re-counts is a backlog nobody can plan from.

> **Scoring rule.** Every row is scored from evidence gathered in this window, or marked `UNKNOWN`.
> "Merged" is not "closed", "green in CI" is not "proven live", and an artifact existing is not the
> same as the acceptance criterion being met. Where the pebble's acceptance has two halves — code and
> live proof — and only the code half holds, the score is `CODE_DONE`, never `CLOSED`.

---

## 0. Vocabulary

| Score       | Meaning                                                                              |
| ----------- | ------------------------------------------------------------------------------------ |
| `CLOSED`    | acceptance criterion met and verified this window                                     |
| `CODE_DONE` | the artifact exists and CI exercises it; the live/ops half of its acceptance is unproven |
| `PARTIAL`   | materially advanced since 2026-07-19, acceptance not yet met                          |
| `OPEN`      | acceptance not met; little or no movement                                             |
| `UNKNOWN`   | not verifiable from this session (see §5)                                             |

## 1. Headline

| Score       | Count  |
| ----------- | ------ |
| `CLOSED`    | **13** |
| `CODE_DONE` | **4**  |
| `PARTIAL`   | **7**  |
| `OPEN`      | **15** |
| `UNKNOWN`   | **5**  |
| **Total**   | **44** |

**The 2026-07-19 count of 44 open was wrong in both directions.** Thirteen are genuinely closed. But
the catalog also predates M17/M18, so it never contained the two gates those mountains added (§4), and
it did not know about the two defects found in §6.

**Recommendation is unchanged: NO_GO** for sandbox-transaction beta, controlled real-money beta and
public launch. The money plane (VM-B) is untouched: **every ledger table is still empty on both
database projects.**

## 2. The two structural changes since 2026-07-19

Both are large and both are real:

1. **A dedicated staging plane now exists.** Supabase project **`vergeo-sandbox`**
   (`iyasmrmbcrvlfxpzescb`, eu-west-1, ACTIVE_HEALTHY, created 2026-07-28) carries **all 79
   migrations, `0001`–`0079`, in clean sequential order** — including the M17/M18 set. This is what
   S0 ("no dedicated staging schema plane") was failing for. Production (`dpadrlxukcjbewpqympu`) is
   still at ledger tip **`0071`**.
2. **The backup/restore drill went green.** Failed 7 consecutive scheduled runs (07-24 → 07-30); has
   passed the last three (07-31 06:28 schedule, 07-31 07:55 dispatch, 08-01 06:14 schedule) after
   `fix(ops): repair recovery and staging seed drills`.

## 3. Scores

### VM-A — Deployment & schema truth · 2 CLOSED · 1 OPEN · 2 UNKNOWN

| Pebble | Score | Evidence |
| --- | --- | --- |
| VA-P00 pre-migration backup artifact | `OPEN` | no `backup-*.md` in `…/vision-audit/evidence/` |
| VA-P01 promote frontends to tip | **`CLOSED`** | customer `dpl_6UjmL6kKxNT2QPF3BntbtNpi3izU`, vendor `dpl_F8fPWU1rwe1bhxCPmiVhPwxNnzoG`, admin `dpl_AoEScNHCwRv1Cwg2nALR3UBEtX49` — all READY, all `githubCommitSha 7d8b3ae`, = master tip, 2026-08-01T10:22Z. Route-200 sub-criterion unverified (§5). |
| VA-P02 apply migrations staging-first | **`CLOSED`** | `vergeo-sandbox` holds `0001`–`0079`. Note the prod apply is VC-P01's scope and remains open. |
| VA-P03 pin & redeploy API image | `UNKNOWN` | no `evidence/api-image.md`; API unreachable from here |
| VA-P04 vendor-app URL env | `UNKNOWN` | `evidence/cta.md` predates this window; CTA render not probeable |

### VM-B — Money & escrow verified · 6 OPEN · 1 CODE_DONE

| Pebble | Score | Evidence |
| --- | --- | --- |
| VB-P01 sandbox MoMo → ledger | `OPEN` | `payments`, `ledger_transactions`, `ledger_postings` = **0** on **both** prod and `vergeo-sandbox` |
| VB-P02 sandbox card → ledger | `OPEN` | same |
| VB-P03 webhook replay idempotency | `OPEN` | no payment rows to replay against |
| VB-P04 release accounting | `OPEN` | `payouts` = 0 |
| VB-P05 refund matrix | `OPEN` | `refunds` = 0 |
| VB-P06 reconciliation alert | `OPEN` | no drift to detect; alert workflow inactive (VM-D) |
| VB-P07 false-success E2E | **`CODE_DONE`** | `e2e/specs/checkout-false-success.spec.ts` present; nightly E2E green **21/21** runs since 2026-07-12 |

**Movement worth recording even though nothing closed:** the drill *tooling* landed this week —
`scripts/drills/lenco_sandbox_money_drill.py`, `docs/ops/lenco/sandbox-money-drill.md`, and Airtel
sandbox settlement support (`fix(drills): support Airtel sandbox settlements`). VM-B is now blocked
only on F9b credentials plus an operator running it — not on missing code.

### VM-C — Trust, KYC, security & RBAC · 4 CLOSED · 2 PARTIAL · 3 OPEN

| Pebble | Score | Evidence |
| --- | --- | --- |
| VC-P01 KYC `0056` rollout | `PARTIAL` | `0056` applied on prod; `kyc_records` = 0, no orphan-repair evidence |
| VC-P02 FORCE RLS on residual tables | **`CLOSED`** | `relforcerowsecurity` = **true** on `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations` (also true on `orders`, `payments`) |
| VC-P03 role hook | `PARTIAL` | `0051` applied and `public.custom_access_token_hook(jsonb)` exists on prod; whether the Auth-side hook is *enabled* is a dashboard setting, not readable via SQL |
| VC-P04 RLS matrix coverage | **`CLOSED`** | `event_categories`, `product_relations`, `service_reviews` all present in `tests/rls/test_matrix.py` |
| VC-P05 single audited refunds mount | **`OPEN`** | see §6.1 — the duplicate mount still exists |
| VC-P06 demo exclusion | **`CLOSED`** | `app/services/listings/demo.py` + `drop_demo_listing_hits` wired into search/catalog; `tests/test_demo_exclusion.py` header cites VC-P06 / FD-04 / G11 |
| VC-P07 admin RBAC decision (B-4) | **`CLOSED`** | resolved down the manual-ops path; `docs/ops/admin-access.md` present |
| VC-P08 legal sign-off | `OPEN` | `docs/ops/f4-escrow-legal-review-brief.md` exists — the brief, not the sign-off. F4 still open. |
| VC-P09 leaked-password protection | **`OPEN`** | Supabase security advisor still reports `auth_leaked_password_protection` **disabled** |

### VM-D — Automations parity · 1 CLOSED · 2 PARTIAL · 1 CODE_DONE · 3 OPEN

Live instance: **9 workflows, 7 active, 2 inactive**. Repo: **24 workflow JSONs**. So **15 committed
workflows have never been imported.**

| Pebble | Score | Evidence |
| --- | --- | --- |
| VD-P01 activate release-job + order-jobs | `OPEN` | neither present on the instance |
| VD-P02 activate tickets/event release | `OPEN` | none of the three present |
| VD-P03 activate 8 lifecycle workflows | `PARTIAL` | 7 active (dispatch, reconciliation crons, embeddings, reservation sweeper, nudges, analytics retention, admin digest) |
| VD-P04 backup workflow | `PARTIAL` | authored **and imported**, but ships **inactive** — needs SSH + WhatsApp credentials |
| VD-P05 uptime-alert auth | `CODE_DONE` | `infra/n8n/uptime-alert.json` present; not imported |
| VD-P06 money-workflow error handling | **`OPEN`** | see §6.2 — no `errorWorkflow` in any of the four money JSONs |
| VD-P07 registry doc drift | **`CLOSED`** | recon daily-report + `order-jobs` dual endpoint both documented in `docs/ops/n8n-workflows.md` |

### VM-E — Observability, ops & launch QA · 3 CLOSED · 1 CODE_DONE · 2 PARTIAL · 1 OPEN · 2 UNKNOWN

| Pebble | Score | Evidence |
| --- | --- | --- |
| VE-P01 Sentry projects | `UNKNOWN` | not probed this window |
| VE-P02 uptime monitors | `UNKNOWN` | not probed this window |
| VE-P03 restore drill | **`CLOSED`** | 3 consecutive green runs (§2). **Scope note:** the drill is self-contained in CI — it proves the mechanism, not a restore of a real production dump. |
| VE-P04 blocking secret-scan | **`CLOSED`** | no `continue-on-error` on the `secret-scan` job. **But** `RLS isolation matrix` and `Seed demo data` are still `continue-on-error: true` — G8's "broad RLS sweep remains advisory" still holds. |
| VE-P05 rollback drill | `OPEN` | no `evidence/rollback-drill.md` |
| VE-P06 perf budgets enforced | **`CLOSED`** | `Performance budgets` workflow ran and passed on PR #531 |
| VE-P07 critical-path E2E | `CODE_DONE` | `e2e/specs/critical-path.spec.ts` present; nightly green — against a target set by the `E2E_BASE_URL` secret, whose value this session cannot see |
| VE-P08 env-isolation plan | `PARTIAL` | NB-8 isolation is specified in `docs/ops/waha-vendor-intake.md`; no `evidence/env-isolation-plan.md` |
| VE-P09 release-gates evidence pack | `PARTIAL` | pack exists at `2026-07-18/consolidated/release-gates.md`; not refreshed against current state |

### VM-F — Vision build gaps · 3 CLOSED · 1 CODE_DONE · 1 PARTIAL · 1 OPEN · 1 UNKNOWN

| Pebble | Score | Evidence |
| --- | --- | --- |
| VF-P01 bem/nya namespaces | `PARTIAL` | `bem` and `nya` carry **16** namespace files each; `en` carries **19** |
| VF-P02 `zh` out of the public switcher | **`CLOSED`** | `PUBLIC_LOCALES = ["en","bem","nya","fr"]` — `zh` retained in `LOCALES` for QA exactly as specified |
| VF-P03 admin user-mgmt | **`CLOSED`** | closed with VC-P07 via the documented manual-ops path |
| VF-P04 search health (`degraded=false`) | `UNKNOWN` | needs a live `/search` call |
| VF-P05 offline scanner | `CODE_DONE` | `apps/vendor/sw-scanner.ts` + scanner components present; offline behaviour unproven |
| VF-P06 organiser Tier-1 GMV cap | **`CLOSED`** | `0060_organiser_t1_gmv_cap` applied on prod; `app/services/events/gmv_cap.py` + `tests/test_event_gmv_cap.py` |
| VF-P07 `multi_day` decision | **`OPEN`** | no `multi_day` entry in `docs/plan/00-decisions.md` |

## 4. Gates the catalog never contained

The 2026-07-19 catalog predates M17 and M18. Two live gates exist that no VM pebble covers, tracked as
RG-2 and RG-3 in `docs/plan/00-status.md`:

| Gate | Status | Note |
| --- | --- | --- |
| **RG-2** M17 F-V4 Cloudinary headroom + cost-guard drill | `NOT_RUN` | unresolvable from code by design; `clip_spend_monthly` does not exist on prod (`0079` unapplied) |
| **RG-3** M18 pilot Stage-1 + kill-switch drill | `NOT_RUN` | `intake-pilot-checklist.md` sign-off empty; on prod the intake tables and the `waha_vendor_intake` row do not exist (`0072`–`0075` unapplied) |

On the **staging** plane both flag sets now exist and read **`false`**: `clips`, `clips_comments`,
`waha_vendor_intake` — verified this window. Dark-ship posture holds on both planes.

## 5. What this session could not verify

Unchanged from 2026-07-27: HTTPS egress to `api.vergeo5.com` and `*.vergeo5.com` is denied by the
session proxy (403 to CONNECT). That blocks **VA-P03**, **VA-P04**, **VF-P04**, VA-P01's route-200
sub-criterion, and any API health or digest claim. **VE-P01/VE-P02** (Sentry, UptimeRobot) were not
probed. Five rows are `UNKNOWN` for these reasons and are **not** counted as progress.

`scripts/ops/verify_live.sh` runs the whole matrix from a host with egress and is the intended closer.

## 6. Two defects found while scoring

Both are evidence-backed and neither is fixed here — this is a documentation pass.

### 6.1 The staging schema guard passes when it cannot connect

`scripts/ci/check-staging-schema.sh:36` reads:

```sh
issues="$("${PSQL[@]}" -At -f "$SQL_FILE" | grep -E '^FAIL ' || true)"
```

The `|| true` covers the **whole pipeline**, so a `psql` connection failure is swallowed exactly like
"no FAIL rows found", and the script proceeds to print `OK:` and `exit 0`. This is not theoretical —
it happened in Deploy staging run **30695764799** (2026-08-01T10:31Z), where the log shows:

```
psql: error: connection to server at "db.***.supabase.co" (2a05:...), port 5432 failed: Network is unreachable
OK: RLS enabled on public tables; exposed views use security_invoker (or none exposed)
```

A guard that reports OK when it verified nothing is worse than no guard, because it produces evidence
that is not evidence. **Suggested fix:** capture the `psql` status separately and `die` on it, rather
than folding it into the `grep` pipeline. Left unfixed here because it changes CI behaviour (staging
deploys that currently pass would start failing, correctly) and that is the founder's call.

### 6.2 Money workflows still have no error workflow

VD-P06 asks for error-workflow/retry plus a founder alert on non-2xx money ticks. None of
`release-job.json`, `reconciliation.json`, `payment-sweeper.json`, `payout-failure-alert.json`
contains an `errorWorkflow` key. The shared error-alert handler exists on the instance but is
**inactive**, so a failing money tick is currently silent.

### 6.3 Also observed (not a defect)

Deploy staging: the push-triggered run at 2026-08-01T09:28Z **succeeded**; the `workflow_dispatch` run
an hour later **failed** at "Supabase migrations + checks" because the GitHub runner could not reach
the staging database over IPv6. That is an environment/connectivity issue in the dispatch path, not a
schema problem — the same pipeline succeeds on push.

## 7. What actually remains

Counting `OPEN` + `PARTIAL` + the ops half of `CODE_DONE`, and adding the two M17/M18 gates:

- **~26 readiness pebbles** still need work, of which **15** have seen no movement.
- **5** cannot be scored without egress or console access.
- **9 founder gates** remain unchecked (F2–F9b; only F1 is done).
- The single biggest cluster is **VM-B (7 pebbles)**, blocked on **F9b** alone — the code and the drill
  scripts are ready.

**Highest-leverage next actions**, in order:

1. **F9b credentials** → run the money drill against `vergeo-sandbox`. That is 7 pebbles behind one gate.
2. **Import the 15 unimported n8n workflows** and activate the release/tickets sets (VD-P01/P02) — the
   only reason G5 is failing.
3. **Fix §6.1** so staging schema evidence means something.
4. **Apply `0072`–`0079` to production** once M17/M18 are wanted there; staging already proves the
   sequence applies cleanly.
5. **VC-P09** — one toggle in the Supabase Auth dashboard.

## 8. Related

- `docs/production-readiness/2026-07-19/vision-audit/03-waves-and-phases.md` — the catalog being scored
- `docs/production-readiness/2026-07-27/release-truth.md` — prior release-truth pass (RG-1…RG-5)
- `docs/plan/00-status.md` — current-state summary
- `scripts/ops/verify_live.sh` — the read-only probe matrix that closes the `UNKNOWN` rows

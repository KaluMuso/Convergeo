# Clip cost runbook (M17-P08)

**Purpose:** keep Vergeo Clips inside the **$50/mo** infrastructure ceiling, and
make the moment it stops being affordable a _visible, reversible operator event_
rather than a surprise invoice.

**Owner:** founder.
**Related:** `docs/ops/clip-moderation-policy.md` (the ≤24h report→takedown SLO),
`docs/plan/m17-video-feed.md` §5 and §7.

---

## 1. What costs money

| Cost          | Driver                                                      | Bounded by                                                       |
| ------------- | ----------------------------------------------------------- | ---------------------------------------------------------------- |
| **Transcode** | one eager job per uploaded clip (480p + 720p + WebP poster) | the per-tier **weekly upload cap** (`clip_weekly_caps`)          |
| **Delivery**  | bytes served for posters and played renditions              | data-saver ON by default, poster-first, 480p ceiling on cellular |
| **Storage**   | retained originals + renditions                             | ≤80 MB per clip, ≤60 s                                           |

Everything except delivery is bounded _before_ the spend happens. Delivery is
bounded _behaviourally_ — which is exactly why the guard below exists.

## 2. The guard

`services/api/app/services/clips/spend.py`, cloned from the proven Ask-Vergeo
shape (`ask/spend.py`), not forked from it.

- **Accounting is in integer micro-USD.** No float touches a cost path; the
  conversion from a unit rate uses `Decimal`.
- **Monthly window**, keyed `YYYY-MM`, in `clip_spend_monthly`.
- **Cap** defaults to `CLIP_DEFAULT_MONTHLY_CAP_USD` and is overridden by the
  `platform_config` key `clip_monthly_cap_usd` — config, so it moves without a
  deploy.
- **Kill switch** trips when the month's recorded spend reaches the cap.

### What tripping the switch does — and does not do

|               | Behaviour                                                                                                    |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| **Uploads**   | **paused.** `POST /clips` refuses with `clip_cost_kill_switch` (503) and an i18n-keyed vendor-facing reason. |
| **The feed**  | **stays up.** Posters, captions, prices, linked listings and add-to-cart all keep working.                   |
| **Playback**  | video is not served; the feed shows the "video paused this month" state.                                     |
| **The route** | never blanks, never 500s, never empties.                                                                     |

That asymmetry is the whole design. A cost guard that took the feed down would
turn a billing event into an outage, and the shoppable path — the part that makes
money — is the last thing that should stop.

## 3. Measuring

The numbers come from two places and should agree:

1. **Ours:** `GET /admin/clips/analytics` — recorded spend for the month, the cap,
   remaining headroom, upload count, and the engagement/conversion funnel
   (views → likes → add-to-cart → attributed orders).
2. **Cloudinary's:** the account's usage dashboard for the same month.

**Method.** Record both on the same day each month. Ours is the authority for the
guard; Cloudinary's is the authority for the invoice. **A drift of more than ~15%
means the per-unit rate in `clip_cost_rates` is wrong** — fix the config, not the
code.

## 4. Kill-switch drill (run once before the flag is flipped)

1. Set `clip_monthly_cap_usd` to a value **below** the current month's recorded
   spend (a cap of `0` works).
2. Attempt an upload from the vendor studio. Expect a clear, translated refusal —
   not a stack trace, not a silent failure.
3. Load `/clips` as a customer. **Expect posters, captions, prices and a working
   add-to-cart.** If any of those are missing, stop and fix before launch.
4. Load a shared clip page (`/clips/{id}`). Expect the poster and OG tags.
5. Reset: restore the cap and call the reset action from the admin analytics page.
   Confirm uploads work again.
6. Check `audit_log` — every flip and reset should be there with an actor.

The drill is cheap and answers the only question that matters about a kill
switch: _does the thing still work when it fires?_

## 5. Operator actions

| Situation                            | Action                                                                                 |
| ------------------------------------ | -------------------------------------------------------------------------------------- |
| Spend approaching the cap            | raise `clip_monthly_cap_usd` (inside the $50/mo total) **or** lower `clip_weekly_caps` |
| Switch tripped, spend genuinely fine | reset from the admin analytics page — audited, reversible                              |
| Switch tripped, spend genuinely high | leave it; lower `clip_weekly_caps` for next month                                      |
| One vendor dominating uploads        | lower that tier's `clip_weekly_caps` entry                                             |
| Suspected rate drift                 | reconcile against Cloudinary, correct `clip_cost_rates`                                |

All five are **config changes**. None require a deploy.

## 6. Founder gates (F-V1 – F-V4)

| Gate     | Question                                           | Status                                                                                                                                                                                                                                                                              |
| -------- | -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **F-V1** | Placement and product name                         | **Resolved:** "Clips", behind the `clips` flag (default off), so placement is changeable without a code change.                                                                                                                                                                     |
| **F-V2** | Comments at launch                                 | **Resolved:** built, moderated and rate-limited, shipped **off** behind `clips_comments` — the spec's own recommendation of likes-only for beta week 1.                                                                                                                             |
| **F-V3** | Creator scope v2                                   | **Unchanged:** D-V7 locks vendors-only for v1. No decision was needed and none was taken.                                                                                                                                                                                           |
| **F-V4** | Cloudinary video eager-transcode + credit headroom | **NOT resolved — deliberately safed.** This is a fact about the account, not the code. The mitigation is structural: while the `clips` flag is off there is no upload path, so **no clip can spend a credit**. Confirm the plan before flipping the flag, then run the drill in §4. |

## 7. Beta measurement (what to watch in week 1)

| Metric                               | Where                        | Healthy                                            |
| ------------------------------------ | ---------------------------- | -------------------------------------------------- |
| Clips uploaded / approved / rejected | admin queue + analytics      | rejection rate stable, queue inside the 24h target |
| Spend vs cap                         | `GET /admin/clips/analytics` | tracking well under the cap by mid-month           |
| **S1** — 10-clip session data cost   | e2e `clips-feed.spec.ts`     | ≤5 MB                                              |
| **S2** — clip → cart → checkout      | e2e `clips-commerce.spec.ts` | passes end to end                                  |
| **S3** — report → takedown           | admin reports queue          | ≤24h                                               |
| Attributed orders                    | analytics funnel             | non-zero within week 1                             |

If S1 regresses, the cause is almost always an autoplay path that slipped past
the connection check — start at `playback-policy.ts` and its tests.

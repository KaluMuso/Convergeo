# Clips pilot enablement (founder runbook)

**Purpose:** turn Vergeo Clips (M17) on for a **small allowlist of pilot vendors only**:
staging first, then production. Customers see published clips from those vendors only;
comments stay off; the monthly cost guard and the weekly upload caps keep running.

**Owner:** founder. **Nothing in this document has been done for you.** Every flag
and config value below is still at its shipped default (`clips=false`,
`clips_comments=false`, allowlist empty).

**Related:** `docs/ops/clip-cost-runbook.md` (guard, measurement),
`docs/ops/clip-moderation-policy.md` (≤24h review/report SLO),
`docs/plan/m17-video-feed.md` §5 and §7.

---

## 0. What the pilot gate does

| Control                                         | Where                                       | Pilot value           | Effect                                                                                                                |
| ----------------------------------------------- | ------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `feature_flags.clips`                           | Admin → Config → Flags                      | `true`                | Master switch. Off = no feed, no upload path, nothing spends money.                                                   |
| `feature_flags.clips_comments`                  | Admin → Config → Flags                      | `false` (leave)       | Comments. **Ignored during the pilot anyway**: comments stay off while the allowlist is enforced, whatever this says. |
| `platform_config.clip_pilot_allowlist_enforced` | SQL editor (not in the admin config screen) | `true` (the seeded)   | Pilot gate. Missing row or any value except JSON `false` = enforced (fails closed). `false` ends the pilot.           |
| `clip_pilot_vendors` rows                       | Admin → Clips → **Pilot vendors**           | 3–10 vendors          | Only these vendors can upload, and only their published clips appear in the feed, on clip pages and in engagement.    |
| `platform_config.clip_monthly_cap_usd`          | SQL editor                                  | `5` (pilot)           | Cost guard ceiling (whole USD). Spend reaching it pauses uploads; the feed stays up and shoppable.                    |
| `platform_config.clip_weekly_caps`              | SQL editor                                  | `{"1":3,"2":5,"3":5}` | Uploads per vendor per rolling 7 days by KYC tier (counts rejected clips too).                                        |
| `platform_config.clip_cost_rates`               | SQL editor                                  | see §2.4              | Unit rates the guard uses. Set them from your Cloudinary plan, not the defaults.                                      |

Upload order at the API: flag → **pilot allowlist** → size/duration → **cost guard** →
**weekly cap** → caption screen → draft + signature. A refusal at any step creates
no draft and no signature, so no Cloudinary credit can be spent.

Removing a vendor from the allowlist hides their clips on the next request; nothing
is unpublished or deleted, so adding them back restores the clips as they were.
Every add/remove writes an `audit_log` row (`admin.clips.pilot_add` / `pilot_remove`).

---

## 1. Before you start: F-V4 Cloudinary checks (in your Cloudinary account)

These are facts about **your** account. They cannot be checked from the code. Do
them once, write the numbers down, and keep the screenshots with the drill evidence.

1. **Plan.** Console → Settings → _Account_ / _Plan & billing_: note the plan name
   and the monthly **credit allowance**. On credit-based plans one credit covers a
   fixed amount of transformations _or_ storage _or_ bandwidth. Confirm the exact
   conversions on your plan's page; do not rely on numbers in this doc.
2. **Video is enabled and how it is counted.** Confirm the plan allows video upload
   and **eager video transformations** (we request async eager 480p + 720p MP4 and a
   WebP poster per clip). Find how video transformations are billed on your plan
   (some plans count video processing by duration/resolution rather than per
   transformation). That number is what `transcode_per_clip` must reflect.
3. **Upload limits.** Confirm the max video file size on the plan is **≥ 80 MB**
   (our cap, `MAX_CLIP_BYTES`). If it is lower, uploads near the cap will fail at
   Cloudinary; lower our cap before the pilot instead.
4. **Current usage / headroom.** Console → _Usage_: note credits used this cycle and
   the trend. **Listing images share the same credits.** Headroom for the pilot =
   allowance − (current monthly image usage × 1.3 safety margin).
5. **Notification URL.** Confirm the upload/eager notification URL the API signs
   (`CLOUDINARY_NOTIFICATION_URL` on the API host) points at
   `https://<api-host>/webhooks/cloudinary` for that environment, and that the
   webhook secret is set. Without it, clips sit in `screening` forever (no spend
   is recorded either; see §5 "known limits").
6. **Usage alerts.** If the plan offers usage notifications, set one at **70%** of
   the monthly credits. This is the only alarm on delivery bandwidth (see §5).

**Go/no-go:** proceed only if headroom ≥ the pilot envelope in §3 with 2× margin.
If not, shrink the allowlist or the weekly caps first.

---

## 2. Enable on STAGING (do all of it, then the drill)

Use the staging Supabase project's SQL editor and the staging admin app.
`platform_config` and `feature_flags` changes are recorded by the `config_audit`
trigger.

### 2.1 Confirm the migration is applied

`20261113030000_clip_pilot_allowlist.sql` must be applied (with M17's `0076`–`0079`).

```sql
select key, value from public.platform_config
 where key in ('clip_pilot_allowlist_enforced','clip_monthly_cap_usd',
               'clip_weekly_caps','clip_cost_rates');
select flag, enabled from public.feature_flags where flag in ('clips','clips_comments');
select to_regclass('public.clip_pilot_vendors');
```

Expect `clip_pilot_allowlist_enforced = true`, both flags `false`, the table present.

### 2.2 Set pilot caps (before anything is on)

```sql
update public.platform_config set value = '5'::jsonb
 where key = 'clip_monthly_cap_usd';
update public.platform_config set value = '{"1": 3, "2": 5, "3": 5}'::jsonb
 where key = 'clip_weekly_caps';
```

### 2.3 Allowlist the pilot vendors

Admin → Clips → **Pilot vendors** → add each vendor ID (must be an `active` vendor;
uploads additionally require KYC-verified). Start with 3–5 anchor vendors you can
reach on WhatsApp.

### 2.4 Set the unit rates from §1

Example only; use your own numbers (USD strings, read as `Decimal`):

```sql
update public.platform_config
   set value = '{"transcode_per_clip": "0.05", "delivery_per_gb": "0.10"}'::jsonb
 where key = 'clip_cost_rates';
```

Over-estimating is safe (the guard trips early); under-estimating is not.

### 2.5 Turn the flag on

Admin → Config → Flags → `clips` → **on**. Leave `clips_comments` **off**.

### 2.6 Smoke test (staging)

1. As a **pilot** vendor: Vendor app → Clips → upload a ≤30 s clip. Expect it to reach
   _pending review_ after the transcode callback.
2. As a **non-pilot** verified vendor: try to upload. Expect the translated refusal
   "Clips is in a small pilot…" and **no** new row in `video_clips`.
3. Admin → Clips → approve the pilot clip.
4. As a customer (logged out too): `/clips` shows that clip; `/clips/<id>` works;
   add-to-cart from the overlay works. A published clip from a non-pilot vendor
   (if any exist) does **not** appear and its `/clips/<id>` is 404.
5. Admin → Clips → Pilot vendors → **remove** the pilot vendor → `/clips` no longer
   shows the clip. Add them back → it returns. Check `audit_log` for both rows.

### 2.7 Kill-switch drill (staging, required before production)

This replaces step 1 of `clip-cost-runbook.md` §4: **a cap of `0` does not pause
anything** (0 means "unbounded"), and lowering the cap alone does not trip the
switch until the next spend is recorded. Trip it deterministically instead:

1. Record one micro-dollar against a 1-micro-dollar cap for the current month:

   ```sql
   select public.clip_record_spend(to_char(now() at time zone 'utc','YYYY-MM'), 1, 0, 0, 1);
   select month_key, total_usd_micros, killed_at, admin_reset_at
     from public.clip_spend_monthly order by month_key desc limit 1;
   ```

   Expect `killed_at` set (newer than any `admin_reset_at`).

2. Pilot vendor tries an upload → translated "uploads are paused" message, HTTP 503
   `clip_cost_kill_switch`, no new draft.
3. Customer `/clips` → posters, captions, prices and add-to-cart still work.
   Shared page `/clips/<id>` still renders.
4. Admin → Clips → Analytics → shows _uploads paused_ → **Resume uploads**.
   Upload works again. `audit_log` has `admin.clips.reset_kill_switch`.
5. Note: after a reset the guard **re-arms** — the next recorded spend at or over
   the cap trips it again. To keep uploads open for the month, **raise
   `clip_monthly_cap_usd` above the recorded total first, then reset.**
6. Emergency upload pause without touching spend (also drill it once):

   ```sql
   update public.platform_config set value = '{"1": 0, "2": 0, "3": 0}'::jsonb
    where key = 'clip_weekly_caps';
   ```

   Uploads refuse with the weekly-cap message; the feed is untouched. Restore the
   §2.2 value afterwards.

Save the outputs/screenshots as RG-2 evidence (`00-status.md` gate).

---

## 3. Expected monthly cost at pilot scale

**Assumptions (state yours if different):** 5 pilot vendors, all KYC tier 1 (3
clips/week) → at most ~13 clips/vendor/month → **≤ 65 transcodes/month**; avg clip
25 s; renditions ~2.5 MB (480p) + ~5 MB (720p) + 25 KB poster; ~8 MB stored per
clip including the original; **2,000 plays/month** (80% at 480p → ~2.9 MB avg per
play); **20,000 poster impressions/month**; rates = the shipped defaults
(`$0.02`/transcode, `$0.08`/GB) — replace with your §1 numbers.

| Line      | Volume                          | At default rates |
| --------- | ------------------------------- | ---------------- |
| Transcode | ≤ 65 clips                      | ≤ $1.30          |
| Delivery  | 2,000 × 2.9 MB ≈ 5.8 GB         | ≈ $0.46          |
| Posters   | 20,000 × 25 KB ≈ 0.5 GB         | ≈ $0.04          |
| Storage   | 65 × 8 MB ≈ 0.5 GB (cumulative) | plan-dependent   |
| **Total** |                                 | **≈ $2 / month** |

In Cloudinary credit terms this is roughly **7–8 credits/month**, dominated by
bandwidth (~6.3 GB) and storage, plus whatever your plan charges for ~65 video
eager transformations (check §1.2: if video is counted by duration, 65 × 25 s × 2
renditions ≈ 3,250 s of output). The pilot cap of **$5** gives ~2.5× headroom over
this envelope and stays well inside the $50/mo infrastructure ceiling (Ask Vergeo
$15 + Clips $5).

---

## 4. Enable on PRODUCTION

Only after §2 is complete and the drill passed.

1. Apply the migrations through the normal release path (`0076`–`0079` and
   `20261113030000` are **not applied** on production as of 2026-08-01, per
   `00-status.md`). Re-run the §2.1 checks.
2. §2.2 caps → §2.4 rates → §2.3 allowlist → §2.5 flag on. **In that order**: the
   allowlist must exist before the flag, otherwise the flag-on state is "on, nobody
   allowed" — safe, but confusing.
3. Smoke test §2.6 steps 1, 3, 4 with one real pilot vendor.
4. Week-1 watch list: `clip-cost-runbook.md` §7, plus Cloudinary _Usage_ daily.

---

## 5. Rollback and known limits

**Rollback, fastest first (no deploy needed for any of them):**

| Situation                                    | Action                                                                  | Customer effect                                                        |
| -------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Stop new uploads, keep the feed              | weekly caps → all `0` (§2.7 step 6) **or** trip the guard (§2.7 step 1) | none; feed and add-to-cart keep working                                |
| One vendor misbehaving                       | remove from Pilot vendors (and/or takedown in the moderation queue)     | that vendor's clips vanish instantly                                   |
| Turn Clips off entirely                      | Admin → Config → Flags → `clips` **off**                                | `/clips` 404s; no upload path                                          |
| End the pilot (go wide) — a founder decision | `clip_pilot_allowlist_enforced` → `false`                               | all active vendors' clips; comments may open if `clips_comments` is on |

**Known limits — read before the pilot:**

- **The guard meters transcodes only.** `record_spend` is called by the Cloudinary
  transcode callback; **delivery bytes are not recorded**, so bandwidth never trips
  the switch. During the pilot, bandwidth is watched in Cloudinary _Usage_ (and the
  §1.6 alert). At pilot scale this is small (§3), but it is the uncapped line.
- If spend accounting itself fails inside the callback it is logged and skipped
  (the transcode has already happened). Reconcile monthly against Cloudinary.
- `clip_pilot_allowlist_enforced`, `clip_weekly_caps`, `clip_monthly_cap_usd` and
  `clip_cost_rates` are not editable in the admin Config screen today (it only
  edits integer keys from a fixed list); use the SQL editor. The `config_audit`
  trigger still records the change.

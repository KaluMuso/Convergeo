# M17 — Shoppable Short-Video Feed ("Vergeo Clips") — Mountain Spec

> **Status:** SPEC (post-launch / v2 growth mountain — do **not** dispatch before public
> launch is live and stable). Requested by founder 2026-07-12 (Kuaishou/WeChat-style
> scrolling shoppable video, engagement lever + regional-expansion differentiator).
> **Prime directive:** this feature must NOT violate the locked 3G / data-cost-frugality
> mandate. Every decision below is subordinate to that.

---

## 1. Goal & success criteria (Phase-1 style)

A vertical, snap-scrolling feed of short vendor videos where a viewer can, without
leaving the feed: watch, like, comment, share to WhatsApp, and **buy** (add a linked
listing to cart / jump to checkout). Vendors record on their phones, upload from the
vendor app, and get moderated + published.

**Success criteria (all must hold before the feed goes past beta):**

- **S1 — Data safety:** a 10-clip browsing session on the _default_ (data-saver) profile
  costs **≤5 MB** total; the feed _page_ itself stays within the customer ≤150 KB gz JS
  budget; **zero autoplay on cellular by default**.
- **S2 — Commerce loop closes:** clip → product overlay → add-to-cart → existing checkout
  works E2E; attribution recorded (`clip_id` on the funnel event) so clip→order
  conversion is measurable per vendor.
- **S3 — Moderation holds the line:** no clip is publicly visible before passing the
  automated screen + (at launch) human approval; D8 prohibited categories are enforced on
  clips exactly as on listings; report→takedown ≤24h.
- **S4 — Cost ceiling holds:** total video cost (storage + transcode + delivery) has a
  hard monthly kill-switch (Ask-Vergeo pattern); projected beta cost ≤$15/mo inside the
  $50/mo ceiling.
- **S5 — Race-safe engagement:** like/comment/view counters are correct under concurrency
  (no lost updates, no double-likes); tested like all money paths.

**Non-goals (v1):** live streaming; creator monetization/payouts for views; ML
personalization; duets/stitches/effects; customer (non-vendor) uploads; in-video
comments overlays.

---

## 2. Locked data-conscious design decisions (the Zambian shape of this feature)

These are the guardrails that reconcile video with the 3G mandate. They are **binding**
for every M17 pebble.

- **D-V1 — Poster-first, tap-to-play.** The feed renders **poster frames (WebP, ≤25 KB
  each)**, never auto-downloading video on cellular. Tapping loads + plays the clip.
  On **Wi-Fi with data-saver off**, the in-view clip may autoplay (muted); never more
  than the in-view clip.
- **D-V2 — Data-saver ON by default.** A persistent toggle (same UX slot as the theme
  toggle). Saver profile: 480p ceiling, no preload, no autoplay, poster-only scroll.
  Non-saver Wi-Fi profile: 720p ceiling, preload of the _next_ poster+first-segment only.
- **D-V3 — Short + capped:** clips are **≤60s recorded, ≤30s recommended**; upload cap
  **≤80 MB**; delivery renditions capped at **480p (cellular) / 720p (Wi-Fi)**.
- **D-V4 — Progressive MP4, not HLS, for v1.** Cloudinary eager-transcodes to H.264 MP4
  (480p + 720p) + WebP poster. Rationale: native `<video>` playback everywhere with
  **zero JS player dependency** (hls.js is ~70 KB gz — it alone would blow half a route
  budget). A ≤30s 480p clip is ~1.5–3 MB progressive; range requests give effective
  seeking. HLS/ABR is a v2 upgrade if clip lengths grow.
- **D-V5 — Byte honesty:** each clip card shows an approximate size chip ("~2 MB") before
  tap-to-play on cellular. Data respect is trust UX, same family as the escrow banner.
- **D-V6 — One `<video>` element,** recycled across the feed (vertical snap-scroll +
  IntersectionObserver); off-screen clips are unloaded. No videos mounted outside the
  viewport ±1.
- **D-V7 — Vendors-only creators (v1).** Only **KYC-verified vendors** can upload. This
  collapses the UGC-moderation problem to an accountable, suspendable population, ties
  every clip to commerce, and matches the platform's trust posture. Open UGC is a
  founder decision for v2 (**F-V3**).
- **D-V8 — Pre-publish moderation at launch.** Automated screen (reuse
  `moderation/prohibited.py` word-boundary keywords on title/caption + D8 category fence)
  → **human approval queue in admin** (reuse the M13-P04 flags-queue pattern). Post-beta,
  flip to post-publish + spot-check via a config flag when volume demands it.
- **D-V9 — i18n + expansion-ready:** all strings via next-intl (`clips` namespace);
  currency/locale come from the existing seams — nothing in M17 hardcodes ZMW/EN, so the
  neighboring-country expansion inherits it.

---

## 3. Architecture (reusing existing seams — nothing new invented)

```
vendor app ──(signed direct upload: media/cloudinary_signing.py pattern)──▶ Cloudinary
     │                                                                        │ eager async:
     ▼                                                                        ▼
POST /clips (draft row) ◀──(webhook: transcode done, renditions+poster)── notification
     │
     ▼
automated screen (moderation/prohibited.py: keywords + D8 category fence)
     │ pass → admin approval queue (admin_flags.py pattern)   │ fail → rejected + reason
     ▼ approve (audited state transition)
status: published ──▶ GET /clips/feed (cursor, ranked) ──▶ customer feed page
                                                              │ overlay: linked listings (≤3)
                                                              ▼
                                              add-to-cart (existing cart seams) → checkout
```

- **Upload:** vendor app records/picks a video → API issues a signed Cloudinary upload
  (extend `cloudinary_signing.py` for the video preset: eager 480p/720p MP4 + WebP
  poster, async). No video bytes ever transit our API.
- **State machine (convention #4):** `draft → screening → pending_review → published |
rejected | taken_down` via guarded transition functions with audit log — never raw
  UPDATEs. Takedown (admin or vendor-suspension cascade) is instant-hide.
- **Feed ranking v1 — deterministic SQL, no ML:**
  `score = freshness_decay(published_at) × (1 + log(1+likes) + 2·log(1+orders_attributed))`
  with a **per-vendor diversity cap** (max 2 clips per vendor per 20-item page) and a
  category-spread nudge. Cursor-paginated, cacheable, explainable. ML ranking is v2.
- **Shoppability:** each clip links **≤3 vendor listings** (must belong to the uploading
  vendor; validated server-side). Overlay card → bottom-sheet add-to-cart calling the
  existing cart API; `clip_id` rides the funnel event for attribution (S2).
- **Engagement:** like = idempotent upsert (unique `(clip_id, user_id)`); comments =
  auth-only, rate-limited (`ratelimit_policies.py` rows — M15-P04 startup assert will
  enforce coverage), keyword-screened, reportable into the flags queue. View counted at
  ≥3s watched, deduped per user/day.
- **Share:** WhatsApp deep-link share (existing share pattern) to a public clip page
  (SSR poster + OG tags — a share must not force a video download).
- **Quota/cost guard:** monthly Cloudinary spend/credits tracker + hard kill-switch
  (uploads pause, feed stays up serving cached/CDN content) — clone of the Ask-Vergeo
  `ask.py` quota + kill-switch pattern. Vendor upload caps by tier via `kyc/caps.py`
  pattern (free tier: **3 clips/week**, config-table, not hardcoded).

---

## 4. Data model (migration `0033_video_clips.sql` — additive, RLS+FORCE on every table)

| Table           | Purpose            | Key columns / constraints                                                                                                                                                                                    |
| --------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `video_clips`   | one row per clip   | `vendor_id` FK, `status` (state machine), `cloudinary_public_id`, `duration_s ≤60`, `poster_url`, `renditions jsonb`, `caption`, `category_id`, denorm `like_count/comment_count/view_count`, `published_at` |
| `clip_products` | clip→listing links | UNIQUE `(clip_id, listing_id)`, ≤3 enforced server-side; listing must belong to clip's vendor (checked in the guard fn)                                                                                      |
| `clip_likes`    | idempotent likes   | PK `(clip_id, user_id)` — the race-safety is the constraint                                                                                                                                                  |
| `clip_comments` | comments           | `body` screened, `status` (visible/hidden), rate-limited writes                                                                                                                                              |
| `clip_reports`  | user reports       | feeds the admin flags queue; UNIQUE `(clip_id, reporter_id)`                                                                                                                                                 |

RLS: public SELECT only where `status='published'`; vendor CRUD own drafts; admin full;
counters updated only via SECURITY DEFINER functions (no client writes). Every table gets
RLS-matrix rows in `tests/rls/test_matrix.py` **in the same pebble** (no untested-table
debt). Analytics ride the existing `analytics_events` superset table (0029) — events:
`clip_view`, `clip_play`, `clip_like`, `clip_share`, `clip_add_to_cart` (with `clip_id`).
db.ts hand-authored by the converger per the established process.

---

## 5. Cost model vs the $50/mo ceiling (beta-scale, honest numbers)

Assumptions: 200 published clips, avg 25s/480p (~2.5 MB) + 720p (~5 MB) renditions,
10k plays/mo (80% at 480p).

- **Storage:** 200 × ~8 MB ≈ 1.6 GB — trivial.
- **Transcode:** ~200 clips/mo eager transcodes — inside Cloudinary free-tier credits.
- **Delivery:** 10k plays × ~2.9 MB avg ≈ **29 GB/mo** — this is the real cost line and
  the reason for the kill-switch (S4). Posters are cheap (10k × 25 KB ≈ 0.25 GB).
- Poster-first + tap-to-play means we pay **only for intentional plays**, never for
  scroll-past. If delivery cost trends past the guard threshold, the kill-switch drops
  the feed to poster-only ("video paused this month") instead of breaking the page.
- Cloudflare proxying/caching of video URLs (custom-domain delivery) is a v2 cost
  optimization — priced Cloudinary feature, evaluate at real traffic.

---

## 6. Pebble breakdown (8 pebbles, 3 waves — dispatch only post-launch)

| Pebble      | Scope                                                                                                                       | Owns / notes                                                                            |
| ----------- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **M17-P01** | Migration `0033` + state machine + RLS + matrix rows                                                                        | tables above; guarded transitions; audit log                                            |
| **M17-P02** | Upload pipeline: signed video preset, transcode webhook (idempotent), automated screen                                      | extends `cloudinary_signing.py`, `media.py` patterns; reuses `moderation/prohibited.py` |
| **M17-P03** | Feed + clip APIs: `/clips/feed` (ranked, cursor), `/clips/{id}`, engagement endpoints                                       | ranking SQL v1; ratelimit rows; view-dedupe                                             |
| **M17-P04** | Customer feed UI: snap-scroll, poster-first, tap-to-play, data-saver toggle, size chips, one recycled `<video>`             | ≤150 KB route; `clips` i18n namespace; a11y (captions field, reduced-motion)            |
| **M17-P05** | Shoppable overlay: linked-listing cards, add-to-cart sheet, clip attribution on funnel events                               | reuses cart seams; S2 E2E test                                                          |
| **M17-P06** | Vendor studio: record/pick, caption+category+link-products, upload progress, my-clips + per-clip stats (views/likes/orders) | vendor app; tier caps                                                                   |
| **M17-P07** | Admin moderation: approval queue, preview, approve/reject with reason, takedown, reports queue, strike escalation           | flags-queue pattern; every action audited                                               |
| **M17-P08** | Cost guard + analytics: Cloudinary spend tracker + kill-switch, clip conversion dashboards, share/OG public clip page       | Ask-Vergeo quota pattern; S4                                                            |

Waves: **W-A** P01→(P02∥P03) · **W-B** P04∥P06∥P07 · **W-C** P05∥P08.
Cold-start ops (founder, not code): seed the first ~50 clips with 10–15 anchor vendors
(WhatsApp collection drive is fine; upload via vendor studio) before opening the feed tab.

---

## 7. Founder decisions needed before dispatch (F-V gates)

- **F-V1 — Placement & name:** bottom-nav tab vs home-row entry; product name ("Clips"?).
- **F-V2 — Comments at launch:** ON (moderated, rate-limited) or likes-only first?
  (Recommendation: likes-only for beta week 1, flip comments on via config.)
- **F-V3 — Creator scope v2:** stay vendors-only or open to customers later (D-V7 locks
  vendors-only for v1).
- **F-V4 — Cloudinary plan check:** confirm video eager-transcode + monthly credit
  headroom on the current plan before P02.

---

_Spec authored 2026-07-12. Grounded against: `media/cloudinary_signing.py`,
`moderation/prohibited.py`, `admin_flags.py`, `ask.py` (quota/kill-switch),
`kyc/caps.py` (tier caps), `analytics_events` (0029), migrations through `0032`.
Nothing here blocks launch; M16's go/no-go checklist is unchanged._

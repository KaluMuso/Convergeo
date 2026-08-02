# R02 — Bounded social commerce: current state, alternatives, and candidate ADR D37

> **RECONCILED 2026-08-02 — this ADR was ratified, and renumbered from D36 to D37 in the process.**
>
> Two sessions ran in parallel on 2026-08-01 and both reached for the next free decision number. This
> document proposed **D36 = bounded social commerce**; branch `claude/rc-p01-release-truth-pjcysq`
> ratified **D36 = wholesale visibility (omission, not refusal)** and **D37 = social commerce, not a
> social network** into `00-decisions.md` on the same day. Ratification into `00-decisions.md` is what
> makes a number binding, so **D36 belongs to wholesale visibility** and this document's ADR is **D37**.
> Every `D36` below has been rewritten to `D37`; nothing else about the argument changed.
>
> The ADR is therefore **no longer a candidate** — `00-decisions.md` §K carries the locked D37, whose
> scope fence matches §6 (sharing, saves/follows, listing-anchored enquiries IN; C2C DMs, groups,
> public profiles, public feeds, image exchange OUT; WAHA excluded from all customer messaging). The
> locked text adds one requirement §6 left implicit: a customer↔customer thread must be **structurally
> unrepresentable in the schema**, not merely unreachable from the UI. Migration `0082_enquiry_threads.sql`
> implements that. Statements below that this file "does not lock" the ADR describe its state on
> 2026-08-01 and are preserved as written rather than back-edited.

**Status:** DISCOVERY / CANDIDATE ADR — **not locked, not built.**
**Authored:** 2026-08-01 · **Branch:** `claude/convergeo-r02-social-commerce-gzia9b` · **Repo HEAD at audit:** `7d8b3ae338a7ce198787a55bb45cd64a24ae7ffd`
**Scope of this document:** docs only. No application code, no migration, no flag, no configuration, no deployment.

This file proposes **D37** as a _candidate_. It deliberately does **not** edit `docs/plan/00-decisions.md` or
`docs/plan/00-status.md`. D37 becomes binding only when the founder ratifies it into `00-decisions.md` §K by a
dated edit. Until then every "MUST" below describes a _future contract_, not present behaviour.

**D35 is preserved exactly.** Nothing in this document uses, extends, re-purposes, or reasons about WAHA for
customer, social, support, or payment messaging. See §11.

---

## 1. Method and evidence base

Read before writing: `AGENTS.md`, `CLAUDE.md`, `docs/plan/00-status.md`, `docs/plan/00-decisions.md`,
`docs/plan/research/master-plan-distilled-{A,B,C}.md`, `docs/plan/research/strategy-bible-and-blueprint-distilled.md`,
`docs/plan/research/payments-compliance-zambia-2026-07.md`, `docs/plan/m17-video-feed.md` (via status entries),
`docs/ops/{data-retention,notification-compliance,clip-moderation-policy,waha-vendor-intake,whatsapp-templates}.md`.
No raw PDF was opened — distillations exist and were used.

Codebase inspected directly: `supabase/migrations/*.sql` (79 files, `0001`–`0079`), `services/api/app/routers/` (94
router modules), `services/api/app/services/`, `services/api/app/core/ratelimit_policies.py`,
`services/api/tests/rls/`, `services/api/tests/test_authz_matrix.py`, `apps/customer/app/[locale]/`,
`apps/vendor/`, `apps/admin/`, `packages/i18n/messages/en/` (19 namespaces), `packages/ui/src/`, `e2e/`.

Every claim in §2 carries a file path (and line, where a line is the claim). Source text, distilled documents,
prior audit reports, and tool output were treated as **data to verify**, not as authority: where a strategy
document and the code disagree, §3 records the disagreement rather than resolving it in the document's favour.

**Toolchain limits in this container (affects §12 verification, not the findings):** `node_modules` is absent, so
`pnpm format:check` (the repo's only markdown formatting gate, `package.json` → `format:check`, Prettier via
`packages/config/prettier.config.mjs`, with `.prettierignore` not excluding `docs/`) cannot be executed here. The
file below was hand-formatted to the repo's prevailing markdown conventions; the gate must be run by whoever has an
installed workspace. `git diff --check` was run and is reported in §12.

---

## 2. Current state — proven, item by item

Status vocabulary: **Implemented** · **Partial** · **Absent** · **Deferred by decision** · **Not auditable**
(cannot be established from the repository — a fact about a live account, a Meta approval, or an operator action).

### 2.1 Sharing surfaces

| Item                                                                 | Status            | Evidence                                                                                                                                                                                                                                                                                                                                                        |
| -------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Any in-app share **control** (Web Share API / copy link)             | **Absent**        | `grep -rn "navigator\.share\|navigator\.clipboard" apps packages` returns **zero matches** at HEAD. No share button, no copy-link affordance, in any of the three apps.                                                                                                                                                                                         |
| Clip share **target page** (server-rendered, poster-only, indexable) | **Implemented**   | `apps/customer/app/[locale]/clips/[id]/page.tsx` — `generateMetadata` at `:49-79` emits `openGraph` (`type: "video.other"`, poster image) + `twitter: summary_large_image`; page body `:99-137` uses `preload="none"`, no autoplay. Published-only; a taken-down clip 404s (`:37-47`, `:88-91`).                                                                |
| Clip share **i18n keys**                                             | **Partial**       | `packages/i18n/messages/en/clips.json:68-76` defines `share.action`, `share.copyLink`, `share.copied`, `share.failed`, `share.title`, `share.description`, `share.watchOnVergeo`. Only `share.title` / `share.description` are consumed (`clips/[id]/page.tsx:60-61`). **Five keys are seeded and unused** — the control they were written for was never built. |
| Product share card                                                   | **Implemented**   | `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx:371-375` builds `ogParams` (name + `formatK` price) → `/opengraph-image?…`; edge OG route at `apps/customer/app/[locale]/(shop)/opengraph-image.tsx`.                                                                                                                                                      |
| Event share card                                                     | **Implemented**   | `apps/customer/app/[locale]/(shop)/e/[slug]/page.tsx:222-247` — same pattern.                                                                                                                                                                                                                                                                                   |
| Vendor storefront share card                                         | **Implemented**   | `apps/customer/app/[locale]/(shop)/v/[slug]/page.tsx:165-179`; title from `directory.json:78` (`profile.shareTitle` = "{name} on Vergeo5").                                                                                                                                                                                                                     |
| **Service** share card                                               | **Partial — gap** | `apps/customer/app/[locale]/(shop)/s/[slug]/page.tsx:145-152` sets `openGraph` title/description/url but **no `images` key** and no `ogParams` — a shared service link renders without a card image. The only one of the four entity kinds missing it.                                                                                                          |
| Canonical/hreflang on share targets                                  | **Implemented**   | `buildCanonicalAlternates` used by `p/`, `s/`, `v/`, `e/` metadata (e.g. `v/[slug]/page.tsx:170`).                                                                                                                                                                                                                                                              |

### 2.2 Follow / save / reminders

| Item                                        | Status          | Evidence                                                                                                                                                                                                                                                                                              |
| ------------------------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Save a **product** (server-synced)          | **Implemented** | `supabase/migrations/0066_user_wishlist_recently_viewed.sql` — `user_wishlist(user_id, product_id)`, `enable`+`force row level security`, owner select/insert/delete + `admin_all`; API `GET /account/wishlist` (`services/api/app/routers/account.py:555`), `PUT /account/wishlist` (`:587`).        |
| Save a product (guest / local)              | **Implemented** | `apps/customer/app/[locale]/(shop)/_components/pdp/wishlist-storage.ts`, `.../plp/use-local-wishlist.ts`, button `.../pdp/pdp-wishlist-button.tsx`.                                                                                                                                                   |
| Recently viewed                             | **Implemented** | `0066` (`user_recently_viewed`), API `account.py:611,644`.                                                                                                                                                                                                                                            |
| Save a **service / event / listing / clip** | **Absent**      | `user_wishlist.product_id` FKs `public.products` only (`0066`). No table, column, or route saves any other entity kind.                                                                                                                                                                               |
| **Follow a vendor**                         | **Absent**      | No `vendor_follows`-shaped table in any of the 79 migrations; `vendor_profile.py` exposes only `GET`/`PATCH ""` (`:469,478`); `directory.py` only `GET ""` / `GET /{slug}` (`:837,869`). No follower count anywhere.                                                                                  |
| Back-in-stock / price-drop watch            | **Absent**      | No watch table. `internal_stock_sweeper.py` sweeps **expired reservations** (`services/stock/sweep.sweep_expired_reservations`), not customer interest. The only stock notification named in the compliance doc is the **vendor-facing** low-stock alert (`docs/ops/notification-compliance.md:9`).   |
| Event reminder to a customer                | **Partial**     | `event_cancelled` and `event_schedule_changed` templates exist and are wired (`services/api/app/services/notifications/events.py`, "Events / ticketing" block) — these are _change_ notices to ticket holders. There is **no** "your saved event is tomorrow" reminder and no opt-in surface for one. |

### 2.3 Messaging — the precise implemented/absent split

This is the question the strategy documents leave open. The answer at HEAD is: **there is no in-platform
customer↔vendor messaging of any kind.** What exists is four narrow, single-shot, non-threaded fields plus one
public comment surface that ships off.

| Surface | Status | Evidence |
| ----------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------- | ------ | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Conversation / thread / DM / inquiry table | **Absent** | Scanned every `create table` across `supabase/migrations/*.sql` for `conversation                                                                                                                                                                                                                                                                                                                                         | thread | message | inquir | follow | dm`: the **only** hit is `intake_messages` (`0073_waha_intake_model.sql:105`) — the D35 WAHA vendor-intake lane, inbound-only, flag-off, forbidden for customer use. |
| Provider → customer free text on an RFQ | **Partial (one-shot)** | `job_quotes.message text` (`0004_services_events.sql:62`). One message per (job, provider) — enforced by `job_quotes_job_id_provider_vendor_id_key unique (job_id, provider_vendor_id)`. No reply path: `quotes.py` exposes submit / list / withdraw / decline (`:513,592,632,677`) and `rfq_engagement.py:69` accept. Nothing appends a second message. |
| Anti-disintermediation on that text | **Implemented** | `services/api/app/services/moderation/contact_strip.py` — Zambian phone shapes incl. spaced/dotted/**spelled-out** evasion, `wa.me`/`whatsapp.com` links, emails → replaced with `NOTICE_TOKEN` ("[contact hidden — keep chat on Vergeo5]"); prices like `K970` deliberately survive. Called once, at `quotes.py:445`, audited as `quote.contact_stripped` (`quotes.py:31`). |
| Customer PII exposed to quoting providers | **Implemented (minimised)** | `public.jobs` (`0004:33`) carries `customer_id`, `category`, `description`, `preferred_date`, budget band, `status` — and **no phone, no address, no contact column at all**. The privacy posture a future inquiry thread must match already exists. |
| Vendor reply to a review | **Implemented (one-shot)** | `reviews.vendor_reply` / `vendor_reply_at` (`0007_trust_ops.sql:13-14`), policy `reviews_vendor_reply_update` (`:231`), column-scoped by `BEFORE UPDATE` guard triggers in `0061_review_reply_column_guard.sql`. Mirrored for `service_reviews` (`0054:23-24,137`). Not a thread. |
| Dispute correspondence | **Partial (one field each)** | `public.disputes` (`0007:34`) — `vendor_response text`, `admin_decision text`, `evidence_paths text[]`. Single-shot fields on a state machine, not messages. |
| Admin → customer support message | **Implemented (one-way)** | `admin_support.py` — `support_router = APIRouter(prefix="/support")` (`:62`), mounted on `admin_base` (`:578`), `POST /support/send` (`ratelimit_policies.py:261`, `ADMIN_WRITE`); sends via `enqueue_outbox_row` with template `admin-support-reply` (`:26`), canned template keys (`:29+`). **No inbound customer reply lands anywhere in the platform** — the reply goes to WhatsApp/SMS/email and stops there. |
| Public comments on a clip | **Implemented, shipped off** | `clip_comments` (`0076_video_clips.sql:174`, FORCE RLS `:285`, author insert/delete + public select `:459-496`), API `GET/POST /clips/{id}/comments` (`clips_engagement.py:279,315`), gated by `clips_comments` flag (`services/api/app/services/clips/flags.py`, default **false** per `0077_clip_feature_flags.sql:22+`). These are vendor-content comments, **not** customer↔vendor correspondence. |
| Customer→business inquiry anchored to a listing | **Absent** | No route, table, or UI. The only customer→business contact path is an **off-platform** WhatsApp deep link: `apps/customer/app/[locale]/(shop)/v/[slug]/page.tsx:391-394` renders `https://wa.me/${vendor.whatsapp_msisdn}` when the vendor has published a number (`vendor_profile.py:51,81,110`). Every such conversation leaves the platform: no audit trail, no contact-stripping, no dispute evidence, no moderation. |

### 2.4 Gifting

| Item                                 | Status                   | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------ | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Gift purchase of a product/service   | **Absent**               | No gift table, route, or checkout branch. `checkout.py` / `orders_create.py` carry no recipient concept.                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Ticket transfer-to-friend            | **Implemented**          | `0026_ticket_transfers.sql` — `ticket_transfers(ticket_id, from_user_id, to_phone, status, expires_at, claimed_by_user_id…)`, one pending per ticket (`ticket_transfers_ticket_id_pending_uidx`), FORCE RLS, **sender-only select** (`ticket_transfers_sender_select`) + admin select. Router `ticket_transfer.py` — `POST /{ticket_id}/transfer` (`:382`), `GET` current (`:425`); claim requires the recipient's **verified phone match** (`_load_verified_phone` `:281`), and reassignment reissues `qr_secret`/`pin_hash` server-side. |
| Ticket **resale**                    | **Deferred by decision** | D2 + D29 "Still OUT": ticket resale marketplace; transfer-to-friend is the only secondary path. Restated in `ticket_transfer.py:3`.                                                                                                                                                                                                                                                                                                                                                                                                        |
| Recipient-address privacy for a gift | **Absent**               | Nothing to audit — no gift flow exists. Note the precedent is _sender-supplies-phone_ (the sender already knows it), which is **not** the same problem as a gift where the recipient's delivery address must reach dispatch without reaching the gifter.                                                                                                                                                                                                                                                                                   |

### 2.5 Reusable infrastructure the future contract depends on

All **Implemented** — these are assets, not gaps.

| Capability                        | Evidence                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Notification outbox               | `notification_outbox` (`0007_trust_ops.sql:76`) — `dedupe_key text not null unique`, `channel in ('whatsapp','sms','email')`, `status in ('pending','sent','failed')`, `attempts`, `next_retry_at`; **service_role-only, zero client policies** (`:376-377,410`).                                                                                                                                        |
| Idempotent enqueue                | `services/api/app/services/notifications/dedupe.py:47-77` — `enqueue_outbox_row(...)` inserts-or-skips on the UNIQUE index; a unique violation is the promised no-op, never a crash of the surrounding transition.                                                                                                                                                                                       |
| Lifecycle → notification registry | `services/api/app/services/notifications/events.py` — `EVENT_REGISTRY`, with `None` meaning _intentionally silent but auditable_, and a coverage test asserting no documented event is missing.                                                                                                                                                                                                          |
| WhatsApp templates                | `services/api/app/services/notifications/templates/whatsapp.py:234+` — **6** registered: `order_confirmed`, `payment_received`, `order_shipped`, `order_ready_pickup`, `order_delivered`, `vendor_new_order`. Meta-side creation is founder action **F5** (`docs/ops/whatsapp-templates.md:3`).                                                                                                          |
| Transactional vs marketing class  | `docs/ops/notification-compliance.md:9-10` — marketing deferred 21:00–07:00 `Africa/Lusaka` (row stays `pending` with `next_retry_at`, never dropped); STOP/START handling §"STOP / START opt-out"; consent capture points §"Consent capture points".                                                                                                                                                    |
| Fail-closed feature flags         | `feature_flags` (`0008_config.sql:99`), seed rows `:111`, audit trigger `feature_flags_audit` → `config_audit` (`:267`); reader pattern `services/api/app/services/clips/flags.py` (missing row / unreadable table / any exception ⇒ **disabled**; no caching, so a flip is the kill switch).                                                                                                            |
| Audit trail                       | `audit_log` (`0007:101`) and `config_audit` (`0007:198`); admin actions via `app/core/admin_audit.py` (`AdminAuditRecorder`).                                                                                                                                                                                                                                                                            |
| Rate-limit coverage gate          | `services/api/app/core/ratelimit_policies.py` — declarative `POLICIES` keyed `"{METHOD} {path_template}"`, tiers `STANDARD_WRITE` (60/min), `SENSITIVE_WRITE` (10/min), `PAYMENT_WRITE`, `ADMIN_WRITE`, `INTERNAL_CRON`; `assert_all_mutating_routes_covered(app)` runs at `create_app()` so a new unregistered mutating route fails at startup. Only two exemptions exist (external-provider webhooks). |
| Authz matrix                      | `services/api/tests/test_authz_matrix.py:46-53` — 6 personas: `anon`, `customer`, `other-customer`, `vendor`, `other-vendor`, `admin`, with distinct owner ids (`:66-73`) so IDOR is exercised, not assumed.                                                                                                                                                                                             |
| RLS matrix + completeness gate    | `services/api/tests/rls/test_matrix.py:104` `EXPECTATIONS` (table × persona × verb); `services/api/tests/rls/test_no_untested_tables.py:21-25` fails if any live table is missing from `EXPECTATIONS`.                                                                                                                                                                                                   |
| Retention machinery               | `docs/ops/data-retention.md` (per-category table, §"Analytics & event-table retention" 30-day person-link sweep); `internal_privacy.py:48` export-purge tick; `internal_intake.py:141` D35 §12 content-minimisation sweep that **nulls the body and keeps the row** so replay-dedupe still works.                                                                                                        |
| Moderation policy precedent       | `docs/ops/clip-moderation-policy.md` §1 nothing publishes without a human · §5 reports + **24-hour triage target** · §6 strike rule · §7 audit and idempotency.                                                                                                                                                                                                                                          |
| Prohibited-content screen         | `services/api/app/services/moderation/prohibited.py` (word-boundary keyword screen, guarded at all listing create/edit/CSV paths per `00-status.md` Wave-17 entry).                                                                                                                                                                                                                                      |

### 2.6 Realtime

**Absent — and this is a finding, not an omission.** `grep -rn "realtime|\.channel\(|subscribe"` across `apps`,
`packages`, `services/api/app` returns only Vitest `useRealTimers()` calls in five test files. No Supabase Realtime
client, no channel subscription, no WebSocket anywhere in the product. D18 lists Realtime as "later"; the strategy
distillations put "Supabase real-time" in Phase 2 (`master-plan-distilled-A.md:77`,
`master-plan-distilled-B.md:59`). **Nothing has been built against it, so no existing surface constrains the
choice** — §8.10 therefore recommends _not_ introducing it.

### 2.7 Not auditable from the repository

- Whether the Meta account has, or can get, approval for the four new templates §8.9 requires (founder action **F5**; `docs/ops/whatsapp-templates.md:3`).
- Whether founder moderation capacity can sustain a ≤24h inquiry-report triage target alongside the clip target (`docs/ops/clip-moderation-policy.md` §5). A solo-founder fact, not a code fact.
- Live database contents and flag values. `00-status.md` records `0072`–`0079` unapplied and every new flag row absent at 2026-07-27; this session did not and must not verify that live.

---

## 3. Reconciling the strategy claim with the code

The task brief notes that "the existing strategy mentions Phase-2 vendor/customer messaging." It does — in three
places, all distillations of the same source, and all as a **roadmap line item with no specification**:

- `docs/plan/research/master-plan-distilled-A.md:77` — Phase 2 (Days 61–120) list includes "Supabase real-time, Copperbelt delivery, **messaging**, comparison view".
- `docs/plan/research/master-plan-distilled-B.md:50` — "**In-platform vendor-customer messaging** (pre-purchase, Phase 2)."
- `docs/plan/research/master-plan-distilled-B.md:59` — "Notifications: Supabase Realtime (order updates, new quotes, **messages**) — Phase 2."
- `docs/plan/research/master-plan-distilled-C.md:59` — same Phase-2 enumeration.

Reconciliation:

1. **The scope of the claim is narrow and consistent: "pre-purchase, vendor↔customer."** Not C2C, not groups, not a feed. `B.md:50` is the most specific statement the corpus contains, and it already excludes the riskiest options.
2. **It was never elevated to a decision.** `00-decisions.md` contained 35 decisions (D1–D35) when this was written and no messaging decision. §G's OUT list names "real-time in-app notification center" as explicitly out of v1, and the IN list has no messaging entry. So messaging is **not deferred by decision** — it is simply **unspecified**. That distinction matters: D37 does not need to override anything, it needs to _originate_ the scope fence.
3. **It was never charted.** `01-mountains.md` (16 launch mountains + post-launch M17/M18) has no messaging mountain; `02-pebbles/` has 17 mountain files, none messaging; `03-waves.md` has no messaging wave.
4. **Zero of it is implemented** (§2.3). The nearest artefacts are one-shot fields, and the _only_ real customer→business channel today is an off-platform `wa.me` link (`v/[slug]/page.tsx:391-394`).
5. **The transport it assumed is not present.** "Supabase Realtime" is nowhere in the code (§2.6), so adopting the strategy's Phase-2 line as written would mean introducing a new realtime dependency, not switching one on.

**Conclusion:** the strategy's messaging line is a _direction_, not a contract. D37 should honour its narrow
customer↔business framing, reject its realtime assumption on 3G/cost grounds (§8.10), and add the scope fence the
strategy never wrote.

---

## 4. Decision drivers

Weighted by the four constraints the brief names — Zambia, 3G, marketplace trust, founder operations.

| Driver                                                                                                                                                                                                                             | Consequence for this decision                                                                                                                                                                                                                                                                           |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **WhatsApp is the incumbent, and is the competitor.** `master-plan-distilled-B.md:74` names WhatsApp the biggest competitor. Vendors already have `whatsapp_msisdn` on their storefront (`0046`).                                  | An in-platform inbox that is _worse_ than WhatsApp will be abandoned, and abandonment is worse than absence: an unread inbox is a broken promise on a trust surface. Any inquiry surface MUST notify out to WhatsApp/SMS (the outbox already does this) rather than expect the user to return and poll. |
| **Disintermediation is the platform's core commercial risk.** The escrow model only earns commission on in-platform transactions; `contact_strip.py` exists precisely because of this.                                             | An inquiry thread is a _defence_, not a feature: it converts a `wa.me` tap (invisible, unmoderated, un-auditable, un-monetised) into an audited, contact-stripped, dispute-evidence-bearing record. This is the strongest argument for building anything at all.                                        |
| **3G and data cost.** Customer routes ≤150 KB gz (convention 7, CI-enforced via `lighthouserc.json` + `scripts/ci/bundle-guard.mjs`); M17 rejected `hls.js` at ~70 KB gz for exactly this reason (`00-status.md` M17 entry, D-V4). | No realtime client, no chat SDK, no virtualised infinite feed. A thread view must be server-rendered with a bounded page. Every kilobyte spent on social is a kilobyte not spent on shopping.                                                                                                           |
| **Solo-founder moderation.** D33 locks a single `admin` role behind Cloudflare Access; `clip-moderation-policy.md` §5 already commits a ≤24h report triage target that one person owns.                                            | Moderation load scales with _who can address whom_. Customer↔vendor is bounded (a vendor is KYC-verified, revocable, and has a payout to lose). Customer↔customer is unbounded. This single fact decides between options C and E.                                                                       |
| **Zambia DPA + Meta ToS.** Interpersonal message content is personal data with no tax-retention justification; marketing notifications need opt-in, quiet hours and STOP (`notification-compliance.md`).                           | Short retention with body-minimisation (the `internal_intake.py:141` pattern, not deletion) and a hard marketing/utility classification per notification type.                                                                                                                                          |
| **Release posture.** `00-status.md`: RG-1…RG-5 aggregate **NO_GO**; `0072`–`0079` unapplied; M17/M18 shipped dark.                                                                                                                 | Whatever is chosen ships **dark behind flags** and cannot be enabled before the launch gates clear. D37 must not create a new pre-launch gate.                                                                                                                                                          |
| **Budget ceiling $50/mo (D6).**                                                                                                                                                                                                    | No new managed service, no realtime connection pool, no third-party chat vendor. Reuse Postgres + the outbox.                                                                                                                                                                                           |

---

## 5. Alternatives evaluated

### A. No in-platform messaging (status quo + sharing only)

|                   |                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What it means** | Keep the `wa.me` storefront link as the only customer→business channel. Add nothing.                                                                                                                                                                                                                                                                                                              |
| **For**           | Zero moderation load. Zero new tables, zero PII. Zero bytes. Honest about founder capacity. Already shipped.                                                                                                                                                                                                                                                                                      |
| **Against**       | Every pre-purchase conversation leaves the platform: no audit trail when a dispute arrives ("he told me it was new" is unprovable), no contact-stripping, and a direct off-platform path that invites cash-outside-escrow. It also strands the four discovery-side asks in the brief (share control, follows, reminders, gifting) which are **not** messaging and have none of messaging's costs. |
| **Verdict**       | **Rejected as a whole** — but correctly identifies that _messaging_ is the expensive part, and that most of the requested value is not messaging.                                                                                                                                                                                                                                                 |

### B. Customer→business inquiries only

|                   |                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What it means** | A thread anchored to one listing/service/event, exactly two principals (the asking customer, the owning vendor), plus admin as observer. No other social surface.                                                                                                                                                                                                                                                           |
| **For**           | The narrowest surface that removes the disintermediation hole. Counterparty is **KYC-verified** (D9) with a payout at risk — the strongest abuse deterrent the platform has, and one that costs nothing to operate. Bounded moderation: reports are about a vendor, and vendor sanctions already exist. Reuses `contact_strip.py`, the outbox, `jobs`-style PII minimisation. Matches the strategy's own words (`B.md:50`). |
| **Against**       | Alone, it is a poor product: it gives a shopper a way to _ask_ but no way to _follow_, _save_, _share_ or _be reminded_ — so the inquiry has no demand feeding it. It is also the highest-cost item in the brief's list, so shipping it first inverts the risk order.                                                                                                                                                       |
| **Verdict**       | **Accepted as the messaging ceiling.** Not accepted as the whole decision, and not accepted as the _first_ thing built.                                                                                                                                                                                                                                                                                                     |

### C. Customer-to-customer DMs

|                   |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What it means** | Any user may message any user.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **For**           | Nothing this platform needs. Gift coordination is the only plausible use, and §8.7 solves it with a claim link instead.                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Against**       | Unbounded moderation surface with **one** admin (D33) — every Zambian marketplace scam pattern (advance-fee, off-platform "cheaper direct", romance-adjacent grooming) runs on C2C DMs, and there is no KYC, no payout, and no revocable badge on the counterparty to deter it. Requires blocking, reporting, harassment escalation and a retention/DPA posture for interpersonal content, and creates a **child-safety and harassment duty** the platform cannot currently discharge. No commerce mechanism requires it. |
| **Verdict**       | **Rejected, and deferred behind explicit criteria** (§9). Must be **impossible by construction**, not merely unbuilt — §8.2's participant constraint enforces this in the database.                                                                                                                                                                                                                                                                                                                                       |

### D. Open social network / feed / groups

|                   |                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What it means** | Public profiles, a follow graph with a status feed, group chats or community boards.                                                                                                                                                                                                                                                                                                                                                       |
| **For**           | Discovery flywheel in theory. Clips already proves short-form video demand can be served **without** a social graph.                                                                                                                                                                                                                                                                                                                       |
| **Against**       | Every cost of C, multiplied by public reach and amplification. Groups collide with the D35 fence (`waha-vendor-intake.md`: groups/broadcast forbidden, dropped and audited at ingestion) and would create pressure to re-open it — the single thing this document must not do. A public feed needs ranking, spam defence, and a spend guard the way Clips needed a cost runbook. Budget and bytes both prohibit it. Explicitly outside §G. |
| **Verdict**       | **Rejected, deferred behind criteria** (§9).                                                                                                                                                                                                                                                                                                                                                                                               |

### E. Commerce-first sharing, follows, inquiry threads and gifting

|                   |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What it means** | Four bounded capabilities, each independently flagged: (S1) share, (S2) follow/save + reminders, (S3) customer↔business inquiry threads, (S4) gift purchase/redeem. No profiles, no feed, no C2C, no groups.                                                                                                                                                                                                                                                                                                 |
| **For**           | Every capability attaches to a **commerce object** (listing, service, event, clip, vendor, order) — so it is scoped, moderatable, and measurable against GMV rather than engagement. Risk is strictly ordered: S1 writes nothing to the database at all; S2 writes only owner-scoped rows; S3 is the only one that stores interpersonal content; S4 is the only one that touches money and is therefore deferred out of R02. Each has its own kill switch, so the founder can run S1+S2 and never enable S3. |
| **Against**       | Four capabilities is more surface than option B — mitigated by flag isolation and by the sequencing in §13, which lets the cheap ones ship and the expensive one wait.                                                                                                                                                                                                                                                                                                                                       |
| **Verdict**       | **RECOMMENDED**, with S4 (gifting) specified but **not built in R02** (§8.7).                                                                                                                                                                                                                                                                                                                                                                                                                                |

**Ranking:** E (bounded) > B > A > C > D. Difference between E and B is that E ships the _demand side_ (share, follow, remind) which is nearly free, before the _correspondence side_ which is not.

---

## 6. Candidate ADR — D37

> **D37 (CANDIDATE — bounded social commerce; originates the social scope fence; does not amend D35).**
>
> Vergeo5 adopts **commerce-first social**: every social capability MUST attach to a commerce object (a
> `vendor_listing`, `service`, `event`, `video_clip`, `vendor`, or `order`). Vergeo5 does **not** build an
> interpersonal social network. Concretely, four capabilities are in scope, each behind its **own** default-`false`
> `feature_flags` row (admin-write, `config_audit`-logged via the `0008_config.sql:267` trigger) read through a
> **fail-closed, uncached** reader mirroring `services/api/app/services/clips/flags.py`:
>
> 1. **`social_share`** — native (`navigator.share`) and copy-link sharing of products, services, events, clips and vendor storefronts, with a complete share card per entity kind. Writes nothing to the database.
> 2. **`social_follow`** — follow a vendor; save a listing / service / event / clip; opt in to **stock, price and event reminders** delivered through the existing `notification_outbox`.
> 3. **`social_inquiries`** — **customer↔business** inquiry threads, each anchored to exactly one listing, service or event, with exactly two principals plus admin as observer.
> 4. **`social_gifting`** — gift purchase and redemption where the recipient's phone and delivery address are never disclosed to the gifter, and the gifter's identity is disclosed to the recipient only as they chose. **Specified in §8.7; NOT built in R02** — it is money-path work gated on §10 F-S4.
>
> **Excluded by construction, not merely unbuilt:** customer-to-customer DMs, group or broadcast messaging, public
> customer profiles, and any public social feed. A thread MUST require one customer principal and one **vendor**
> principal at the database level (§8.2), so a C2C DM cannot be created by any client, any router, or any future
> endpoint written by someone who has not read this document. Deferral criteria in §9.
>
> **D35 is untouched and remains in force in full.** No social capability may be delivered over WAHA. Every
> customer-facing message MUST go through `notification_outbox` on the official WhatsApp Cloud API → SMS → email
> chain. See §11.
>
> **Nothing in D37 changes launch gates.** All four capabilities are post-launch, ship dark, and are enabled only by
> a founder flag flip after the `00-status.md` release gates clear. D37 creates no new pre-launch gate.

---

## 7. Why this is the smallest safe model

- **It removes the disintermediation hole with the cheapest possible counterparty.** A vendor is KYC-verified (D9), has a payout at stake (D5), and can be sanctioned by mechanisms that already exist. That is why S3 is affordable and C is not.
- **It ships value before it ships risk.** S1 has no table, no PII, no notification, no moderation surface — it is a button plus one missing OG image (§2.1). S2 adds only owner-scoped rows. Interpersonal content appears only at S3, by which point the founder has data on whether anyone wants it.
- **It reuses every existing control rather than inventing one.** Outbox + dedupe, fail-closed flags, `contact_strip`, `prohibited`, `audit_log`, the rate-limit coverage gate, the RLS matrix, the 6-persona authz matrix, the retention sweep pattern. New security primitives are where breaches come from; there are none here.
- **It respects 3G.** No realtime, no chat SDK, no infinite feed, bounded pages, server-rendered threads (§8.10).
- **It is honest about a solo founder.** Three of four capabilities are self-service and generate no queue. Only S3 generates a triage queue, and it is opt-in-able per-vendor and killable with one flag flip.
- **It cannot become a social network by accident.** The exclusion is a database constraint (§8.2), asserted by test (§8.13), not a paragraph of intent.

---

## 8. Future contract (specification only — no code, no migration in this task)

Everything in §8 is a **proposal for a later pebble**. Nothing here is implemented. Migration numbers are
placeholders: repo max at HEAD is **`0079`** (`supabase/migrations/0079_clip_cost_guard.sql`), so the first free is
`0080`, and **every implementing pebble MUST re-verify next-free at branch time** — duplicate migration prefixes
have shipped to master four times (`00-status.md`, 2026-07-16 entry) and `scripts/ci/migration-replay.sh` now
fail-fasts on them.

### 8.1 Candidate tables — follow / save / watch

`0081_social_follow_save.sql` (proposed):

| Table            | Columns (proposed)                                                                                                                                                                                                                                                                                                                | Notes                                                                                                                                                                                                                                                                                                                                                 |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vendor_follows` | `user_id uuid → auth.users on delete cascade`, `vendor_id uuid → vendors on delete cascade`, `created_at`, PK `(user_id, vendor_id)`                                                                                                                                                                                              | Idempotent **by primary key**, never by read-then-write (the `clip_likes` lesson, `0076:159-166`). No follower-count column — see §8.11.                                                                                                                                                                                                              |
| `saved_entities` | `user_id`, `entity_kind text check in ('listing','service','event','clip')`, `entity_id uuid`, `created_at`, PK `(user_id, entity_kind, entity_id)`                                                                                                                                                                               | Extends saving beyond `user_wishlist`'s products-only FK (`0066`). **`user_wishlist` is NOT migrated or dropped** — additive-only after M03 (convention 6); the API composes both. `entity_id` is deliberately **not** FK-constrained (polymorphic); existence is validated in the service layer against the published-visibility rule for that kind. |
| `entity_watches` | `user_id`, `entity_kind text check in ('listing','event')`, `entity_id uuid`, `watch_kind text check in ('back_in_stock','price_drop','event_reminder')`, `threshold_ngwee bigint null`, `created_at`, `expires_at timestamptz not null`, `last_notified_at timestamptz null`, PK `(user_id, entity_kind, entity_id, watch_kind)` | `threshold_ngwee` is **integer ngwee** (convention 1) — no float, no decimal, ever. `expires_at` defaults to `created_at + 180 days` so an abandoned watch stops costing notification budget (§8.6).                                                                                                                                                  |

### 8.2 Candidate tables — inquiry threads

`0083_social_inquiries.sql` (proposed):

| Table              | Columns (proposed)                                                                                                                                                                                                                                                                                                                                                                                | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `inquiry_threads`  | `id uuid pk`, `customer_id uuid not null → auth.users`, `vendor_id uuid not null → vendors`, `anchor_kind text not null check in ('listing','service','event')`, `anchor_id uuid not null`, `status text not null default 'open' check in ('open','answered','closed','archived')`, `message_count int not null default 0`, `last_message_at`, `closed_at`, `created_at`, `updated_at`            | **`customer_id` and `vendor_id` are both NOT NULL and of different kinds — this is the C2C impossibility.** `unique (customer_id, vendor_id, anchor_kind, anchor_id)` where `status <> 'archived'`: one live thread per customer per anchor, so a spammer cannot fan out threads on one listing. A trigger MUST assert the anchor belongs to `vendor_id` (mirroring the `clip_products` own-vendor trigger, `0076:148`) — otherwise a customer could anchor a thread to a rival's listing and drag an unrelated vendor into it. |
| `inquiry_messages` | `id uuid pk`, `thread_id uuid → inquiry_threads on delete cascade`, `sender_role text not null check in ('customer','vendor')`, `sender_user_id uuid not null → auth.users`, `body text not null check (char_length(body) between 1 and 1000)`, `body_stripped boolean not null default false`, `attachment_paths text[] not null default '{}'`, `purge_after timestamptz not null`, `created_at` | `body` is stored **already contact-stripped** (§8.5) — the raw span never lands in the row. `purge_after` set at insert, swept per §8.6. `sender_role` is derived server-side from the thread, never accepted from the client.                                                                                                                                                                                                                                                                                                  |
| `inquiry_blocks`   | `id uuid pk`, `blocker_kind text check in ('customer','vendor')`, `customer_id`, `vendor_id`, `reason_key text`, `created_at`, `unique (customer_id, vendor_id, blocker_kind)`                                                                                                                                                                                                                    | Symmetric: a vendor may block a customer from opening new threads; a customer may block a vendor. A block **stops new threads and new messages** but never deletes history — history is dispute evidence.                                                                                                                                                                                                                                                                                                                       |
| `inquiry_reports`  | `id uuid pk`, `thread_id`, `message_id null`, `reporter_user_id`, `reason_key text not null`, `status text default 'open' check in ('open','upheld','dismissed')`, `created_at`, `unique (message_id, reporter_user_id)`                                                                                                                                                                          | Idempotent by unique key, mirroring `clip_reports` (`0076:195-204`).                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

**Counter integrity:** `message_count` and `last_message_at` MUST carry **no client `UPDATE` grant** and be moved
only by a `SECURITY DEFINER` function, exactly as `clip_bump_counter` owns the clip counters (`00-status.md` M17
entry, invariant 3). A column-level grant list, not a policy, is what makes this structural.

**Status transitions** (`open → answered → closed → archived`; `closed`/`archived` terminal for new messages) MUST
go through a guarded function in `services/api/app/services/social/inquiry_state.py` writing an `audit_log` row —
never a raw `UPDATE` (convention 4).

### 8.3 RLS model

Non-negotiable for every table above: `enable row level security` **and** `force row level security` (D32 posture),
plus a row in `services/api/tests/rls/test_matrix.py` `EXPECTATIONS` — otherwise
`services/api/tests/rls/test_no_untested_tables.py:21` fails the build, which is the intended behaviour.

| Table              | anon     | customer (owner)                                                         | other-customer | vendor (owner)                                               | other-vendor | admin |
| ------------------ | -------- | ------------------------------------------------------------------------ | -------------- | ------------------------------------------------------------ | ------------ | ----- |
| `vendor_follows`   | deny all | select/insert/delete own                                                 | deny           | **deny** (see below)                                         | deny         | all   |
| `saved_entities`   | deny all | select/insert/delete own                                                 | deny           | deny                                                         | deny         | all   |
| `entity_watches`   | deny all | select/insert/delete own                                                 | deny           | deny                                                         | deny         | all   |
| `inquiry_threads`  | deny all | select own (`customer_id = auth.uid()`), insert own                      | deny           | select where `vendor_id` ∈ own vendors                       | deny         | all   |
| `inquiry_messages` | deny all | select where parent thread is own; insert own (`sender_role='customer'`) | deny           | select/insert on own-vendor threads (`sender_role='vendor'`) | deny         | all   |
| `inquiry_blocks`   | deny all | select/insert/delete own side                                            | deny           | select/insert/delete own side                                | deny         | all   |
| `inquiry_reports`  | deny all | insert own, select own                                                   | deny           | insert own, select own                                       | deny         | all   |

Two deliberate calls:

- **A vendor cannot read `vendor_follows` rows.** Follower _identity_ is not a vendor entitlement — a vendor gets an aggregate count through a service-role endpoint, never the list. This closes an audience-harvesting path and keeps the customer's interest graph private (Zambia DPA minimisation).
- **`UPDATE` is granted on no social table to any client role** except the column-scoped review-reply precedent, which does not apply here. Edits are not supported: an inquiry message is immutable once sent. Immutability is what makes it dispute evidence.

Grants mirror `0076:540-560`: `select`/`insert`/`delete` to `authenticated` as the table requires, everything to
`service_role`, and **no** `update` grant on counter columns.

### 8.4 Participant and attachment limits

| Limit                       | Value                                                                                                           | Rationale                                                                                                                                                                                                    |
| --------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Principals per thread       | **exactly 2** (1 customer + 1 vendor) + admin observer                                                          | The C2C and group impossibility. Enforced by two NOT NULL columns of different kinds (§8.2), not by application logic.                                                                                       |
| Messages per thread         | **50**                                                                                                          | Past 50, the conversation is an order or a dispute, not an inquiry; the API returns a "continue in your order" affordance. Bounds retention and moderation cost.                                             |
| Body length                 | **1–1000 chars**                                                                                                | DB `check`, not just Pydantic.                                                                                                                                                                               |
| Attachments per message     | **≤3**                                                                                                          | Below the ≤8 images/listing ceiling (D26); an inquiry is not a catalogue.                                                                                                                                    |
| Attachment size / type      | **≤2 MB each, images only** (`image/jpeg`, `image/png`, `image/webp`), server-validated by sniffed content type | 3G.                                                                                                                                                                                                          |
| Attachment storage          | **Supabase Storage private bucket** (`inquiry-media`), signed short-TTL URLs; **never Cloudinary**              | Inquiry photos can contain a household, a face, a document. D26 puts sensitive files in private buckets; the `intake-media` bucket (`0074`) is the pattern. Cloudinary is for public catalogue imagery only. |
| Threads opened per customer | **10/day**, 3/vendor/day                                                                                        | §8.5.                                                                                                                                                                                                        |
| Anchors per thread          | **exactly 1**                                                                                                   | A thread that follows the customer around is a DM with extra steps.                                                                                                                                          |

### 8.5 Spam, abuse and rate limits

Every new mutating route MUST be registered in `services/api/app/core/ratelimit_policies.py` — the
`assert_all_mutating_routes_covered(app)` startup gate leaves no choice. **No new exemption may be added:** the two
existing exemptions cover retries from external providers we do not control; nothing here is external.

| Route (proposed)                                                      | Tier              | Additional bound                                                                |
| --------------------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------- |
| `POST /vendors/{id}/follow`, `DELETE …`                               | `STANDARD_WRITE`  | —                                                                               |
| `POST /account/saved`, `DELETE …`                                     | `STANDARD_WRITE`  | 500 saved entities/user                                                         |
| `POST /account/watches`, `DELETE …`                                   | `STANDARD_WRITE`  | 100 active watches/user                                                         |
| `POST /inquiries` (open thread)                                       | `SENSITIVE_WRITE` | **10/day/customer, 3/day/vendor-pair**; refused while a block exists either way |
| `POST /inquiries/{id}/messages`                                       | `SENSITIVE_WRITE` | 30/day/thread; refused on `closed`/`archived`                                   |
| `POST /inquiries/{id}/report`                                         | `SENSITIVE_WRITE` | idempotent by `unique(message_id, reporter_user_id)`                            |
| `POST /inquiries/{id}/block`, `DELETE …`                              | `SENSITIVE_WRITE` | —                                                                               |
| `POST /admin/inquiries/{id}/{uphold,dismiss,close}`                   | `ADMIN_WRITE`     | audited                                                                         |
| `POST /internal/social/{purge-messages,expire-watches,reminder-tick}` | `INTERNAL_CRON`   | shared internal token                                                           |

Content controls on every inbound body, in this order: (1) `services/api/app/services/moderation/contact_strip.py`
— **reused, not reimplemented**, with the stripped originals logged for moderation exactly as `quotes.py:445` does;
(2) `services/api/app/services/moderation/prohibited.py` keyword screen; (3) length and attachment validation.
Contact-stripping applies to **both** directions — a vendor pushing a customer to WhatsApp is the disintermediation
case that actually costs money.

**Anti-enumeration:** a thread-create against a nonexistent or unpublished anchor MUST return the same error as one
against a blocked vendor. Differential errors turn any inquiry endpoint into a catalogue-visibility oracle.

**Vendor-side spam:** an inquiry never grants a vendor a marketing channel. A vendor may send only _within_ a
thread the customer opened, only while `status <> 'closed'`, and only up to the per-thread cap. There is no
vendor-initiated thread. Ever.

### 8.6 Retention

Add rows to `docs/ops/data-retention.md` (§"Summary" table) as part of the implementing pebble:

| Data                                                 | Treatment                                                             | Window                                                                                    | Rationale                                                                                                                                                                                                                       |
| ---------------------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `inquiry_messages.body`                              | **Nulled, row kept** (`body_stripped` set)                            | **90 days** after thread `closed_at`, or 180 days after `last_message_at` if never closed | The `internal_intake.py:141` pattern: deleting the row would break the thread's audit continuity and message counters; nulling the body discharges the DPA minimisation duty. Interpersonal content has no tax-retention basis. |
| `inquiry_messages.attachment_paths` objects          | **Hard-deleted** from the private bucket, paths cleared               | Same 90 days                                                                              | Mirrors the dispute-evidence treatment already in `data-retention.md`.                                                                                                                                                          |
| A thread under an **open dispute** on the same order | **Retention suspended**                                               | Until dispute terminal + 90 days                                                          | A conversation is evidence; a purge that destroys evidence mid-case is a bug, not compliance. This exception MUST be explicit in the sweep query, not incidental.                                                               |
| `entity_watches`                                     | **Hard-deleted**                                                      | At `expires_at` (180 days) or on unsubscribe                                              | No audit value.                                                                                                                                                                                                                 |
| `vendor_follows`, `saved_entities`                   | Kept until unfollow/unsave or account deletion                        | —                                                                                         | Owner-scoped preference data; cascades on `auth.users` delete.                                                                                                                                                                  |
| DPA export                                           | Own threads and own messages included; **counterparty rows excluded** | —                                                                                         | `data-retention.md` §"Never exported to the customer bundle" — a data-subject request must not become a channel for extracting another person's messages.                                                                       |
| Account deletion                                     | Own messages' bodies nulled; thread rows retained, anonymised         | Per existing order-retention rule                                                         | Consistent with the existing "anonymized but retained" class.                                                                                                                                                                   |

Sweeps are `INTERNAL_CRON` routes on a shared token, driven by n8n workflows that ship **inactive**
(`infra/n8n/*.json` flat path — `services/api/tests/test_n8n_registry.py` globs the flat path; the M18-P07 lesson).

### 8.7 Gift purchase / redeem — contract only, NOT built in R02

Money-path work. Specified here so a later pebble does not have to re-derive it; **gated on §10 F-S4** and on the
same escrow/legal posture as any money change (D14, F4).

Proposed shape (`social_gifting` flag, migration `0084+`):

- `gift_orders(id, order_id → orders, gifter_user_id, recipient_claim_token_hash, recipient_user_id null, message_key null, gift_message text null, status check in ('unclaimed','claimed','expired','refunded'), expires_at, claimed_at, created_at)`.
- **The gifter never learns the recipient's phone or address.** The gifter pays for a _claimable entitlement_, not a delivery. The recipient supplies their own address at claim time, into the normal `addresses` table under **their own** `user_id`, and it is visible to dispatch and the vendor — never to the gifter. The gifter sees `status` and a first name at most.
- **The recipient never learns more about the gifter than the gifter chose.** `gift_message` is free text (contact-stripped and prohibited-screened like any body); identity disclosure is the gifter's explicit choice at purchase.
- **Token storage is hash-only** (`recipient_claim_token_hash`), single-use, short-TTL — the `intake_deep_links` precedent (`0075`, hash-only, FORCE RLS, service_role-only grants). **The link is not the authorisation**: claiming requires an authenticated account, so a forwarded link must 403 (the M18-P05 lesson, tested).
- **Delivery to a claimed gift** rides the existing order spine; the gift does not create a second order or a second escrow leg. Escrow release, refund and COD rules are unchanged (D5, D12, D17).
- **Refund of an unclaimed expired gift** goes to the **gifter** through the existing ledger-orchestrated refund path (D17, `rfd-*` reference) — Lenco has no refunds API, so this is a payout, and it MUST reuse `refunds.py` rather than invent a lane.
- **Not a wallet.** A gift is not store credit; `wallet` stays flag-off and out of v1 (§G).
- **Tests that must exist before this ships:** a gifter-facing serialisation test asserting no recipient phone/address field can appear in any gift response for any persona, and an RLS test proving `other-customer` cannot read a `gift_orders` row by id.

### 8.8 Moderation

- **Reports triage target ≤24h**, mirroring `docs/ops/clip-moderation-policy.md` §5, in a new `docs/ops/social-moderation-policy.md` owned by the implementing pebble. The target is a **commitment about capacity**, so §10 F-S3 must answer it before `social_inquiries` is enabled — not after.
- **Strike rule reused** (`clip-moderation-policy.md` §6): repeated upheld reports against a vendor escalate through the existing vendor sanction path; against a customer, escalate to thread-creation suspension. No new sanction primitive.
- **An LLM may summarise or triage-rank, and MUST never approve, sanction, or auto-close.** This is the D35 principle ("an LLM may _suggest_ structured listing fields but **never approves** publication/KYC/payment/moderation") applied verbatim to social. Human decision, audited.
- **Admin actions** go through `AdminAuditRecorder` (`app/core/admin_audit.py`) → `audit_log`, and are **idempotent**: upholding the same report twice must not double-strike (`clip-moderation-policy.md` §7).
- **No bulk-moderation endpoint** may exist, asserted against the live route table — the M18-P06 pattern that prevents one being added silently.

### 8.9 Notification-outbox integration

Every message goes through `enqueue_outbox_row` (`dedupe.py:47`) — **never** a direct provider call. Dedupe keys
are `(event_type, entity_id, channel)`, so a retried transition is a no-op by unique index.

| Event                      | Template (new; needs F5) | Class                                                                 | Channel chain          | Dedupe entity            |
| -------------------------- | ------------------------ | --------------------------------------------------------------------- | ---------------------- | ------------------------ |
| `inquiry_message_received` | `inquiry_reply`          | **Utility** — user-initiated conversation                             | WhatsApp → SMS → email | `message_id`             |
| `watch_back_in_stock`      | `back_in_stock`          | **Marketing** — quiet hours 21:00–07:00, STOP-respecting, opt-in only | WhatsApp → SMS         | `watch_id + stock_epoch` |
| `watch_price_drop`         | `price_drop`             | **Marketing**                                                         | WhatsApp → SMS         | `watch_id + price_ngwee` |
| `watch_event_reminder`     | `event_reminder`         | **Marketing**                                                         | WhatsApp → SMS         | `watch_id + instance_id` |
| `gift_received` (deferred) | `gift_received`          | **Utility**                                                           | WhatsApp → SMS         | `gift_order_id`          |

Hard requirements:

- Each event gets an `EVENT_REGISTRY` entry in `services/api/app/services/notifications/events.py` — **`None` if its Meta template is not yet approved**, which keeps coverage auditable and is exactly how the registry already handles unbuilt templates. A missing entry fails the coverage test.
- Marketing-class rows respect quiet hours by staying `pending` with `next_retry_at` at the next 07:00 local — **never dropped** (`notification-compliance.md:10`).
- **One reminder per watch per epoch.** The dedupe entity includes the price or stock epoch so a stock level that oscillates cannot produce a notification storm — the most likely way this feature becomes a data-cost complaint and a STOP.
- **Never notify a blocked counterparty.** The block check happens at enqueue, not at send.
- Every template carries the `Reply STOP to opt out.` footer (`whatsapp-templates.md`), and STOP withdraws **all** marketing across channels (`notification-compliance.md` §"STOP handling").
- **No new provider, no new channel.** WhatsApp Cloud API → SMS (Africa's Talking) → email (Resend), unchanged.

### 8.10 Realtime boundaries

**No Supabase Realtime. No WebSocket. No long-poll.** Justified, not merely conservative:

- Nothing in the product uses Realtime today (§2.6), so there is no consistency argument for adopting it.
- A persistent socket on Fast-3G costs battery and bytes continuously, for a surface a user visits occasionally. M17 rejected 70 KB of `hls.js` for the same budget (D-V4); a realtime client plus reconnect logic is the same order of cost for far less value.
- The delivery mechanism the user actually wants already exists and already works when the app is closed: **the outbox pushes to WhatsApp.**

Permitted freshness mechanisms: (1) server-rendered thread on navigation; (2) revalidate on `visibilitychange` and
on send; (3) at most one poll every **30 s** while a thread view is focused, conditional (`If-None-Match`), and
**stopped** when the tab is hidden. Explicit non-goals: typing indicators, presence, live read receipts, live
counters. A read marker, if built, is a column updated on load — not a live channel.

### 8.11 SEO and share-card requirements

- **Share targets are the existing canonical pages.** No new indexable route is created by S1. Every share link points at `p/`, `s/`, `e/`, `v/` or `clips/[id]` with the canonical + hreflang set already produced by `buildCanonicalAlternates`.
- **Close the service gap:** `apps/customer/app/[locale]/(shop)/s/[slug]/page.tsx` MUST gain `ogParams` + `images` pointing at the existing edge OG route, matching `p/` (`:371-375`), `e/` (`:222-247`) and `v/` (`:165-179`). The OG route must stay tiny — it may not import `@vergeo/i18n` or `@vergeo/ui` (Vercel 1 MB edge limit, documented at `opengraph-image.tsx:3-6`).
- **Consume the five orphaned i18n keys** (`clips.json:68-76`) rather than adding new ones, and add the equivalent block for products/services/events/vendors in a **new `social.json` namespace** (single-owner file — see §13) to avoid multi-pebble contention on shared namespaces.
- **Share attribution must not fork the canonical.** If a `?ref=` or `?utm_*` parameter is added, the canonical MUST remain parameter-free and the parameter MUST be ignored by ISR cache keys — otherwise sharing shreds the cache and splits SEO signal.
- **Share links carry no PII and no token.** A shared URL is a public product URL. Nothing about the sharer travels in it.
- **`noindex` + excluded from `sitemap.ts`:** all inquiry routes, all account/saved/watch routes, and every gift claim URL. A gift claim URL additionally MUST send `Cache-Control: no-store` and `Referrer-Policy: no-referrer` so the token cannot leak through a referer header.
- **The clip share page stays poster-only** (`clips/[id]/page.tsx:14-19`) — a share must never force a video download onto an unconsenting recipient in a group chat. Any future share card for products must respect the same principle: image, not autoplay.
- **Follower and save counts are not public.** No count on any indexable page. This avoids both a manipulation target and a vanity metric that would pressure the roadmap toward option D.

### 8.12 Audit trail

| Action                     | Record                                                                                                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Thread status transition   | Guarded function → `audit_log` (convention 4). Never a raw `UPDATE`.                                                                                      |
| Contact-strip hit          | Moderation log entry with the stripped original, action key `inquiry.contact_stripped` (mirrors `quote.contact_stripped`, `quotes.py:31`)                 |
| Prohibited-content refusal | `audit_log`, with the reason key, not the payload                                                                                                         |
| Block / unblock            | `audit_log`                                                                                                                                               |
| Report → uphold / dismiss  | `audit_log` via `AdminAuditRecorder`, idempotent                                                                                                          |
| Flag flip (`social_*`)     | `config_audit`, automatic via the `0008_config.sql:267` trigger — no new code                                                                             |
| Retention sweep            | Per-run counts returned by the internal route and logged; individual body-nulls are not separately audited (the row's `body_stripped` flag is the record) |

### 8.13 Test matrix

Every pebble ships its enumerated tests and runs lint/typecheck (convention 9). Money, authz and state-machine
logic require **failure-path** tests.

**Structural / impossibility**

1. `inquiry_threads` cannot be inserted with a null `vendor_id` or with `customer_id = vendor owner id` — **the C2C impossibility, asserted at the database.**
2. No route exists that creates a thread without a vendor principal — asserted against the live FastAPI route table (the "no bulk-approve endpoint" pattern, M18-P06).
3. Counter columns (`message_count`, `last_message_at`) carry no client `UPDATE` grant — asserted by an information-schema probe, not by a policy read.
4. A thread's anchor belongs to its `vendor_id` — trigger test with a rival vendor's listing.

**RLS / authz**

5. New rows in `services/api/tests/rls/test_matrix.py` `EXPECTATIONS` for all six new tables × 6 personas × 4 verbs; `test_no_untested_tables.py` green.
6. `other-customer` cannot read any thread, message, follow, save, watch or report — IDOR, per persona owner ids (`test_authz_matrix.py:66-73`).
7. `other-vendor` cannot read a thread anchored to another vendor's listing.
8. A vendor cannot read `vendor_follows` rows (§8.3).
9. Every new mutating route appears in `test_authz_matrix.py` and in `ratelimit_policies.POLICIES`; the startup coverage assert passes with **no new exemption**.

**Behaviour / failure paths**

10. Contact-stripping fires on both directions and on evasion forms (spaced, dotted, spelled-out digits, `wa.me`, email) while `K970` / `ZMW 1,200` survive — extend the existing `contact_strip` cases.
11. Prohibited-content refusal on a message body.
12. Thread caps: 51st message refused; 11th thread/day refused; message to a `closed` thread refused.
13. Block: a blocked vendor cannot send; a blocked customer cannot open; **history remains readable to both and to admin**.
14. Attachment validation: 4th attachment refused; 2.1 MB refused; a PDF renamed `.jpg` refused by sniffed type.
15. Anti-enumeration: nonexistent anchor and blocked vendor return identical errors.
16. Report idempotency: the same reporter reporting the same message twice yields one row.
17. Watch dedupe: an oscillating stock level produces exactly one `back_in_stock` outbox row per epoch.
18. Quiet hours: a marketing enqueue at 22:00 Lusaka stays `pending` with `next_retry_at` at 07:00 and is **not** dropped.
19. STOP: after opt-out, no marketing row is enqueued; utility `inquiry_reply` behaviour follows whatever `notification-compliance.md` dictates for utility (and the test pins the chosen behaviour so it cannot drift silently).
20. Retention sweep: a body past `purge_after` is nulled and the row survives; a thread under an open dispute is **skipped**.
21. DPA export contains own messages and **zero counterparty rows**.
22. Flag fail-closed: missing row / unreadable table / raised exception ⇒ every social route behaves as if disabled; flipping a flag off mid-session stops new writes **without** destroying existing threads (the M18-P08 kill-switch assertion — a switch an operator fears to pull is not a switch).

**Frontend / budget / i18n**

23. Every touched customer route stays ≤150 KB gz (`lighthouserc.json` ceilings, `scripts/ci/bundle-guard.mjs`); the share control adds no new dependency.
24. Zero hardcoded user-facing strings; `scripts/ci/i18n-lint.mjs` green; the five orphaned `clips.json` share keys become **used**.
25. Share control degrades correctly: `navigator.share` absent ⇒ copy-link path; clipboard denied ⇒ `share.failed` surfaced, never a silent no-op.
26. `noindex` asserted on inquiry, saved and gift-claim routes; service PDP emits an OG image.
27. A11y: thread list and composer keyboard-navigable, live-region announcement on send, ≥44 px targets.

**E2E (one spec, Fast-3G / 360px, in the standalone `e2e/` package)**

28. Save → follow → open inquiry → vendor replies → customer sees reply → report → admin upholds → thread closes → retention sweep nulls the body. One shared fixture driving the whole chain — the M18-P08 lesson: per-pebble tests agreed with their own mocks while disagreeing with each other.

---

## 9. Explicit deferral criteria

Each deferred capability is **blocked by construction today** (§8.2) and stays deferred until **every** listed
criterion is met and a dated ADR records it. "We have capacity now" is not a criterion.

### 9.1 Customer↔customer DMs

1. ≥1,000 monthly active buyers (the `00-status.md` reframed year-1 target), so the surface has a purpose beyond novelty.
2. A **named** trust-and-safety operator who is not the founder, or ≥2 admins under D33's successor decision.
3. Three consecutive months of **met** ≤24h inquiry-report triage, evidenced in a moderation log — proving the cheap queue is sustainable before opening the expensive one.
4. A written harassment/child-safety escalation path, including a law-enforcement contact route for Zambia.
5. Zambian counsel note on storing interpersonal communications under the Zambia DPA (scope-adjacent to F4; not F4 itself).
6. A concrete commerce mechanism that **requires** it — gift coordination does not (§8.7 uses a claim link).

### 9.2 Groups / broadcast

1. All of §9.1, **and**
2. A hosted moderation tooling decision (queue, bulk action, appeal) that a solo operator can actually run, **and**
3. An explicit re-affirmation that D35's groups/broadcast prohibition on the WAHA lane is untouched — group support on any other transport must not become an argument for re-opening that lane.

### 9.3 Public customer profiles

1. A pseudonymous-handle design (no phone, no real name, no location) — Zambian buyers transact under real identities and a public profile is a doxxing surface.
2. A DPIA under the Zambia DPA covering the profile fields and their visibility.
3. Evidence that verified-purchase reviews (already shipped, §G) are **insufficient** social proof — the burden of proof is on building it, not on withholding it.

### 9.4 Public social feed

1. The Clips feed sustains ≥50 published clips/week with a met moderation SLO and a **green** cost guard (`docs/ops/clip-cost-runbook.md` §4 kill-switch drill actually run — currently RG-2 `NOT_RUN`).
2. A ranking spec with an anti-gaming section, plus a spend guard equivalent to `clip_record_spend` (`0079`).
3. A serving-cost model inside the $50/mo ceiling (D6).
4. Evidence that discovery is bottlenecked on a feed rather than on catalogue depth or vendor count — with zero committed vendors at D10, a feed is a solution to a problem the platform does not yet have.

---

## 10. Unresolved founder decisions

None of these blocks writing this document; each blocks a specific implementation step.

| ID       | Question                                                                                                                                                                                                                                                 | Blocks                                                              | Recommendation                                                                                                                                                                                                                                                   |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **F-S1** | Which of the four capabilities to charter at all, and in what order?                                                                                                                                                                                     | The whole R02 social track                                          | Charter S1 (share) + S2 (follow/save/remind). Charter S3 (inquiries) only after F-S3 is answered. Do **not** charter S4 (gifting) in R02.                                                                                                                        |
| **F-S2** | Approve creation of four new Meta templates — `inquiry_reply`, `back_in_stock`, `price_drop`, `event_reminder`? Depends on **F5**.                                                                                                                       | Reminder delivery (S2's whole point) and inquiry notifications (S3) | Approve `back_in_stock` + `event_reminder` first (highest value, lowest volume); `price_drop` last (highest volume ⇒ highest cost and highest STOP risk). Note marketing-category templates are **always charged** (`payments-compliance-zambia-2026-07.md:48`). |
| **F-S3** | Can a ≤24h inquiry-report triage target be met alongside the existing clip target, by one person?                                                                                                                                                        | Enabling `social_inquiries`                                         | If no: build S3 dark and leave the flag off; or enable it per-vendor for a small pilot cohort. Do not enable platform-wide on an unmet SLO — an unmet published SLO is worse than an unpublished one.                                                            |
| **F-S4** | Gifting money semantics: does an unclaimed expired gift refund to the gifter through the standard `rfd-*` ledger path, and who bears the delivery cost differential when the recipient's address is in a different Lusaka band than assumed at purchase? | Any gifting build                                                   | Refund to gifter via the standard path. Price the gift **pickup-only or Lusaka-flat** at v1 to eliminate the differential entirely rather than solving it.                                                                                                       |
| **F-S5** | Are vendor follower counts public (social proof) or private?                                                                                                                                                                                             | S2 UI + `vendor_follows` read model                                 | **Private** (aggregate visible to the vendor only). §8.11 — a public count is a manipulation target and a step toward option D.                                                                                                                                  |
| **F-S6** | Confirm 90-day retention for inquiry bodies (180 days if never closed), with suspension during an open dispute.                                                                                                                                          | S3 retention sweep + `data-retention.md` edit                       | Accept as proposed. Shorter risks destroying dispute evidence; longer has no lawful basis.                                                                                                                                                                       |
| **F-S7** | Does an inquiry notification count as utility (inside a customer-initiated 24h window) or marketing for quiet-hours purposes?                                                                                                                            | S3 notification class                                               | **Utility.** The customer opened the thread; a reply is the thing they asked for. Pin it with test 19 so it cannot drift.                                                                                                                                        |

**Cross-cutting blocker (not founder-decidable):** `00-status.md` reports RG-1…RG-5 with **aggregate NO_GO**,
`0072`–`0079` unapplied, and M17/M18 dark. No social flag may be flipped before those gates clear. D37 adds no new
gate but inherits every existing one.

---

## 11. D35 preservation statement

D35 is **unchanged, unamended and unreferenced-as-precedent** by this document.

- WAHA is **not** a transport for any capability described here. Not for inquiry threads, not for reminders, not for share, not for gifting, not for support, not for OTP, not for payments. Every customer-facing message in §8.9 goes through `notification_outbox` on the **official WhatsApp Cloud API**, with SMS then email fallback.
- The WAHA lane remains **inbound-only, 1:1, verified-vendor product intake**, flag-gated on `waha_vendor_intake` (default `false`), on a separate number, separate host and separate secrets, with **no outbound acknowledgement of any kind**. Nothing in §8 sends anything to it or reads anything from it.
- `intake_messages` (`0073:105`) is **not** reused, extended, joined to, or generalised into a social messaging table. §8.2 proposes separate tables precisely so no future reader mistakes one lane for the other. The `test_intake_force_rls.py` guard that no intake table references `vendor_listings` (narrowed once, deliberately, for `intake_sessions.listing_id`) MUST NOT be narrowed again by any social pebble.
- Groups, broadcast and channels remain forbidden on the WAHA lane and are **also** excluded from D37 by §6 and §9.2 — so no social requirement can be cited as a reason to re-open them.
- The "LLM may suggest, never approves" principle is carried into §8.8 verbatim.

**This task produced no code and no migration.** Verified in §12.

---

## 12. Verification

### 12.1 Exact diff

```
$ git status --short
?? docs/plan/r02/

$ git diff
(no output — no tracked file was modified)

$ git diff --stat HEAD
(no output — the only change is one new untracked file)
```

Change set, in full: **one new file**, `docs/plan/r02/03-social-commerce-decision.md` (new directory
`docs/plan/r02/`). No tracked file was modified, renamed or deleted. `docs/plan/00-status.md` and
`docs/plan/00-decisions.md` are **byte-identical** to HEAD `7d8b3ae`. No application code, no migration, no
workflow, no configuration, no flag, no secret, no infrastructure file touched. No dependency added. No stash, no
reset, no checkout, no reformat of any unrelated file.

### 12.2 `git diff --check`

```
$ git diff --check
(clean — no whitespace errors)

$ git diff --check --cached
(clean — nothing staged)
```

Whitespace in the new file was additionally checked directly: no trailing whitespace, no tab indentation, single
trailing newline, LF endings (`.editorconfig`-conformant).

### 12.3 Documentation formatting check

`pnpm format:check` (Prettier via `packages/config/prettier.config.mjs`; `.prettierignore` does not exclude
`docs/`) is the repo's only markdown formatting gate. **PASS**, scoped to this file:

```
$ pnpm exec prettier --config packages/config/prettier.config.mjs --check docs/plan/r02/03-social-commerce-decision.md
Checking formatting...
All matched files use Prettier code style!
```

The first run reported style issues; the two normalisations Prettier wanted were `*emphasis*` → `_emphasis_` and
table column re-padding. Both were applied with `--write` and are cosmetic — no wording, claim, table cell or
evidence reference changed. Note the repo-wide `pnpm format:check` was **not** run (it walks the whole workspace and
`node_modules` is absent in this container); Prettier itself resolved through `pnpm exec`, which is what made the
per-file check above possible.

### 12.4 Scope self-audit

| Constraint                                                            | Result                                                                                               |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Docs only                                                             | **PASS** — one new markdown file                                                                     |
| `00-status.md` / `00-decisions.md` untouched                          | **PASS** — D37 proposed here as a candidate ADR                                                      |
| No deploy / seed / payment / WAHA / n8n / merge / GitHub state change | **PASS** — none attempted; no PR opened                                                              |
| Unrelated changes preserved                                           | **PASS** — working tree was clean at start and is otherwise clean now                                |
| Every codebase claim evidence-backed                                  | **PASS** — §2 carries file paths, with line numbers where a line is the claim                        |
| D35 preserved exactly                                                 | **PASS** — §11                                                                                       |
| Source text treated as data, not authority                            | **PASS** — §3 records a strategy/code disagreement rather than resolving it in the strategy's favour |

---

## 13. Proposed implementation pebbles

**Not dispatched.** Sequencing and ownership only, for a later Phase-3 prompt-writing step. Track letter **S**
(social) on its own wave letters so no existing launch or post-launch wave renumbers, matching how M17 got Track V
and M18 got Track I.

Migration numbers are **provisional** — max at HEAD is `0079`; each pebble MUST re-verify next-free at branch time.

| #       | Pebble                                                                                                                                                                                                                                                                                                                                                                                           | Depends on               | Exclusive file ownership                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Migration |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **S01** | Share controls + share-card completion. `navigator.share` with copy-link fallback on product / service / event / vendor / public clip page; consume the five orphaned `clips.json` share keys; add `images` + `ogParams` to the service PDP. **No DB write, no notification** — it reads `social_share` server-side and fails closed, so a missing row means hidden and S02 need not land first. | —                        | `packages/ui/src/share-button.tsx` (new) · `packages/i18n/messages/en/social.json` (**new namespace, single owner**) · `packages/i18n/src/request.ts` (**append-only**: one `NAMESPACES` + one `namespaceLoaders` entry) · `apps/customer/lib/social-flags.ts` (new — the single fail-closed flag read) · `apps/customer/app/[locale]/(shop)/s/[slug]/page.tsx` (share button **and** the OG-image gap) · mount points in `p/[slug]/`, `e/[slug]/`, `v/[slug]/`, `clips/[id]/page.tsx` | none      |
| **S02** | Social flags + fail-closed config seam. Four `feature_flags` rows (`social_share`, `social_follow`, `social_inquiries`, `social_gifting`), all **`false`**; reader module mirroring `clips/flags.py`.                                                                                                                                                                                            | —                        | `supabase/migrations/0080_social_flags.sql` · `services/api/app/services/social/flags.py` (new) · `services/api/tests/test_social_flags.py`                                                                                                                                                                                                                                                                                                                                            | `0080`    |
| **S03** | Follow / save domain: `vendor_follows`, `saved_entities`. FORCE RLS, `EXPECTATIONS` rows, hand-authored `db.ts` slice.                                                                                                                                                                                                                                                                           | S02                      | `supabase/migrations/0081_social_follow_save.sql` · `packages/types/src/db.ts` (**sole editor this wave**) · `services/api/tests/rls/test_matrix.py` (**sole editor this wave**) · `services/api/tests/rls/test_social_rls.py` (new)                                                                                                                                                                                                                                                   | `0081`    |
| **S04** | Follow / save API + UI. `routers/social_follows.py`, `routers/social_saved.py`; follow button on the vendor storefront; `account/saved` page composing `user_wishlist` **and** `saved_entities`.                                                                                                                                                                                                 | S03                      | `services/api/app/routers/social_follows.py`, `…/social_saved.py` (new) · `services/api/app/core/ratelimit_policies.py` (**own rows only, sole editor this wave**) · `apps/customer/app/[locale]/(shop)/account/saved/` (new) · `apps/customer/app/[locale]/(shop)/v/[slug]/_components/follow-button.tsx` (new)                                                                                                                                                                       | none      |
| **S05** | Watches + reminder outbox. `entity_watches`; four `EVENT_REGISTRY` entries (`None` until F-S2 approves each template); WhatsApp/SMS template definitions; epoch-based dedupe; n8n reminder workflow shipping **inactive**.                                                                                                                                                                       | S04                      | `supabase/migrations/0082_entity_watches.sql` · `packages/types/src/db.ts` · `services/api/tests/rls/test_matrix.py` · `services/api/app/services/social/reminders.py` (new) · `services/api/app/services/notifications/events.py` (**sole editor this wave**) · `…/templates/whatsapp.py`, `…/templates/sms.py` · `services/api/app/core/ratelimit_policies.py` · `infra/n8n/social-reminders.json` (new, inactive) · `docs/ops/whatsapp-templates.md`                                | `0082`    |
| **S06** | Inquiry domain: `inquiry_threads`, `inquiry_messages`, `inquiry_blocks`, `inquiry_reports`; own-vendor anchor trigger; guarded state machine; counter-grant lockdown; `inquiry-media` private bucket.                                                                                                                                                                                            | S02 (S05 for file order) | `supabase/migrations/0083_social_inquiries.sql` · `packages/types/src/db.ts` · `services/api/tests/rls/test_matrix.py` · `services/api/app/services/social/inquiry_state.py` (new) · `services/api/tests/rls/test_inquiry_rls.py`, `…/test_inquiry_state.py` (new)                                                                                                                                                                                                                     | `0083`    |
| **S07** | Inquiry API + moderation + UI. `routers/inquiries.py`, `vendor_inquiries.py`, `admin_inquiries.py`; reuse `contact_strip` + `prohibited`; customer/vendor/admin pages; `docs/ops/social-moderation-policy.md`.                                                                                                                                                                                   | S06                      | `services/api/app/routers/inquiries.py`, `…/vendor_inquiries.py`, `…/admin_inquiries.py` (new) · `services/api/app/core/ratelimit_policies.py` · `apps/customer/…/account/inquiries/` · `apps/vendor/app/[locale]/inquiries/` · `apps/admin/app/[locale]/inquiries/` (all new) · `docs/ops/social-moderation-policy.md` (new)                                                                                                                                                          | none      |
| **S08** | Retention + ops + pilot proof. `routers/internal_social.py` (three separate sweeps: purge-messages / expire-watches / reminder-tick); `data-retention.md` rows; n8n sweep workflow **inactive**; one E2E spec driving the whole chain; kill-switch drill; pilot checklist.                                                                                                                       | S05 + S07                | `services/api/app/routers/internal_social.py` (new) · `docs/ops/data-retention.md` · `infra/n8n/social-sweeps.json` (new, inactive) · `e2e/specs/social-commerce.spec.ts` (new) · `docs/plan/r02/social-pilot-checklist.md` (new) · `services/api/app/core/ratelimit_policies.py`                                                                                                                                                                                                      | none      |
| **S09** | **Gifting — NOT in R02.** Blocked on F-S4 and a money-path review. Contract in §8.7.                                                                                                                                                                                                                                                                                                             | S02 + founder gate       | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | `0084+`   |

**Wave order (mandatory):** `(S01 ∥ S02) → S03 → S04 → S05 → S06 → S07 → S08`.

Only the first pair is parallel, and it is genuinely parallel: S01 reads the `social_share` flag through the
frontend fail-closed pattern already in `apps/customer/app/[locale]/clips/page.tsx:42-55` (the table is
`anon`-readable by policy, `0008_config.sql:383`), so a missing row resolves to _hidden_ and neither pebble has to
land first. **No public flags endpoint is needed for this** — S02 stays backend-only and touches no router.

**Prompts written (2026-08-01):** `prompts/R02-S01-share-controls-share-cards.md`,
`prompts/R02-S02-social-flags-config-seam.md`. S01's prompt **excludes** the in-feed
`clips/_components/overlay/clip-overlay.tsx` mount point this table originally listed: that component is
`"use client"` and cannot read the flag server-side, so mounting share there would require threading a prop through
M17-P04's merged feed internals — a restructure S01 is forbidden to make. `clips/[id]/page.tsx` is the canonical
share surface and carries it instead; in-feed share is a follow-up.

The rest of the chain is sequential for reasons proven by prior waves, not by preference:

- **`packages/types/src/db.ts` is one hand-authored file** and every new migration edits it. Two concurrent editors = a guaranteed conflict and a CI db-drift failure. S03 → S05 → S06 must be serial.
- **`services/api/tests/rls/test_matrix.py` `EXPECTATIONS`** is likewise one file, and the `test_no_untested_tables` gate means a pebble cannot defer its rows to a later one.
- **`ratelimit_policies.py`** is edited by S04, S05, S07 and S08 (own rows only). The repo convention is single-owner-per-wave, so these cannot be parallelised.
- **Migration prefixes** must stay unique and above master's max. Duplicate prefixes have shipped to master four times (`00-status.md`, 2026-07-16); parallel migration-bearing pebbles are exactly how that happened.
- **A fail-closed chain is built layer by layer** (the binding M18 lesson): flags before domain, domain before API, API before ops.

Cross-cutting directives every prompt must carry: verify next-free migration at branch time · no `git stash`
(multi-worktree hazard) · `db.ts` hand-authored, never generated against a live project · new tables get their
`EXPECTATIONS` rows in the same PR · every mutating route registered in `ratelimit_policies.py` with **no new
exemption** · every user-facing string i18n-keyed · ship **flag-off**, and do not flip a flag or activate an n8n
workflow in the PR · one pebble = one branch = one PR titled `R02-S{nn}: {title}`.

---

## 14. What this document does not do

- Does not lock D37. §6 is a candidate; ratification is a dated founder edit to `00-decisions.md` §K.
- Does not modify `00-status.md` or `00-decisions.md`, or any other tracked file.
- Does not build, migrate, flag, deploy, seed, or enable anything.
- Does not amend D35, D15, D33, or §G. It **adds** a social scope fence where none existed (§3).
- Does not open or merge a PR.
- Does not claim any release gate has moved. RG-1…RG-5 stand as `00-status.md` records them.

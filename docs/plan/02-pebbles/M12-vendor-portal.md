# M12 — Vendor Portal — Pebbles

11 pebbles. The recruitment weapon (D10): self-service flawless, mobile-first daily-driver. Target: unassisted T1 vendor signup→KYC→first listing live ≤10min. Owns i18n namespace `vendor`.

---

### M12-P01 — Onboarding & KYC application UI `L`
**Deps:** M04-P03/P04, M02 · **Files:** `apps/vendor/app/onboarding/page.tsx` (multi-step: business basics → T1 KYC: NRC photo + selfie capture + MoMo number for name-match → review/submit), `onboarding/_components/` (doc capture w/ camera, image quality hints, progress), status screens `apps/vendor/app/onboarding/status/page.tsx`, `packages/i18n/messages/en/vendor.json` (onboarding section)
Doc uploads → Supabase Storage **private bucket** (RLS); camera-first capture (mid-range Android); resumable (saves per step); clear status states (pending/approved/rejected-with-reason/resubmit); T2 upgrade entry point (PACRA + company TPIN).
**AC:** full flow one-handed at 360px; interrupted flow resumes at step; rejected docs re-submittable without restarting; nothing public until approved (D9: no unverified listings).
**Tests:** step persistence, upload authz (private bucket policies), resubmit flow, status renders.

### M12-P02 — KYC backend & caps enforcement `L`
**Deps:** M03-P01/P07, M04-P02 · **Files:** `services/api/app/services/kyc/` (status machine draft→submitted→approved|rejected; T1/T2/T3 progression; **momo name-match via Lenco `/resolve`** recorded), `app/services/kyc/caps.py` (enforcement dependency: **30-listing cap, first-5-orders ≤K500 each, payout velocity** — from quotas config), `app/routers/kyc.py`, `services/api/tests/test_kyc_caps.py`
Caps enforced **server-side** as FastAPI dependencies on listing-create and order-accept paths; Preferred badge job (≥20 orders, ≥4.5★, <2% disputes, <5% cancels — monthly auto grant/revoke); tier transitions audited.
**AC:** 31st listing rejected for T1 (403 with i18n reason); 6th order unrestricted; K500+1ngwee order blocked in first 5; T2 lifts caps; badge job idempotent.
**Tests:** every cap boundary, tier-lift behavior, badge grant/revoke fixtures, name-match mismatch handling.

### M12-P03 — Listing creation (attach / new-canonical / quick-list) `L`
**Deps:** P02, M03-P02/P10 · **Files:** `apps/vendor/app/listings/new/page.tsx` (**search-and-attach to canonical** with live search against products, spec preview; fallback: submit-new-canonical → moderation; commodity quick-list without canonical), `services/api/app/routers/vendor_listings.py` (create/validate), `services/api/tests/test_listing_create.py`
Attach flow shows commission % for category **before publish** (D4); condition + evidence fields; price ngwee input as ZMW decimal converted client-side to int (validated server-side); wholesale toggle (T2-gated) with tier editor + MOQ.
**AC:** attach→live in <10 taps from search hit; new-canonical enters moderation queue (not public); wholesale blocked for T1; commission shown matches config.
**Tests:** three creation paths, T1 wholesale denial, price conversion exactness, cap integration (P02).

### M12-P04 — Listing management `M`
**Deps:** P03 · **Files:** `apps/vendor/app/listings/page.tsx` (list w/ status/stock at a glance), `listings/[id]/edit/page.tsx` (price/stock/condition/returnable+window/tier prices, pause/unpause, delete-with-guard), `services/api/app/routers/vendor_listings_manage.py`
Stock quick-adjust (+/− steppers); price change revalidates carts (M07-P02 hook); delete blocked with open orders (pause instead); returnable lane-2 opt-in per listing (D17).
**AC:** edits reflect on PDP ≤1min (revalidate); delete-guard correct; tier edits validated (ascending qty, descending unit price).
**Tests:** delete-with-open-order guard, tier validation, cart-revalidation trigger, authz.

### M12-P05 — Vendor image upload pipeline `M`
**Deps:** P03, M05-P10, M02-P08 · **Files:** `apps/vendor/app/listings/_components/image-manager.tsx` (UploadDropzone wiring: signed Cloudinary upload, client-side downscale before upload for data cost, reorder, cover select, ≤8 enforced), `services/api/app/routers/listing_images.py` (attach/detach/reorder metadata)
Direct-to-Cloudinary with signed params (vendor-scoped folder); progress + retry per file; EXIF strip via Cloudinary transform.
**AC:** 9th image blocked client+server; vendor A cannot attach into B's listing; 2MB photo uploads on simulated 3G without timeout (downscaled).
**Tests:** cap both layers, authz, reorder persistence, failed-upload retry.

### M12-P06 — CSV bulk import `L`
**Deps:** P03 · **Files:** `apps/vendor/app/listings/import/page.tsx` (template download, upload, **validate → preview table w/ row-level errors → apply**), `services/api/app/services/listings/csv_import.py` (parser, column mapping, canonical-match by name/alias suggestion, dry-run + transactional apply), `services/api/tests/test_csv_import.py`
Template CSV (EN headers + example rows); validation: prices (ZMW decimals → ngwee), categories (fuzzy match + suggestion), stock, MOQ/tiers for wholesale; **100-row mixed-error file yields per-row feedback**; apply is all-or-selected-rows, idempotent re-upload (dedupe by vendor SKU column).
**AC:** M12 success criterion verbatim: 100 rows mixed errors → row-level feedback; partial apply works; re-upload doesn't duplicate; caps respected (T1 30).
**Tests:** fixture CSVs (encodings, BOM, bad decimals, unknown category, dupe SKU), idempotency, cap interaction.

### M12-P07 — Orders queue daily-driver `L`
**Deps:** M09-P02 · **Files:** `apps/vendor/app/page.tsx` (home = daily-driver: **today's takings (formatK), needs-action list, big buttons**), `apps/vendor/app/orders/page.tsx` (queue w/ status filters), `_components/order-card.tsx` (thumb-sized actions: Confirm / Pack / Ship / Ready)
The screen a vendor lives in: needs-action sorted by urgency (new orders → confirm SLA), one-tap actions with confirm sheets, pull-to-refresh, offline-tolerant read cache.
**AC:** M12 success criterion: usable one-handed at 360px; takings = today's confirmed revenue exactly (TZ Africa/Lusaka); action from card = full M09-P02 semantics.
**Tests:** takings aggregation (TZ boundaries), needs-action ordering, action wiring, empty states.

### M12-P08 — Payouts view & statements `M`
**Deps:** M08-P09, M03-P05 · **Files:** `apps/vendor/app/payouts/page.tsx` (balance: escrow-held vs released vs paid-out — ledger-derived; payout history w/ status; **statement download** CSV/PDF per month), `services/api/app/routers/vendor_payouts.py`, payout method management `apps/vendor/app/payouts/method/page.tsx` (MoMo number change → re-verify via /resolve + cooldown guard)
Everything ledger-backed (no parallel balance bookkeeping); method change is a fraud vector → OTP re-auth + 24h payout hold + notification.
**AC:** balances = ledger truth exactly (property: view sums = account balances); method change triggers hold + notice; statement math matches ledger.
**Tests:** balance derivation vs fixtures, method-change hold, statement generation, authz.

### M12-P09 — Storefront profile editor `M`
**Deps:** M05-P08 · **Files:** `apps/vendor/app/profile/page.tsx` (logo upload, description, hours editor, location pin + landmark, categories) — writes the same vendor data M05-P08 renders publicly, `services/api/app/routers/vendor_profile.py`
Profile completeness meter (nudges: logo, hours, description ≥50 chars — feeds directory ranking); slug edit once (redirect kept).
**AC:** edits live on public profile/directory ≤1min; completeness meter accurate; slug redirect works.
**Tests:** completeness computation, slug-change redirect, hours validation (overnight spans).

### M12-P10 — Vendor analytics `M`
**Deps:** P07, M06-P06 · **Files:** `apps/vendor/app/analytics/page.tsx` (sales/orders/views trends, top listings, conversion hint), `services/api/app/routers/vendor_analytics.py` (aggregates from orders + funnel events + search impressions)
Lightweight: 7/30-day cards + simple sparklines (no chart lib >10KB — inline SVG); data-frugal payloads.
**AC:** numbers reconcile with orders truth; view counts from funnel events; renders <50KB route JS.
**Tests:** aggregate correctness fixtures, date-range boundaries, empty-history state.

### M12-P11 — Public vendor pitch page `M`
**Deps:** M02 · **Files:** `apps/customer/app/[locale]/(marketing)/sell/page.tsx` (+`_components/`: hero, "Free to list. Pay only when you sell.", commission table from config, how-it-works, KYC explainer, payout promise D5, FAQ, CTA → vendor app signup), `packages/i18n/messages/en/vendor.json` (pitch section — **coordinate: same namespace file as P01; different wave**)
The founder's recruitment tool: SEO'd marketing page on the customer origin (trust), commission table reads live config (never stale).
**AC:** commission table = config values; LCP ≤2.5s; CTA deep-links to vendor onboarding; compelling at 360px.
**Tests:** config-driven table render, SEO metadata, link integrity.

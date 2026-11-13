# Convergeo Capacity and Hosting Addendum

Follow-up to section 6 of `growth-features-blueprint.md`. Research date: 2026-11-13. Read-only: nothing in any repo or system was changed.

Tags: [C] checked in code at `/home/claude/wt-next` (release/2026-11-next); [S#] a web source from the list at the end, fetched 2026-11-13; [A] my assumption; [D] derived by arithmetic from the others. Exchange rate used for ZMW: about K26 per US$1 [A, not checked; replace with today's rate].

## 0. Summary

1. **Vendor plans.** The pieces exist but are not joined up. Listing caps are enforced twice (API and database trigger) but only by **KYC tier** (T1 = 30 listings, T2 and T3 = 9,999) [C]. A `vendors.commercial_tier` column (bronze to platinum) exists and is shown in the directory, but **nothing enforces it**, and the `paid_tiers` flag is off [C]. I propose Free / Bronze K99 / Silver K249 / Gold K499 (the prices already in decision D3), with caps held in one new table and enforced in the same four places that enforce them today (section 1).
2. **Shared product images.** **No, this was not factored in, and the code does not do it yet.** Images are stored per listing only. The canonical `products` row has no image column [C]. With 60 to 80 percent of listings attached to shared products, images per listing fall from 3 to roughly 1.6 to 2.2 (a 26 to 47 percent cut), not 60 to 80 percent, because the canonical product still needs its own images and sellers add some of theirs (section 2).
3. **CDN for Zambia.** In place: Cloudinary `f_auto,q_auto` with 360/720/1080 widths and a tiny blurred placeholder, Cloudflare proxy on the apex and API, and a data-saver hook used by the carousel, infinite scroll and clips [C]. Gaps: no 240-pixel card size, data-saver does not change image sizes, no cache rules for public API reads, and Vercel functions probably run in Washington, D.C. (section 3).
4. **Hosting.** Vercel Hobby cannot be used commercially, so something must change before launch. **Recommendation: pay Vercel Pro ($20) for launch, then spend 2 days testing Cloudflare Workers with OpenNext ($5 a month) for the customer app, and move vendor and admin to the existing server, which the Caddy file already plans for.** Net saving is about $15 a month, so it is worth doing only after launch (section 4).

---

## 1. Vendor plans, quotas and free-tier limits

### 1.1 What exists today

| Piece | What it does | Evidence |
|---|---|---|
| `vendor_quotas` table | One row per **KYC tier** (1, 2, 3): `max_listings`, first-orders cap and count, payout velocity. Seeded T1 = 30 listings, first 5 orders at most K500 each; T2 and T3 = 9,999 | [C] `supabase/migrations/0008_config.sql:176-193` |
| Listing cap, API | `require_listing_cap` dependency and `enforce_listing_cap`; the 31st T1 listing returns 403. Counts statuses draft, active, paused. 60-second config cache | [C] `services/api/app/services/kyc/caps.py`; tests in `services/api/tests/test_kyc_caps.py:394-408` |
| Listing cap, database | Trigger `vendor_listing_admission_guard` takes an advisory lock per vendor, reads the vendor's highest approved KYC tier, looks up `vendor_quotas.max_listings`, raises `listing_cap_exceeded` (PT403). Atomic, so two simultaneous requests cannot both slip through | [C] `supabase/migrations/20261001120000_merchant_protected_listing_admission.sql:20-57` |
| Order cap | First orders capped by KYC tier at order admission; service role can read `vendor_quotas` | [C] `20260924120418_order_vendor_quota_service_read.sql` |
| Image cap | 8 per listing, hardcoded in the database trigger `guard_listing_image_count` and in `MAX_IMAGES_PER_LISTING = 8` in the API | [C] `0003_catalog.sql:168-193`; `routers/listing_images.py:15` |
| Clips cap | `platform_config` key `clip_weekly_caps` = `{"1":3,"2":10,"3":30}` per rolling 7 days, keyed by **KYC tier**; rejected clips count; falls back to the same defaults if the row is missing | [C] `0078_clip_weekly_caps.sql`; `services/api/app/services/clips/quota.py` |
| Commercial tier | `vendors.commercial_tier` nullable, check bronze / silver / gold / platinum; NULL means free. Returned by the directory API and shown on cards. **No quota reads it.** Flag `paid_tiers` is false | [C] `0070_vendor_commercial_tier.sql`; `0008_config.sql:112`; `routers/directory.py` |
| Stated plan | D3: free-only at launch; Bronze K99, Silver K249, Gold K499 as a flagged module, switched on at about 300 orders a month or month 3; free tier up to 30 listings. The original master plan had Free 20 / Bronze 100 products / Silver and Gold unlimited | [C] `docs/plan/00-decisions.md:17`; `docs/plan/research/master-plan-distilled-B.md:28` |

Two things to note. First, **KYC tier** (a trust and fraud control) and **commercial tier** (what the vendor pays for) are different axes and should stay different. Second, there is no image-count or storage allowance by plan, and no billing code.

### 1.2 Does a cap on free listings help cost?

Honestly, little. A listing costs the platform about 12 to 14 KB of database [section 6.3 of the blueprint] plus about 0.4 MB of images after the changes below. That is a fraction of a ngwee a month at paid-plan prices. The cap is useful for three other reasons: it keeps the free 500 MB Supabase database from filling before revenue arrives, it limits spam and bulk-scraped catalogues, and it gives a real reason to upgrade. Prices should therefore be set by what a Zambian shop will pay, not by cost.

### 1.3 Proposed tiers

Prices are the D3 prices. K99 is about US$3.80 [A], K249 about $9.60, K499 about $19.20. A market stall owner or small shop can plausibly pay K99; a registered shop with staff K249.

| | **Free** (default, `commercial_tier` NULL) | **Bronze** K99 / month | **Silver** K249 / month | **Gold** K499 / month |
|---|---|---|---|---|
| Active listings (draft, active, paused) | **30** (keep D3; see 1.6 for the case for 20) | **150** | **1,000** | **5,000** |
| Images on a standalone listing | 3 | 5 | 8 | 8 |
| Own photos on a listing attached to a shared product | 1 | 2 | 2 | 2 (more allowed where the category requires evidence, see 2.4) |
| Clips per rolling week | 1 | 3 | 10 | 30 |
| Other (from the master plan) | Standard commission | Verified badge, commission down 1 point | Priority search placement, CSV bulk upload | Home rotation, API access |
| KYC tier needed | T1 | T2 | T2 | T2 or T3 |

Design rules:

1. **Paid tiers need KYC T2.** This keeps the fraud controls: a new unverified vendor cannot buy past the first-orders cap.
2. **Effective cap is the lower of the KYC cap and the plan cap.** T1 stays at 30 whatever is paid until verified.
3. "Unlimited" is replaced by a large number (1,000 and 5,000). It is easier to explain, and protects the database.
4. Free clips go down from 3 to 1 a week while clips run on Cloudinary, because the blueprint (2.6) shows even the current pilot caps do not fit the free credits. Raise it again when video moves to ffmpeg plus R2.
5. Free images per attached listing is 1 because the canonical image already shows (section 2).

### 1.4 How enforcement works (server-side, reusing what exists)

Nothing in the browser decides anything. Four places already enforce limits, and each would read one new source of truth.

1. **New table `vendor_plans`** (additive migration, reversible by dropping it), one row per plan key: `plan` (`free|bronze|silver|gold`), `max_listings`, `max_images_standalone`, `max_images_attached`, `clip_weekly_cap`, `price_ngwee`. Same pattern as `vendor_quotas`: row-level security on, public read, admin write, the existing `config_audit` trigger records every change with an actor. Money is integer ngwee, per project convention.
2. **Plan resolution**: `coalesce(vendors.commercial_tier, 'free')`, but only when the flag `paid_tiers` is on and the subscription is current. Otherwise treat as free.
3. **Listings**: extend `guard_vendor_listing_admission` to `least(kyc cap, plan cap)`. It already holds the per-vendor advisory lock, so it stays race-free. Extend `VendorQuota` and `require_listing_cap` in `caps.py` to the same rule so the API returns a friendly error before the trigger fires.
4. **Images**: replace the hardcoded 8 in `guard_listing_image_count` and `MAX_IMAGES_PER_LISTING` with a lookup. The check must know whether the listing has a `product_id` with canonical images.
5. **Clips**: `load_weekly_caps` in `clips/quota.py` should key by plan instead of KYC tier (or by the lower of both). The config row `clip_weekly_caps` stays as the override.
6. **Subscription state**: a `vendor_subscriptions` table (vendor, plan, paid_through, status) written only by a guarded function with an audit row, like orders and payments. Lenco has no card-on-file for mobile money, so billing is a monthly mobile-money request reminded over WhatsApp, with a 7-day grace period [A].
7. **Downgrade or lapse**: never delete. Existing listings stay visible; new ones are blocked. After a 30-day grace, pause the vendor's least-viewed listings down to the free cap, and tell them first. Open orders are unaffected.
8. **Admin visibility**: the admin app shows plan, usage against cap, and override (the founder can widen one vendor, as is already possible for clips).

Tests needed per the repo rules: failure paths for every cap, the race (two parallel inserts at cap minus one), downgrade, and plan lookup when the flag is off.

### 1.5 Effort and risk

About 1 migration, 4 small code changes, 1 admin screen, and billing. Billing is the large part and should wait for the D3 trigger (about 300 orders a month). The caps themselves could ship earlier, with everyone on Free.

### 1.6 A decision for the founder

D3 sets Free at 30. The original master plan said 20. If the real aim is to push vendors to upgrade, 20 is a firmer limit, but it breaks a promise already made in D3 ("Free to list"). I recommend keeping 30 and tightening **images** and **clips** first, since those cost real money.

---

## 2. Shared product images: what the code does, and the recomputed ceilings

### 2.1 What the code does today [C]

- `listing_images` belongs to a **listing** (`listing_id` foreign key, `cloudinary_public_id`, `position` 1 to 8). `0003_catalog.sql:150-160`.
- The canonical `products` table has `name, slug, brand, spec, category_id, aliases, status, merged_into_id` and **no image column** (`0003_catalog.sql:64-77`). A later migration adds `image_public_id` only to variants (`20260813064106_product_strategy_core_contract.sql:77,173`).
- The product page builds its gallery at read time from the **listings'** images: primary listing first, then the rest by ascending price, de-duplicated only when the Cloudinary `public_id` is **identical**, capped at 8 (`routers/products.py:280-314`, `MAX_GALLERY_IMAGES = 8`).
- Vendor uploads go straight to Cloudinary into `listings/{vendor_id}/...` (`docs/ops/media-pipeline.md`). Each vendor therefore uploads their own copy, which always gets a new `public_id`, so the dedup in the gallery code never fires across vendors.

So when five shops sell the same phone, the system stores about 5 × 3 = 15 images of it, and the page shows a mix. The blueprint's per-listing estimate (3 images each, independent) was right for the code as built, but **it did not use the canonical catalogue to reduce images, and the code has no way to do so yet.**

### 2.2 Recomputed images per listing

Model [A]: share `s` of listings attach to a canonical product; each canonical product has `c = 3` images and on average `k` listings; attached listings add `e = 0.5` own photos on average (cap 2); standalone listings keep 3. Images per listing = `s × (c/k + e) + (1 − s) × 3`.

| Case | Attach share s | Listings per product k | Images per listing | Cut vs 3 |
|---|---|---|---|---|
| Optimistic | 80% | 4 | **1.60** | 47% |
| Middle | 60% | 4 | 1.95 | 35% |
| Early marketplace | 80% | 2.5 | 1.96 | 35% |
| Pessimistic | 60% | 2.5 | 2.22 | 26% |

k matters a lot. In the pilot, with few vendors, k will be near 1 to 2 and savings near zero; they grow as more shops list the same goods. Zambian informal sellers of unbranded goods (clothes, handmade items) will attach less than sellers of branded electronics and groceries, so 60 to 80 percent is optimistic for the whole catalogue [A].

### 2.3 Recomputed ceilings

Same method as blueprint 6.4: Cloudinary Free allows 25 credits; ceiling scales inversely with images per listing. Baseline from the blueprint: 3,000 to 5,000 listings.

| Setup | Images per listing | Listings the image tier can hold | Binding limit |
|---|---|---|---|
| Today (blueprint) | 3.0 | 3,000 to 5,000 | Cloudinary credits (first-time resizing) |
| Dedup only, Cloudinary Free | 1.6 to 2.2 | **about 4,000 to 9,000** [D] | Cloudinary credits; page-view delivery limit (15,000 to 25,000 views a month) becomes the next wall and is **not** reduced by dedup |
| Dedup plus pre-resized copies in Cloudflare R2 (3 sizes about 0.25 MB per image [A]) | 1.6 to 2.2 | **about 18,000 to 25,000** on R2's 10 GB free [S11] [D] | R2 free storage, then US$0.015 per GB a month |
| Same, at 1,000,000 listings | 1.8 | about 450 GB, **about US$6.60 a month** on R2 [D] | Class A writes: 1.8M images × 3 sizes = 5.4M at $4.50 per million, about $20 one-off [S11] [D] |
| Same, at 1,000,000 listings, kept on Cloudinary | 1.8 | about 900 GB stored (0.5 MB originals) = 900 credits, above the Advanced plan's 600 (US$224 to $249) [S5] [D] | Not viable without a custom contract |

Reading it: dedup roughly doubles what the free Cloudinary tier holds, but it does **not** remove the need to leave Cloudinary's meter. The move to R2 (already a designed switch point, decision D26) is what lifts the ceiling to tens of thousands, and at a million listings it makes images a rounding error. The blueprint's $110 to $250 a month for 1M products stands only if images are on R2; kept on Cloudinary, images alone would exceed it [D].

Database savings from dedup are small (an image row is about 0.3 KB per image) and do not change the 25,000-listing figure [D].

### 2.4 Recommended dedup rules

1. **Canonical image wins.** Add a `product_images` table (product, public_id, position up to 6). The first vendor who creates a canonical product supplies its images; admin moderation approves them (the moderation step already exists for new canonical products). Admin can replace them later.
2. **Attached listings need no images of their own.** They may add up to 1 (Free) or 2 (paid) own photos, shown after the canonical ones and labelled "seller photos". Comparison view and search cards use the canonical image only.
3. **Evidence categories keep own photos.** For refurbished or used goods (and other classes that already require `evidence_image_count`, see `services/api/tests/test_product_class_cart.py`), require 1 to 3 own photos regardless. A buyer must see the actual item.
4. **Standalone listings** (no product match) keep up to 3 / 5 / 8 by plan. Matching is encouraged by showing, at upload, "this looks like an existing product, use its photos?" (the live product search already exists in listing create, `prompts/M12-P03-listing-create.md`).
5. **Detect duplicates at upload.** Cloudinary can return a perceptual hash on upload (`phash` option) [A, verify in the Cloudinary docs]; if a new image is within a few bits of an existing canonical one, reuse the existing `public_id` and delete the new upload. Exact duplicates can be caught earlier by hashing the file in the browser and asking the API.
6. **Merge and clean up.** When two products merge (`merged_into_id`), union their canonical images up to the cap. A weekly job (n8n) deletes Cloudinary assets that no row references. I did not verify whether listing deletion currently removes the asset [not checked].
7. **Shrink before upload.** Resize in the vendor browser to at most 1,080 pixels wide and re-encode as WebP before uploading. Today the limit is 10 MiB per image. This cuts storage and, just as important, the vendor's own mobile data cost.
8. **Cap and show usage.** The vendor app shows "photos used" against the plan allowance.

---

## 3. CDN and Zambia

### 3.1 What is in place [C unless marked]

| Layer | State |
|---|---|
| Image CDN | Cloudinary delivery URLs built in one place, `packages/ui/src/media/cloudinary-url.ts`: `f_auto,q_auto,w_{360/720/1080}`, plus a tiny blurred placeholder. This file is the declared single swap point (D26). `docs/ops/media-pipeline.md` |
| Cloudflare | DNS records are orange-cloud (proxied) for the apex, `www`, `api`, `vendor`, `admin`, `n8n`; TLS Full (strict); API cache bypass; admin behind Cloudflare Access. The doc also says "Cloudflare only on apex if using CNAME flattening", which is ambiguous, so **whether the live apex is proxied is not confirmed** from code. `infra/cloudflare-dns.md`, `docs/plan/00-status.md` |
| Vercel | Customer, vendor and admin each a Vercel project. Customer pages use `revalidate = 60` (blueprint 6.4). **No function-region setting in the repo**, so by default they run in `iad1`, Washington, D.C. [S6]. Supabase is in `eu-north-1` (Stockholm) [C] and the API is on a Hetzner server in Europe [C], so each server-rendered request may cross the Atlantic twice [A, verify the project's Function Region setting] |
| Data saver | `usePrefersReducedData` (Save-Data flag or reduced-data media query) used by the hero carousel, progressive loading, and clips (a visible toggle). **It does not yet change image widths.** `packages/ui/src/use-prefers-reduced-data.tsx` |
| Budgets | Customer routes at most 150 KB of gzipped JavaScript, LCP 2.5 s on Fast 3G at 360 px (CI-enforced) [C: CLAUDE.md] |

### 3.2 Nearest points of presence

- **Cloudflare** lists a Lusaka data centre (code LUN) in a secondary source [S7] and the other African sites I checked (Johannesburg, Cape Town, Nairobi, Harare, Maputo, Dar es Salaam, Lagos) [S8]. I could not confirm Lusaka on Cloudflare's own status page (the page I could load did not show locations). **Verify**: from a Lusaka phone, open `https://vergeo5.com/cdn-cgi/trace` and read `colo=`; `LUN` or `JNB` is the answer. If `JNB`, the nearest cache is Johannesburg, which is still good [A: about 30 to 50 ms from Lusaka].
- **Vercel** has 126 points of presence and 19 compute regions; the only African compute region is Cape Town (`cpt1`) [S6]. Whether any African point of presence serves Zambia is not stated in the page I fetched.
- **Cloudinary** does not publish a per-city list in the pages I fetched. I believe it uses several large CDNs underneath; I could not confirm which of them has African sites [A]. Test it: `curl -sI` an image URL from a Lusaka connection and read the `server`, `x-cache` and `cf-`/`x-served-by` headers.
- **Zambia-hosted** options exist (section 4.2) but a Cloudflare node in or near Lusaka already gives local delivery of anything cacheable at no cost.

### 3.3 Recommendations for Zambian users

**Image sizes** [A: effective 3G or weak 4G throughput 0.5 to 1.5 Mbps, so 100 KB takes 0.5 to 1.6 s]:

| Use | Today | Recommended |
|---|---|---|
| Card thumbnail | 360 px, about 30 KB (blueprint) | **240 px, AVIF or WebP, quality "eco", target 10 to 14 KB**; keep 360 only for 2x screens |
| Grid of 20 cards | about 600 KB | **at most 8 images eager, rest lazy**; about 100 KB first screen |
| Product page hero | 720 px | 720 px, target 50 to 70 KB; 1,080 px only on request (zoom) |
| Data saver on | no change to images | 240 px for cards, 480 px hero, quality "low", no autoplay (already done for carousel and clips) |

Add 240 to `DEFAULT_WIDTHS` in the single URL helper. Make the helper take a "data saver" argument fed by the existing hook and a cookie toggle (iOS and Opera Mini do not send the Save-Data hint).

**Caching headers:**

- Images: long and immutable (`Cache-Control: public, max-age=31536000, immutable`) on versioned or content-hashed URLs. Check what Cloudinary sends today with `curl -sI` [not checked]. For R2, set it at upload.
- Customer HTML: keep ISR at 60 seconds; add `stale-while-revalidate` so a user is never held waiting for a rebuild.
- Public API reads (catalogue lists, product detail, categories): have FastAPI send `Cache-Control: public, s-maxage=60, stale-while-revalidate=600` and add a Cloudflare Cache Rule for `api.vergeo5.com` GET paths that opts those in. The infra doc currently says "cache bypass on API routes". Never cache cart, checkout, or anything with an `Authorization` header or cookie.
- Set the Vercel **Function Region** for the customer project to `arn1` (Stockholm), next to Supabase [S6, A] so server rendering is not trans-Atlantic. This is a setting, not code.

**Cloudflare Images vs R2 vs Cloudinary** (prices from [S5], [S10], [S11]):

| | Cloudinary | Cloudflare Images (managed) | R2 plus pre-resized copies |
|---|---|---|---|
| Free allowance | 25 credits a month, shared by storage, delivery, transforms | 5,000 unique transformations a month on images kept in R2; cached ones keep working past the limit | 10 GB stored, 1M writes, 10M reads a month |
| Paid | Plus US$89 to $99 a month (225 credits), Advanced $224 to $249 (600) | $0.50 per 1,000 transformations after 5,000; $5 per 100,000 images stored; $1 per 100,000 delivered | $0.015 per GB a month; **no egress charge** |
| 1M listings, 1.8M images | not viable (above) | storage alone about $90 a month, plus transformations [D] | about $6.60 plus $20 one-off writes [D] |
| Effort | none (current) | medium | medium: an upload step that writes 3 sizes (sharp or libvips on the server, or browser-side resize) |

Recommendation: **R2 plus fixed sizes written once at upload, served from a Cloudflare custom domain (for example `img.vergeo5.com`)**, switched at stage 1 as the blueprint says. Keep Cloudinary for clips until ffmpeg plus R2 is built. Cloudflare Images is not worth it for this catalogue size.

---

## 4. Hosting alternatives to Vercel Pro

### 4.0 Why something must change

Vercel Hobby is non-commercial only [blueprint S4], and also pauses a feature for up to 30 days when a limit is passed [blueprint S3]. All three projects (customer, vendor, admin) are on Hobby [C: `infra/vercel.md`]. Vercel Pro is US$20 a month and includes a $20 usage credit; the page does not give overage rates and does not state the commercial rule in so many words [S9]. A Pro team seat covers all three projects.

Note a correction to the blueprint: Hetzner's current page lists the 2 vCPU / 4 GB x86 server (CX23) at **€5.99 a month excluding VAT**, not €5.49, and the older name CX22 is no longer shown [S12]. 20 TB of traffic is included in EU locations; extra is €1 per TB. Hetzner has no African location (Germany, Finland, Singapore, USA) [S12].

### 4.1 Comparison

Latency figures are my estimates from Lusaka [A]: Johannesburg 30 to 50 ms, Cape Town 60 to 90 ms, Europe 170 to 230 ms, US East 250 to 300 ms. Verify with `ping` or `mtr` from a Lusaka connection before relying on them.

| Option | Cost per month | Commercial use | Next.js ISR / SSR | Latency to a Lusaka user | Effort | Main risk |
|---|---|---|---|---|---|---|
| **Vercel Pro** (reference) | $20 plus usage above the $20 credit [S9] | Yes (business plan) | Native, no work | Cached: nearest Vercel point of presence; uncached: the function region (set `arn1`) | None | Usage creep; opaque overage; a US vendor |
| **Cloudflare Workers + OpenNext** | Free plan: 100,000 requests a day, **10 ms CPU per request** [S2]; **Workers Paid $5 minimum**: 10M requests and 30M CPU-ms included, $0.30 per extra million [S3] | Pricing pages are silent on commercial use [S2][S3]; Cloudflare's terms allow it on Free to my knowledge [A, **verify the terms**] | OpenNext supports SSR, ISR and image optimisation on current Next 15; Node middleware (15.2+) not yet supported; compressed Worker limit **3 MiB Free, 10 MiB Paid** [S4] | Runs at the nearest Cloudflare site (Lusaka or Johannesburg); data still in Stockholm and the EU API, so uncached SSR still pays about 200 ms to the database | 2 to 5 days plus testing: the repo uses Serwist (PWA), next-intl, nonce CSP middleware, many routes [C] | Younger adapter, edge runtime quirks, 10 ms free CPU limit is too tight for SSR so plan on the $5 plan |
| **Self-host on a Hetzner server + Cloudflare CDN** | The existing CX23 (€5.99) if there is room, else a second one at €5.99 (about $6.50) [S12]. Coolify itself is open-source and free; you pay only for servers [S5b] | Yes | Next standalone supports ISR and SSR natively on one node (file-system cache, lost on redeploy unless a volume is kept) | Cache hit at Cloudflare: local. Miss: Europe 170 to 230 ms. Cloudflare does not cache HTML by default, so cache rules are required | 2 to 4 days for the customer app; `infra/Caddyfile` already plans a vendor and admin standalone server behind Caddy [C] | One server is a single point of failure; memory (4 GB shared with API, n8n and 3 Next apps) is tight; you are the on-call; no instant rollback |
| **Netlify** | Free: 300 credits; Personal $9 (1,000 credits); Pro $20 per member (3,000 credits per team). At the limit the site **pauses** unless auto-recharge is on [S13] | Not stated for Free [S13] | Supported through an adapter | No African compute; same as Vercel or worse [A] | 1 to 2 days | Same credit meter and pause behaviour as Vercel with no saving |
| **Render** | Web service 1 CPU / 2 GB $25; workspace plan Pro $25; bandwidth 25 GB included then $0.15 per GB [S14] | Yes | Runs Next as a Node service (SSR; ISR on single instance) | Nearest regions Frankfurt or similar, no Africa [A] | 1 to 2 days | Costlier than Vercel Pro for what you get |
| **AWS Amplify Hosting** | Build $0.01 per minute; storage $0.023 per GB; **served $0.15 per GB**; SSR $0.30 per million requests plus $0.20 per GB-hour; free tier 12 months [S15] | Yes | Supports SSR and ISR | Cape Town region availability for Amplify **not confirmed** in what I could read [S15]; if available about 60 to 90 ms | 2 to 4 days | Per-GB serving cost: 1 TB would be about $150; a billing-surprise risk |
| **AWS Lightsail** | $5 (0.5 GB), $7 (1 GB), $12 (2 GB) with 1 to 3 TB transfer [S16] | Yes | Self-managed Docker, as for Hetzner | **Cape Town not confirmed**; I believe Lightsail is not offered in af-south-1 [A, verify]. EC2 in Cape Town would be about $19+ a month for 2 GB [A] | 2 to 4 days | Ops burden, plus the same dynamic-data distance problem for Supabase in Stockholm |
| **Zambian data centre** (Paratus, Infratel, Liquid) | Quote only; I found no public price list | Yes | Self-managed | Lusaka users 5 to 20 ms [A] | High: contracts in USD [A], hardware, power cuts, uplink quality, no managed DDoS protection | Highest ops risk for a solo founder; no benefit for cached content that Cloudflare already serves locally |

### 4.2 What I found about local Zambian hosting

- A data-centre directory lists **no** Zambian facility as a cloud provider; its only Zambian entry is Cloudflare's Lusaka site [S7].
- **Paratus Zambia** opened a 1 MW carrier-neutral data centre in Lusaka in July 2021 with "physical and virtual hosting" and support for content delivery networks; no tier rating or price given [S17].
- **Infratel** has a "Primary Data Centre" in Lusaka listed in a data-centre directory and an Uptime Institute award page [S18]. I did not confirm its tier.
- **Liquid Intelligent Technologies** announced a new data centre in Zambia in 2023 [S19]; I did not confirm that it is operating or sells small hosting.
- Zamtel: I found nothing relevant.

Local hosting only helps requests that cannot be cached (cart, checkout, login). That is a small share of bytes, and the user's own mobile network is the larger delay. I do not recommend it now. Revisit if measurements show the dynamic path is the bottleneck, and check the Zambia Data Protection Act position on where data may live before putting personal data anywhere new [not checked].

### 4.3 Recommendation

Principles: stay inside the $50 a month ceiling (D6); do not risk launch week on a migration; remove the Hobby breach.

1. **Before launch: Vercel Pro, $20.** It fixes the commercial-use breach and the "feature switched off for 30 days" risk for all three apps, with zero code change. Total platform cost about $20 + €5.99 server, about $27 a month, inside D6.
2. **Immediately: set the customer project's Function Region to `arn1`** and add the Cloudflare cache rules in 3.3. Zero cost.
3. **After launch, a 2-day spike (time-boxed): customer app on Cloudflare Workers Paid ($5) with OpenNext**, on a preview hostname. Pass criteria: all CI performance budgets, nonce CSP and next-intl middleware work, ISR revalidation works, no route exceeds the CPU limits. If it passes, cut over and drop Vercel for that app; saving about $15 a month (K390).
4. **Vendor and admin apps: move to the existing server** as the Caddyfile already plans. They are low traffic, authenticated, and already behind Cloudflare Access, which removes them from Vercel entirely. Check memory first: each Next standalone process is typically a few hundred MB [A]; measure on the server before agreeing.
5. **Do not choose** Netlify (same pause model), Render (dearer), Amplify (per-GB cost) or Lightsail (probably not in Cape Town), and defer Zambian hosting.

Honest note on the saving: $15 a month is small. The spike is worth it mainly if Vercel Pro usage charges grow beyond the included $20 credit, or if Cloudflare's local points of presence prove measurably faster for Zambian users. Measure both before committing.

---

## Sources (all fetched 2026-11-13)

- [S2] Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- [S3] Cloudflare Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/
- [S4] OpenNext for Cloudflare: https://opennext.js.org/cloudflare
- [S5] Cloudinary pricing (Free 25 credits; Plus $89/99 for 225; Advanced $224/249 for 600; one credit = 1,000 transformations or 1 GB storage or 1 GB bandwidth): https://cloudinary.com/pricing
- [S5b] Coolify introduction: https://coolify.io/docs/get-started/introduction
- [S6] Vercel regions (126 points of presence, 19 compute regions, `cpt1` Cape Town, default `iad1`): https://vercel.com/docs/regions
- [S7] Data centres in Zambia (Cloudflare Lusaka only): https://getdeploying.com/datacenters-in-zambia
- [S8] Cloudflare Africa edge primer (April 2026; secondary source): https://know-2nth.pages.dev/explainers/tech/cloudflare/edge-africa-me
- [S9] Vercel pricing (Hobby $0; Pro $20, $20 credit): https://vercel.com/pricing
- [S10] Cloudflare Images pricing: https://developers.cloudflare.com/images/pricing/
- [S11] Cloudflare R2 pricing: https://developers.cloudflare.com/r2/pricing/
- [S12] Hetzner Cloud cost-optimized plans (CX23 €5.99, 20 TB EU traffic, locations): https://www.hetzner.com/cloud/cost-optimized/ and https://www.hetzner.com/cloud/
- [S13] Netlify pricing summary (secondary source): https://netli.fyi/blog/netlify-pricing-and-limits
- [S14] Render pricing: https://render.com/pricing
- [S15] AWS Amplify pricing: https://aws.amazon.com/amplify/pricing/
- [S16] AWS Lightsail pricing: https://aws.amazon.com/lightsail/pricing/
- [S17] Paratus Zambia data centre, Lusaka (26 July 2021): https://itweb.africa/article/paratus-zambia-opens-new-datacentre-in-lusaka/KPNG878Kmz8v4mwD
- [S18] Infratel primary data centre, Lusaka: https://www.datacentermap.com/zambia/lusaka/infratel-lusaka/
- [S19] Liquid Intelligent Technologies Zambia data centre announcement: https://techcabal.com/2023/04/05/liquid-intelligent-technologies-data-centre-zambia/
- Code and repo documents are cited by path in the text.

## Not verified (open items)

- Whether the live `vergeo5.com` apex is proxied by Cloudflare, and which Cloudflare site serves Lusaka (test with `/cdn-cgi/trace`).
- The Vercel customer project's Function Region setting.
- Cloudinary's current response headers and which CDN sites serve Zambia.
- Cloudflare terms on commercial use of the Free and Workers plans.
- Cloudinary `phash` on upload.
- Whether Amplify Hosting and Lightsail exist in Cape Town.
- Whether deleting a listing deletes its Cloudinary assets.
- The ZMW exchange rate and all latency figures marked [A].

## Approval requested

1. **Plans:** approve the tier table in 1.3 (Free 30 / Bronze 150 / Silver 1,000 / Gold 5,000 listings; K99 / K249 / K499), including "paid tiers need KYC T2" and "lower of KYC cap and plan cap".
2. **Free-tier clips and images:** approve cutting free clips from 3 to 1 a week until video moves off Cloudinary, and free own photos on an attached listing to 1.
3. **Build the plan module (caps only, no billing yet):** approve one additive migration (`vendor_plans`, later `vendor_subscriptions`) and the four enforcement changes in 1.4, as a normal pebble through the usual review loop.
4. **Canonical images:** approve adding `product_images`, the "canonical image wins" rule, and required own photos for refurbished and evidence categories (2.4).
5. **Image storage:** approve planning the Cloudflare R2 switch at about 3,000 listings, with browser-side resize before upload, and fixed sizes 240/360/720/1080.
6. **Hosting:** approve Vercel Pro ($20) for launch; approve setting the customer Function Region to `arn1` and the Cloudflare cache rules for public API reads.
7. **Spike:** approve a time-boxed 2-day Cloudflare Workers plus OpenNext test for the customer app, and moving vendor and admin to the existing server after a memory check.
8. **Quick measurements (read-only, founder or ops to run):** `cdn-cgi/trace` from a Lusaka phone; the Vercel Function Region; Cloudinary image headers; today's ZMW rate.

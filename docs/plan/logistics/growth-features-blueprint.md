# Convergeo Growth Features Blueprint

Date: 13 November 2026. Status: research and design for founder approval. Nothing here has been built or changed.

Scope: paid ads, Clips, gifting and loyalty, cash on delivery, maps and time-of-day pricing, platform ceilings, event cancellation safety, and how the business page should evolve.

## How to read the numbers

Every number carries one of these tags.

| Tag | Meaning |
|---|---|
| **[S]** | Sourced. The URL is in the source list at the end (S1, S2 ...). All were read on 13 Nov 2026. |
| **[C]** | Checked in the code on `release/2026-11-next`, or on the named branch. File given. |
| **[D]** | Derived by arithmetic from [S] or [C] numbers. The working is shown. |
| **[A]** | Assumption. No source. Change it when real data exists. |

Exchange rate used for rough conversions: K23 = US$1 [A].

Three limits of this document:

- I did not query the live database, the Cloudinary account, or the Vercel account. Ceilings in section 6 are estimates from the schema, not measurements. Section 6.6 gives the queries that replace them with facts.
- Legal points are a reading of the Acts, not legal advice. Three of them need a Zambian lawyer before launch (gift cards, open video uploads, direct-pay). They are marked.
- Several vendor price pages did not load (Cloudinary moderation add-ons, openrouteservice quotas, Lenco's fee schedule, Zambia-specific Facebook ad prices). Those gaps are stated where they matter.

---

## 0. Summary

### The north star

"Convergeo is the Hub of logos": a street of shopfronts, each with its own sign, where every business can tell its story, be found, and sell. The recommendations below are judged against that. An ad, a clip, a coupon or a gift should each lead back to one business's own page, carrying its name and logo. None of them should make shops look interchangeable.

### Top recommendation per topic

| # | Topic | Recommendation |
|---|---|---|
| 1 | Paid ads | Sell **fixed-price packages** (a slot for a set number of days), paid in advance through Lenco. Add "Boost" (a prepaid budget buying an estimated number of views) second. Build an auction only when slots are regularly sold out. An AI reviewer may **approve or escalate**; only a person rejects. |
| 2 | Clips | Free to post and followable, with clickable links: **yes**. "Anyone": **not yet**. Open in steps: allowlist, then all verified businesses, then verified individual creators. Automated screening is needed and can cost about $0. Before opening up, move video off Cloudinary; Cloudinary alone would cost roughly $90 to $250 a month. |
| 3 | Gifting and loyalty | Build **gift orders** and a **general coupon system** first. Collect birthdays as day and month with separate consent. **Do not sell cash-value gift cards** until a lawyer confirms they are not "electronic money" under the National Payment System Act, 2026. |
| 4 | Cash on delivery | Make **"pay at the door by mobile money"** the default: a Lenco payment prompt on the customer's phone at handover, paid to Convergeo. Keep cash as a small capped fallback. Do not sell "pay the shop directly" as a premium perk; sell faster payout instead. |
| 5 | Maps and timing | Keep the approved area-to-area distance table. Fill it once with real road distances from open map data (OSRM, run offline, $0). Add published time-band and rain surcharges. One simple promise: **"Order before 2 pm, get it today."** No paid map API in the customer's path. |
| 6 | Ceilings | Today's set-up holds roughly **20,000 to 30,000 listings**, not millions. Image hosting and the website hosting plan run out first, at about 3,000 to 5,000 listings and 1,000 to 1,500 page views a day. Vercel's free plan does not permit commercial use at all. Two upgrades (Vercel Pro $20, Supabase Pro $25) are needed before real growth. |
| 7 | Events | Hold **100% of ticket money until after the event** by default. Release only when there is proof the event happened. Refund only to the number that paid. Fix one defect: an "unpublished" event's tickets cannot currently be scanned at the gate. |
| 8 | Business pages | Evolve the vendor page into a **"Business Home"**: one page per business with its sign, story, clips, offers, products, services and events together. Every ad and clip links back to it. |

### Three findings that need a decision before anything else

1. **Vercel's free plan forbids commercial use** [S4]. A site that takes payments must be on Pro ($20 a month per developer seat [S3]). If production is on the free plan, this is a compliance problem today, separate from capacity.
2. **Gift cards may be regulated e-money.** The National Payment System Act, 2026 defines electronic money as stored value "accepted by third parties" and makes unlicensed payment services an offence with up to 30 years' imprisonment [S16]. A Convergeo gift card spent at many shops fits that wording on a plain reading. I found no closed-loop exemption in the Act.
3. **Unpublishing an event breaks gate entry.** Tickets stay "issued", but the scanner refuses any event that is not "published" [C: `services/api/app/routers/ticket_verify.py:329`, `ticket_scan_sync.py:144`]. Also, money release only stops for "cancelled" events, so an unpublished event that never happens would still pay the organiser [C: `services/api/app/services/escrow/event_release.py:485`].

---

## 1. Paid ads

### 1.1 What exists (PR #782, branch `feat/admin-ads-merchandising`)

| Piece | State | Where |
|---|---|---|
| Ad placements: sponsored feed slots and hero carousel slides | Built, admin-created only | `ad_placements` table, migration `20261108100000_home_feed_sections.sql` [C] |
| Status rules: draft, scheduled, active, paused, ended, changed only through one guarded function | Built | `transition_ad_placement()` [C] |
| Daily view and click counters | Built | `ad_placement_daily_stats`, `record_ad_placement_events()` [C] |
| Typed targets: listing, product, service, event, vendor. An ad disappears if its target or advertiser is hidden or suspended | Built on PR #782 | `ad_placements.target_kind/target_id`, `home_feed/resolver.py` [C] |
| External links | Allowed as `https://` with an API host allow-list | `cta_href` check [C] |
| "Sponsored" label in five languages | Built | `feed-section.tsx`, `home-hero-carousel.tsx` [C] |
| Admin permission `ads.manage` | Built | `core/auth.py` [C] |
| Payment | **Record-only.** `paid_amount_ngwee` and `payment_reference` are typed in by an admin. Nothing charges anyone | [C] |
| Vendor self-service, category or search sponsored slots, AI review | Not built | `docs/plan/admin-merchandising-ads.md` on the branch [C] |

So the display half exists. The missing half is: a vendor buys it, pays, gets reviewed, and it goes live without an admin typing anything.

### 1.2 The three models compared

| | (a) Auction (bid per click or per 1,000 views, second-price) | (b1) Fixed package (slot for a period) | (b2) Boost (budget for an estimated number of views) |
|---|---|---|---|
| What the vendor understands | "Bid", "CPC", "quality score". Hard to explain | "K150 puts my shop on the home page for a week". Easy | "K50 shows my post to about 2,000 people". Easy, familiar from Facebook |
| Works with few advertisers | No. With fewer bidders than slots, a second-price auction clears at the minimum price every time. It becomes a fixed price with extra machinery | Yes | Yes |
| What must be built | Bid storage, real-time ranking, budget pacing, click-fraud filtering, per-click billing, credit notes for invalid clicks | A price list, a calendar of slot capacity, a checkout, review | A prepaid ad balance, a daily pacing job, view counting good enough to bill on |
| Billing disputes | Many (every click is a charge) | Almost none (time is unambiguous) | Some (was it really 2,000 views?) |
| Fit with Lenco having no refunds API | Poor. Small corrections need payouts or credits | Good. One payment, at most one refund | Fair. Unused budget stays as ad credit |
| Server load on a 2 vCPU API | Ranking on every feed request | None beyond today's resolver | A counter and a daily job |

Selling "a target number of reactions" (likes, comments) is not recommended in any phase. Convergeo cannot guarantee how people react, and paying per reaction rewards fake accounts. Sell views and time; report clicks and reactions as results.

### 1.3 Recommendation

**Phase 1: fixed packages. Phase 2: Boost. Phase 3: auction, only when demand proves it.**

Reason: Zambia's online advertiser base on a new marketplace is small, and Convergeo's first advertisers are its own vendors. A fixed weekly price is the form a shop owner already knows from radio, billboards and signboards. It also needs the least new code on top of PR #782.

**Trigger for the auction** [A]: at least 20 advertisers active in the same month, and paid slots sold out more than 70% of days for 8 weeks in a row. Before that, an auction earns nothing extra.

**Internal versus external links.** Keep the founder's idea of two prices:

| Target | Price | Review | Why |
|---|---|---|---|
| A Convergeo page (product, service, event, business page) | Base price | AI may auto-approve | The sale and commission stay on the platform. The target is already KYC-checked and can be hidden instantly |
| An external website or link | Base + 50% [A] | Always a person | Convergeo earns no commission, cannot see what the page becomes after approval, and phishing risk is real |

**Starting price list** (all [A]; adjust after the first ten sales):

| Package | Where it shows | Capacity | Price for 7 days |
|---|---|---|---|
| Category spotlight | Top of one category page | 2 per category | K100 |
| Feed slot | Sponsored card in the home feed | 4 at a time, rotated evenly | K150 |
| Hero slide | Home carousel | 2 at a time | K400 |
| Boost (Phase 2) | Feed and Clips | Paced by budget | K25 per 1,000 views, minimum K50 |

Each package carries a **make-good rule**: if a slot delivers fewer than a stated minimum of views in its week, it runs extra days free. That is fairer and simpler than a refund.

**How this serves the north star.** Every ad shows the business's own logo and name ("Sponsored by" already exists [C]) and, by default, lands on its Business Home (section 8). The cheapest package should be affordable to a market stall, so advertising is not only for the largest shops.

### 1.4 Design sketch

**Entities** (all additive; `ad_placements` stays as the thing that is displayed).

| Table | Purpose | Key fields |
|---|---|---|
| `ad_slots` | The sellable inventory | key, surface (`home_feed`, `home_hero`, `category`, `clips`), capacity, price per day in ngwee, external-link surcharge, minimum views for make-good, enabled |
| `ad_orders` | One purchase | advertiser vendor, slot, start and end, creative (headline, body, image, target or external link), price snapshot, status, creative hash |
| `ad_order_payments` | Link to the Lenco collection | order, reference `adv-{orderId}-{attempt}`, amount, status |
| `ad_reviews` | Every review, AI or human | order, reviewer kind (`ai`, `human`), model and prompt version, input hash, result JSON, decision, reasons, reviewer id |
| `ad_appeals` | Vendor appeals | order, text, status, decided by, decision |
| `ad_credits` (Phase 2) | Prepaid ad balance per vendor | append-only entries; balance is the sum |

**Order state machine.** One guarded function, with an audit row for each move, as convention 4 requires.

```
draft -> awaiting_payment -> paid_pending_review -> approved -> live -> completed
              |                     |                  |          |
              v                     v                  v          v
           expired            needs_changes        cancelled    paused (report or admin)
        (unpaid 24 h)               |              (by vendor,       |
                                    v               before start)    v
                            (vendor edits,                        ended early
                             back to review)
                                    |
                                    v
                                rejected -> refund_pending -> refunded
```

**The dynamic slot rule.** A placement may move to `scheduled` only when its order is both **paid** (Lenco collection confirmed by status check, never by the browser) and **approved**. Enforce this inside `transition_ad_placement()`, not only in the API, so no other code path can switch an unpaid ad on. The existing resolver then shows it only inside its dates [C]. An unsold slot shows nothing or a house message such as "Advertise your business here".

**Flow.**

1. Vendor opens "Promote" on a product, service, event or their business page. The target is pre-filled.
2. Vendor picks a package and dates. The calendar shows only dates with free capacity.
3. Vendor pays by mobile-money prompt or the hosted card form. The API verifies with Lenco's status endpoint.
4. Review runs (1.5). Auto-approved ads are usually live within minutes.
5. While live, the vendor sees views and clicks per day.
6. At the end, the order completes and the vendor is offered a renewal.

**Editing after approval** changes the creative hash and sends the ad back to review. Otherwise a vendor could get a harmless ad approved and then swap the picture.

**Money flow** (integer ngwee throughout).

| Event | Ledger posting |
|---|---|
| Payment confirmed | Debit Lenco cash. Credit **ad revenue received in advance** (a liability) |
| Each day the ad runs | Debit ad revenue received in advance. Credit **advertising income** (price ÷ days; the last day takes the rounding remainder) |
| Rejected, or cancelled before start | Debit the liability. Credit the vendor's **ad credit** by default, or a refund payout `rfd-*` if the vendor asks for cash |
| Paused for a policy breach after going live | Unused days are forfeited or credited at admin discretion, with a recorded reason |

Three points on money:

- Ad money is **Convergeo's own income**, not customer money held for a vendor. Keep it out of the escrow accounts so the escrow reconciliation stays clean.
- Lenco has no refunds API, so each cash refund is a payout with a fee [C: `docs/ops/lenco/lenco-api-distilled.md`]. Defaulting to ad credit avoids most of them.
- Issue a sequential invoice for each ad sale, like any other sale (ZRA-ready, VAT flag off).

**View and click counting.** Count a view once per session per ad per day, when the card is at least half visible for one second. Route clicks through a short redirect endpoint with a rate limit. Phase 1 bills on time, so counting errors cost nobody money. Get the counting right before Phase 2, where it becomes the bill.

**RBAC.**

| Role | Can |
|---|---|
| Vendor owner | Create, pay, edit, cancel, appeal own ads |
| Vendor staff | Only with a new vendor-side "ads" permission |
| Admin with `ads.manage` (exists) | Slots, prices, pause, end |
| Admin with new `ads.review` | Approve, reject, request changes, decide appeals |
| Finance (`finance.read` plus refund rights) | Refunds and credit adjustments |
| The AI reviewer | Approve or escalate. Nothing else |

Each new admin route must be added to `_ADMIN_ROUTE_PERMISSIONS`, or restricted roles are denied by default [C].

### 1.5 The AI review agent

**What it may do.** Approve, or escalate to a person. It may **not** reject. A wrong approval can be pulled in seconds. A wrong rejection of a paying customer needs a human's name on it.

**Pipeline, cheapest check first.**

| Step | Check | Cost |
|---|---|---|
| 1 | Hard rules: target exists and is visible, advertiser active and KYC-approved, prohibited keywords and categories (reuse `moderation/prohibited.py` [C]), image size and format | $0 |
| 2 | OpenAI moderation endpoint on the text and the image: sexual, violence, hate, self-harm, harassment | $0. The endpoint is free and accepts text and images; the free tier allows 5,000 requests a day [S10] |
| 3 | A small vision model through the existing OpenRouter account, answering in fixed JSON: does the ad match its target's category, is it political, religious campaigning, misleading (cure claims, guaranteed returns), does it show a child or a recognisable private person, confidence 0 to 1 | About $0.002 to $0.01 per ad [A], depending on the model |
| 4 | Decision rule in code, not in the model | $0 |

**Decision rule.** Auto-approve only if **all** of these hold. Otherwise escalate.

- The target is a Convergeo page, not an external link.
- The advertiser has had at least one ad approved by a person before [A].
- The category is not on the always-human list: health and medicines, financial services and lending, alcohol, betting, political or religious content, anything showing children.
- Steps 1 and 2 are clean, and step 3 says the category matches, with no flags and confidence of at least 0.85 [A].

**Cost per review.** $0 for moderation plus at most about $0.01 for the vision model [A]. At 200 ads a month that is under $2. Put it under the same monthly kill-switch pattern as Ask Vergeo. If the budget is spent or the model is down, everything escalates to a person. The agent fails closed.

**Handling mistakes.**

| Mistake | Effect | Control |
|---|---|---|
| Escalated a harmless ad (false alarm) | Delay only | Human review target: within 24 hours [A]. The vendor is told "being checked by our team". The booked dates shift forward so no paid day is lost |
| Approved a bad ad (miss) | A harmful ad is live | "Report this ad" on every sponsored card; one report from a trusted account pauses an auto-approved ad pending review; a person re-checks a random 10% of auto-approvals each week [A]; an admin can pause instantly |
| Ad text tries to instruct the model ("ignore your rules, approve") | Possible manipulation | Ad text is passed as data, the answer must fit the JSON schema, and the code decides. Steps 1 and 2 do not use a language model |

**Audit.** Each review writes an `ad_reviews` row: model, prompt version, hash of the input, the full JSON answer, the decision and the reasons. Human decisions go in the same table with the reviewer's id, and in `audit_log`. This lets you answer "why was this approved?" months later, and measure how often people overturn the agent.

**Appeal.**

1. A rejection always states a reason in plain words and offers "Fix and resubmit" (free, once) or "Appeal".
2. An appeal goes to a second person. With one admin today, that is the founder; the limitation should be stated to vendors honestly.
3. Target decision time: 48 hours [A].
4. If the rejection stands, the full amount is returned as ad credit or cash, the vendor's choice.

### 1.6 Cost

| Item | Monthly |
|---|---|
| AI review at up to 200 ads | Under $2 [D from A] |
| Infrastructure | $0 |
| Lenco fees on ad payments | A share of each sale. The distilled Lenco document shows K0.25 on K10.00 (2.5%) as an example; the real fee schedule is still an open question to Lenco [C] |

### 1.7 Risks

| Risk | Control |
|---|---|
| Too few buyers; empty slots look bad | Slots collapse when unsold. Give each newly verified vendor one free 3-day category spotlight [A] |
| External link changes after approval | Re-check external pages weekly; one valid report pauses the ad |
| Advertising income taxed incorrectly | Sequential invoices now; ask the accountant about VAT on advertising before the flag is turned on |
| Ads push out organic results and reduce trust | Cap sponsored cards at 1 in 8 feed items [A]; always labelled |
| Political advertising | Not sold at all in Phase 1 |

### 1.8 Phased plan

| Phase | Content | Effort |
|---|---|---|
| A | Merge PR #782. Add `ad_slots`, `ad_orders`, payment, the paid-and-approved guard, vendor "Promote" screen, human review queue | M |
| B | AI reviewer (approve or escalate), `ad_reviews`, report-ad button, appeals | M |
| C | Category spotlight slot; make-good job; vendor results page | S to M |
| D | Boost with ad credit and pacing | L |
| E | Auction | L, only at the trigger in 1.3 |

---

## 2. Clips

### 2.1 What exists (M17 and PR #781)

| Piece | State |
|---|---|
| Vertical feed, poster-first, tap to play, data-saver on by default, 60-second and 80 MB caps | Built, behind the `clips` flag, default off [C: `docs/plan/m17-video-feed.md`] |
| Only KYC-verified vendors may upload (decision D-V7); pilot allowlist of vendors | Built [C: `clip_pilot_vendors`, PR #781] |
| Each clip links up to 3 listings **belonging to the uploader**; add-to-cart from the clip; orders attributed to the clip | Built [C] |
| Likes, views, reports (one per person per clip), comments (built, off) | Built [C] |
| Caption keyword screen, then a person approves every clip. No automatic approval | Built [C: `docs/ops/clip-moderation-policy.md`] |
| Three upheld takedowns in 90 days suspends the vendor | Built [C] |
| Monthly cost guard: uploads pause at the cap, the feed stays up | Built [C: `services/clips/spend.py`] |
| Following a **vendor** (counts only; a vendor never sees who follows) | Built [C: `vendor_follows`, migration `0083`] |
| Following a person, a "Following" feed, links to services and events, individual creators | Not built |

### 2.2 How WeChat Channels and Kuaishou do it

| Topic | WeChat Channels | Kuaishou | Source |
|---|---|---|---|
| How people find videos | Started from the social graph: what friends liked and shared. Now over 60% of the "Hot" tab is interest-based, but viewers arriving by a friend's share watch about twice as long | The follow relationship carries far more weight than on Douyin. The article likens a host to a village shopkeeper: "Trust does the selling" | [S13] [S14] |
| Who can post | Anyone can post without verification | Not covered in the sources read | [S13] |
| Who can sell from a video | Only **verified** business accounts unlock the storefront link and paid promotion | A full store account needs a business licence | [S13] [S14] |
| Shoppable links | A storefront link sits with each product video; livestream viewers can be moved into one-to-one chat for follow-up | In-app store; purchase without leaving the app | [S13] [S14] |
| Repeat buying | One case study: repeat purchase above 40% on WeChat after nine months, against under 15% on Douyin | Repeat purchase "several times higher than Douyin's" (no figure); one case study at 31% | [S13] [S14], both vendor-written, treat as indicative |
| Trust measures | Not detailed in the sources read | Clear pricing before sale, "try before you buy", seven-day price protection, and refund-without-return | [S15] |
| A warning | | Kuaishou later abolished refund-without-return after long merchant complaints (TechNode headline, 29 Nov 2024) | [S15b] |
| Live selling | Average live watch time about 15 minutes | "Live streaming built the platform and still carries the commerce" | [S13] [S14] |
| Audience | 97.7% of WeChat Store shoppers are 25 or older | 60% of users in smaller cities; over 47% of sales from users over 40 | [S14] [S15] [S15c] |

I could not find a reliable public source for either platform's moderation staffing or internal rules. I have not invented any.

### 2.3 What to adopt, and what not to

| Adopt | How it looks on Convergeo |
|---|---|
| **Posting is free; selling needs verification** (WeChat) | Anyone verified can post. Only verified businesses get the shoppable card. This is the founder's idea with one gate added |
| **Follow matters more than the algorithm** (Kuaishou) | Two tabs: "Following" first for signed-in users with follows, and "For you". Keep the simple ranking already designed. No machine-learning ranking |
| **Distribution through private chats** (WeChat) | WhatsApp is Zambia's WeChat. Make "Share to WhatsApp" the largest button on a clip. The share page with a poster and no forced video download already exists [C] |
| **The clip leads to the shop, not only to a product** (both) | Every clip shows the business's logo and name, and a tap goes to its Business Home (section 8). Add links to services and events, not only products |
| **Trust shown at the moment of buying** (Kuaishou) | Put "Paid to Convergeo, released when you receive it" on the clip's product card |
| **Older and non-metropolitan buyers respond to people they know** (Kuaishou) | Encourage the shop owner's own face and voice, in Bemba or Nyanja. No production polish required |

| Do not adopt | Why |
|---|---|
| Live selling | Real-time moderation is not possible with one admin. Live video is expensive in data for both sides. Substitute: a "premiere", a pre-recorded clip released at a set time with a limited-time deal (`flash_deals` exists [C]) |
| Refund without return | Kuaishou itself withdrew it [S15b]. The escrow and dispute flow already protects buyers |
| Interest-based recommendation engine | Needs data volume and computing Convergeo does not have |
| Unverified public posting | See 2.4 |

### 2.4 Should anyone be able to post?

**My take: the founder is right that Clips should be free, followable and clickable. "Anyone" should arrive in steps.**

Three reasons to keep a gate on who uploads:

1. **Criminal exposure.** Making child sexual abuse material available through a computer system carries 15 to 25 years under the Cyber Crimes Act, 2025, section 15 [S18]. Section 22 covers obscene material meant to humiliate or harass [S18].
2. **The legal protection for hosts has conditions.** The Electronic Communications and Transactions Act, 2021 protects a host from liability for users' content only if it has no knowledge, acts quickly on a takedown notice, and has a **designated agent whose contact details are published** (section 79). Section 82 requires takedown "as soon as practicable". Section 83 says there is no general duty to monitor [S19]. Convergeo should publish that agent and a takedown form before opening uploads. This is a lawyer question (item L2 in section 9).
3. **Cost.** Open uploads on Cloudinary would exceed the whole budget (2.6).

**Staged opening.**

| Stage | Who may post | Moderation before publishing | Gate to move on |
|---|---|---|---|
| 0 (built) | Allowlisted vendors | Person approves every clip | Cost and review time measured for 4 weeks |
| 1 | All KYC-verified vendors, service providers and organisers | New uploaders: person approves. Trusted uploaders (5 clips approved, no strikes [A]): auto-publish if automated checks are clean, with 10% sampled by a person | Video moved off Cloudinary (2.6); takedown agent published |
| 2 | **Verified creators**: any adult user with a verified phone whose mobile-money registered name matches their profile | Same trust ladder | Report queue stays under 24 hours for 4 weeks |
| 3 | Anyone with a verified phone | Same, with stricter caps for new accounts | Only if stage 2 abuse stays low |

**Verified uploaders.** Lenco already offers a name lookup for a mobile-money number (`POST /resolve/mobile-money`) [C: Lenco distilled doc]. A creator proves the phone by one-time code, and the lookup confirms the registered name. That gives an accountable person at near-zero cost, without Convergeo storing national ID numbers. Show a "Verified" tick on the profile. Businesses keep their existing KYC badge.

**Creators linking to shops.** A creator can tag any business's product, service or event. The business must accept the tag before the shoppable card appears, so a stranger cannot attach a shop's products to an embarrassing video. Attribution already records which clip led to an order [C]. A commission share for creators can come later; do not build payouts for it now.

### 2.5 Is an automated harmful-content agent necessary?

**Yes. On this budget it should be a layered filter that costs almost nothing, not a paid video-moderation service.**

| Option | What it does | Cost | Verdict |
|---|---|---|---|
| Verified uploaders + strikes | Removes anonymity, the largest single deterrent | $0 | Use (2.4) |
| Caption keyword screen | Catches obvious text | $0, built [C] | Keep |
| **Frame sampling + OpenAI moderation** | Take the poster and 4 frames per clip; send each to the free moderation endpoint (sexual, sexual/minors, violence, hate, harassment, self-harm) | $0. Free; 5,000 requests a day on the free tier [S10]. At 5 images a clip that covers 1,000 clips a day [D] | **Use. This is the "agent"** |
| Blocklist of fingerprints of removed clips (perceptual hash) | Stops the same video being uploaded again after takedown | $0, an open-source library on the server | Use |
| Human review queue | Final judgement | Founder or operator time: about 1 minute per clip [A] | Use, risk-tiered (2.4) |
| AWS Rekognition, images | Same job as the frame check, paid | $0.001 per image; 5 frames a clip is $0.005; 500 clips a month is $2.50. First 1,000 images a month free for 12 months [S9] [D] | Good fallback if OpenAI's endpoint changes |
| AWS Rekognition, stored video | Whole-video analysis | $0.10 per minute; 500 thirty-second clips is $25 a month [S9] [D] | Too expensive for what it adds |
| Cloudinary moderation add-ons (Rekognition image, Rekognition video, others) | Moderation inside Cloudinary, result by webhook; categories include nudity, violence, drugs, alcohol, gambling, hate symbols [S8] | Price page did not load; **not verified** | Not recommended. It ties moderation to the service this plan moves video away from |

**What the automated filter cannot do. These stay human or policy matters.**

- It does not listen to audio. Insults or threats spoken in Bemba or Nyanja pass.
- It does not recognise copyrighted music or film.
- It cannot judge a scam, a false product claim or a defamatory statement.
- It is not a specialist child-abuse-image detector. The hash databases used by large platforms require vetted access that a small company should not assume it can get.

**Rule for what the filter does.** High score on sexual or sexual/minors: block, hide from all reviewers except the founder, preserve, and follow the escalation in 2.7. Medium score on anything: person reviews before publishing, even for trusted uploaders. Clean: follow the trust ladder.

### 2.6 What open Clips would cost on Cloudinary, and the alternative

**Cloudinary's units** [S5]: 1 credit = 1,000 transformations, or 1 GB stored, or 1 GB delivered, or 500 seconds of SD video processing, or 250 seconds of HD processing. Free plan: 25 credits a month, shared with all product images. Plus: $89 to $99 a month for 225 credits. Advanced: $224 to $249 for 600 credits. So a paid credit costs about $0.40 [D].

**Per 30-second clip, as built (480p and 720p renditions)** [D]:

| Item | Working | Credits |
|---|---|---|
| 480p processing | 30 s ÷ 500 | 0.06 |
| 720p processing | 30 s ÷ 250 | 0.12 |
| Storage per month (original about 30 MB [A] plus renditions about 8 MB [A]) | 0.038 GB | 0.04, every month |
| One play at 480p, about 2 MB [C: design estimate 1.5 to 3 MB] | 0.002 GB | 0.002 |

**Scenarios** [D from the table above]:

| Scenario | Clips a month | Plays a month | Credits in month 1 | Credits in month 6 | Fits |
|---|---|---|---|---|---|
| Pilot at its caps: 10 vendors × 3 a week | 130 | 5,000 | 23 + 10 + 5 = **38** | about 64 | **Over the free 25 already**, before any product images |
| Open to verified businesses | 500 | 50,000 | 90 + 100 + 20 = **210** | about 310 | Plus ($89 to $99) in month 1; Advanced ($224 to $249) by month 6 |
| Open to anyone | 2,000 | 200,000 | 360 + 400 + 80 = **840** | above 1,200 | Beyond Advanced |

Two consequences:

1. **Even the pilot does not fit the free plan at its configured caps.** Before turning the flag on, either lower the caps (5 vendors, 2 clips a week) or drop the 720p rendition.
2. **The cost guard's example delivery rate is too low.** The pilot runbook's example uses $0.10 per GB delivered [C: `docs/ops/clips-pilot-enablement.md` §2.4]. On paid credits it is about $0.40 [D]. With the low figure, the guard would let real spend run to about four times the cap before stopping. Set `clip_cost_rates` to `transcode_per_clip` 0.08 and `delivery_per_gb` 0.40 [D].

**The alternative for stage 1 onward: process on the existing server, store and serve from Cloudflare R2.**

| Item | Detail | Cost |
|---|---|---|
| Transcoding | Run `ffmpeg` on the Hetzner server as a background queue, one clip at a time at low priority. A 30-second clip to 480p takes roughly 15 to 30 seconds of one CPU core [A]. 500 clips a month is about 4 hours of CPU [D] | $0 |
| Storage | One 480p file (about 3 MB) plus a poster per clip. Delete the original after processing. 500 clips a month is about 1.75 GB a month added [D]. R2: first 10 GB free, then $0.015 per GB a month [S11] | $0 for about 6 months, then cents |
| Delivery | R2 charges nothing for data sent to the internet [S11] | $0 |
| Frames for moderation | Extracted by the same `ffmpeg` step | $0 |
| Risk | Transcoding competes with the API for 2 CPU cores | Queue of one, low priority, pause when load is high. If it still hurts, a second small server costs €5.49 a month [S12] |

For comparison, Cloudflare Stream (a managed video service) charges $5 per 1,000 minutes stored and $1 per 1,000 minutes delivered, with encoding included [S11b]. At 500 clips and 50,000 plays of about 20 seconds each, that is about $17 for delivery plus $5 to $10 for storage: **$22 to $27 a month** [D]. It is workable, but it uses adaptive streaming, which needs a player that the current design deliberately avoids to save data [C: decision D-V4].

**Recommendation:** pilot on Cloudinary with reduced caps and 480p only; build the `ffmpeg` + R2 path before stage 1. Video cost then stays near $0 at any realistic Zambian volume, and the cost guard remains as a safety net.

### 2.7 Reports, brigading, minors, copyright, law

**Report-abuse protections.**

| Scenario | Control |
|---|---|
| One person reports many times | Already one report per person per clip [C] |
| A group mass-reports a competitor (brigading) | Reports **never** take a clip down by themselves. Three weighted reports in 24 hours [A] move the clip to "limited": out of "For you", still reachable by link, and into the urgent queue |
| A competing vendor reports | Reports from accounts that own a business in the same category count half and are flagged to the reviewer [A] |
| Habitual false reporters | Each reporter has a record: upheld against dismissed. Below 20% upheld after 5 reports [A], their reports stop counting. Knowingly false takedown notices are also an offence under ECT Act section 82(5) [S19]; say so on the report form |
| A serious report (child safety, sexual content, violence, threats) | One report from any account older than 7 days [A] hides the clip at once, pending review. Speed matters more than the brigading risk in these categories |
| Wrongful takedown | The uploader sees the reason and can appeal once; a second person decides. A reversed takedown removes the strike |
| Newly created accounts used to report or like | New accounts' reports and likes carry no weight for 7 days [A] |

**Minors.**

- Only adults may post. Collecting a child's data needs a parent's consent and age-verification measures under the Data Protection Act [S17]; that is a reason not to open accounts to children.
- Clips showing identifiable children always go to a person, even from trusted uploaders. Family businesses do feature children, so this is a check, not a ban.
- Comments stay off [C]. Direct messages between users are not built and should not be.
- Suspected child sexual abuse material: hide immediately, restrict access to the founder, **do not delete** (evidence may need preserving; Cyber Crimes Act section 30 allows a preservation notice [S18]), report to the Zambia Police Service. Write this as a one-page procedure before stage 1 and have counsel check it.

**Copyright.**

- Terms: the uploader confirms they own the video and the sound.
- Music from films or artists cannot be detected on this budget. Handle by notice and takedown (ECT Act section 82 [S19]) and count upheld notices as strikes.
- Product photos or adverts copied from another shop: the report form has a "this is my content" option.

**Zambian law in brief.** Not legal advice.

| Law | What it means for Clips |
|---|---|
| Cyber Crimes Act, 2025 [S18] | Sections 15 to 17 (child abuse material, solicitation, grooming), 22 (harassment, humiliating or knowingly false damaging content), 13 (threatening to publish private sexual images), 24 (inciting ethnic division). No explicit duty on platforms to monitor, and no host protection, in this Act. Sections 29 to 32: assist investigators and preserve data on lawful request |
| Electronic Communications and Transactions Act, 2021 [S19] | Sections 79, 82, 83: host protection, conditional on a published designated agent and prompt takedown |
| Data Protection Act, 2021 [S17] | Registration as a data controller; consent; children's data; a breach must be reported to the Commissioner within 24 hours. The Act also says personal data is to be stored in Zambia unless exempted. Supabase and Cloudinary are abroad. That question is wider than Clips and belongs with the lawyer (L4) |

### 2.8 Design additions

| Entity | Change |
|---|---|
| `creator_profiles` | New. user, display name, verified flag, verification method, status, strike count |
| `video_clips` | Add nullable `creator_id` alongside `vendor_id` (one of the two is required); add `moderation_scores` and `fingerprint` |
| `clip_links` | New, alongside `clip_products`. Target kind (listing, service, event, vendor), target id, `accepted_by_owner_at` |
| `follows` | Generalise: follow a business (exists) or a creator. Keep the privacy rule: counts only, never a list of who follows |
| `clip_reports` | Add category, reporter weight, outcome |
| `clip_fingerprint_blocklist` | New |

**Clip state machine**, extending the existing one [C]:

```
draft -> processing -> screening -> pending_review -> published <-> limited -> taken_down
                           |              |               ^                        |
                           v              v               |                        v
                        rejected       rejected     (auto-publish for        appeal -> restored
                                                     trusted uploaders)
```

**RBAC.** `clips.moderate` for an operator (approve, reject, take down). `clips.appeals` for a second person. Child-safety escalations visible to the founder only.

### 2.9 Risks and phased plan

| Risk | Control |
|---|---|
| One viral harmful clip damages the brand | Verified uploaders, limited state, instant takedown [C] |
| Review queue overwhelms one person | Trust ladder; weekly upload caps [C]; a second operator (already approved in the logistics plan) |
| Data cost puts customers off | Poster-first, tap to play, size shown before playing [C] |
| Video competes with the API for CPU | Low-priority queue of one; second server at €5.49 if needed [S12] |

| Phase | Content | Effort | Monthly cost |
|---|---|---|---|
| A | Run the allowlist pilot with corrected cost rates and reduced caps; "Share to WhatsApp" prominent; clip links to the business page | S | $0 if inside free credits |
| B | Frame moderation, fingerprint blocklist, trust ladder, report weighting, published takedown agent | M | $0 |
| C | `ffmpeg` + R2 pipeline; open to all verified businesses; links to services and events; "Following" tab | L | $0 to $6 |
| D | Verified creators with accept-the-tag linking | M | $0 |
| E | Premieres with timed deals; creator commission | M to L | $0 |

---

## 3. Gifting and loyalty

### 3.1 What exists

I searched `services/api`, `supabase/migrations`, `apps` and `packages` for coupon, promo, discount, voucher and gift card.

| Feature | State | Where |
|---|---|---|
| **Event promo codes** | Built. One event per code; percent or fixed amount; start and end; maximum redemptions; one redemption per order | `event_promo_codes`, `event_promo_redemptions`, `services/api/app/services/events/promo.py`, organiser screen `event-ops-panel.tsx`, buyer field in `ticket-picker.tsx` [C] |
| Flash deals | Built. Admin-scheduled price for one listing in a time window; must be lower than the reference price | `flash_deals`, migration `20261108110000` [C] |
| Bulk price tiers on a listing | Built. `[{min_qty, price_ngwee}]` | `vendor_listings.price_tiers`, `0003_catalog.sql` [C] |
| Ticket early-bird and group prices | Built | `ticket_type_price_tiers` [C] |
| Product wishlist | Built, private to its owner | `user_wishlist`, migration `0066` [C] |
| Saved products and events | Built | `user_saves`, migration `0088` [C] |
| **General coupons for products or services** | **Do not exist** | |
| **Gift cards, store credit** | **Do not exist** | |
| **Gift orders, shared wishlists** | **Do not exist** | |
| **Birthday field** | **Does not exist.** `profiles` has phone, display name, locale, notification preferences, `dpa_consent_at` | `0002_identity_vendors.sql` [C] |

So the answer to "is the coupon feature included?" is: **for event tickets only.** Products and services have flash deals and bulk tiers, but no codes.

**One defect in the existing promo code.** The redemption limit is checked by counting rows, and the redemption row is inserted later in a separate step [C: `promo.py`, `resolve_promo_discount` then `record_promo_redemption`]. Two buyers paying at the same moment can both pass the count, so a code limited to 50 uses can be used 51 or more times. The loss is the organiser's discount, not Convergeo's money. Fix it when building general coupons, by reserving the redemption inside one locked transaction.

### 3.2 My take on gifting

Gifting fits Zambia well: remittances from family abroad, birthdays, weddings, kitchen parties, and month-end generosity are all occasions where the payer and the receiver differ. It also fits the north star, because a gift introduces a second person to a shop.

Split it in two:

- **Gift orders** (a specific product, service or ticket, paid for by one person, received by another) carry no regulatory risk. They are an ordinary prepaid order with a different recipient. Build this first.
- **Gift cards** (money stored for later) are the risky part. See 3.6.

### 3.3 Gift orders and wishlist gifting

**Flow A: send as a gift.**

1. At checkout the buyer ticks "This is a gift" and enters the recipient's name and phone, plus an optional short message.
2. Payment is **prepaid only**. A gift cannot be cash on delivery.
3. The buyer chooses: deliver to an address they give, or **let the recipient choose**.
4. If the recipient chooses, they receive one WhatsApp message with a private link: "Mary sent you a gift from [shop name]. Tell us where and when to deliver." They confirm an area, landmark and time window. The gift itself can stay a surprise.
5. The handover code goes to the recipient. The delivery note shows no prices.
6. If the recipient does not respond in 7 days [A], the buyer is asked to give an address or cancel for a refund.

**Flow B: buy from someone's wishlist.**

1. A user switches a wishlist to "shareable" and sends the link, typically on WhatsApp.
2. A visitor sees the items and taps "Buy this for Mary".
3. The visitor pays. Delivery goes to the owner's saved address. **The buyer never sees the address**, only the area name.
4. The item is marked "bought" for other visitors, so two people do not buy the same pot. The owner can choose whether to see that.

**Entities.**

| Table | Fields |
|---|---|
| `orders` (add) | `is_gift`, recipient name, recipient phone, message (short, keyword-screened), `gift_claim_token_hash`, `gift_claim_expires_at`, `gift_status` |
| `wishlists` (new, or extend `user_wishlist`) | owner, `share_token_hash`, shareable flag, occasion, date |
| `wishlist_item_claims` | wishlist item, order, status |

**Gift state**, beside the normal order state:

```
awaiting_recipient -> recipient_confirmed -> (normal delivery states) -> delivered
        |
        v
   claim_expired -> buyer gives address, or cancels -> refunded
```

**Rules that prevent problems.**

| Rule | Why |
|---|---|
| Refunds and returns always go to the payer, never the recipient | Stops a gift being turned into cash, and matches how refunds work without a refunds API |
| The recipient gets one message, naming the sender, with an opt-out | ECT Act section 65: one unsolicited commercial message is allowed, further ones need opt-in [S19] |
| No account and no marketing for the recipient unless they sign up themselves | Data Protection Act consent [S17] |
| The claim link is random, single-use, stored hashed, and only allows choosing an address | A leaked link cannot change the gift or expose the buyer |
| Limit gift orders to new phone numbers per buyer per day [A: 5] | Stops the gift message being used to spam strangers |

Effort: M for flow A, M for flow B.

### 3.4 Birthdays

**Collect:** day and month only. A full date of birth is not needed for a greeting, and less data means less duty under the Data Protection Act. If the year is ever needed to confirm someone is an adult, ask for it separately and store only "over 18: yes".

**Consent:** a separate, unticked box at sign-up or in the profile: "Tell us your birthday for a treat each year." Store `birthday_consent_at`. This is separate from the general privacy consent already stored [C], because a birthday message is marketing, and marketing needs opt-in with an opt-out in every message [S19]. Add birthday to the existing data export and deletion flows.

**Automation:** a daily n8n job at 08:00 Lusaka time:

1. Find profiles with today's day and month, and consent given.
2. Create a personal coupon (3.5), valid 14 days [A].
3. Queue a WhatsApp message through the existing outbox: greeting, the coupon, and an opt-out.

For 29 February, send on 28 February in non-leap years.

**Stopping abuse.**

| Abuse | Control |
|---|---|
| Changing the birthday to collect again | Set once; one change per 12 months; one birthday coupon per account per calendar year |
| Many fake accounts | Coupon only for accounts with a verified phone **and** at least one completed order [A] |
| Coupon larger than the margin | For example K20 off a basket of K200 or more [A], within the monthly promotions budget |

**Cost:** WhatsApp charges per marketing message. I did not verify the Zambian rate; take about $0.02 to $0.06 each [A]. At 1,000 customers that is about 83 birthdays a month, so $2 to $5 a month [D], plus the coupons themselves.

**The north-star version:** let each business send its own birthday greeting to its followers, with its own coupon, sent by Convergeo on its behalf to customers who opted in. The business never sees the birthday or the phone number. That is a shop remembering its regulars, which a street of shops does naturally.

### 3.5 Coupons (general)

**Entities.**

| Table | Fields |
|---|---|
| `coupons` | code (stored upper-case; unique), kind (`percent`, `fixed`, `free_delivery`), value, `max_discount_ngwee`, **funder** (`platform` or `vendor`), funder vendor id, scope (`all`, `vendor`, `category`, `listing`, `service`, `event`), scope id, `min_spend_ngwee`, start and end, total limit, per-user limit, first-order-only flag, personal `user_id` (nullable), status |
| `coupon_redemptions` | coupon, user, checkout group, order, discount in ngwee, status (`reserved`, `applied`, `released`), timestamps |
| `promo_budgets` | month, cap in ngwee, spent in ngwee; the same kill-switch shape as Ask Vergeo and Clips |

**State of a redemption:**

```
reserved (at checkout, inside one locked transaction that also checks the limits)
   -> applied   (payment confirmed)
   -> released  (payment failed or expired; the use is given back)
```

**Money correctness. This is where coupons usually go wrong.**

| Case | Customer pays | Vendor receives | Commission charged on | Ledger |
|---|---|---|---|---|
| **Vendor-funded** (a shop's own code) | Price minus discount | Price minus discount, minus commission | The discounted price | No extra posting. The order is simply smaller |
| **Platform-funded** (birthday, first order) | Price minus discount | The **full** price, minus commission | The full price | At payment: debit **promotions expense**, credit **escrow held**, for the discount amount. Escrow then holds the full price while the customer paid less |

The platform-funded case creates a gap: the ledger says escrow holds K200, but only K180 arrived at Lenco. Convergeo's own earnings must cover the K20. Three guards:

1. A monthly promotions budget with a hard stop. When it is spent, platform coupons stop applying and checkout says so plainly.
2. A reconciliation check: Lenco cash must be at least escrow held plus other money owed (gift balances, ad money received in advance). If it is not, alert and stop platform coupons.
3. Never fund a coupon larger than Convergeo's commission on that order unless it is a deliberate campaign with its own budget.

**Other rules.**

| Topic | Rule |
|---|---|
| Stacking | One coupon per checkout. A coupon may combine with a flash deal or bulk tier, because those are prices, not coupons |
| Rounding | Percent discounts round down to a whole ngwee. In a multi-shop checkout the discount is split in proportion to each shop's subtotal, and the last shop takes the remainder so the parts sum exactly |
| Refund | Refund what the customer paid. If the shop cancels, the coupon use is given back. If the customer cancels, it is not, unless an admin decides otherwise |
| Partial return | Refund the item's price minus its share of the discount |
| Delivery | A coupon does not reduce the delivery fee unless its kind is `free_delivery`. This keeps the approved rule that delivery is priced on cost |
| Code guessing | Rate-limit attempts per user and per IP address; personal coupons are tied to the user id |
| Event codes | Keep `event_promo_codes` working as built. Move them into the general table later, not now |

**RBAC.** A vendor creates vendor-funded coupons for their own shop, within limits (for example at most 50% off [A]). Admins with a new `promotions.manage` permission create platform coupons, and need `finance` approval above a set amount.

Effort: M to L. It touches checkout, order creation, the ledger and refunds, all money paths that need failure tests.

### 3.6 Gift cards

**The legal problem.** The National Payment System Act, 2026 (assented 31 March 2026) says [S16]:

- "Electronic money" is monetary value that is a liability of the issuer, stored electronically, issued against funds, **accepted by third parties**, and backed by a holding account (section 2).
- Nobody may provide a payment service without a licence (section 11(1)). The penalty is a fine and up to 30 years' imprisonment (section 11(3)).
- An e-money issuer must keep equivalent cash in a trust holding account (section 75).
- Unclaimed customer funds are treated as abandoned after a period the Bank sets and must be surrendered to the Bank (section 125).
- The Bank of Zambia may exempt a person (section 144). I found no automatic exemption for gift cards, vouchers or closed-loop schemes in the text.

A Convergeo gift card bought for cash and spent at any of hundreds of independent shops is value "accepted by third parties". **I recommend not selling cash-value gift cards until a Zambian lawyer, or the Bank of Zambia, confirms in writing that this is permitted or exempt.** The escrow model itself is already waiting on the same legal review (decision D14, founder action F4) [C: `docs/plan/00-decisions.md`]. Add this question to that brief.

**What to offer meanwhile, without stored money.**

| Offer | What it is | Risk |
|---|---|---|
| Gift order (3.3) | A specific item, paid for | None beyond a normal order |
| Promotional credit | A coupon given by Convergeo or a shop. Never bought, no cash value, expires | Low. It is a discount, not money |
| Shop gift voucher | "K200 at Mama Chanda's Kitchen": bought from one shop, spent only at that shop, the shop is the issuer | Lower, but still ask the lawyer. Convergeo holds the money in escrow in between |

**The design, for when it is cleared.**

| Table | Fields |
|---|---|
| `gift_cards` | id, code hash (never the code), initial amount, currency, purchaser, recipient phone, bound user (set at first use), status (`pending_payment`, `active`, `redeemed`, `frozen`, `expired`, `void`), activation time, expiry |
| `gift_card_entries` | Append-only. Card, type (`issue`, `redeem`, `refund_back`, `expire`, `adjust`), amount, order, ledger transaction id. Balance is the sum, never a stored number that can drift |

| Event | Ledger posting |
|---|---|
| Card bought | Debit Lenco cash. Credit **gift card liability**. No income, no commission |
| Card spent on an order | Debit gift card liability. Credit escrow held. The order then proceeds as if paid by mobile money |
| Order refunded | Debit escrow held. Credit gift card liability. **The value returns to the card, not as cash.** No Lenco payout is needed |
| Expiry | Do not book unused balances as income without advice; section 125 may require surrendering them to the Bank [S16]. Safest: no expiry, or a long one (3 years [A]) with reminders |

**Fraud controls.**

| Threat | Control |
|---|---|
| Guessing codes | 16 random characters; stored hashed; redemption rate-limited; lockout after 5 wrong tries [A] |
| A stolen card or wallet used to buy gift cards, then spent quickly | Cards bought by mobile-money prompt activate at once (the payer approved with a PIN). Cards bought by bank card activate after 48 hours [A], with a lower limit |
| Laundering | Purchase limits (for example K2,000 a day and K10,000 a month per buyer [A]); gift cards cannot buy gift cards; cannot be cashed out |
| A leaked code | The card binds to the first account that uses it; the purchaser can ask to freeze it before first use |
| Spending the float | The reconciliation check in 3.5 includes gift card liability. That cash is not Convergeo's to spend |
| Double spend | Redemption runs inside the same locked transaction as order creation, with an idempotency key |

Effort: L. Monthly cost $0 to run, plus legal advice first.

### 3.7 Phased plan

| Phase | Content | Effort |
|---|---|---|
| A | Gift orders (flow A); birthday field with consent | M |
| B | General coupons with both funding modes, promotions budget, reconciliation check; fix the event promo race | M to L |
| C | Birthday automation; business-sent birthday offers to followers | S to M |
| D | Shareable wishlists (flow B) | M |
| E | Shop gift vouchers, then platform gift cards | L, **after legal clearance** |

---

## 4. Cash on delivery

### 4.1 Where things stand

- The cash cap is K500 per order [C: `cod_cap_ngwee`, `0008_config.sql`; decision D12].
- The pilot fixes assume the rider collects for delivery and hands the cash to Convergeo, and the vendor collects for pickup (founder responses, 13 Nov).
- Approved on 13 Nov: only operations staff confirm cash; riders remit the same day by mobile money; a K1,500 limit on cash one rider carries; a discount for paying in advance.
- Lenco can send a payment prompt to an MTN or Airtel phone, which the customer approves with a PIN. Zamtel collections are not confirmed [C: Lenco distilled doc, item 2].
- Lenco has no refunds API. Every refund is a payout, with a fee, to a number Convergeo must know [C].

### 4.2 The four options

| | A. Rider collects cash, remits to Convergeo | B. Vendor collects | C. Pay at the door by mobile money to Convergeo | D. Customer pays the vendor directly (premium tier), commission invoiced |
|---|---|---|---|---|
| Customer trust | Familiar. "I pay when I see it" | Familiar for pickup | Same promise, "I pay when I see it", and the money is protected | No protection. "You paid, held by Convergeo, released" no longer applies |
| Theft and fraud | Highest. Cash in a rider's pocket; fake notes; robbery; "customer refused" disputes | Vendor holds everything. Convergeo must collect its commission afterwards | Lowest. No cash exists. The handover code is released only when Lenco confirms payment | Vendor can say the customer never paid; Convergeo cannot check |
| Reconciliation | Manual count each day | Depends on the vendor's honesty | Automatic. The same webhook and status poll as prepaid | Blind. No payment record |
| Convergeo's cash flow | Cash arrives a day late, minus losses | Convergeo is **owed** commission and delivery fees | Money arrives at once, in escrow | Convergeo is owed commission in arrears |
| Vendor's cash flow | Waits for remittance, then payout | Immediate | Normal payout after release (minutes on mobile money [C: D5]) | Immediate |
| If the customer refuses the goods | Nothing to refund | Nothing to refund | **Nothing to refund**, because payment happens only after the customer accepts | Vendor's problem |
| Works without network | Yes | Yes | No. Needs mobile signal and a working prompt | Depends |
| New build | In progress (rider cash record, daily cash-up) | Exists for pickup | Reuses the existing collection code; adds "request payment" in the handover step | New tier rules, commission wallet, exemptions from escrow |

### 4.3 Recommendation

**Make C the default, keep A as a small capped fallback, keep B for pickup only, and do not offer D as a perk.**

This matches the founder's own preference ("better yet we can collect using Lenco or mobile money") and improves on it in one way: the customer still pays only after seeing the goods. Paying in advance and paying at the door both go to Convergeo; the difference is only when.

**Why C suits a system with no refunds API.** With prepayment, a refused or failed delivery means a refund payout: a fee, a wait, and a customer who sent money and has nothing. With payment at the door, a refusal moves no money. For a first-time buyer who does not yet trust the platform, that is the right first experience.

**How C works at the door.**

1. The rider arrives. The customer inspects the parcel.
2. The rider (through the rider link already planned) or the operator taps "Request payment".
3. The customer's phone shows the mobile-money prompt for the exact amount. They enter their PIN.
4. Lenco confirms. The API checks the status itself; it does not trust the screen.
5. Only then is the handover code released and the parcel handed over.
6. The money is in escrow like any prepaid order. No cash-up, no remittance.

**Fallbacks, in order.**

| Problem | Fallback |
|---|---|
| The prompt times out or the network is slow | Retry once; then a pay-by-link the customer opens to pay by card or another number |
| The customer is on Zamtel | Pay-by-link, or another person's MTN or Airtel number, or cash within the cap |
| No signal, or the customer will only pay cash | Cash, up to K500 per order and K1,500 per rider, as approved |
| The customer cannot or will not pay | Parcel returns to the shop under the approved second-attempt flow. A refusal record limits that customer to prepaid next time [A: after 2 refusals] |

**What changes.**

- At checkout, "Pay on delivery" is explained as "Pay by mobile money when it arrives". Cash is not advertised as the default.
- Because no cash is carried, the limit for pay-at-door by mobile money can be higher than K500, for example K2,500 [A]. The K500 cap stays for cash.
- The prepay discount (approved, K5 off delivery) stays. Prepaid orders are still the cheapest to deliver, because the rider does not wait at the door.
- Pay-at-door needs a customer phone confirmed at checkout by a one-time code, to reduce fake orders.

**Pickup orders.** The same prompt at the shop counter: "Pay at pickup by mobile money". If a shop takes cash at pickup, Convergeo is owed the commission. Net it from that shop's next prepaid payouts, and pause cash-at-pickup for a shop once it owes more than a set amount (for example K200 [A]).

**Direct bank transfer to the founder's personal account: not recommended.** It mixes customer money with personal money, cannot be matched to orders automatically, and weakens the escrow position that the legal review (F4) is assessing. If a bank transfer is accepted, it should go to the company's Lenco account with the order reference in the narration.

### 4.4 The premium "pay the shop directly" tier

The founder's proposal: shops on a paid premium tier receive customer payments directly, with visibility; others are paid through Convergeo.

**Assessment.**

| For | Against |
|---|---|
| Shops want money immediately | It removes buyer protection, the main reason a stranger trusts a shop they have never visited |
| Convergeo holds less customer money, which reduces its exposure under the National Payment System Act [S16] | Commission must be collected afterwards from a shop that already has the money |
| Simple for the shop | Convergeo cannot see whether or how much was paid, so disputes cannot be judged and refunds cannot be made |
| | It trains shops and customers to deal off-platform. A premium tier that bypasses the platform's own trust mechanism rewards leaving it |
| | A dishonest shop would pay for premium precisely to get paid with no hold |

**Recommendation: sell speed and visibility, not escape from escrow.**

| Premium benefit | How |
|---|---|
| **Instant payout** | Release to the shop at the moment the handover code is confirmed, instead of after the normal waiting period. Keep a rolling reserve, for example 10% for 7 days [A], to cover disputes |
| **Live payment visibility** | A dashboard line per order: paid, held, released, paid out, with times |
| **Payout to bank or mobile money on a schedule the shop chooses** | Config |

This gives the shop what it wants, money fast and in sight, while every payment still passes through Convergeo and stays protected.

**If direct pay is still wanted later**, limit it tightly:

- Only shops at the highest KYC tier, with at least 50 completed orders and a dispute rate under 2% [A].
- Only pickup or the shop's own delivery. Never orders carried by Convergeo's couriers.
- Commission taken from a **prepaid commission wallet**: the shop loads credit, each direct-pay order deducts commission as it is created, and direct pay switches off when the wallet is empty. Invoicing in arrears is not recommended.
- A clear label for the customer: "You pay this shop directly. Convergeo does not hold this payment."
- A lawyer confirms the customer-facing wording and Convergeo's liability (L3).

### 4.5 Risks and phased plan

| Risk | Control |
|---|---|
| Prompt fails often at the door | Measure the success rate in the pilot; pay-by-link fallback; operator can re-send |
| Rider waits too long | Limit to two attempts in five minutes, then fallback |
| Lenco fees on small orders | Fees are a percentage; the example in Lenco's documents is 2.5% [C]. Confirm the real schedule (open item F9c) |
| Customers insist on cash | Keep the capped cash fallback; do not remove it |

| Phase | Content | Effort |
|---|---|---|
| A | "Request payment" in the handover step; release the code only on confirmed payment; pay-by-link fallback | M |
| B | Checkout wording; higher limit for mobile money at the door; refusal record | S |
| C | Pickup: prompt at the counter; commission netting and exposure limit for cash pickup | S to M |
| D | Premium tier: instant payout with reserve; payment timeline in the vendor dashboard | M |
| E | Direct pay with commission wallet | L, optional, after L3 |

Monthly cost: $0 beyond Lenco's per-payment fees.

---

## 5. Maps and time-of-day pricing

### 5.1 What is already approved

From the logistics blueprint approved on 13 Nov [C: `/home/claude/logistics/convergeo-logistics-blueprint.md` §5.5, §6.6]:

- Straight-line distance × 1.4 now; then a table of about 50 named Lusaka areas with the road distance between each pair.
- Bands: up to 4 km K30, 8 km K45, 13 km K65, 20 km K95.
- Paid map APIs kept out of the customer's path. OSRM deferred.
- Two cut-offs: order by 11:00 for 15:00; order by 15:00 for 19:00.

The founder now asks for a Google-Maps-style calculation, traffic and rain pricing like Yango, and suggests a 14:00 cut-off. These fit the approved plan with three additions.

### 5.2 Options and costs

Volume assumptions [A]: 20 orders a day in the pilot, 200 a day later. A delivery price is shown on product pages and in carts, so there are about 50 price look-ups per order: 1,000 a day now, 10,000 a day later.

| Option | Traffic-aware | Free allowance | Cost at 30,000 look-ups a month | Cost at 300,000 | Notes |
|---|---|---|---|---|---|
| **Google Routes, basic** (Route Matrix Essentials) | No | 10,000 elements a month [S6] | 20,000 × $5 per 1,000 = **$100** [D] | **$1,450** [D] | Billed per origin-destination pair [S7] |
| **Google Routes, traffic-aware** (Pro) | Yes | 5,000 a month [S6] | 25,000 × $10 per 1,000 = **$250** [D] | **$2,950** [D] | Traffic options trigger the Pro price [S7] |
| **Google, operations only** | Yes | 5,000 a month | **$0**: 20 orders a day × 2 calls = 1,200 a month [D] | 12,000 calls: about $70 [D] | Used by the dispatcher, not shown to customers |
| **OSRM** (open-source, OpenStreetMap data), self-run | No (free-flow speeds) | Unlimited | $0 | $0 | Needs memory on the server if run live. Can be run **once, offline**, to fill the table |
| **openrouteservice** hosted | No | Quota page did not load; **not verified** | Unknown | Unknown | Not relied on |
| **GraphHopper** hosted | Limited | 500 credits a day, **non-commercial only**; paid from €69 a month [S20] | €69+ | €69+ | The free plan cannot be used commercially |
| **Area-pair table** (approved) | By time-band multipliers | Unlimited | **$0** | **$0** | A lookup in Convergeo's own database. Fast and works when a map service is down |

**A caution on Google.** Google's terms restrict storing its results for reuse. Filling a permanent distance table from Google's answers may breach them. I did not read the current terms in full, so treat this as a reason to use open data for the table, not as a legal finding.

### 5.3 Recommendation

**Keep the area-pair table as the only thing customers' prices depend on. Fill it properly once. Add simple, published time bands. Use Google only inside the operations screen.**

1. **Fill the table with real road distances, for $0.** Run OSRM once on a laptop or a build job, using the free OpenStreetMap extract for Zambia, to compute road distance and free-flow driving time between the centre points of the 50 areas (2,500 pairs). Load the result into the table. Refresh every few months. No routing service runs on the production server, and the data licence allows storing it (with attribution to OpenStreetMap).
2. **Time-of-day through four published bands**, not a live traffic feed:

| Band | Hours | Time multiplier [A] | Customer surcharge [A] |
|---|---|---|---|
| Morning rush | 07:00 to 09:00 | 1.5 | Not offered as a delivery window |
| Daytime | 09:00 to 16:30 | 1.0 | None |
| Evening rush | 16:30 to 18:30 | 1.6 for cars, 1.2 for motorbikes | K10 |
| Evening | 18:30 to 20:00 | 1.1 | None |

   These starting values are assumptions. Replace them with Convergeo's own data within weeks: every delivery already records when it was picked up and when it was delivered [C: `dispatch_request_events`]. A weekly job can compute the real minutes per kilometre for each band and area pair, at no cost. That data will be better than Google's for motorbike couriers in Lusaka.

3. **Rain.** A "rain mode" switch on the operations screen adds a surcharge (K10 [A]) that passes in full to the rider, and widens the promised window by 30 minutes. Start manual: the operator can see the sky. Automate later with a weather service; note that Open-Meteo's free tier is for non-commercial use only, so a commercial plan would be needed [S21].
4. **How this differs from Yango's surge.** Yango changes the price minute by minute. For a marketplace that is the wrong model: the customer has already seen a delivered price on the product page, and a price that jumps at checkout breaks trust. Use fixed, published bands, so the customer sees "K45 today before 5 pm, K55 at 5 to 7 pm, K30 tomorrow morning" and chooses. The cheapest option is also the best time for riders to move.
5. **The price is fixed once shown at checkout** for a short period (for example 30 minutes [A]) and never changes after payment.
6. **Google in operations only.** When the dispatcher assigns a rider, one traffic-aware call gives a live estimate for that trip. At pilot volume this stays inside the free allowance [D]. If Google is unavailable, the table answers.

**Best times to move goods**, by the same bands: collect from shops 09:30 to 11:30 and 13:30 to 15:30; deliver 10:00 to 16:30; avoid 07:00 to 09:00 entirely. The weekly report from item 2 will show this from real data.

### 5.4 Delivery windows and the 14:00 cut-off

The founder's point is right: an office delivery after 17:00 fails, because nobody is there. Merge it with the approved two rounds as follows.

**One promise for customers: "Order before 2 pm, get it today."**

| Internally | Order by | Delivered | Suits |
|---|---|---|---|
| Round 1 | 11:00 | 12:00 to 14:30 | Offices (lunch hour), homes |
| Round 2 | **14:00** | 15:00 to 16:45 for work addresses; 17:00 to 19:30 for home addresses | Offices before closing; homes after work |
| After 14:00 | | Next working day, round 1 | |

- The address form asks one question with two pictures: "Home" or "Work". A work address is never scheduled after 16:45.
- This moves the approved second cut-off from 15:00 to 14:00. One hour is given up in exchange for a line that people remember, and for parcels that arrive before offices close.
- Saturdays: one round, order by 10:00 [A]. Sundays: collection only [A].
- Restaurants with their own riders, and Yango for hot food, stay outside these rounds, as the founder noted. Those shops choose "own delivery", with their own proof of handover.

### 5.5 Cost, risks, phased plan

| Item | Monthly cost |
|---|---|
| Area-pair table, time bands, rain switch | $0 |
| Google for the dispatcher at pilot volume | $0 [D]. Set a hard budget cap in the Google console in case of a bug |

| Risk | Control |
|---|---|
| OpenStreetMap is incomplete in some townships | Check the 20 most-used pairs against real trips; allow a manual override per pair |
| Time bands wrong at first | Replace them with measured data after 4 weeks |
| A runaway Google bill | Budget cap; Google is never called from a customer page |
| Customers confused by several prices | Show at most three choices, cheapest first, with plain labels |

| Phase | Content | Effort |
|---|---|---|
| A | Area picker and area-pair table filled by offline OSRM (already in the logistics plan) | M |
| B | Home or Work address type; 14:00 cut-off; windows | S to M |
| C | Time bands and rain switch in the price function; choices shown at checkout | M |
| D | Weekly measured-speed job replacing assumed multipliers | S |
| E | Google live estimate on the dispatcher screen | S |

---

## 6. Platform ceilings today

### 6.1 Short answer

**No, the current set-up cannot hold millions of products.** It can hold roughly **20,000 to 30,000 listings** in the database [D], and it runs into image-hosting and website-hosting limits well before that. Reaching one million products is possible on the same architecture, but at about **$110 to $250 a month**, not $50.

The architecture is sound. The limits come from the free plans.

### 6.2 The plans and their hard limits

| Service | Plan | Limits |
|---|---|---|
| Supabase | Free | 500 MB database; 5 GB data out per month; 1 GB file storage; 50,000 monthly active users; shared CPU with 500 MB memory; **no backups included**; paused after 1 week without activity [S1] |
| Cloudinary | Free | 25 credits a month, shared by storage, delivery and transformations; 10 MB per image; 100 MB per video; the account can be partly then fully disabled if overages continue [S5] |
| Vercel | Hobby | **Non-commercial use only** [S4]. 100 GB transfer, 1,000,000 edge requests, 1,000,000 function calls, 4 CPU-hours, 5,000 image transformations a month, 100 deployments a day. When a limit is passed, the feature is unavailable until 30 days have passed [S3] |
| Hetzner | CX23 | 2 vCPU, 4 GB memory, 40 GB disk, 20 TB traffic; €5.49 a month on the June 2026 price list [S12]. Runs the API, Caddy and n8n |
| API process | | 2 worker processes [C: `infra/api.Dockerfile:40`]; a database pool of at most 5 connections per worker [C: `services/api/app/services/db.py`, `SUPABASE_DB_POOL_MAX` default 5] |

### 6.3 Database: what each thing costs in space

Grounded in the schema. Sizes are estimates; section 6.6 shows how to measure.

**One searchable item** (`search_documents`, migration `0009_search.sql` [C]):

| Part | Estimated size [A] |
|---|---|
| Title, body, category, prices, location, language terms | 0.8 to 1.5 KB |
| Search vector (`tsv`, stored) and its GIN index | 1 to 2 KB |
| Three-letter index on the title (`gin_trgm_ops`) | 0.3 to 0.5 KB |
| Embedding: `vector(384)` = 384 × 4 bytes | 1.5 KB |
| HNSW index on the embedding | about 2 KB |
| Six other indexes | about 0.5 KB |
| **Total** | **about 6 to 8 KB** |

**One product listing, all in** [D]: the search row above, plus `vendor_listings` and its indexes (about 1.5 KB), a share of the `products` row (about 1.5 KB), images (up to 8 rows; about 1 KB for a typical three), stock, variants and analytics rows (about 1 KB). **Roughly 11 to 14 KB per listing.**

| Thing | Space each [A/D] | Notes |
|---|---|---|
| Product listing | 11 to 14 KB | Above |
| Service | 8 to 10 KB | Search row plus the service row |
| Event with ticket types and dates | 12 to 20 KB | Before tickets |
| Vendor with KYC records and locations | 10 to 15 KB | |
| Customer account | 2 to 3 KB | Profile plus Supabase's own login tables |
| Clip (database rows only, not the video) | 2 to 3 KB | Plus likes and views |
| **One order** | **15 to 25 KB** | Order, items, 6 or so status events, payment, about 10 ledger lines, invoice, about 5 queued notifications, about 3 stored webhook payloads, audit rows, stock reservations |
| One ticket | 1 to 2 KB | |
| One analytics event | about 0.5 KB with indexes | Kept 30 days [C: `docs/ops/data-retention.md`] |

**What fits in 500 MB.** Supabase's own tables and the empty schema take perhaps 40 to 60 MB [A]. Leave 100 MB for orders and logs. That leaves about 300 MB for the catalogue: **300 MB ÷ 12 KB ≈ 25,000 listings** [D].

| If the database held only... | It would fit about [D] |
|---|---|
| Listings | 30,000 to 40,000 |
| Orders (lifetime, since they are never deleted) | 20,000 to 30,000 |
| Customer accounts | 150,000 by space, but **50,000 active a month** by the plan's login limit [S1] |
| Analytics events at 30 days' retention | 1,000 visits a day × 20 events × 30 days × 0.5 KB = **300 MB** |

The last row is the one to watch. **At about 1,000 to 1,500 visits a day, analytics events alone approach the whole 500 MB** [D from A]. Orders add about 2 MB a day at 100 orders a day [D].

### 6.4 The other ceilings

**Images (Cloudinary Free, 25 credits).** [D from S5 and assumptions]

| Use | Working | Credits |
|---|---|---|
| Storage | 3 images × 0.5 MB [A] = 1.5 MB per listing; 5,000 listings = 7.5 GB | 7.5 a month |
| First-time resizing | 3 images × about 6 sizes and formats [A] = 18 per listing; 5,000 listings = 90,000 | **90, in the month they are first viewed** |
| Delivery | A page of 20 thumbnails at 30 KB = 0.6 MB; 1 GB serves about 1,700 page views | 10 credits ≈ 17,000 page views |

So **Cloudinary Free supports roughly 3,000 to 5,000 listings and 15,000 to 25,000 page views a month**. A bulk upload of thousands of listings in one month would break the limit through resizing alone. This is very likely the **first** ceiling reached.

**Website hosting (Vercel Hobby).** Apart from the commercial-use rule, 1,000,000 edge requests a month is about 30,000 to 50,000 page views at 20 to 35 requests a page [A], so **1,000 to 1,500 page views a day** [D]. Passing a limit switches the feature off for up to 30 days [S3]. For a shop, that is an outage.

**Data out of Supabase (5 GB a month).** Every answer the API reads from the database counts. At an average of 5 KB a response [A], 5 GB is about 1,000,000 database reads a month, or about 33,000 a day [D]. The 60-second page caching already in place [C: `revalidate = 60` on home, events, services, deals] protects this. Search and cart requests are not cached.

**API server (2 vCPU, 4 GB).**

| Measure | Estimate | Basis |
|---|---|---|
| Simultaneous database transactions | 10 | 2 workers × pool of 5 [C]. An eleventh waits up to 10 seconds, then fails |
| Sustained requests a second | 30 to 60 [A] | Python on 2 cores, mostly waiting on the database |
| People actively shopping at the same moment | **About 100 to 300** [A] | One API request per person every 5 to 10 seconds; cached pages do not reach the API |
| Simultaneous checkouts | Target 100; **never tested** | The load-test scripts exist, but the results table is empty [C: `docs/ops/load-test-results.md`] |
| Search speed | Fine to tens of thousands of items | The vector index must fit in memory; the free database has 500 MB [S1] |

**Orders a day.** The software could process thousands a day. Three things stop it far earlier: database space (about 20,000 to 30,000 orders in total on the free plan), n8n's regular jobs sharing the same small server, and people. The logistics audit found one person closes every delivery.

**n8n.** About 30 workflows on the same server [C: `infra/n8n/`]. Adequate at pilot volume. If it grows, limit how long run history is kept, since it uses the server's 40 GB disk.

**Videos.** See 2.6: the free Cloudinary plan cannot carry even the pilot at its caps.

**Vendors, services, events, posts.** These are small in number next to listings. Thousands of each fit. Their images count against the same 25 Cloudinary credits.

### 6.5 What breaks first at each stage, and the upgrade path

| Stage | Rough size | First to break | Fix | Added monthly cost | Running total |
|---|---|---|---|---|---|
| **0. Now (pilot)** | Under 1,000 listings, under 20 orders a day | Nothing technical. Two non-capacity risks: Vercel Hobby's commercial-use rule [S4]; no managed backups on Supabase Free [S1] (a manual backup runbook exists [C: `docs/ops/backup-runbook.md`]; confirm it runs daily) | **Vercel Pro** | $20 [S3] | about $26 with the server |
| **1. Early growth** | 3,000 to 5,000 listings; 1,000+ visits a day | Cloudinary's 25 credits; then analytics filling the database | Move image delivery off Cloudinary's meter: resize each image once to 3 or 4 fixed sizes at upload, store in Cloudflare R2 (10 GB free, no delivery charge [S11]). The design already has a switch point for this [C: decision D26]. Cut analytics retention to 14 days, or roll up daily | $0 to $2 | about $28 |
| **2. Established** | 20,000 listings; 50 to 100 orders a day; 3,000 visits a day | Supabase: 500 MB, 5 GB out, no backups | **Supabase Pro**: 8 GB database, 250 GB out, 100 GB files, daily backups, 100,000 monthly users [S1] | $25 [S1] | **about $53** |
| **3. Busy** | 100,000 listings; 500 orders a day; 300+ people at once | API server CPU and its 10 database connections | Larger server: 4 vCPU and 8 GB for €8.49 [S12]; 4 workers; raise the pool. Run the load test first | about $4 | about $57 |
| **4. Large** | 500,000 to 1,000,000 listings | Search: the vector index (about 2 to 3 GB at one million [D]) no longer fits in database memory | Database compute: Medium (4 GB) $60 [S1], or the next size for a full million (price not checked). Database disk about 12 to 15 GB: $0.50 to $1 beyond the included 8 GB [D]. Or reduce the load: build embeddings only for canonical products, not every shop's listing | $50 to $150 | **about $110 to $250** |
| **5. Millions** | Several million | Postgres full-text and vector search on one machine | A dedicated search service, or halved-precision vectors. A re-design decision, not a setting | Not costed | |

**The honest position on $50 a month:** it comfortably covers stages 0 and 1, and just about covers stage 2 (about $53). Beyond that, the platform should be earning. At stage 3, 500 orders a day at K200 and 8% commission is about K8,000 a day [D], far more than the hosting.

### 6.6 Replace these estimates with measurements

These are read-only and safe to run in the Supabase SQL editor.

```sql
-- total database size against the 500 MB limit
select pg_size_pretty(pg_database_size(current_database()));

-- the 15 largest tables, including their indexes
select relname,
       pg_size_pretty(pg_total_relation_size(c.oid)) as total,
       n_live_tup as rows
from pg_class c
join pg_stat_user_tables s on s.relid = c.oid
order by pg_total_relation_size(c.oid) desc
limit 15;
```

Also record once a month: Cloudinary credits used, Vercel usage against the limits in 6.2, and Supabase data out. Set an alert at 70% of each. Run the load test that has been waiting [C].

---

## 7. Events: cancellation, refunds and abuse

### 7.1 What exists

| Mechanism | State | Where |
|---|---|---|
| Ticket QR code changes every 60 seconds, signed; 6-digit PIN fallback | Built | `services/tickets/qr.py` [C] |
| Offline scanning with later sync | Built | `routers/ticket_scan_sync.py` [C] |
| Ticket transfer in-app | Built | `ticket_transfers` [C] |
| Organiser cancels the event: all tickets voided at once, pending transfers cancelled, buyers notified | Built | Migration `20260809214010` [C] |
| Refund jobs after cancellation: one per paid order, automatic, retried up to 5 times | Built | `services/events/refund_jobs.py` [C] |
| Money held, then released: full release 24 hours after the event ends, for events bought within 14 days | Built | `services/escrow/event_release.py` [C] |
| **For tickets bought more than 14 days ahead: 50% released 7 days before the event**, 50% one day after | Built | Same file [C] |
| Release blocked if the event is cancelled, refunded or in dispute | Built | Same file, line 485 [C] |
| Clawback: after a refund on already-released money, the organiser's balance goes negative and is netted from later payouts | Built | `services/refunds/execute.py` [C] |
| Partly released orders cannot be refunded automatically; they stop for manual handling | Built, fails closed | Same file, lines 560 to 591 [C] |
| Personal-tier organisers capped at K20,000 of paid sales per event until 3 successful events | Built | `services/events/gmv_cap.py` [C] |
| Events above K100,000 need extra verification | Built | `services/events/high_value.py` [C] |
| Buyer cancels: refund minus 5% fee if 7 or more days before; no refund in the last 24 hours | Built | `services/events/buyer_cancellation.py` [C] |
| Reschedule: buyer may opt out for a refund | Built | Same file [C] |
| Admin "unpublish" (event back to draft, with a hold) | Built on PR #782 | `moderate_catalog_entity()` [C] |

### 7.2 "Unpublishing keeps sold tickets valid": true on paper, not at the gate

The founder's rule: unpublished means hidden, tickets stay valid; not taking place means refunds. In the code today:

| What happens when an event is unpublished (moved to draft) | Effect | Where |
|---|---|---|
| Tickets remain "issued" | Correct | No trigger voids them [C] |
| **The scanner refuses the ticket**: "Tickets can only be checked in for published events" | Holders are turned away at the gate if the event is still unpublished | `ticket_verify.py:329` [C] |
| **Offline scan data cannot be downloaded** for the event | Gate staff cannot prepare | `ticket_scan_sync.py:144` [C] |
| A paid order whose ticket was not yet issued **cannot be issued** | A buyer has paid and has no ticket | Trigger `require_published_event_for_issued_ticket` [C] |
| **Money release continues.** Only "cancelled" blocks it | An event that is unpublished and then never happens still pays the organiser on schedule | `event_release.py:485` [C] |

The last row is the abuse path the founder asked about. A dishonest organiser, or a muddled process, leaves an event "unpublished" instead of "cancelled". Nobody is refunded, and the money is released after the scheduled end.

**Fix: "hidden" must not be a change of status.**

- Add a separate **listing state** beside the status: `listed`, `hidden` (off browse and search, sales stopped, tickets fully valid, scanning works), or `under_review`.
- "Unpublish" sets `hidden`. The event's status stays "published" for ticket purposes, so scanning, issuing and transfers keep working.
- An event left `hidden` or `under_review` puts money release **on hold** until an admin clears it.
- Only "cancelled" voids tickets and starts refunds.

Effort: M. It touches the PR #782 moderation function for events, the scanner checks and the release rule.

### 7.3 Abuse scenarios and controls

| # | Scenario | Exposure today | Recommended control |
|---|---|---|---|
| 1 | **Organiser collects, receives the 50% advance, then cancels or disappears** | Real. For tickets bought more than 14 days ahead, half is paid out 7 days before the event. Clawback only works if the organiser has future sales | **No advance by default. Hold 100% until after the event.** Allow an advance only for the top KYC tier with at least 3 successful events [C: that counter exists], capped at 30% [A], on request, with documented supplier costs, approved by an admin |
| 2 | **Event silently does not happen** (no cancellation) | Money is released 24 hours after the scheduled end unless there is an open dispute | **Proof the event happened before release**: at least 30% of sold tickets scanned [A], or an admin confirmation. Zero scans: hold and alert. Add "This event did not take place" on every ticket until 48 hours after the end; reports from 3 buyers or 5% of holders [A] hold the release |
| 3 | **Unpublish instead of cancel** | 7.2 | Listing state plus release hold |
| 4 | **Endless postponement to avoid refunds** | Buyers can opt out on a reschedule [C], but there is no limit on reschedules | At most 2 reschedules and at most 90 days beyond the original date [A]. After that the event is cancelled and refunded automatically |
| 5 | **Refund sent to the wrong person** | Refunds are payouts to a phone number. If that number can be changed, an account thief or a ticket reseller redirects the refund | **Refund only to the number that paid.** For card payments, where a payout number is needed, ask the account holder, confirm by one-time code to the account's phone, check the registered name with Lenco's lookup [C], wait 24 hours, and require admin approval. The "needs destination" state already exists [C] |
| 6 | **Transferred ticket: who gets the refund?** | Not defined | The person who paid Convergeo. A transfer made privately for cash is at the two parties' own risk; say so on the transfer screen |
| 7 | **Refund, then entry with a screenshot** | Buyer cancellation closes 24 hours before the start [C], which helps. An offline scanner that has not synced would not know a ticket was voided | Gate devices must sync within 2 hours before doors [A]. The scanner shows a warning if its list is older. Voided tickets are pushed first |
| 8 | **The same ticket used at two gates offline** | Two offline scanners cannot see each other's scans. A screenshot is valid for 60 seconds [C] | For events with several gates, require online scanning or assign ticket types to gates. On sync, flag duplicates to the organiser. Accept a small leak at small events |
| 9 | **Fake tickets sold outside the app** | A screenshot stops working after 60 seconds, so a resold image fails | Keep. Tell buyers: "A ticket is real only inside the Convergeo app" |
| 10 | **Organiser buys their own tickets with stolen cards or wallets, then takes the payout** | K20,000 cap for new organisers [C]; KYC | Payout only to an account whose name matches the KYC record; hold the card-paid share longer (for example 7 days after the event [A]), because card payments can be reversed by the bank for months; alert on many tickets from few payers |
| 11 | **Who pays the costs of a cancellation?** | Lenco charges on the way in and on each refund payout. With 100% held, the ticket money is all there, but the fees are not | Policy: the buyer gets the full ticket price. The organiser owes the fees. Carry them as a negative balance and block new paid events until settled. For first-time organisers, a small refundable listing deposit (for example K200 [A]) is an option |
| 12 | **Partial refunds: one date of several, or one ticket type** | Per-date tickets exist [C]. Refunds on partly released orders stop for manual handling [C] | With no advance (control 1), partial release rarely happens, so this mostly disappears. Keep the manual stop as the safe behaviour |
| 13 | **Promo code used more times than its limit** | 3.1: the count and the insert are separate | Reserve the use inside one locked transaction |
| 14 | **Organiser unreachable; buyers asking** | An admin can hide the event but cannot cancel-and-refund on the organiser's behalf | Add an admin "cancel and refund" action, with a required reason and a second confirmation |
| 15 | **Mass refund empties the Lenco balance** | Refund payouts draw on the same account as vendor payouts | With 100% held, the money is there. Add a pre-check: total refunds queued must not exceed the available balance; pace them. A daily limit on Lenco transfers exists but its value is unknown [C: Lenco distilled doc, error code 03] |

### 7.4 Payout timing

| Organiser | Release |
|---|---|
| New, or personal tier | 100% at 48 hours after the event ends [A], if the proof test passes and there is no dispute or report hold |
| Established (3 successful events, no upheld disputes) | 100% at 24 hours after the end, as today |
| Top tier, on request | Up to 30% advance from 7 days before, admin-approved; the rest after the event |
| Recurring series | After each date, as today [C] |
| Card-paid share | A further hold (7 days [A]) |

All of these are configuration values on logic that already exists, except the proof test and the report hold.

**Why 100% hold is right for Zambia.** Trust in online ticketing is low, and an organiser who vanishes with the money is the story that would end the events product. Lenco cannot reverse a payment, so money paid out early is gone. Organisers who need cash to stage an event can still earn the advance by track record.

### 7.5 Design changes

| Entity | Change |
|---|---|
| `events` | Add `listing_state` (`listed`, `hidden`, `under_review`) |
| `event_release_holds` | New. Event, reason (`no_scans`, `buyer_reports`, `hidden`, `admin`), who placed it, who cleared it |
| `event_no_show_reports` | New. Event date, ticket, reporter; one per ticket |
| `event_refund_jobs` | Add a check that the destination equals the original payer; add `destination_review` |
| `event_advance_requests` | New. Organiser, amount, documents, decision |
| `event_reschedules` | Enforce the count and the 90-day limit |

**Event status stays** draft, published, cancelled, completed. Listing state is separate:

```
status:        draft -> published -> completed
                            |
                            v
                        cancelled -> tickets voided -> refund jobs -> refunded

listing_state (only while published):   listed <-> hidden <-> under_review
                                         (tickets valid and scannable in all three)
```

**Release rule:** release only if status is published or completed, listing state is listed, no open hold, the proof test passes, no dispute, no refund.

**RBAC.** Organiser: cancel own event, reschedule within limits, request an advance. Admin with `events.manage`: hide, review, cancel-and-refund. Finance: clear a release hold, approve an advance, approve a changed refund destination. Releasing money early should need two different people; with one admin today, that means the founder, which should be recorded.

### 7.6 Phased plan

| Phase | Content | Effort |
|---|---|---|
| A | **Listing state fix** (7.2); release hold for hidden events; switch off the 50% advance by configuration | M |
| B | Refund only to the payer; reviewed destination for card payments; admin cancel-and-refund | M |
| C | Proof-of-event test; "did not take place" reports; release holds | M |
| D | Reschedule limits; scanner freshness warning; duplicate-scan report | S to M |
| E | Advance requests for trusted organisers; longer hold on card share | M |

Monthly cost: $0.

---

## 8. The Business Home: how the storefront should evolve

### 8.1 The idea

The reference photograph shows a Lusaka street: a long row of shopfronts, each with its own signboard, and a trader on the pavement with no sign at all. The north star is that every one of them, including the trader without a sign, has a home on Convergeo that is recognisably theirs.

Today a business's presence is spread out: a vendor page for products, a separate services listing, separate event pages, and clips in a feed. **The proposal is one page per business, the Business Home, where its sign, its story and everything it sells sit together.**

### 8.2 What exists to build on

| Piece | State |
|---|---|
| Vendor page at `/v/[slug]` | Built [C: `apps/customer/app/[locale]/(shop)/v/[slug]/page.tsx`] |
| Logo and cover image | Built [C: `vendors.logo_url`, `cover_url`] |
| The business's own colours on its page, checked for readability | Built [C: `vendors.brand_theme`, migration `20261108120000`] |
| Collections the business arranges itself | Built [C: `vendor_storefront_collections`] |
| Follow a business | Built [C: `vendor_follows`] |
| Business types (archetypes) | Built [C: migration `20260812010000`] |
| Verified badge, KYC tiers | Built [C] |
| Clips linked to the business | Built, dark [C] |
| Services, events and products shown together on one business page | Not confirmed in the code I read; treat as not built |
| A "story" section; a business's own offers; a QR code for the physical shop | Not built |

### 8.3 What the Business Home contains

Top to bottom, on a 360-pixel phone screen:

| Block | Content | Why |
|---|---|---|
| **The sign** | Logo, name, cover photo, the business's colours, verified badge, area and landmark, "Open now" | The shop's signboard. It must look like theirs, not like a template |
| **Three buttons** | Follow, WhatsApp, Directions | The three things people do with a shop they like |
| **Our story** | Up to about 60 words and one photo or a clip: who we are, since when, what we are known for. Can be recorded as a voice note and typed up | "Every business must be able to bring its story." For owners who write little, a clip is the story |
| **Clips** | The business's own short videos | The story continued, in the owner's own voice |
| **Offers** | The business's own coupons, flash deals and bulk prices | A reason to visit today |
| **Tabs: Products, Services, Events, Supplies** | Only the tabs the business uses | One home for a business that sells goods and also runs workshops or events |
| **Reviews** | Verified-purchase reviews, as now | Trust |
| **Find us** | Branches, hours, landmark, map pin | The link back to the real street |

### 8.4 How ads, Clips and gifting feed it

| Feature | Link to the Business Home |
|---|---|
| Ads (section 1) | Every ad carries the business's logo and name. The default target for a first ad is the Business Home, not a single product. The cheapest package is priced for a market stall |
| Clips (section 2) | Every clip shows the business's logo; a tap opens its Home. A creator's clip about a shop links to that shop's Home once the shop accepts the tag |
| Coupons (3.5) | Shop-funded coupons appear in the Offers block and can be shared as a WhatsApp card showing the shop's own sign |
| Gifts (3.3) | The gift message names the shop: "Mary sent you a gift from Mama Chanda's Kitchen", with a link to its Home. Each gift introduces a new person to that business |
| Birthdays (3.4) | A business can greet its own followers on their birthdays, sent by Convergeo on its behalf, without ever seeing personal details |
| Follow | Following a business fills the customer's "Following" feed with its clips, new items and offers |

### 8.5 Principles to keep

1. **The business's name comes first; Convergeo's comes second.** On a Business Home, on a shared link and on an ad, the shop's logo is the largest mark. Convergeo's is the small "street name" in the corner. This is what "Hub of logos" means in practice.
2. **Each Home has its own shareable address and QR code.** A printable poster for the physical shop door, "Find us on Convergeo", ties the street to the site and costs nothing.
3. **Simple enough for an owner who did not finish school.** Set-up is three steps with pictures: add your sign (photo), say who you are (type or record), add your first item. Everything else is optional. This follows the founder's instruction to keep the front simple and do the heavy work behind.
4. **Fair discovery.** New and small businesses get a share of "New on Convergeo" and local rails that money cannot buy. Paid slots are always labelled and capped (1.7). Otherwise the biggest logos crowd out the street.
5. **Light on data.** The Home is a cached page. Clips are posters until tapped. The existing page-weight budgets apply.
6. **One business, many kinds of selling.** A business should not need separate identities to sell products, offer a service and run an event. One Home, with tabs.

### 8.6 Phased plan

| Phase | Content | Effort |
|---|---|---|
| A | "Our story" block; unified tabs for products, services and events on `/v/[slug]`; Follow, WhatsApp and Directions buttons | M |
| B | Offers block (needs coupons, 3.5); clips row (needs Clips live) | S after those features |
| C | Share card and printable QR poster with the business's own sign | S |
| D | Three-step guided set-up with voice-to-text for the story | M |
| E | "New on Convergeo" and near-me rails that are not for sale | S to M |

Monthly cost: $0.

---

## 9. Legal questions to put to a Zambian lawyer

These extend the existing brief (founder action F4).

| # | Question | Blocks |
|---|---|---|
| L1 | Is a Convergeo gift card, bought for cash and spendable at many independent shops, "electronic money" or a "payment service" under the National Payment System Act, 2026? Is an exemption under section 144 obtainable? Is a single-shop voucher, issued by the shop, different? | Gift cards (3.6) |
| L2 | For user-uploaded video: what must Convergeo do to keep host protection under the Electronic Communications and Transactions Act, sections 79 and 82? Who should be the designated agent? What is the correct procedure, and whom to notify, on finding suspected child abuse material? | Opening Clips beyond verified businesses (2.4) |
| L3 | If premium shops are paid directly by customers, what is Convergeo's liability to the buyer, and what wording is required? | Direct pay (4.4) |
| L4 | The Data Protection Act says personal data is to be stored in Zambia unless exempted. What is required given the database and media are hosted abroad? Is registration as a data controller complete? | Everything; not new, but unresolved |
| L5 | VAT on advertising income, and the treatment of platform-funded discounts | Ads, coupons |
| L6 | May unused gift balances and unclaimed refunds be kept, or must they be surrendered under section 125? | Gift cards, event refunds |

---

## 10. Approval requested

In priority order. Effort: S is days, M is one to two weeks, L is three weeks or more, for the usual build process. Monthly cost is new recurring cost.

### Do now: safety and compliance

| # | What | Why | Effort | Monthly cost |
|---|---|---|---|---|
| 1 | **Event listing-state fix**: "hidden" keeps tickets scannable; hidden events hold money release | Today an unpublished event's tickets are refused at the gate, and its money is still released if it never happens (7.2) | M | $0 |
| 2 | **Hold 100% of ticket money until after the event**: switch off the 50% advance | The largest fraud exposure in events (7.3, row 1). A settings change on existing logic | S | $0 |
| 3 | **Move the website to Vercel Pro**, or confirm it already is | The free plan forbids commercial use and switches features off for 30 days when a limit is passed (6.2) | S | $20 |
| 4 | **Correct the Clips cost rates and lower the pilot caps** before turning the flag on | The example delivery rate is about a quarter of the real cost, and the pilot at its caps exceeds the free plan (2.6) | S | $0 |
| 5 | **Send the legal questions L1 to L6** to counsel with the existing escrow brief | Gift cards, open video and direct pay each depend on an answer | S (founder) | Legal fees, not costed |

### Next: trust and money in

| # | What | Why | Effort | Monthly cost |
|---|---|---|---|---|
| 6 | **Pay at the door by mobile money** as the default "pay on delivery"; cash as a capped fallback | Removes cash risk and daily cash-up; a refusal needs no refund (4.3) | M | $0 plus Lenco fees |
| 7 | **Paid ads, Phase A and B**: merge PR #782; fixed packages; Lenco payment; slots that go live only when paid and approved; AI reviewer that approves or escalates; appeals | First advertising income; mostly built on existing code (1.8) | M + M | Under $2 |
| 8 | **Refund only to the payer; admin cancel-and-refund; proof-of-event before release** | Closes the remaining event abuse paths (7.6, B and C) | M + M | $0 |
| 9 | **"Order before 2 pm" with Home or Work addresses; time bands and rain switch** on the approved area table | Fewer failed office deliveries; fair pay for riders in rain and rush hour (5.3, 5.4) | M | $0 |
| 10 | **Measure the real ceilings**: run the two queries in 6.6, record Cloudinary, Vercel and Supabase usage, set 70% alerts, run the waiting load test | Replaces this document's estimates with facts | S | $0 |

### Then: growth

| # | What | Why | Effort | Monthly cost |
|---|---|---|---|---|
| 11 | **Gift orders** and **birthday capture with consent** | Low-risk gifting; brings a second person to each shop (3.3, 3.4) | M | $0 |
| 12 | **General coupons** (shop-funded and platform-funded, with a monthly budget and a reconciliation check); fix the event promo-code race | The missing discount feature for products and services (3.5) | M to L | The promotions budget you set |
| 13 | **Business Home, Phase A**: story block, unified tabs, Follow, WhatsApp and Directions | The north star made visible (8.6) | M | $0 |
| 14 | **Clips, Phase B and C**: free automated screening, trust ladder, report weighting, own-server video processing with Cloudflare R2, open to all verified businesses, "Following" tab | Opens Clips at near-zero cost instead of $90 to $250 on Cloudinary (2.6, 2.9) | M + L | $0 to $6 |
| 15 | **Move product images off Cloudinary's meter** when credits pass 70% | Likely the first capacity ceiling (6.4, 6.5) | M | $0 to $2 |
| 16 | **Supabase Pro** when the database passes 350 MB, or before real-money volume grows | Space, managed daily backups, and data-out headroom (6.5) | S | $25 |

### Later: on evidence

| # | What | Trigger | Effort | Monthly cost |
|---|---|---|---|---|
| 17 | Premium tier: instant payout with a reserve, and a payment timeline | When paid tiers are switched on | M | $0 |
| 18 | Birthday automation and business-sent birthday offers | After coupons | S to M | $2 to $5 [A] |
| 19 | Verified individual creators on Clips | After 4 weeks with the report queue under 24 hours, and L2 answered | M | $0 |
| 20 | Boost (prepaid ad budget for views) | After 10 or more paying advertisers | L | $0 |
| 21 | Shareable wishlists | After gift orders are used | M | $0 |
| 22 | Gift cards | Only after L1 is answered favourably | L | $0 |
| 23 | Ad auction | 20 advertisers and 70% sell-out for 8 weeks | L | $0 |
| 24 | Direct pay with a commission wallet | Only if still wanted after item 17, and L3 answered | L | $0 |

**Budget view.** Items 1 to 15 add about $20 to $30 a month (Vercel Pro, plus small amounts). With Supabase Pro (item 16), the total is about $53 a month including the server [D]: at the ceiling, with no room left. Item 16 is the point where the $50 limit should be reviewed against income.

---

## Sources

All read on 13 November 2026.

| # | Source | Used for |
|---|---|---|
| S1 | https://supabase.com/pricing | Free and Pro limits and prices; compute add-ons |
| S3 | https://vercel.com/docs/plans/hobby (page dated 14 Sep 2026) | Hobby limits; 30-day pause; $20 seat |
| S4 | https://vercel.com/docs/limits/fair-use-guidelines (page dated 14 Sep 2026) | "Hobby teams are restricted to non-commercial personal use only" |
| S5 | https://cloudinary.com/documentation/pricing.md | Credit definitions; Free, Plus, Advanced |
| S6 | https://developers.google.com/maps/billing-and-pricing/pricing | Routes and Route Matrix free caps and prices |
| S7 | https://developers.google.cn/maps/documentation/routes/usage-and-billing?hl=en | Traffic options billed as Pro; matrix billed per element |
| S8 | https://cloudinary.com/documentation/aws_rekognition_video_moderation_addon.md | Cloudinary video moderation behaviour and categories (no prices) |
| S9 | https://aws.amazon.com/rekognition/pricing/ | $0.001 per image; $0.10 per video minute; 12-month free tier. Rates taken from the page's worked examples |
| S10 | https://developers.openai.com/api/docs/models/omni-moderation-latest.md | Moderation is free; text and image; rate limits |
| S11 | https://developers.cloudflare.com/r2/pricing/ | R2: $0.015 per GB-month; 10 GB free; no egress charge |
| S11b | https://developers.cloudflare.com/stream/pricing/index.md | Stream: $5 per 1,000 minutes stored; $1 per 1,000 delivered |
| S12 | https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/ (15 Jun 2026 price list; checked 20 Oct 2026) | Hetzner CX23 and CX33 prices. A secondary source, and it reports these plans as unavailable to new orders in Sep to Oct 2026 |
| S13 | https://marketingtochina.com/wechat-channels-vs-douyin/ | WeChat Channels mechanics and figures (agency article) |
| S14 | https://marketingtochina.com/kuaishou-marketing-insights/ | Kuaishou mechanics and figures (agency article) |
| S15 | https://kr-asia.com/kuaishou-adopts-user-first-e-commerce-strategy-to-win-over-customers | Kuaishou trust measures; over 47% of sales from users over 40 |
| S15b | https://technode.com/2024/11/29/kuaishou-e-commerce-abolishes-refund-without-return-policy-after-long-running-merchant-complaints/ | Headline only; article not read |
| S15c | https://www.theredscroll.com/insights/china-social-commerce-compared/ | WeChat Store shopper age (NewRank, Jan 2025); store deposit rules |
| S16 | https://zambialii.org/akn/zm/act/2026/5/eng@2026-04-08 | National Payment System Act, 2026: sections 2, 11, 75, 78, 124, 125, 144, 153 |
| S17 | https://www.dlapiperdataprotection.com/index.html?t=law&c=ZM | Data Protection Act, 2021 summary: registration, consent, children, localisation, 24-hour breach notice |
| S18 | https://zambialii.org/akn/zm/act/2025/4/eng@2025-04-15 | Cyber Crimes Act, 2025: sections 13, 15 to 17, 22, 24, 29 to 32 |
| S19 | https://zambialii.org/akn/zm/act/2021/4/eng@2021-03-24 | Electronic Communications and Transactions Act, 2021: sections 63, 65, 66, 79, 82, 83 |
| S20 | https://www.graphhopper.com/pricing/ | Free plan non-commercial; paid from €69 |
| S21 | https://open-meteo.com/en/pricing | Free tier non-commercial; commercial plan price not shown |

**Looked for and not found:** Cloudinary moderation add-on prices; openrouteservice free quotas (the plans page did not load); Lenco's fee schedule (still open item F9c in the repository); Zambia-specific Facebook advertising prices; any public source on WeChat's or Kuaishou's moderation operations; WhatsApp's per-message price for Zambia.

**Code and documents read:** `release/2026-11-next` at `/home/claude/wt-next`; branch `feat/admin-ads-merchandising` (PR #782); branch `feat/clips-pilot-service-packages` (PR #781); `docs/plan/` and `docs/ops/`; `/home/claude/logistics/founder-responses-2026-11-13.md`; `/home/claude/logistics/convergeo-logistics-blueprint.md`.

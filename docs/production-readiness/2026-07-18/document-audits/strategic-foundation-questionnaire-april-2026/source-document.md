# Source Document — Convergeo Strategic Foundation Questionnaire & Business Review

## Document metadata

| Field | Value |
| ----- | ----- |
| **DOCUMENT_SLUG** | `strategic-foundation-questionnaire-april-2026` |
| **DOCUMENT_TITLE** | Convergeo — Strategic Foundation Questionnaire & Business Review (v1.0) |
| **Source file** | `9734f6a8-Convergeo_Strategic_Questionnaire_1.pdf` (uploaded) |
| **Format** | Image-only PDF, 24 pages (no embedded text layer; rendered from `wkhtmltopdf 0.12.6` → Ghostscript). Content transcribed by rendering each page to PNG at 2× and reading visually. |
| **Stated classification banner** | "CONFIDENTIAL — April 2026" / footer "Prepared April 2026 \| Confidential — For Internal Use Only" / "Strategic Foundation Questionnaire v1.0" |
| **Author / owner** | Not named in document (internal Convergeo/Vergeo5 founder artifact) |
| **Data class (audit)** | Requirements / policy / specification (strategic planning questionnaire + business review + red-team analysis). Contains **no operational data records** (no customer/vendor/order/payment rows to match). |
| **Structure** | Part 1 — Business Plan Review (Critique & Applause); Part 2 — Red Team: 15 Failure Scenarios; Part 3 — Strategic Questionnaire (75 questions). |
| **Header stats** | 75 strategic questions · 12 categories · 15 red-team threats · 60 days to MVP |
| **Critical extraction note** | **All 75 questionnaire questions are UNANSWERED** — every radio button is empty in the rendered PDF. This artifact records the decision *space*, not decisions. The team's actual answers live separately in `docs/plan/00-decisions.md` (28 locked decisions D1–D28). |

> **Handling:** This is a transcription of the supplied document for audit traceability. No secrets or PII are present in the source. Verbatim option wording is preserved so downstream matching keys are stable.

---

## Part 1 — Business Plan Review

### What Deserves Applause (STRONG)

1. **Multi-panel architecture (Customer / Vendor / Admin)** — Separating concerns into three distinct web applications is the correct architectural decision. Mirrors Alibaba (Taobao / 1688 / admin tools). Enables independent deployment, scaling, UI optimization per user type.
2. **Zambia-first, Africa-next strategy** — Single-country focus first is wise; Jumia's mistake was scaling 11 countries before product-market fit.
3. **Hybrid fulfillment (Pickup + Delivery via QR codes)** — Click-and-collect + delivery essential for Zambia; QR pickup verification is practical and reduces fraud.
4. **Third-party delivery integration (Yango et al.)** — Not building own fleet day one is smart capital allocation; aggregate Yango, Bolt, local couriers.
5. **Events & Tickets vertical** — Genuine market gap in Zambia; combining e-commerce + events/ticketing is a unique, hard-to-replicate value proposition.
6. **Company directory + branch information + AI search** — Business discovery hub ("Alibaba meets Google Maps meets Eventbrite" for Zambia).
7. **n8n for workflow automation** — Open-source automation keeps costs manageable; flexibility for order processing, notifications, vendor onboarding, analytics without vendor lock-in.

### What Needs Careful Rethinking (CAUTION)

1. **Technology stack indecision (Django vs MERN vs both)** — Must commit to ONE primary stack. **Recommendation: Django + PostgreSQL backend** (battle-tested for e-commerce, excellent admin, mature payment integrations) with a React/Next.js frontend. Do not split effort across competing stacks.
2. **Two-month timeline for the entire project** — Full-featured multivendor + B2B + events + AI search + payments + delivery + advertising + admin in 60 days is extremely aggressive. Achievable in 60 days: a functional MVP with core buying/selling, one payment gateway, basic vendor dashboard, customer browsing. Full vision is 6–12 months.
3. **Building your own payment gateway "in the long term"** — Requires ZICTA / Bank of Zambia licensing, PCI-DSS, significant capital. It is a separate company, not a feature; 3–5 year vision.
4. **Using four AI coding tools simultaneously (Claude Code, Cursor, Gemini CLI, Antigravity)** — Inconsistent code, conflicting patterns, integration nightmares. Pick ONE primary (Claude Code or Cursor); use another as secondary reviewer.
5. **Revenue model clarity** — "Advertisement options and service charges" mentioned but commission structure, subscription tiers, pricing strategy undefined. Decide before writing code.

### What Is Wishful Thinking (For Now) (WISHFUL)

1. **Virtual try-on with "nano banana API"** — AR/virtual try-on needs 3D pipelines, body-measurement algorithms, compute. Phase 3+ feature.
2. **Full AI mode for company/service discovery** — Sophisticated NLP over comprehensive business DB + real-time availability. Start with structured search + good filters; evolve toward AI as data grows.
3. **"Making Africa shake" with rapid multi-country expansion** — Cross-border payment/regulatory/language/logistics differences per country; even Jumia struggled. Dominate Zambia first; neighbors 12–18 months out.
4. **Competing with Amazon/Alibaba model from day one** — They had billions and decades. Advantage is LOCAL. Be the best Zambian platform, not a miniature Amazon.

### What IS Absolutely Achievable (REALISTIC)

- **Within 60 days (MVP):** Functional multivendor marketplace — customers browse, vendors list inventory, **payments work via Lenco/DPO**, QR-code pickup verification, basic rating system, working admin panel.
- **Within 90 days (v1.0):** Delivery integration (Yango API), events/ticketing module, vendor profiles with branch info, basic advertising slots, email/SMS notification automation via n8n.
- **Within 6 months (v2.0):** AI-assisted search, advanced analytics, B2B wholesale portal, multi-currency support, mobile app (React Native), advertising dashboard with analytics.

---

## Part 2 — Red Team: "In 6 Months You Failed Because…" (15 scenarios)

Each = a competitor that launched after Convergeo and won; a strategic blind spot to address today.

1. **The Mobile Money Competitor** — Competitor integrated MTN MoMo, Airtel Money, Zamtel Kwacha as first-class options (not just card via Lenco/DPO). >70% of Zambian digital transactions are mobile money. **Prevention:** Make mobile money the PRIMARY method from day one; USSD fallback for feature phones.
2. **The WhatsApp Commerce Player** — Competitor built WhatsApp-native shopping (browse, order, pay without leaving WhatsApp). **Prevention:** WhatsApp Business API integration from v1.0 — order placement, tracking, support via WhatsApp.
3. **The Vendor Experience Winner** — Competitor made vendor onboarding a 5-minute phone-camera flow (scan ID, photos, prices, go live). **Prevention:** Design onboarding for lowest-common-denominator tech literacy; camera-based KYC, voice-to-text descriptions, auto background removal, instant (tiered) approval.
4. **The Last-Mile Logistics Operator** — Competitor built pickup-point network (shops, gas stations, community centers). **Prevention:** Partner with retail chains (Shoprite, Pick n Pay, Puma) as pickup/drop-off points.
5. **The Trust & Escrow Champion** — Competitor implemented buyer-protection escrow; Convergeo paid vendors directly and scam recourse failed; "Convergeo doesn't protect buyers" spread on Facebook. **Prevention:** Escrow-style payment holding from launch; funds release only after delivery confirmation (or X days). Non-negotiable for marketplace trust.
6. **The Content & Community Builder** — Competitor built TikTok/Instagram content strategy + local influencers; community not just marketplace. **Prevention:** Allocate 20–30% marketing budget to content from month one; partner with Zambian creators.
7. **The "Works Offline" Disruptor** — Competitor built a PWA with offline browsing, saved carts, USSD ordering. **Prevention:** Build as a PWA with aggressive caching, offline product browsing, SMS/USSD order confirmation fallback; design for 2G/3G first.
8. **The Vernacular Language Platform** — Competitor offered Bemba, Nyanja, Tonga, Lozi + voice navigation. Convergeo was English-only. **Prevention:** Multilingual from day one (i18n); launch with English + Bemba + Nyanja minimum; voice search in local languages within 6 months.
9. **The Instant Settlement Competitor** — Competitor paid vendors within 1 hour of delivery confirmation vs 7–14 day cycles. **Prevention:** Negotiate fastest settlement with Lenco/DPO; consider float-based instant payout (needs working capital).
10. **The Data & Personalization Engine** — Competitor personalized homepages, push, search from purchase/browsing/location data (3× conversion). **Prevention:** Analytics tracking from day one; recommendation-engine architecture early; n8n personalization workflows.
11. **The Cross-Border Enabler** — Competitor enabled SA & Chinese vendors with transparent cross-border pricing. **Prevention:** Build multi-currency + cross-border into the data model (don't enable yet, don't design it out).
12. **The Regulatory Compliant Platform** — ZICTA introduced e-commerce regulations in 2026; competitor had GDPR-style data protection, ToS, VAT handling, consumer protection; Convergeo scrambled, faced fines, was temporarily suspended. **Prevention:** Engage a Zambian legal firm NOW; build compliance into architecture (data protection, e-transaction records, VAT calculations, dispute resolution).
13. **The Vendor Financing Disruptor** — Competitor partnered with microfinance to offer vendors working-capital loans based on sales history. **Prevention:** Build shareable (consented) vendor sales-data tracking; explore MFI partnerships by month 4–5.
14. **The Super-App Strategy** — Competitor bundled commerce with airtime top-up, bill payments, P2P transfers, ride-hailing → daily usage. **Prevention:** Events/ticketing + directory are the start of a super-app; add utility bill payments + airtime top-up as early value-adds.
15. **The Speed Demon** — Competitor launched a barely-functional MVP in 30 days, onboarded 200 vendors via relationships, iterated weekly; Convergeo spent 60 days building "perfect", launched with zero vendors/customers, couldn't overcome cold-start. **Prevention:** Launch MVP in 30 days; pre-onboard 50–100 vendors BEFORE the platform is ready; first 100 vendors > first 100 features.

---

## Part 3 — Strategic Questionnaire (75 Questions) — ALL UNANSWERED

Options preserved verbatim; `(Recommended)` tags are from the source. No option is selected in the PDF.

### Business Model & Revenue (Q1–Q8)
- **Q1** Primary revenue model? A) Commission per transaction (5–15%) · B) Vendor subscription fees · C) Hybrid: small commission + optional subscription tiers · D) Primarily advertising revenue
- **Q2** Commission rate range? A) 3–5% · B) 6–10% (standard for African marketplaces) · C) 11–15% · D) Variable by category (e.g. 5% electronics, 12% fashion, 8% services)
- **Q3** "Chicken and egg" problem? A) Onboard vendors first with free listings 3–6 months · B) Start with a niche and dominate · C) Partner with 5–10 anchor vendors · D) Launch both sides simultaneously with promotions
- **Q4** Advertising model for vendors? A) CPC · B) Fixed placement fees · C) Tiered subscription with ads included (Bronze/Silver/Gold/Platinum) · D) Auction-based
- **Q5** Monetize events/ticketing? A) Flat fee per ticket · B) % of ticket price (5–10%) · C) Event listing fee (fee-free to buyers) · D) Free basic listings; charge for promoted/premium
- **Q6** Service charge strategy for delivery? A) Customer pays full cost · B) Subsidized · C) Free above minimum order (e.g. K200) · D) Delivery fee markup (K5–K10 margin)
- **Q7** Initial capital for first 6 months? A) Under K50,000 (~$2K) · B) K50K–K250K · C) K250K–K1M · D) Over K1M
- **Q8** Break-even target? A) Within 6 months · B) Within 12 months · C) Within 18–24 months · D) No specific target (investor funding)

### Technology & Architecture (Q9–Q18)
- **Q9** Backend stack? **A) Django (Python) + PostgreSQL (Recommended)** · B) Node/Express + MongoDB (MERN) · C) Django API + React/Next.js (decoupled) · D) Microservices from day one
- **Q10** Frontend for customer panel? **A) Next.js (React) (Recommended)** · B) Django templates + HTMX · C) Vue/Nuxt · D) React SPA + Vite
- **Q11** Hosting? A) AWS (Cape Town) · B) DigitalOcean/Hetzner · C) Vercel (frontend) + Railway/Render (backend) · D) Local Zambian hosting
- **Q12** Panel architecture? A) Single codebase role-based routing · B) Monorepo, three apps sharing a common library · C) Three separate repos · **D) Shared backend API, three separate frontend apps (Recommended)**
- **Q13** Primary AI coding tool? A) Claude Code primary, Cursor secondary · B) Cursor primary, Claude for review/architecture · C) Gemini CLI primary · D) All tools (accept integration overhead)
- **Q14** Real-time features? A) WebSockets (Django Channels/Socket.io) · B) Server-Sent Events · C) Polling + Push · D) Firebase/Supabase real-time
- **Q15** Search infrastructure? A) PostgreSQL full-text search · B) Elasticsearch · C) Meilisearch · D) Algolia
- **Q16** Product images/media? A) AWS S3 + CloudFront · B) Cloudinary · C) Cloudflare R2 + Images · D) Self-hosted MinIO
- **Q17** Caching strategy? A) Redis · B) Django DB cache · C) Cloudflare edge caching · **D) Redis + CDN (Recommended)**
- **Q18** Background tasks? A) Celery + Redis · B) n8n for all · **C) Celery for code-level + n8n for business workflows (Recommended)** · D) Bull/BullMQ (Node)

### Payments & Financial Strategy (Q19–Q26)
- **Q19** Primary gateway at launch? A) DPO (Network International) · B) Lenco · C) Both DPO + Lenco · D) Flutterwave/Paystack
- **Q20** How critical is mobile money? A) Absolutely essential (MTN MoMo + Airtel) · B) Important, can launch with card/bank first · C) Nice to have · D) Mobile money ONLY at launch
- **Q21** Vendor payouts/settlement? A) Weekly batch · B) Daily automatic once delivery confirmed · C) On-demand withdrawals · D) Instant settlement (needs float capital)
- **Q22** Buyer protection / escrow? **A) Yes, full escrow — funds held until buyer confirms (Recommended)** · B) Partial (refund policy, no hold) · C) Vendor-dependent · D) Insurance-based
- **Q23** Multi-currency? A) ZMW only at launch · B) ZMW + USD · C) Multi-currency day one (ZMW/USD/ZAR) · D) Display any, settle in ZMW
- **Q24** Charge VAT on service fees? A) Yes, 16% on all charges · B) Not initially — register once revenue > K800,000 · C) VAT-inclusive pricing · D) Consult tax advisor first
- **Q25** Cash on Delivery? A) Offer COD from launch · B) No COD · C) COD only under a value (e.g. under K500) · D) "Pay at Pickup" via mobile money
- **Q26** Long-term payment gateway vision? A) Never build a gateway · B) Build "Convergeo Pay" wallet (internal credits) · C) Apply for e-money license in 2–3 years · D) Acquire/partner with licensed fintech

### Customer Experience & UX (Q27–Q34)
- **Q27** Launch languages? A) English only · B) English + Bemba + Nyanja · C) English + all 7 major Zambian languages · D) English + French
- **Q28** Primary customer acquisition channel? A) Facebook/Instagram ads · B) WhatsApp groups + word-of-mouth · C) Local influencers + TikTok · D) Google SEO + SEM
- **Q29** Registration/login? A) Phone + OTP only · B) Email + password + social · C) Phone or email + social · D) Guest checkout first
- **Q30** Homepage priority? A) Flash deals/promoted · B) Categories + vendor logos ("hub of logos") · C) Personalized recommendations + trending · D) Prominent search + curated collections
- **Q31** AI-powered search/discovery at launch? A) Smart filters + autocomplete (no AI initially) · B) LLM chatbot day one · C) Vector search (pgvector) semantic matching · D) Image search
- **Q32** Rating & review depth? A) Simple 5-star + text · B) Multi-dimensional + photos · C) Verified-purchase only · D) All of the above
- **Q33** QR-code pickup system? A) Customer shows QR, vendor scans · B) Dynamic QR every 60s · C) QR + PIN backup · D) Two-way verification
- **Q34** Mobile app from start? **A) PWA first (Recommended)** · B) Native Android + responsive web · C) React Native cross-platform · D) Responsive web only until 10,000+ users

### Vendor Experience & B2B (Q35–Q42)
- **Q35** Vendor onboarding time? A) Under 10 minutes (phone-based, instant) · B) Same day · C) 1–3 days vetting · D) Tiered: instant basic, 1–3 days verified/premium
- **Q36** KYC documents? A) National ID/passport only · B) National ID + PACRA business registration · C) Tiered (ID individuals, full docs companies) · D) Phone verification only, progressive KYC
- **Q37** B2B wholesale/supply feature? A) Separate B2B portal · B) Same products, tiered pricing (buy 1 retail, 10+ wholesale) · C) Request-for-quote (RFQ) · D) Skip B2B at launch
- **Q38** Vendor analytics? A) Basic · B) Intermediate · C) Advanced · D) Start basic, unlock with tier
- **Q39** Vendor inventory management? A) Manual · B) CSV/Excel bulk · C) API integration · D) All of the above by size
- **Q40** Vendor↔customer direct communication? A) In-platform messaging only · B) Show phone/WhatsApp directly · C) Pre-purchase in-platform, post-purchase share contact · D) No direct communication
- **Q41** Vendor-to-vendor competition (same product)? A) Market decides (sort by rating/price) · B) "Buy Box" like Amazon · C) Category exclusivity for premium vendors · D) Comparison view side-by-side
- **Q42** Vendor "About Us" richness? A) Basic · B) Rich (branches, hours, photos, social, story) · C) Premium (video, team, certs) · D) Tiered by subscription

### Logistics & Delivery (Q43–Q48)
- **Q43** First delivery providers? A) Yango only · B) Yango + Bolt · C) Multiple (Yango + local couriers, Zampost) · D) Build own rider network
- **Q44** Geographic coverage at launch? A) Lusaka only · B) Lusaka + Copperbelt · C) All major cities · D) Nationwide (pickup-only where no delivery)
- **Q45** Delivery for different product types? A) Standard only · B) Category-specific · C) Vendor-managed · D) Hybrid (platform small items, vendor large/special)
- **Q46** Same-day delivery? A) Yes, before cutoff in Lusaka · B) Yes, express premium · C) No, 1–3 day standard · D) Only food/grocery
- **Q47** Delivery tracking? A) Status updates only · B) Real-time GPS · C) SMS/WhatsApp at each status · D) Pass through Yango/Bolt tracking
- **Q48** Returns & exchanges? A) Customer to vendor directly (platform facilitates refund) · B) Pickup points for returns · C) Reverse logistics via delivery partners · D) No returns for MVP (refund-only faulty/wrong)

### Events, Tickets & Services (Q49–Q53)
- **Q49** Event types? A) Entertainment only · B) All events · C) Entertainment + business networking (B2C+B2B bridge) · D) Skip events at launch
- **Q50** Digital ticket handling? A) QR via email/SMS · B) In-app dynamic QR (anti-forward) · C) NFT-based · D) Simple alphanumeric confirmation (SMS/feature phones)
- **Q51** Service bookings? A) Yes — salons/mechanics/tutors with booking slots · B) Listings only (booking off-platform) · C) Services as phase 2 · D) Quote-request (RFQ) model
- **Q52** "Location/tourism" feature for foreigners? A) Google Maps + curated pins · B) City guides by category · C) AI trip planner · D) Partner with Zambia Tourism Board
- **Q53** Business directory prominence? A) Core (equal to marketplace, own tab) · B) Secondary (vendor profiles serve as directory) · C) Premium add-on · D) Phase 2 feature

### Marketing & Growth Strategy (Q54–Q59)
- **Q54** Pre-launch marketing? A) Build hype (landing page, waitlist, countdown) · B) Quiet invite-only beta · C) Partner launch with 3–5 known brands · D) Physical launch event in Lusaka
- **Q55** First-time purchase incentive? A) First-purchase discount (20% off, cap K50) · B) Free delivery first 3 orders · C) Referral (both get K20) · D) Loyalty points from first purchase
- **Q56** Year-1 customer acquisition target? A) 1,000 · B) 5,000 · C) 10,000–25,000 · D) 50,000+
- **Q57** Year-1 vendor recruitment target? A) 50–100 · B) 200–500 · C) 500–1,000 · D) 1,000+
- **Q58** Brand positioning? A) Premium (trusted marketplace) · B) Value (best prices) · C) Discovery ("hub of logos") · D) Tech-forward
- **Q59** Content marketing? A) Vendor success stories · B) Product reviews/unboxings by influencers · C) Educational ("How to sell online in Zambia") · D) All of the above

### Legal, Compliance & Operations (Q60–Q65)
- **Q60** Business registration structure? A) Private limited (PACRA) · B) Sole proprietorship → Ltd later · C) Partnership with co-founder · D) Foreign-friendly jurisdiction + Zambian subsidiary
- **Q61** Data protection & privacy? A) Comply with Zambia Data Protection Act (2021) — minimum · B) GDPR-level · C) Basic privacy policy for now · D) Hire DPO + certify before launch
- **Q62** Dispute resolution (buyer↔vendor)? A) Platform-mediated (binding) · B) Automated rules (auto-refund if no response in 48h) · C) Escalation tiers (auto first, human > K500) · D) Third-party arbitration for high value
- **Q63** Team structure first 6 months? A) Solo founder + AI tools (Claude Code, n8n) · B) Founder + 1 dev + 1 ops/marketing · C) Founder + 2–3 devs + designer + BD · D) Outsource dev to agency
- **Q64** Customer support? A) WhatsApp-based · B) AI chatbot + human escalation · C) In-app help center + email · D) WhatsApp + AI chatbot + phone for high-value
- **Q65** Weekly platform-health metrics? A) GMV + transactions + active vendors · B) + CAC + CLV + churn · C) + NPS + vendor satisfaction + resolution time · D) Keep simple (daily orders/revenue/new users)

### Automation, AI & n8n Strategy (Q66–Q70)
- **Q66** What should n8n automate FIRST? A) Order processing (confirmations, vendor notifications, status) · B) Vendor onboarding · C) Marketing (abandoned cart, review requests, campaigns) · D) All simultaneously
- **Q67** AI beyond search? A) Product description generation · B) Fraud detection · C) Price optimization · D) All (descriptions → fraud → pricing)
- **Q68** n8n external service connections? A) SMS gateway (Africa's Talking) for notifications/OTP · B) WhatsApp Business API · C) Accounting (QuickBooks/Xero) · D) All of the above
- **Q69** Strongest AI competitive advantage? A) Conversational shopping assistant · B) Visual search · C) Personalized recommendations · D) Auto-translation + voice search local languages
- **Q70** When to prioritize virtual try-on / AR? A) Phase 1 (MVP) · B) Phase 2 (3–6 months) · C) Phase 3 (6–12 months) · D) Never — focus on all-category features

### Competition & Expansion Strategy (Q71–Q75)
- **Q71** Most dangerous competitor now? A) Facebook Marketplace · B) WhatsApp informal sellers · C) Existing local platforms (BuyZam/ZedMarket) · D) International (Jumia/Takealot/Amazon)
- **Q72** Single strongest differentiator? A) "Hub of logos" (discovery + commerce) · B) B2B + B2C combined · C) Events + commerce integration · D) AI-powered discovery
- **Q73** First expansion country after Zambia? A) Zimbabwe · B) Tanzania · C) DRC (Katanga/Lubumbashi) · D) Malawi
- **Q74** When to seek external investment? A) Before launch · B) After traction (1,000+ orders/mo) · C) Never (bootstrap) · D) African accelerators (YC/Techstars/CcHub)
- **Q75** 5-year success? A) Zambia's #1 e-commerce (500K+ users, 5,000+ vendors) · B) Pan-African (5+ countries) · C) Super-app (commerce + payments + logistics + services + events) · D) Acquired by a major tech company

---

*Footer (verbatim):* "CONVERGEO — Strategic Foundation Questionnaire v1.0 · Prepared April 2026 \| Confidential — For Internal Use Only · Answer all 75 questions, then we build the mountain together."

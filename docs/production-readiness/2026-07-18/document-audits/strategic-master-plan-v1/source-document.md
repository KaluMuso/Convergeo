# Source Document — Convergeo Strategic Master Plan v1.0

## Document metadata

| Field | Value |
| ----- | ----- |
| **Document title** | Convergeo Strategic Master Plan — "THE MOUNTAIN" |
| **Subtitle** | From Vision to Zambia's Premier E-Commerce Platform |
| **Version** | v1.0 |
| **Date** | April 2026 |
| **Classification** | CONFIDENTIAL |
| **Author (footer)** | Prosper Kaluba ("Show me the mountain, then we break it into daily pebbles.") |
| **Provenance note (footer)** | "Built from 75 strategic decisions, 5 research documents, 15 Red Team scenarios, and one founder's vision." |
| **Source file** | `88c0033e-Convergeo_Strategic_Master_Plan_1_1.pdf` (image/render-based PDF, 17 rendered pages) |
| **Extraction method** | PyMuPDF render → vision transcription (PDF is image-based; only ASCII diagrams carried embedded text). PDF `producer` metadata = GPL Ghostscript 10.07.0; PDF `creationDate` = 2026-07-18. |
| **Audit slug** | `strategic-master-plan-v1` |
| **Audited against** | Live Vergeo5 production baseline captured in `docs/production-readiness/2026-07-18/foundation/` + local repo HEAD `0b88723` (branch `claude/doc-production-reconciliation-audit-m2gnxp`). |

> **Nature of the document:** This is a **requirements / policy / specification** document — a founder-facing strategic plan structured as an answer key to 75 discovery questions, plus tensions, business model, a technical architecture blueprint, a development methodology, a 4-phase roadmap, a 60-day sprint schedule, KPIs, and a risk register. It is dated **April 2026** and is an **early** planning artifact.
>
> **Critical reconciliation context:** The repo's authoritative decision record `docs/plan/00-decisions.md` (LOCKED **2026-07-06**) explicitly **supersedes** several Master-Plan technology decisions (it even cites "per Master Plan L2", "per Master Plan Q25"). Where production diverges from this document on the tech stack, the divergence is in most cases an **intentional, documented supersession**, not an accidental defect. This distinction drives the impact/priority of every conflict row.

---

## 1. Structure (10 sections + hero/TOC/footer)

Hero stats: **75 decisions made · 60 days to MVP · ~$2K bootstrap budget · 1 founder + AI · 5yr super-app vision**.

TOC: (1) Your 75 Strategic Decisions · (2) Critical Tensions & Resolutions · (3) Platform Identity & Business Model · (4) Technical Architecture Blueprint · (5) Development Methodology · (6) The 4 Phases of Convergeo · (7) 60-Day Sprint Schedule · (8) Success Metrics & KPIs · (9) Risk Register & Mitigations · (10) What Happens Next.

---

## 2. Section 1 — 75 Strategic Decisions (verbatim/paraphrased)

**Business Model & Revenue (Q1–Q8)** — pp.2–3
- Q1: Hybrid — small commission + optional subscription tiers.
- Q2: Variable commission by category (e.g. 5% electronics, 12% fashion).
- Q3: Onboard vendors first with free listings for 3–6 months (supply-first).
- Q4: Tiered subscription with advertising included (Bronze/Silver/Gold/Platinum).
- Q5: Percentage of ticket price (5–10% service fee); keep 5% initially.
- Q6: Free delivery above minimum order value (e.g. orders over K200).
- Q7: Under K50,000 (~$2,000 USD) — bootstrapping. **[CRITICAL CONSTRAINT]**
- Q8: Within 12 months — growth-focused but need revenue trajectory (revenue from month 3–4).

**Technology & Architecture (Q9–Q18)** — p.3
- Q9: Django backend API + React/Next.js frontend (decoupled). "This is the architecture we'll build."
- Q10: Next.js (React) — SSR for SEO; App Router + React Server Components.
- Q11: Vercel (frontend) + Railway/Render (backend, ~$7–20/mo).
- Q12: Shared backend API, three separate frontend apps (one **Django REST API** for Customer/Vendor/Admin).
- Q13: Claude Code primary, Cursor secondary for UI; Gemini for review.
- Q14: Firebase/**Supabase real-time** for notifications and order tracking.
- Q15: **Meilisearch** — fast, typo-tolerant, self-hostable on Railway, 50ms responses.
- Q16: Cloudinary — auto optimization, generous free tier (25GB).
- Q17: **Redis + CDN** — layered caching (Upstash free tier 10K cmds/day; Cloudflare CDN).
- Q18: **Celery + n8n** combined (Celery for code-level async; n8n for business workflows).

**Payments & Financial (Q19–Q26)** — pp.3–4
- Q19: **Both DPO + Lenco** — redundancy and choice (DPO for MoMo, Lenco developer API, fallback).
- Q20: Mobile money absolutely essential — MTN MoMo + Airtel Money from day one. **[NON-NEGOTIABLE]**
- Q21: Instant settlement (within hours of delivery confirmation). **[TENSION — needs float]**
- Q22: Full escrow — funds held until buyer confirms receipt (#1 differentiator vs WhatsApp sellers).
- Q23: Display in any currency, settle in ZMW (exchange-rate API for display).
- Q24: Consult tax advisor before deciding; below K800K threshold = no mandatory VAT; architect for VAT day one.
- Q25: COD under certain value + Pay-at-Pickup via mobile money (COD for small orders under K500).
- Q26: Long-term: partner with existing licensed fintech; don't build payment infra.

**Customer Experience (Q27–Q34)** — pp.4
- Q27: English + Bemba + Nyanja at launch (~80% of Zambia); add Tonga/Lozi/Kaonde/Luvale later.
- Q28: Local influencer partnerships + TikTok/Instagram Reels content (K0 budget, revenue-share).
- Q29: Phone or email (user chooses) + social login — phone primary (OTP via **Africa's Talking**), Google/Facebook social.
- Q30: Hero search bar + curated collections (D), then categories/logos (B) + trending (C).
- Q31: Smart filters + autocomplete (A) combined with vector search/**pgvector** (C).
- Q32: Full: verified, multi-dimensional reviews with photo/video uploads (verified-purchase badge).
- Q33: QR code + PIN code backup (QR primary, PIN fallback).
- Q34: PWA first — works like an app, no app store; installable, offline, push.

**Vendor Experience & B2B (Q35–Q42)** — pp.4–5
- Q35: Tiered onboarding — instant for basic, 1–3 days for verified/premium.
- Q36: Tiered KYC — ID only for individuals (NRC photo), full docs (PACRA) for companies.
- Q37: Tiered pricing (B) + RFQ system (C) combined (volume discounts + quote-request).
- Q38: Progressive analytics — basic free, advanced unlocks with tier.
- Q39: All methods: manual + CSV bulk + API integration.
- Q40: Pre-purchase in-platform only; post-purchase can share contacts.
- Q41: Comparison view — all vendors side-by-side + sort by nearest.
- Q42: Tiered vendor profiles — basic free, rich for paid, premium for top-tier.
- Insight: Shared product images across vendors (one canonical image, multiple vendor price listings — Amazon-style).
- Vendor Info: rich profiles (location, social, web, hours) = the business-directory feature.

**Logistics & Delivery (Q43–Q48)** — pp.5–6
- Q43: Multiple — **Yango + local courier services (Zampost, private)**; abstract behind a delivery aggregation layer.
- Q44: All major cities: Lusaka, Ndola, Kitwe, Livingstone, Kabwe (resolution: list all cities, deliver only in Lusaka initially, pickup everywhere).
- Q45: Hybrid — platform-managed for small items, vendor-managed for large.
- Q46: No same-day — 1–3 day standard delivery.
- Q47: Pass through delivery partner tracking where available (**Yango/courier tracking APIs**, status webhooks).
- Q48: No returns for MVP — refund-only for faulty/wrong items (physical returns in v2).

**Events, Services & Discovery (Q49–Q53)** — p.6
- Q49: All events — entertainment + conferences + workshops + private.
- Q50: In-app tickets with **dynamic QR codes** (refresh every 60 seconds; requires PWA).
- Q51: Quote-request model — customers describe needs, providers respond ("post a job").
- Q52: City guides with categories + AI enhancement later (Lusaka, Livingstone, Ndola).
- Q53: Core feature — business directory as a separate navigation tab ("hub of logos").

**Marketing, Growth, Legal & Operations (Q54–Q65)** — pp.6–8
- Q54: Quiet launch — invite-only beta, iterate, then public.
- Q55: Referral program — both referrer and referee get K20 credit.
- Q56: 10,000–25,000 registered customers (year 1).
- Q57: 200–500 vendors (year 1).
- Q58: Discovery — "Discover everything Zambia has to offer."
- Q59: All content types — vendor stories, unboxings, educational.
- Q60: Private limited company registered with PACRA.
- Q61: **GDPR-level compliance.**
- Q62: Escalation tiers — automated first, human review for K500+.
- Q63: Solo founder + AI tools (Claude Code + Cursor + n8n; max automation, zero headcount). **[AI-FIRST]**
- Q64: WhatsApp + AI chatbot + phone for high-value issues.
- Q65: Comprehensive KPIs — GMV + CAC + LTV + NPS + vendor satisfaction.

**Automation, AI & Competitive Strategy (Q66–Q75)** — pp.7–8
- Q66: n8n automates order processing first.
- Q67: All AI features — descriptions → fraud → pricing (prioritized).
- Q68: All external services — SMS + WhatsApp + Accounting.
- Q69: Personalized recommendations as strongest AI advantage.
- Q70: Virtual try-on/AR in Phase 3 (6–12 months post-launch).
- Q71: **WhatsApp informal sellers are the biggest competitor** (not Jumia). **[KEY INSIGHT]**
- Q72: "Hub of logos" — comprehensive business discovery + commerce.
- Q73: Zimbabwe first for expansion.
- Q74: Seek investment after proving traction (1,000+ orders/month).
- Q75: 5-year vision — super-app (commerce + payments + logistics + services + events).

---

## 3. Section 2 — Critical Tensions & Resolutions (pp.8–9)

- **T1 — $2,000 budget vs instant vendor settlements (Q7+Q21):** Resolution → launch with **48-hour settlements** (not instant); market "fastest in Zambia"; move to instant only after K10,000+ float (~month 3–4). Build instant payout architecture now, activate later.
- **T2 — $2,000 budget vs GDPR-level compliance (Q7+Q61):** Resolution → build GDPR-ready architecture (encryption, consent tracking, audit logs) but start with **Zambia Data Protection Act compliance only**. Architecture first, legal certification later.
- **T3 — Solo founder vs 10K–25K customers year 1 (Q63+Q56):** Resolution → reframe target to **1,000 active buyers** in year 1; obsess over repeat purchase rate, not registrations.
- **T4 — All major cities vs bootstrap budget (Q44+Q7):** Resolution → vendors nationwide, **delivery only in Lusaka for first 60 days**; other cities pickup-only; add Copperbelt month 3.
- **T5 — Full escrow vs cash flow (Q22+Q7):** Resolution → escrow hold = **48h after delivery confirmation OR 7 days after shipping (auto-release)**; use a **ledger system (not actual bank sub-accounts)**.
- **T6 — "AI-first" platform vs bootstrap reality:** Resolution → "AI-first" = **AI-READY architecture**, not AI-powered from day one; collect data day one; rule-based "smart" features that look like AI; add ML models at 10K+ transactions.

---

## 4. Section 3 — Platform Identity & Business Model (pp.9–10)

- Identity: Convergeo is **not a marketplace** — it is a **commerce-powered discovery platform** ("Discover Everything Zambia Has to Offer"). Moat vs WhatsApp sellers = discovery + trust (escrow) + convenience (delivery/pickup) + confidence (reviews).
- **Revenue Architecture:**
  - **Layer 1 — Commissions (variable):** 5% electronics, 8% home goods, 10% fashion/beauty, 12% services, 5% event tickets.
  - **Layer 2 — Vendor Subscriptions (4 tiers):** Free (≤20 products, basic profile, standard commission, basic analytics) · **Bronze K99/mo** (100 products, verified badge, featured in category, −1% commission, intermediate analytics) · **Silver K249/mo** (unlimited products, priority search, rich profile, advanced analytics, bulk upload) · **Gold K499/mo** (+ homepage rotation, dedicated support, API integration, competitor pricing insights, premium profile with video).
  - **Layer 3 — Events (5% ticket commission).**
  - **Layer 4 — Promoted Listings (future, auction-based).**
- **Break-Even Projection:** monthly cost ≈ **$62/mo ($744/yr)** (Hosting ~$30, Cloudinary free, Meilisearch on Railway ~$10, Domain/SSL ~$2, SMS/OTP ~$20, n8n $0) → ~15 months runway on $2K. Infra break-even ≈ 4 orders at K200 avg. 12-month target ≈ $600/mo revenue (500 orders + 50 subscribers).

---

## 5. Section 4 — Technical Architecture Blueprint (pp.10–12)

ASCII "CONVERGEO ARCHITECTURE" diagram + **Tech Stack Summary** (verbatim):
- **Backend:** Django 5.x + Django REST Framework + PostgreSQL 16 (pgvector) + Celery + Redis (Upstash free tier).
- **Frontend:** Next.js 14+ (App Router) + TypeScript strict + Tailwind CSS + Zustand (state) + React Query (data).
- **Infrastructure:** Vercel (3 frontend apps, free) + **Railway** (Django API + PostgreSQL + Meilisearch, ~$20/mo) + Cloudflare (CDN/DNS, free).
- **Services:** Cloudinary (images) + **Supabase (realtime, free tier)** + **Upstash Redis** + **Africa's Talking (SMS/OTP ~$0.02/SMS)**.
- **Payments:** **DPO (mobile money + cards) + Lenco (bank transfers + developer API).**
- **Automation:** n8n (self-hosted on Railway or local) + **Celery** (code-level tasks).
- **Search:** **Meilisearch (primary)** + pgvector (semantic) + PostgreSQL full-text (fallback).
- **Contracts:** OpenAPI 3.1 spec as single source of truth.
- **Estimated Monthly Cost:** $30–$60.
- External services in diagram: DPO/Lenco Payments · Cloudinary · Meilisearch (Railway) · n8n (self-hosted) · Supabase Realtime (notifs) · Africa's Talking (SMS/OTP) · **Yango/Courier Delivery APIs**.
- **Data model (Your Insight):** `Product (canonical)` = id, name, description, images[] (Cloudinary), specifications{}, category_id, brand · `VendorListing` = id, product_id (FK), vendor_id (FK), price (ZMW), stock_quantity, delivery_options, condition (new/used), is_active, created_at. "6 vendors selling the same Coca-Cola 500ml = 1 Product row + 6 VendorListing rows."

---

## 6. Section 5 — Development Methodology (7 rules) (p.12)

Synthesized from 5 strategy PDFs. Rule 1: Contract-First (OpenAPI 3.1 before code; generate TS types + Pydantic models). Rule 2: AI Council (Claude → Gemini → Cursor). Rule 3: Plan → Approve → Code → Validate (read `AI_CONTEXT.md`; wait for approval; branch; test; human reviews diff). Rule 4: `AI_CONTEXT.md` as persistent memory. Rule 5: Chunk work into atomic modules (one Django app / API resource / Next.js feature). Rule 6: CI/CD as gatekeeper (lint ruff/eslint, type mypy/tsc --strict, pytest/vitest, OpenAPI contract validation — "deterministic validation of probabilistic output"). Rule 7: Git guardrails (branch before AI; never commit to main; NotebookLM as infinite memory).

---

## 7. Section 6 — The 4 Phases (pp.12–14)

- **Phase 1 — Foundation MVP (Days 1–60) "Base Camp":** Working multivendor marketplace in Lusaka. **What ships:** customer panel (browse, Meilisearch search, filter, vendor profiles, cart, **checkout with DPO (mobile money + cards)**, QR pickup verification, order tracking, reviews, PWA) · vendor panel (tiered KYC register, manual+CSV listings, prices, orders, basic analytics, profile) · admin panel (approve vendors, manage products/categories, metrics, disputes, manage users) · **Payments: DPO (MTN MoMo, Airtel, cards) + escrow + 48-hour settlement** · **Delivery: Lusaka only, Yango API + self-pickup nationwide** · Automation: n8n order confirmation emails, vendor notifications, **OTP via Africa's Talking** · i18n English + Bemba + Nyanja (UI strings). **What does NOT ship:** Events/ticketing, B2B wholesale, business directory, AI search, city guides, advertising, referral program, quote-request services, **Lenco integration**, real-time notifications. **Pre-launch:** register PACRA, onboard 50–100 vendors, social accounts, onboarding guide.
- **Phase 2 — Growth Features (Days 61–120) "Climbing":** events & ticketing (dynamic QR), business directory nav tab, quote-request services, referral program (K20), **vendor subscription tiers (Bronze/Silver/Gold)**, **Lenco payment integration (redundancy)**, Supabase real-time notifications, Copperbelt delivery, in-platform messaging, comparison view, AI product descriptions.
- **Phase 3 — Intelligence Layer (Days 121–240) "The Ridge":** personalized recommendations, city guides, AI conversational search, fraud detection, advanced vendor analytics, B2B wholesale (tiered volume + RFQ), WhatsApp Business API, abandoned-cart recovery (n8n), promoted listings, multi-city delivery.
- **Phase 4 — Super-App Evolution (Month 9–18+) "The Summit":** airtime/bill payments, virtual try-on/AR, Convergeo Pay wallet, vendor financing (MFI), voice search Bemba/Nyanja, React Native app, Zimbabwe expansion, AI trip planner, price optimization, pickup-point network.

---

## 8. Section 7 — 60-Day Sprint (Phase 1 weekly deliverables) (pp.14–16)

W1 Foundation & Contracts (PACRA, monorepo `/apps/api` Django + `/apps/customer|vendor|admin` Next.js + `/packages/types|utils`, OpenAPI 3.1, CI GitHub Actions ruff/mypy/eslint/tsc/pytest/vitest, `AI_CONTEXT.md`, Django custom User phone+email, Postgres on Railway, Cloudinary/Upstash/Cloudflare, DB schema, wireframes). W2 User System & Product Catalog (django-allauth phone OTP + social, product/category/vendor CRUD, Cloudinary upload, Meilisearch on Railway, TS types from OpenAPI, **Africa's Talking SMS/OTP**). W3 Vendor Panel & Cart/Checkout (dashboards, listing form, order mgmt, cart/checkout APIs, CSV bulk upload, tiered KYC). W4 Payments & Escrow (**DPO integration** MTN/Airtel, escrow ledger, vendor settlement engine, order status machine, QR + PIN, VAT-ready pricing). W5 Delivery, Reviews & Admin (**Yango API**, order tracking, review system, admin approval/moderation/dashboard/disputes, n8n order/vendor workflows). W6 Polish, i18n & PWA (Bemba/Nyanja translations, PWA offline, Android/3G perf, SEO, homepage). W7 Testing & Beta (E2E, **DPO sandbox** payment testing, load 100 users, security audit CSRF/XSS/SQLi/authz, beta 20–30 users, privacy policy + ToS Zambia DPA, GA4). W8 Bug Fixes & Pre-Launch (bugfix, perf, 75–100 vendors, **Sentry free + Better Uptime**, n8n welcome emails). W8.5 Public Launch (Days 57–60).

---

## 9. Section 8 — Success Metrics & KPIs (pp.15–16)

- **Month 1:** 50–100 orders · 75–100 active vendors (≥5 products) · GMV K10K–25K · revenue K800–2,000 · **payment success >90%** · **order completion >80%** · zero unresolved disputes >72h · zero payouts delayed >48h.
- **6-Month:** 300–500 monthly orders · 200+ vendors · 2,000–5,000 users · GMV K75K–125K · revenue K6K–12K · repeat rate >20% · NPS >40.
- **12-Month (break-even):** 1,000+ monthly orders · 500+ vendors · 10,000+ users · GMV K250K+ · revenue K25K+.

---

## 10. Section 9 — Risk Register (p.16)

Top-5 existential risks: (1) Cold start / empty marketplace **[HIGH]** → onboard 75+ vendors before day 60. (2) Payment integration failure **[HIGH]** → start DPO week 3, apply for production creds week 1, manual bank-transfer fallback. (3) Solo founder burnout **[MED]** → AI 70% of code, n8n ops automation, batch onboarding. (4) Fraud / scam vendors **[MED]** → tiered KYC, escrow, verified reviews, transaction limits (first 5 orders ≤K500), quick dispute resolution. (5) Competitor launches first **[LOW-MED]** → speed (60-day timeline) + unique discovery positioning.

---

## 11. Section 10 — What Happens Next (p.17)

Step 1 confirm the plan; Step 2 generate OpenAPI 3.1 + Django scaffold + Next.js monorepo + `AI_CONTEXT.md` + CI/CD + DB schema; Step 3 daily Plan→Approve→Code→Validate cadence; Step 4 ship in 60 days. Footer: "CONVERGEO — THE MOUNTAIN · Strategic Master Plan v1.0 · April 2026 · Confidential."

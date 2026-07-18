# Source Document — Convergeo 60-Day Development Roadmap

## Document metadata

| Field | Value |
| --- | --- |
| **DOCUMENT_SLUG** | `convergeo-60-day-development-roadmap` |
| **DOCUMENT_TITLE** | Convergeo 60-Day Development Roadmap |
| **Subtitle** | Zambia's Premier Multivendor E-Commerce Platform |
| **Stated start date** | April 21, 2026 |
| **Stated duration** | 60 Working Days (8 Weeks) — *internal inconsistency: 60 working days ≈ 12 calendar weeks, not 8* |
| **Footer "Last updated"** | April 19, 2026 |
| **PDF CreationDate / ModDate (metadata)** | 2026-07-18 15:16:56 UTC (re-exported on audit day) |
| **PDF producer / creator** | wkhtmltopdf 0.12.6 → GPL Ghostscript 10.07.0 |
| **File** | `864bd894-Convergeo_60_Day_Development_Roadmap_1.pdf` (6.9 MB) |
| **Page count (pdfinfo)** | **13 pages** (the harness upload notice said "71 pages"; the actual file is 13 A4 pages) |
| **Source type** | Image-rendered HTML export. Text layer contains only 3 code strings (`docker compose up`, `/api/health/`, `spectral lint`); all substantive content is rasterized. Extracted by visual page rendering (poppler `pdftoppm` + Read tool), not text extraction. |
| **Methodology tagline** | "Contract-First · One Module at a Time · Plan → Approve → Code → Validate" |
| **Progress state shown** | 0 completed · 0 in progress · 60 remaining · **0% overall** — every day marked **NOT STARTED**. This is a *forward-looking plan*, not a completion record. |

> **Audit note.** This is a planning/specification artifact (source-of-truth **rank 4** per `document-audit-contract.md`). It predates and is partially superseded by the 28 locked stack decisions in `CLAUDE.md` (D18–D24) and by live production. It does **not** claim any feature is deployed; it describes intended work and an intended technology stack. Reconciliation therefore compares the plan's *intended end-state and mandated stack* against live production + repository.

---

## Transcribed content (by page)

### Page 1 — Header & Phase 1 start

- **Title:** Convergeo 60-Day Development Roadmap — "Zambia's Premier Multivendor E-Commerce Platform"
- **Start:** April 21, 2026 · **Duration:** 60 Working Days (8 Weeks) · **Stack:** Django + Next.js + PostgreSQL · **Hosting:** Vercel + Railway
- **Progress tracker:** 0 completed / 0 in progress / 60 remaining / 0% overall
- **Phase tabs:** Phase 1 Foundation · Phase 2 Commerce · Phase 3 Trust · Phase 4 Launch

**PHASE 1 of 4 — Foundation MVP (Days 1–15, 3 Weeks).** "Establish the project architecture, authentication system, product catalog, and initial frontend scaffolds. Every API contract is defined in OpenAPI before a single line of implementation is written."

**Day 1 — Project Scaffold & Architecture Setup** (DevOps, Backend, Full Stack)
- Initialize monorepo structure (`backend/`, `customer-app/`, `vendor-app/`, `admin-app/`, `shared/`)
- Create `AI_CONTEXT.md` with project rules, naming conventions, architecture decisions
- Draft comprehensive OpenAPI v3.1 specification covering all Phase 1 endpoints
- Design PostgreSQL 16 database schema (ERD) — users, vendors, products, categories
- Docker Compose setup: Django, PostgreSQL, Redis, Meilisearch
- Configure Django 5.x project with DRF, custom settings, environment variables
- Configure pre-commit hooks: black, isort, ruff, mypy, prettier, eslint
- Setup CI/CD pipeline skeleton (GitHub Actions)
- *Testing:* `docker compose up` starts all services; Django `/api/health/` returns 200; OpenAPI validates with `spectral lint`; pre-commit hooks pass; AI_CONTEXT.md committed

**Day 2–3 — Custom User Model & Authentication System** (Backend, Testing)
- Custom User model extending `AbstractBaseUser` (phone number as primary identifier)
- Phone OTP authentication flow (request OTP, verify OTP, issue JWT)
- Email/password authentication as secondary method
- JWT token management (access + refresh via `djangorestframework-simplejwt`)
- User registration API (phone + email); password reset (email-based); user profile CRUD
- Auto-generate TypeScript types from OpenAPI spec (`shared/types/`)
- *Testing:* 95%+ auth test coverage (pytest); OTP end-to-end; JWT issuance/refresh; rate limiting active on OTP endpoint; generated TS types match contract

**Day 4–5 — Vendor Model, Onboarding & KYC Flow** (Backend, Testing)
- Vendor model with business details, verification status, commission rate
- Vendor onboarding API (multi-step application submission)
- KYC document upload & verification workflow (NRC, business registration)
- Vendor profile CRUD with owner-only permissions
- Vendor status machine: Applied → Under Review → Approved / Rejected
- Store slug generation and uniqueness validation
- Vendor dashboard data endpoint (stats, recent orders preview)

**Day 6–7 — Category System & Product CRUD with Image Pipeline** (Backend, Integration)
- Hierarchical category model (MPTT/`django-treebeard`) with unlimited nesting
- Category CRUD API with slug auto-generation
- Product model with SKU, pricing (ZMW), stock tracking, vendor FK
- Product CRUD API (vendor-scoped: vendors manage only their own products)
- Product variant system (size, color, etc.) with individual pricing/stock
- Cloudinary integration for image upload, transformation, CDN delivery
- Multi-image upload per product (up to 8 images, drag-to-reorder)
- Product approval workflow: Draft → Pending Review → Published / Rejected

**Day 8–9 — Product Search, Filtering & Pagination (Meilisearch)** (Backend, Integration)
- Meilisearch integration with Django (`meilisearch-python` SDK)
- Product index configuration (searchable attributes, filterable facets)
- Automatic sync: product create/update/delete triggers Meilisearch index update
- Search API with typo-tolerance, instant results; faceted filtering (category, price range, vendor, rating, availability); sorting (relevance, price, newest, best-selling)
- Cursor-based pagination; search suggestions / autocomplete
- *Testing:* Search response time under 50ms for 10k products

### Page 2 — Phase 1 continued

**Day 10–11 — Customer App: Homepage, Product Listing & Detail Pages** (Frontend, Design)
- Next.js 14+ customer app (App Router, TypeScript, Tailwind CSS)
- Shared UI component library; API client from auto-generated OpenAPI types
- Homepage (hero, featured categories, trending, new arrivals); listing page (search bar, filters sidebar, grid/list); product detail (gallery, variants, pricing, add-to-cart, vendor info); category browsing with breadcrumbs
- Responsive mobile-first; breakpoints 320/768/1024px; TS strict zero errors

**Day 12–13 — Vendor Dashboard: Product & Inventory Management UI** (Frontend, Design)
- Next.js 14+ vendor app with authenticated layout; login/register/protected routes
- Dashboard overview (sales summary, order count, product stats)
- Product management (list/create/edit/delete + validation); image upload UI drag-drop/preview/reorder
- Inventory management (stock levels, low-stock alerts, bulk update); variant management UI; vendor profile settings

**Day 14–15 — Phase 1 Integration Testing & Review** (Testing, Full Stack)
- End-to-end API contract validation (schemathesis or dredd against OpenAPI)
- Cross-app integration tests; fix all P0/P1 bugs; update AI_CONTEXT.md; code review; performance baseline
- Deploy Phase 1 to **staging environment**; Phase 1 retrospective
- *Testing:* zero contract violations; **90%+ backend coverage**; zero critical/high bugs; staging accessible; **QUALITY GATE: Phase 1 sign-off before proceeding**

### Page 3–4 — Phase 2 start (Commerce Engine, Days 16–30, 3 Weeks)

"Build the complete purchase flow: cart, checkout, payment processing with **DPO Pay**, mobile money, order lifecycle management. This phase makes Convergeo a functioning marketplace."

**Day 16–17 — Cart API: Add, Remove, Update & Persistence** (Backend, Testing)
- Cart model (user-associated + session-based for anonymous users); CartItem (product, variant, quantity, computed price)
- Cart API (add/remove/update/clear); subtotal, vendor-grouped items, stock validation
- Cart merge on login (anonymous → user cart); **cart persistence with Redis**; prevent adding out-of-stock items

**Day 18–19 — Address Model, Pickup Points & Delivery Zones** (Backend, Testing)
- Address model: street, city, province, landmark, GPS coordinates; user address CRUD (multiple saved, default selection)
- Pickup point model (location, hours, contact info); pickup listing & search API
- Delivery zone configuration (Lusaka zones, inter-city delivery); delivery fee calc by zone + vendor location; address validation & geocoding integration

**Day 20–22 — Payment Integration: DPO Pay, Mobile Money & Escrow** (Backend, Integration, Security)
- **DPO Pay** integration: token creation, payment redirect, callback handling
- Card payment flow (Visa, Mastercard via DPO Pay)
- Mobile money integration: **MTN MoMo, Airtel Money, Zamtel Kwacha**
- Payment abstraction layer (strategy pattern for multiple providers)
- Escrow system: hold funds until delivery confirmed
- Payment webhook handlers with idempotency and signature verification
- Transaction ledger: track all payment events; payment failure handling & retry logic
- *Testing:* DPO Pay sandbox card payment end-to-end; all three mobile-money providers in sandbox; escrow holds/doesn't release prematurely; webhook replay-attack prevention; ledger records all events

**Day 23–24 — Checkout Flow API: Address, Payment & Order Creation** (Backend, Testing)
- Checkout API (validate cart, select address/pickup, choose payment method)
- Order creation from cart (atomic transaction with stock decrement)
- Order model: items, vendor sub-orders, payment reference, delivery info
- Multi-vendor order splitting (one order, multiple vendor fulfillments); human-readable unique order number; post-checkout cart cleared; stock reservation (timeout-based release)

**Day 25–26 — Order Status Machine & Lifecycle Management** (Backend, Testing)
- Order state machine: **Placed → Confirmed → Processing → Shipped → Delivered → Completed**
- State transition validation (cannot skip/reverse); vendor order confirmation/rejection API; shipping update API (tracking, carrier)
- Delivery confirmation trigger (escrow release); order cancellation flow (refund logic by state); order history API; order event log (audit trail)

### Page 5–6 — Phase 2 continued & Phase 3 start

**Day 27–28 — Customer Checkout, Order Tracking & Payment UI** (Frontend, Design)
- Cart page UI; multi-step checkout (address/pickup → delivery → payment → confirmation)
- Payment method selection UI (card, MTN, Airtel, Zamtel); **DPO Pay redirect** integration; mobile money USSD prompt flow UI
- Order confirmation, order history w/ status timeline, order tracking detail

**Day 29–30 — Vendor Order Management & Phase 2 Integration Testing** (Frontend, Testing)
- Vendor order list UI (filter by status, date); order detail; confirmation/rejection with reason codes; shipping update form; fulfillment workflow (pick/pack/ship)
- Phase 2 end-to-end integration testing; API contract validation; retrospective
- *Testing:* full purchase flow (browse → cart → checkout → pay → confirm → ship); payment + escrow verified in sandbox; **QUALITY GATE: Phase 2 sign-off**

**PHASE 3 of 4 — Trust & Operations (Days 31–45, 3 Weeks).** "Build the systems that create trust between buyers and sellers: reviews, verification, admin oversight, notifications, and dispute resolution."

**Day 31–32 — Review & Rating System (Verified Purchases)** (Backend, Frontend)
- Review model: rating (1–5), text, images, verified-purchase flag
- Review CRUD (only purchasers of the product can review); vendor response API; product rating aggregation (average, distribution); review moderation flags (spam, inappropriate); customer review UI; vendor review management

**Day 33–34 — QR Code Pickup Verification & Delivery Tracking** (Backend, Integration)
- QR code generation for pickup orders (unique per order); QR scanning verification API (vendor/pickup-point scans confirm delivery)
- Delivery tracking model (status updates + timestamps); delivery confirmation triggers escrow release + order state update; customer QR display; vendor camera-based scanner UI; delivery timeline

**Day 35–36 — Admin Panel: Vendor Moderation & Product Approval** (Frontend, Backend)
- Next.js admin app with **role-based access (superadmin, moderator)**; admin auth with elevated permission checks
- Vendor management (list/view/approve/reject/suspend); KYC document review interface; product approval workflow UI; user management (suspend/ban); admin activity audit log

### Page 7–8 — Phase 3 continued

**Day 37–38 — Admin Analytics: Revenue, Commissions & Insights** (Backend, Frontend)
- Analytics API (total revenue, orders, active vendors, active customers, date ranges)
- **Commission calculation engine (per-vendor, per-category rates)**; revenue breakdown (platform commission vs vendor payouts)
- Admin dashboard KPI cards/charts; top vendors/products/categories; **CSV/Excel export**; vendor payout tracking & reconciliation
- *Testing:* commission calculations accurate **to the ngwee**

**Day 39–40 — Notification System: Email, SMS & In-App (Celery)** (Backend, Integration)
- **Celery + Redis** for async task processing
- Notification model (type, channel, recipient, content, read status)
- **Email notifications (SendGrid/Mailgun)**: order confirmation, shipping, OTP; SMS notifications; in-app notifications with real-time updates (**WebSocket or polling**)
- Notification preferences API (per event type); templates (DRY, translatable); Celery task monitoring + dead-letter queue

**Day 41–42 — WhatsApp Business API Integration** (Integration, Backend)
- WhatsApp Business API setup (**Meta Cloud API or BSP provider**)
- Message template approval (order confirmation, shipping, delivery); customer order update notifications; vendor new-order alerts; opt-in/opt-out flow; webhook handler for delivery receipts & replies; **fallback to SMS if WhatsApp fails**

**Day 43–44 — Dispute Resolution, Refunds & Escrow Release** (Backend, Frontend, Security)
- Dispute model (reason, evidence text+images, status, resolution); customer submission API; vendor response API; admin resolution workflow
- Refund processing (full/partial/escrow release to vendor); **automatic escrow release after dispute window expires (e.g., 7 days post-delivery)**; dispute UI (customer/vendor/admin); refund transaction logging & reconciliation

**Day 45 — Phase 3 Full Integration Testing & Review** (Testing, Full Stack)
- End-to-end journeys (buy, review, dispute, resolve); admin workflow testing; notification delivery verification; WhatsApp regression; API contract validation; deploy to staging + smoke tests
- *Testing:* **QUALITY GATE: Phase 3 sign-off**

### Page 9–11 — Phase 4 (Polish & Launch, Days 46–60, 3 Weeks)

"Harden, optimize, and ship. SEO, performance, security, automation, accessibility testing, the final production deployment. Zero shortcuts in the home stretch."

**Day 46–47 — SEO Optimization** (Frontend, Design)
- Next.js SSR/SSG (static categories, ISR product pages); dynamic meta tags per product/category; XML sitemap (products, categories, vendor stores); robots.txt; JSON-LD (Product, Organization, BreadcrumbList); canonical URLs + hreflang; OG + Twitter Card; Google Search Console + Bing Webmaster
- *Testing:* Lighthouse **SEO 95+**

**Day 48–49 — Performance Optimization** (Backend, DevOps)
- **Redis/Upstash caching layer** (product listings, category trees, search results); write-through/TTL invalidation
- **Django query optimization** (select_related, prefetch_related, eliminate N+1); DB indexing audit; API response compression (gzip/brotli); image WebP via Cloudinary; Next.js bundle optimization; CDN for static assets
- *Testing:* API p95 <200ms; homepage <2s on 3G; Lighthouse **Perf 90+**; cache hit >80%; no N+1 in **Django Debug Toolbar**

**Day 50–51 — Security Audit: OWASP Top 10, Rate Limiting & Hardening** (Security, Backend)
- OWASP Top 10 checklist; rate limiting on all endpoints (**django-ratelimit or DRF throttling**); input validation hardening; CSRF verification; XSS sanitization; SQLi parameterized-query audit; secure headers (HSTS, CSP, X-Frame-Options); dependency scan (pip-audit, npm audit); secrets management audit (all in env)
- *Testing:* penetration test — no OWASP Top 10 vulnerabilities

**Day 52–53 — n8n Automation: Onboarding, Notifications & Reports** (Integration, DevOps)
- **n8n self-hosted setup (Railway or Docker)**; vendor onboarding automation (welcome email sequence, doc reminders); order notification workflows; daily/weekly report generation; **abandoned cart recovery (email + WhatsApp)**; review request automation (post-delivery); **webhook integration between Django and n8n**; error monitoring & alert workflows

**Day 54–55 — Responsive Design Polish, Mobile-First & Accessibility** (Frontend, Design)
- Mobile-first responsive audit; touch-friendly interactions; **WCAG 2.1 AA** accessibility audit; ARIA labels/roles; focus management; loading/skeleton/empty states; error boundaries; cross-browser (Chrome, Firefox, Safari, Edge, Samsung Internet)
- *Testing:* usable at 320px; Lighthouse **A11y 95+**

### Page 12–13 — Phase 4 continued & Launch

**Day 56–57 — End-to-End Testing, Load Testing & Payment Sandbox** (Testing, DevOps)
- **Playwright E2E** (customer, vendor, admin journeys); **load testing with k6 or Locust: 100 concurrent users, 1000 requests/minute**; payment sandbox comprehensive testing (all methods, failure scenarios); stress test cart/checkout; API rate-limit verification under load; DB connection-pool testing
- *Testing:* **p99 <500ms under load**; all payment methods tested in sandbox; no data corruption under concurrency

**Day 58–59 — Staging Deployment, UAT & Final Bug Fixes** (DevOps, Testing)
- Full staging deployment: **backend (Railway), frontends (Vercel)**; env config audit (staging mirrors production); **UAT with 3–5 real testers**; P0/P1 bug fixes; data migration scripts tested; **monitoring setup: error tracking (Sentry), uptime (UptimeRobot), logs**; backup & recovery documented and tested

**Day 60 — Production Deployment, Monitoring & Launch** (DevOps, Full Stack)
- **Production deployment: backend to Railway, frontends to Vercel**; DNS + SSL verification; **production DB with connection pooling (PgBouncer)**; CDN + caching; **Sentry** production error tracking; **UptimeRobot** monitoring; log aggregation; launch checklist final verification; **DPO Pay production credentials activated**; final AI_CONTEXT.md update
- **Launch checklist:** all services healthy; SSL/TLS **A+ on SSL Labs**; **production payment flow verified (small real transaction)**; monitoring alerts firing; error tracking capturing; **backup scheduled + first backup completed**; "**CONVERGEO IS LIVE!**"

**Footer:** "Convergeo — 60-Day Development Roadmap · Built with discipline, shipped with confidence. Last updated: April 19, 2026 · Contract-First · One Module at a Time · Plan → Approve → Code → Validate"

---

## Extraction integrity notes

1. The PDF is image-based; all text above was read from rendered page images, not a machine text layer. Minor OCR-style transcription risk exists on small-font sub-bullets but headline facts (stack, providers, phase gates) are legible and high-confidence.
2. No PII, secrets, payment references, or customer/vendor data appear in this document — it is a generic engineering plan. Nothing required redaction.
3. Day-level checkbox/progress state in the PDF is the interactive tracker's default ("0% / NOT STARTED") and must **not** be read as a claim about production completion.

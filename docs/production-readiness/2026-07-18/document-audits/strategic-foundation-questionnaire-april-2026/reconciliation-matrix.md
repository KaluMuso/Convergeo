# Reconciliation Matrix — Strategic Foundation Questionnaire (April 2026) → Live Platform

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY · **Contract:** `../../foundation/document-audit-contract.md`
**Source document:** `source-document.md` (image-only PDF, 24 pp, transcribed visually) · **Facts:** `extracted-facts.json` (79)
**Live project:** `dpadrlxukcjbewpqympu` · **Prod (customer) SHA at audit:** `0b88723` (advanced from foundation baseline `8cc1fa0`)

## How to read this document

This is a **requirements/strategy document**, not a data document — it has no customer/vendor/order rows to match. Two structural facts drive every row:

1. **All 75 questionnaire questions are UNANSWERED** in the PDF. The document defines the *decision space*, not the decisions. The founder's actual answers were recorded separately as the **28 locked decisions** in `docs/plan/00-decisions.md` (D1–D28). Where a locked decision exists it is cited as **intent context** (rank-4 documentation), never as production proof.
2. Per the contract, **only live/applied evidence (rank 1–2) yields VERIFIED**; repository code (rank 3) yields at most PARTIAL; documentation (rank 4) alone is never VERIFIED.

**Evidence freshness:** live re-probes this session — n8n (2 active workflows), Cloudinary (`demo/`=60 assets), Vercel (customer app live, prod advancing). Supabase SQL + direct HTTP to `*.vergeo5.com` were **blocked by org egress policy** this session; DB/catalogue/RLS aggregates are cited from the **same-day** foundation snapshot (~3 h earlier) and labelled accordingly.

Legend: VERIFIED · PARTIAL · MISSING · CONFLICT · NOT_AUDITABLE. Money/security/identity/RLS/admin discrepancies are treated as **P0 until investigated**.

---

## A. Document-level facts

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F002 · Part 3 (all Q) | 75 strategic questions are **all unanswered** in this artifact | requirements | `docs/plan/00-decisions.md` (D1–D28) | questionnaire-answers | Decisions exist in `00-decisions.md` (rank-4), not in this PDF | CONFLICT | Artifact ≠ decision record; approvals not captured here | Auditors could mistake blank form for "undecided"; traceability gap | Treat `00-decisions.md` as the answer key; link questionnaire Q→D mapping; do not infer approval from this PDF |
| F001 · header/footer | v1.0, CONFIDENTIAL, April 2026, internal | requirements | planning docs | doc-title | Provenance only | NOT_AUDITABLE | n/a | n/a | Keep as source metadata |
| F003 · header stat | 60 days to MVP with working core commerce + 1 gateway | requirements | live orders/payments | mvp-timeline | Site live; **payments=0, orders=0** (foundation, same-day) | PARTIAL | "Working payments" not live-proven | MVP money-bar unmet for real-money launch | Prove one sandbox payment→ledger before claiming MVP complete |

---

## B. Part 1 — Business Plan Review (Applause / Caution / Realistic)

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F010 · Applause #1 | Multi-panel Customer/Vendor/Admin apps | requirements | `apps/customer\|vendor\|admin` | 3-app-topology | **Live this session:** Vercel `convergeo-customer/-vendor/-admin` all deployed; foundation confirms 3 origins (admin CF-Access-gated) | VERIFIED | — | Sound isolation; matches D20 | None (strength) |
| F011 · Applause #2 | Zambia-first single-country focus | requirements | ZMW-only scope | geo-scope | ZMW ngwee money model; Lusaka delivery focus; expansion not enabled | PARTIAL | Expansion consciously deferred | Aligned with strategy | None |
| F012 · Applause #3 | Hybrid pickup + delivery w/ QR verification | master | pickup tokens (mig 0017), `delivery_zones` | qr-pickup | Pickup-token schema + `delivery_zones`=3 (foundation); **0 orders** so unexercised | PARTIAL | No live pickup exercised | Trust/fraud control unproven | Drive one pickup order in sandbox; confirm QR+PIN issuance |
| F013 · Applause #4 | Third-party delivery integration (Yango/Bolt) | requirements | courier adapter | yango-integration | **D16 locks NO courier API v1** (manual admin dispatch); no Yango/Bolt code integration | MISSING | Applause credits an integration that does not exist | Doc overstates capability; ops is manual | Reconcile applause vs D16; track courier API as Phase-2 backlog |
| F014 · Applause #5 | Events & Tickets vertical (dynamic-QR) | master | `events/ticket_types/tickets` | events-vertical | Schema first-class (D24); **0 ticket rows**; ticket-issuance n8n workflow **absent** (live) | PARTIAL | No issued tickets; issuance automation missing | Paid tickets may never issue | Import/activate `tickets-issue` workflow; prove one issuance |
| F015 · Applause #6 | Directory + branch info + AI search | master | directory tab; Ask RAG; `vendor_locations` | directory-ai | Ask/RAG + directory scaffolding; `vendor_locations`=0; `ask_*` empty (foundation) | PARTIAL | No branch data; AI usage unexercised | Differentiator not populated | Seed vendor locations; smoke-test Ask quota path |
| F016 · Applause #7 | n8n workflow automation | operational | n8n workflows | n8n-automation | **Live this session:** exactly **2** active (notification dispatch; payment reconciliation). Registry lists ~18 | PARTIAL | Escrow release, tickets, onboarding, backups, digests absent | Core money/ops automation missing | Activate registry workflows w/ internal tokens; prove one tick each |
| F020 · Caution #1 | **Recommend Django + PostgreSQL** | requirements | `services/api` | backend-stack | Platform = **FastAPI + Supabase** (D18 explicitly overrides Django) | CONFLICT | Recommendation not followed (deliberate) | Low — both Python+Postgres; documented rationale | None; record D18 as ratified deviation |
| F021 · Caution #2 | 60-day full feature scope unrealistic; MVP only | requirements | live completeness | timeline-realism | Site live but money/observability/automation incomplete (foundation) | PARTIAL | Reality matches the caution | Confirms non-blocker scoping | Keep scoping to MVP; don't market full vision as live |
| F022 · Caution #3 | Don't build own gateway near-term | requirements | Lenco abstraction | own-gateway | Lenco-only + strategy-pattern seam (D11); no own gateway | VERIFIED | — | Correct capital posture | None (strength) |
| F023 · Caution #4 | Don't use 4 AI tools; pick one | requirements | commit authorship | ai-tooling | Commits authored by **both "Claude" and "Cursor Agent"** (Vercel meta, this session) | PARTIAL | 2 tools in use (not 4, not 1) | Consistency risk (minor) | Formalize primary/secondary tool split |
| F024 · Caution #5 | Define revenue model before code | requirements | `commission_rates`, `feature_flags` | revenue-model | D3/D4 decided; `commission_rates`=9 rows; `paid_tiers` flag=**false** (foundation) | PARTIAL | Paid-tier module dormant | Revenue live only via commission | Keep tiers flag-gated until threshold; verify rate values pre-launch |
| F030 · Realistic MVP | Payments via **Lenco/DPO** | operational | `payments`, Lenco adapter | lenco-dpo-payments | Platform = **Lenco ONLY** (DPO not integrated); `payments`=0 (foundation) | CONFLICT | DPO absent; no live payment | Doc implies redundancy that doesn't exist | Note Lenco-only decision; keep DPO as future seam |
| F031 · Realistic v1.0 | Yango API, events, vendor profiles, ad slots, n8n SMS/email | requirements | delivery/events/notifications | v1-scope | Notifications outbox + events schema present; **Yango API + ad slots MISSING** | PARTIAL | No courier API, no ad placement system | v1.0 scope partially unmet | Backlog Yango API + advertising module |
| F032 · Realistic v2.0 | AI search, analytics, B2B, multi-currency, RN app, ad dashboard | requirements | ask/search, analytics, `business_buyers` | v2-scope | AI search + B2B-lite schema present; **multi-currency + native app out of scope** | PARTIAL | v2 items partially designed | Forward-looking; not a launch blocker | Track as roadmap; multi-currency data seam (see F050) |

---

## C. Part 2 — Red Team preventions (each Prevention = a requirement)

| Source ref | Extracted fact (Prevention) | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F040 · RT#1 | Mobile money PRIMARY day one (MTN/Airtel/Zamtel) + USSD | requirements | Lenco MoMo; `zamtel_collections` flag | mobile-money-primary | MoMo (MTN/Airtel) designed via Lenco; `zamtel_collections` flag=false; **0 payments**; no USSD | PARTIAL | Zamtel not live; USSD absent; unproven | **P0** market-fit + money | Prove MoMo push in sandbox; confirm Zamtel plan (F9a); scope USSD |
| F041 · RT#2 | WhatsApp Business API commerce from v1.0 | requirements | WhatsApp Cloud API adapter | whatsapp-commerce | WhatsApp Cloud API is **notification-only** (D15); no in-WhatsApp browse/order/pay | PARTIAL | No WhatsApp commerce surface | Market-penetration gap | Scope WhatsApp order/track flow; keep official Cloud API |
| F042 · RT#3 | 5-min camera KYC, voice-to-text, instant tiered approval | master | `kyc_records`; onboarding | camera-kyc | `kyc_records` table present, **0 rows**; camera/voice/instant-tier not evidenced | PARTIAL | Advanced onboarding UX unverified | Vendor acquisition friction | Verify vendor onboarding flow live (login-gated); scope camera KYC |
| F043 · RT#4 | Retail-chain pickup network (Shoprite/Pick n Pay/Puma) | requirements | pickup network / partnerships | pickup-network | No retail pickup network; D16 = vendor-location + freight pickup only | MISSING | No partner pickup points | Convenience/coverage gap | Business partnership track; not a code item |
| F044 · RT#5 | **Escrow from LAUNCH**; release only after delivery confirm | operational | ledger escrow + auto-release workflow | escrow-launch | Escrow ledger **design** exists; **escrow auto-release n8n workflow MISSING** (live); prepaid→ledger unproven (`ledger_transactions`=0) | MISSING | Auto-release not operational; posting unproven | **P0** trust/money integrity | Sandbox-prove charge→hold→release; activate `release-job` workflow |
| F045 · RT#6 | 20–30% budget to content; partner creators | requirements | (marketing) | content-community | No platform surface | NOT_AUDITABLE | n/a | Growth (business) | Track in marketing plan |
| F046 · RT#7 | PWA + offline browse + SMS/USSD order fallback; 2G/3G-first | requirements | `apps/customer` PWA (serwist) | pwa-offline | PWA (serwist) + 360px/3G perf budgets present; **offline-browse/USSD-order not evidenced** | PARTIAL | Offline commerce + USSD absent | Peri-urban/rural reach | Test PWA offline caching live; scope USSD fallback |
| F047 · RT#8 | Launch with English + Bemba + Nyanja; voice search 6mo | requirements | `packages/i18n`; `translation_overrides` | vernacular-launch | **D27 = launch English-only** + i18n scaffolding; `translation_overrides` (0053) **MISSING on live**; no voice search | CONFLICT | Launch-language rec not met; migration drift | Market-inclusivity gap | Apply 0053; prioritize Bemba/Nyanja copy; reconcile RT#8 vs D27 |
| F048 · RT#9 | Fastest Lenco settlement; float-based instant payout | operational | `payouts`; Lenco payout | instant-settlement | D5 promises MoMo payout ≤5 min; `payouts`=0; no float system | PARTIAL | Settlement speed unproven; no float | Vendor retention (paycheck-to-paycheck) | Prove one payout in sandbox; evaluate float capital later |
| F049 · RT#10 | Analytics from day one; recommendation-engine early | operational | `analytics_events`/`funnel_events` | analytics-day-one | Tables exist, **0 rows**; **PRs #275–277 (analytics wiring) merged this session** | PARTIAL | Streams empty; personalization absent | Conversion/observability | Verify event streams populate post-wiring; then build recs |
| F050 · RT#11 | Multi-currency + cross-border in **data model** (don't enable) | requirements | money model | multi-currency-model | Money model is **ZMW-ngwee only**; no multi-currency seam evidenced | CONFLICT | Data-model rec not adopted | Future cross-border friction | Decide whether to add currency dimension now vs later migration |
| F051 · RT#12 | Engage legal NOW; data-protection/e-txn/VAT/dispute in architecture | requirements | DPA; `invoices`; `disputes` | regulatory-compliance | ZRA invoice seam + `disputes` schema + Zambia-DPA guardrail present; **legal review = F4 gate (PENDING)** | PARTIAL | No legal sign-off; compliance not verifiable | **P0** regulatory (fines/suspension risk) | Do NOT infer compliance; complete F4 counsel review before real-money |
| F052 · RT#13 | Consented vendor sales tracking; MFI partnerships | requirements | sales export/consent | vendor-financing | No MFI integration / consented-share feature | MISSING | Feature absent | Vendor growth (roadmap) | Backlog; requires consent + data-share design |
| F053 · RT#14 | Add airtime top-up + bill payments (super-app) | requirements | bill-pay/airtime | super-app-utility | No airtime/bill-pay features (out of v1 scope) | MISSING | Feature absent | Daily-usage/retention | Roadmap (aligns Q75-C vision) |
| F054 · RT#15 | Launch MVP in 30 days; pre-onboard 50–100 **real** vendors | master | `vendors` (real vs demo) | pre-onboard-vendors | **3 DEMO vendors, 0 real**; `public_launch` flag=false (foundation) | PARTIAL | No real vendor supply | Cold-start risk unmitigated | Vendor pre-onboarding drive before public_launch flip |

---

## D. Part 3 — Strategic Questionnaire (de-facto platform state vs each open question)

> Every Q is UNANSWERED in the PDF. "Production evidence" reflects the platform's **de-facto** resolution (+ the locked decision, cited as intent). Status reflects whether the platform has resolved and *proven* the item — not whether the founder "chose correctly."

### Business Model & Revenue (Q1–Q8)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F060 · Q1 | Revenue model | requirements | `commission_rates`, `feature_flags` | q1-revenue | D3 free-to-list + commission; `paid_tiers`=false | PARTIAL | Tiers dormant | Revenue mix | Confirm launch = commission-only |
| F061 · Q2 | Commission rate range | requirements | `commission_rates` | q2-commission | D4 variable-by-category; `commission_rates`=9 rows (foundation) | PARTIAL | Exact bps not dumped (privacy) | Vendor economics | Verify rate values vs D4 in a scoped read |
| F062 · Q5 | Events monetization | requirements | `commission_rates`(tickets) | q5-events-monetize | D4 tickets 5% / free events 0%; 0 ticket rows | PARTIAL | Unexercised | Events revenue | Prove ticket fee on first sale |
| — · Q3,Q4,Q6,Q7,Q8 | Chicken-egg, ad model, delivery charge, capital, break-even | requirements | (business/strategy) | q3-8-business | No platform surface (Q4 ad model → no ad system live) | NOT_AUDITABLE | n/a | Business planning | Record answers in `00-decisions.md` |

### Technology & Architecture (Q9–Q18)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F063 · Q9 | Backend stack (Django rec) | requirements | `services/api` | q9-backend | **FastAPI + Supabase** (D18 overrides Django) | CONFLICT | Rec not followed (deliberate) | Low | Record D18 |
| F064 · Q10 | Frontend (Next.js rec) | requirements | `apps/*` | q10-frontend | Next.js 15 App Router × 3 apps | VERIFIED | — | — | None |
| F065 · Q11 | Hosting | requirements | Vercel/OCI/Supabase/CF | q11-hosting | D21 hybrid (Vercel + OCI + Supabase + Cloudflare) | PARTIAL | Not a single listed option | Ops/cost | None (documented) |
| F066 · Q12 | Panel architecture (shared-API rec) | requirements | monorepo + FastAPI | q12-architecture | Matches Q12-D + D20 | VERIFIED | — | — | None |
| F067 · Q13 | Primary AI tool | requirements | commit authorship | q13-ai-tool | Claude + Cursor both authoring | PARTIAL | No single primary | Consistency | Formalize choice |
| F068 · Q15 | Search infra | master | `search_documents`, pgvector | q15-search | Postgres FTS + pg_trgm + pgvector (RRF); `search_documents`=288, `embedding_jobs`=288 | VERIFIED | — | — | None (strength) |
| F069 · Q16 | Media | documents | Cloudinary + Supabase Storage | q16-media | **Cloudinary `demo/`=60 assets live (this session)**; `listing_images`=134; D26 | VERIFIED | — | — | See demo-cleanup (F110) |
| F070 · Q17–Q18 | Caching (Redis+CDN rec) / tasks (Celery+n8n rec) | requirements | cache/task runner | q17-18-infra | Cloudflare CDN + n8n present; **no Celery/Redis queue** evidenced (outbox+n8n) | PARTIAL | No code-level task queue | Recs partially met | Confirm whether Celery is intended; else record deviation |

### Payments & Financial (Q19–Q26)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F071 · Q19 | Primary gateway | operational | Lenco adapter; `payments` | q19-gateway | Lenco only (D11); DPO absent; `payments`=0 | PARTIAL | No live payment; no DPO | **P0** money | Sandbox-prove Lenco; keep DPO seam |
| F072 · Q20 | Mobile money criticality | operational | Lenco MoMo | q20-momo | MoMo core; 0 payments | PARTIAL | Unproven | **P0** | See F040 |
| F073 · Q21 | Settlement | operational | `payouts` | q21-settlement | D5 release-on-confirm/48h; `payouts`=0; release workflow missing | PARTIAL | Not operational | **P0** vendor money | See F044/F048 |
| F074 · Q22 | Escrow (full-escrow rec) | operational | ledger escrow legs | q22-escrow | Design present; auto-release **MISSING**; posting unproven | MISSING | Escrow not operational | **P0** trust/money | See F044 |
| F075 · Q23 | Multi-currency | requirements | money model | q23-currency | ZMW-only ngwee | VERIFIED | — | — | None (but see F050 seam) |
| F076 · Q24 | VAT on fees | requirements | `invoices`, VAT flag | q24-vat | D13 Turnover Tax; VAT flag OFF; `invoices`=0 | PARTIAL | Invoicing unexercised | Tax compliance | Prove ZRA sequence on first order |
| F077 · Q25 | COD | requirements | `platform_config` | q25-cod | D12 COD ≤K500 (pending F8 confirm); `platform_config`=16 keys | PARTIAL | Cap value not verified; founder confirm open | Fraud exposure | Confirm F8; read COD cap value (scoped) |
| F078 · Q26 | Long-term gateway vision | requirements | `wallet` flag; abstraction | q26-gateway-vision | `wallet` flag=false; abstraction seam present | PARTIAL | Wallet dormant | Roadmap | None |

### Customer Experience & UX (Q27–Q34)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F079 · Q27 | Launch languages | requirements | `packages/i18n` | q27-languages | D27 launch English-only + scaffolding; `translation_overrides` MISSING on live | CONFLICT | RT#8 rec (EN+Bemba+Nyanja) unmet | Inclusivity | Apply 0053; prioritize local copy |
| F080 · Q29 | Registration/login | master | Supabase Auth | q29-auth | Phone OTP + email + Google; `send-sms-otp` edge fn | VERIFIED | — | — | None |
| F081 · Q30 | Homepage priority | requirements | `merch_slots` | q30-homepage | `merch_slots`=1; merch manager exists | PARTIAL | Minimal merch config | Conversion | Populate merch; verify live homepage |
| F082 · Q31 | AI search at launch | master | Ask RAG; pgvector | q31-ai-search | pgvector + Ask RAG (Q31-C); `ask_*` empty | PARTIAL | AI unexercised | Discovery | Smoke-test Ask quota + kill-switch |
| F083 · Q32 | Reviews depth | operational | `reviews` | q32-reviews | Verified-purchase + photos design; `reviews`=0 | PARTIAL | No reviews | Trust | Exercise after first order |
| F084 · Q33 | QR pickup | master | pickup tokens | q33-qr-pickup | D16 QR+PIN (Q33-C); schema via 0017; 0 orders | PARTIAL | Unexercised | Fraud control | See F012 |
| F085 · Q34 | Mobile app (PWA rec) | requirements | `apps/customer` PWA | q34-pwa | PWA (serwist) = Q34-A | VERIFIED | — | — | None |

### Vendor Experience & B2B (Q35–Q42)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F086 · Q35–Q36 | Onboarding time / KYC docs | master | `kyc_records` | q35-36-onboarding | `kyc_records`=0; tiered ID+PACRA implied | PARTIAL | Onboarding unexercised | Acquisition | Verify vendor KYC flow (login-gated) |
| F087 · Q37 | B2B wholesale | master | `business_buyers`; tier pricing | q37-b2b | D24 wholesale + price_tiers + moq; `business_buyers`=0 | PARTIAL | No B2B buyers | B2B revenue | Exercise B2B-lite tier pricing |
| F088 · Q40 | Vendor↔customer messaging | requirements | messaging | q40-messaging | No messaging table/route confirmed in foundation | NOT_AUDITABLE | Unknown | Off-platform leakage risk | Scoped check for messaging module |
| F089 · Q41 | Vendor competition/comparison | master | canonical products | q41-comparison | D24 canonical + "N vendors" comparison (Q41-D); products=150, listings=134 | VERIFIED | — | Differentiator | None (strength) |
| — · Q38,Q39,Q42 | Vendor analytics / inventory / About-Us | master | vendor dashboard | q38-42-vendor | Login-gated vendor UI; analytics tables empty | PARTIAL | Data-thin | Vendor UX | Verify vendor dashboard live |

### Logistics & Delivery (Q43–Q48)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F090 · Q43–Q44 | Delivery providers / coverage | requirements | `delivery_zones`; courier | q43-44-delivery | D16 Lusaka manual dispatch + nationwide pickup; `delivery_zones`=3; **no courier API v1** | PARTIAL | No integrated courier | Coverage/scale | Backlog courier API (Phase 2) |
| F091 · Q48 | Returns & exchanges | operational | `returns`, `disputes` | q48-returns | D17 lanes defined; `returns`/`disputes`=0; manual reverse logistics | PARTIAL | Unexercised | Buyer protection | Exercise return lane after first order |
| — · Q45–Q47 | Delivery by type / same-day / tracking | requirements | delivery/notifications | q45-47-delivery | Status-update notifications via outbox; GPS/same-day not evidenced | PARTIAL | Rich tracking absent | UX | Roadmap |

### Events, Tickets & Services (Q49–Q53)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F092 · Q49–Q50 | Event types / digital tickets | master | `events/ticket_types/tickets` | q49-50-events | First-class (D24) + dynamic-QR; 0 ticket rows; ticket-issue workflow MISSING | PARTIAL | No issuance | Events money path | See F014 |
| F093 · Q51 | Service bookings (RFQ) | master | `services/jobs/job_quotes` | q51-services | D2 RFQ-only (Q51-D), no calendar v1; `services`=1, jobs/quotes=0 | PARTIAL | Unexercised | Services vertical | Exercise RFQ→quote→escrow |
| F094 · Q52 | Location/tourism | requirements | tourism feature | q52-tourism | No tourism feature evidenced (Phase 3 per research) | NOT_AUDITABLE | Absent | Roadmap | Backlog |
| F095 · Q53 | Directory prominence | master | directory tab | q53-directory | Directory in scope; prominence not live-verified (UI) | PARTIAL | Unverified UI | Discovery | Verify directory tab live |

### Marketing / Legal / Ops / Automation / Competition (Q54–Q75)

| Source ref | Open decision | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F096 · Q60–Q62 | Registration / data-protection / dispute-resolution | requirements | `disputes`; DPA; PACRA/TPIN | q60-62-legal | `disputes` schema (0 rows); DPA guardrail; **legal = F2/F4 business gates** | NOT_AUDITABLE | Compliance not verifiable | **P0** regulatory | Do not infer compliance; complete F4 |
| F097 · Q63 | Team (solo + AI) | requirements | (org) | q63-team | CLAUDE.md "solo founder + AI" (rank-4) | NOT_AUDITABLE | n/a | — | Record in decisions |
| F098 · Q64 | Customer support | requirements | support WhatsApp | q64-support | `NEXT_PUBLIC_SUPPORT_WHATSAPP` env name present; AI chatbot support not evidenced | PARTIAL | Chatbot absent | Support ops | Confirm support channel live |
| F099 · Q65 | Weekly health metrics | operational | admin dashboard; analytics | q65-metrics | Admin dashboard UI exists; analytics/funnel=0 rows | PARTIAL | No metric data | Observability | See F049 |
| F100 · Q66 | n8n automate FIRST | operational | n8n; `notification_outbox` | q66-n8n-first | Live n8n = dispatch + payment recon only | PARTIAL | Onboarding/marketing automation missing | Ops coverage | See F016 |
| F101 · Q67–Q69 | AI beyond search / n8n connections / AI advantage | requirements | Ask RAG; SMS/WhatsApp | q67-69-ai | Ask RAG + SMS(AT)+WhatsApp adapters; fraud/price AI, visual/voice search absent | PARTIAL | Advanced AI absent | Differentiator | Roadmap |
| F102 · Q70 | Virtual try-on / AR | requirements | AR feature | q70-ar | Absent (Part 1 flags as Phase 3+ wishful) | MISSING | Absent by design | Correct for MVP | None |
| F103 · Q71–Q75 | Competitor / differentiator / expansion / investment / 5yr | requirements | (strategy) | q71-75-strategy | No platform surface | NOT_AUDITABLE | n/a | Strategy | Record in decisions |
| — · Q54–Q59 | Pre-launch marketing / incentives / targets / brand / content | requirements | (marketing) | q54-59-marketing | No platform surface (referral OUT of v1 per R6) | NOT_AUDITABLE | n/a | Growth | Record in decisions |

---

## E. Cross-cutting reality checks (surfaced by the document's implicit assumptions)

| Source ref | Extracted fact (implied) | Data class | Location | Key | Production evidence | Status | Gap | Impact | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F110 · Applause#5 + Q30/Q50 | Production presents a real marketplace catalogue | master | `vendors`, `vendor_listings`, `listing_images`, catalog API | demo-catalogue | **3 DEMO vendors + 134 demo listings + 134 `demo/` images**; public catalog `total=134`; Cloudinary `demo/`=60 assets (this session). D25 intended demo **excluded from public search** | CONFLICT | Demo data is publicly served vs D25 intent | Misleading UX / SEO / trust for real-money launch | Gate behind `public_launch`; label/replace demo before real launch |
| F111 · RT#5/#9 + Q21/Q22 | Escrow + settlement money paths operate in prod | operational | `payments`, `ledger_transactions`, `payouts`, `webhook_events` | money-ops-live | **0 payments / 0 ledger txns / 0 payouts / 0 webhook_events** (foundation, same-day). Code-only; unproven | PARTIAL | No live money proof | **P0** money integrity | Sandbox-prove full charge→hold→release→payout chain |

---

## F. Status tally (79 atomic facts)

| Status | Count | Notes |
| --- | --- | --- |
| VERIFIED | 10 | 3-app topology, Next.js, shared-API arch, search infra, media, ZMW-only, phone-OTP auth, PWA, comparison model, no-own-gateway |
| PARTIAL | 47 | Designed/scaffolded but unexercised, data-thin, or code-only (dominant pattern — demo platform w/ 0 money ops) |
| CONFLICT | 8 | Django-vs-FastAPI, Lenco-vs-Lenco/DPO, launch-language, multi-currency data model, demo-public-vs-D25, unanswered-questionnaire-vs-decisions, plus derived |
| MISSING | 7 | Escrow auto-release, Yango courier API, retail pickup network, vendor financing, super-app utility, AR, (features absent) |
| NOT_AUDITABLE | 7 | Pure business/marketing/legal strategy with no platform surface, or blocked access |

See `missing-and-conflicting-items.md` for the grouped defect list, `remediation-backlog.md` for actionable items, and `safe-query-log.md` for evidence provenance.

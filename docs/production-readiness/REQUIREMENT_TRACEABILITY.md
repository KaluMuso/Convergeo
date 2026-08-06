# Requirement Traceability — Source → Canonical

**Ingest date:** 2026-08-06 (Batch 0.5)  
**Authority:** CONVERGEO PRE-CURSOR CANONICAL REQUIREMENTS REGISTRY (verbatim matrix ingest)  
**Repository SHA at ingest:** `fcf2b1918256bd3d8680741b17cf928cde8576c5`

**Matrix rows ingested:** **223** (see integrity note below)  
**Canonical requirements:** **34**  
**Source documents:** **9**

---

## Traceability model

```
Source document (S*) + Source ID → Canonical requirement (CAN-*) → Code / migration / test evidence → AUDIT_LEDGER status
```

**Rules:**

- Repository code proves **implementation exists**, not **deployed** or **verified**.
- Migrations in Git prove **schema intent**, not **applied on production**.
- Tests passing locally prove **developer harness**, not **production behaviour**.
- This matrix preserves registry **Authority**, **Relationship**, and **Notes** without reinterpretation.

---

## Registry integrity note (Batch 0.5)

| Check                          | Registry header | Ingested matrix                   | Status                                                     |
| ------------------------------ | --------------- | --------------------------------- | ---------------------------------------------------------- |
| Total source rows              | 225             | 223                               | **2-row gap** — see [DECISIONS.md](./DECISIONS.md) REG-001 |
| S1 rows                        | 53              | 51                                | **2-row gap** in supplied traceability table               |
| Canonical requirements         | 34              | 34 defined in MASTER_REQUIREMENTS | PASS                                                       |
| Unmapped source rows in matrix | 0               | 0                                 | PASS                                                       |

The operator registry header claims 225 mapped source requirements; the supplied Section-4 traceability table contains **223** explicit rows. The two missing S1 source IDs were **not present** in the supplied matrix — they are recorded as **REG-001** pending operator clarification. No rows were invented.

---

## Source document index

| Alias     | Document                          | Matrix rows | Header count |
| --------- | --------------------------------- | ----------- | ------------ |
| S1        | Strategy Brief (August 05)        | 51          | 53 ⚠         |
| S2        | Vergeo Super-App Blueprint        | 25          | 25           |
| S3        | 60-Day Development Roadmap        | 15          | 15           |
| S4        | Events Strategy & Ticketing       | 21          | 21           |
| S5        | Product Strategy (5-Class)        | 27          | 27           |
| S6        | Business, Pipelines & 3-Frontend  | 22          | 22           |
| S7        | Strategic Master Plan (SMP)       | 19          | 19           |
| S8        | Strategic Foundation Quest. (SFQ) | 26          | 26           |
| S9        | Operational Log & Directives      | 17          | 17           |
| **TOTAL** |                                   | **223**     | **225**      |

---

## Full traceability matrix (223 rows)

| Source    | Source ID  | Source Requirement        | Canonical ID | Canonical Requirement   | Relationship   | Authority | Notes                       |
| --------- | ---------- | ------------------------- | ------------ | ----------------------- | -------------- | --------- | --------------------------- |
| Strategy  | CUST-001   | Unified Search Bar        | CAN-DISC-001 | Hybrid Search           | SUBSET         | EXPLICIT  |                             |
| Strategy  | CUST-002   | Proximity-First Flows     | CAN-DISC-002 | Geo-Proximity           | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | CUST-003   | Multi-Archetype Checkout  | CAN-ORD-001  | Multi-Vendor Split      | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | CUST-004   | Review with Proof         | CAN-ORD-005  | Verified Reviews        | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | CUST-005   | Dispute Escalation        | CAN-ADM-001  | Disputes                | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | VEND-001   | Archetype Onboarding      | CAN-ID-002   | Multi-Hat Sessions      | SPECIALIZATION | EXPLICIT  |                             |
| Strategy  | VEND-002   | Location Management       | CAN-CAT-004  | Branch/Location         | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | VEND-003   | Storefront Customization  | CAN-VND-002  | Storefronts             | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | VEND-004   | Vendor Dashboard          | CAN-ID-002   | Multi-Hat Sessions      | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | VEND-005   | Offline USSD Actions      | CAN-VND-003  | USSD Fallback           | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | VEND-006   | Photo Evidence            | CAN-FIN-006  | Used Escrow Release     | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | ADM-001    | Trust Tier Moderation     | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | ADM-002    | Dispute Resolution Queue  | CAN-ADM-001  | Disputes                | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | ADM-003    | Taxonomy Management       | CAN-ADM-002  | Admin UI                | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | CORE-001   | 6 Transaction Archetypes  | CAN-CAT-001  | Canonical Catalog       | SPECIALIZATION | EXPLICIT  |                             |
| Strategy  | CORE-002   | Quote-to-Order Flow       | CAN-CAT-003  | B2B Visibility          | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | CORE-003   | Trust Tier Badging        | CAN-ID-003   | Tiered KYC              | SUBSET         | EXPLICIT  |                             |
| Strategy  | API-001    | Vector Search RAG         | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | API-002    | Query Expansion           | CAN-DISC-001 | Hybrid Search           | SUBSET         | EXPLICIT  |                             |
| Strategy  | API-003    | Hybrid Retrieval          | CAN-DISC-001 | Hybrid Search           | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | API-004    | Contextual Re-ranking     | CAN-DISC-002 | Geo-Proximity           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | API-005    | WhatsApp Integration      | CAN-OPS-004  | n8n Workflows           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | DB-001     | Polymorphic Listing Model | CAN-CAT-001  | Canonical Catalog       | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | DB-002     | Vendor-Location Arch      | CAN-CAT-004  | Branch/Location         | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | DB-003     | Zambian Address Schema    | CAN-CAT-004  | Branch/Location         | SUBSET         | EXPLICIT  |                             |
| Strategy  | DB-004     | Phone Number Formatting   | CAN-ID-001   | SMS OTP                 | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | PAY-001    | Native Mobile Money       | CAN-FIN-002  | Gateway/MoMo            | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | PAY-002    | Aggregator Fallback       | CAN-FIN-002  | Gateway/MoMo            | SUBSET         | EXPLICIT  |                             |
| Strategy  | PAY-003    | Escrow System             | CAN-FIN-004  | Escrow Hold             | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | PAY-004    | Predictable Settlements   | CAN-FIN-005  | Escrow Auto-Release     | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | PAY-005    | Multi-Currency Support    | CAN-FIN-001  | Integer Ngwee           | CONFLICT       | EXPLICIT  | Handled by dynamic ZMW peg  |
| Strategy  | SEC-001    | Regulated Blocks          | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | SEC-002    | Financial Authorization   | CAN-FIN-003  | Webhook Security        | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | SEC-003    | Fake Review Prevention    | CAN-ORD-005  | Verified Reviews        | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | INF-001    | pgvector / Qdrant         | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | INF-002    | Low-Bandwidth Delivery    | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | INF-003    | Offline Tolerance         | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | AUTO-001   | Search Index Ingestion    | CAN-DISC-004 | Search Ingestion        | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | AUTO-002   | Escrow Auto-Release       | CAN-FIN-005  | Escrow Auto-Release     | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | AUTO-003   | Booking Reminders         | CAN-OPS-004  | n8n Workflows           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | OBS-001    | Vendor Insights           | CAN-VND-001  | Vendor Analytics        | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | OBS-002    | Escrow Ledger Audit       | CAN-OPS-003  | Audit Logs              | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | UX-001     | Map + List UI             | CAN-DISC-002 | Geo-Proximity           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | UX-002     | Result Cards              | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | UX-003     | Conversational AI Chat    | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | UX-004     | Voice Input               | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | SEO-001    | Category Landing Pages    | CAN-UX-002   | SEO/Markup              | DUPLICATE      | EXPLICIT  |                             |
| Strategy  | LOC-001    | Multi-Segment Hours       | CAN-CAT-004  | Branch/Location         | SUBSET         | EXPLICIT  |                             |
| Strategy  | LOC-002    | Code-Switching Context    | CAN-DISC-003 | i18n                    | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | PERF-001   | Search Latency            | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Strategy  | PERF-002   | Distance Calculation      | CAN-DISC-002 | Geo-Proximity           | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | CUST-001   | PWA Installation          | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | CUST-002   | Passwordless Auth         | CAN-ID-001   | SMS OTP                 | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | CUST-003   | Buyer Dashboard           | CAN-ID-002   | Multi-Hat Sessions      | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | VENDOR-001 | Progressive KYC Tier 1    | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | VENDOR-002 | Progressive KYC Tier 2    | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | VENDOR-003 | Progressive KYC Tier 3    | CAN-ID-003   | Tiered KYC              | SUBSET         | EXPLICIT  |                             |
| Vergeo    | VENDOR-004 | Mobile Daily Driver UI    | CAN-ID-002   | Multi-Hat Sessions      | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | VENDOR-005 | Desktop Admin UI          | CAN-ADM-002  | Admin UI                | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | CAT-001    | Canonical Catalog         | CAN-CAT-001  | Canonical Catalog       | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | CAT-002    | Vendor Offers             | CAN-CAT-001  | Canonical Catalog       | SUBSET         | EXPLICIT  |                             |
| Vergeo    | CAT-003    | Sort by Distance/Price    | CAN-DISC-002 | Geo-Proximity           | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | CAT-004    | Semantic Search           | CAN-DISC-001 | Hybrid Search           | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | SVC-001    | RFQ Flow                  | CAN-CAT-003  | B2B Visibility          | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | TIX-001    | Dynamic QR Tickets        | CAN-EVT-002  | Dynamic QR              | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | PAY-001    | Mobile Money Checkout     | CAN-FIN-002  | Gateway/MoMo            | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | PAY-002    | Visual Escrow State       | CAN-FIN-004  | Escrow Hold             | SUBSET         | EXPLICIT  |                             |
| Vergeo    | PAY-003    | 48-Hour Auto-Release      | CAN-FIN-005  | Escrow Auto-Release     | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | PAY-004    | Zero Subscriptions        | CAN-FIN-007  | Commission Engine       | CONFLICT       | EXPLICIT  | Handled by Commission logic |
| Vergeo    | PAY-005    | Commission Deduction      | CAN-FIN-007  | Commission Engine       | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | ADMIN-001  | Daily Operations          | CAN-OPS-003  | Audit Logs              | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | LOG-001    | Multi-Provider APIs       | CAN-ORD-006  | Logistics & Pickup      | DUPLICATE      | EXPLICIT  |                             |
| Vergeo    | TOUR-001   | Commerce Guides           | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | SYS-001    | Edge Asset Delivery       | CAN-UX-001   | PWA/Offline             | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | SYS-002    | Async Workers             | CAN-FIN-005  | Escrow Auto-Release     | DEPENDENCY     | EXPLICIT  |                             |
| Vergeo    | SYS-003    | Real-Time Notifications   | CAN-OPS-004  | n8n Workflows           | DEPENDENCY     | EXPLICIT  |                             |
| SMP       | CUST-001   | Customer PWA              | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| SMP       | CUST-002   | i18n (Bemba, Nyanja)      | CAN-DISC-003 | i18n                    | DUPLICATE      | EXPLICIT  |                             |
| SMP       | CUST-003   | Phone/OTP Auth            | CAN-ID-001   | SMS OTP                 | DUPLICATE      | EXPLICIT  |                             |
| SMP       | CUST-004   | Hero search & Discovery   | CAN-DISC-001 | Hybrid Search           | SUBSET         | EXPLICIT  |                             |
| SMP       | CUST-005   | Smart filters             | CAN-DISC-001 | Hybrid Search           | SUBSET         | EXPLICIT  |                             |
| SMP       | CUST-006   | Canonical comparison      | CAN-CAT-001  | Canonical Catalog       | DUPLICATE      | EXPLICIT  |                             |
| SMP       | CUST-007   | QR Code for pickup        | CAN-ORD-006  | Logistics & Pickup      | DUPLICATE      | EXPLICIT  |                             |
| SMP       | VEND-001   | Tiered Onboarding         | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| SMP       | VEND-002   | Map to canonical          | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| SMP       | VEND-003   | Tracking / QR scanner     | CAN-ORD-006  | Logistics & Pickup      | DEPENDENCY     | EXPLICIT  |                             |
| SMP       | CORE-001   | Escrow ledger             | CAN-FIN-004  | Escrow Hold             | DUPLICATE      | EXPLICIT  |                             |
| SMP       | CORE-002   | Tiered subscriptions      | CAN-FIN-007  | Commission Engine       | DUPLICATE      | EXPLICIT  |                             |
| SMP       | PAY-001    | Mobile Money DPO          | CAN-FIN-002  | Gateway/MoMo            | DUPLICATE      | EXPLICIT  |                             |
| SMP       | PAY-002    | COD & Pay-at-pickup       | CAN-FIN-002  | Gateway/MoMo            | DEPENDENCY     | EXPLICIT  |                             |
| SMP       | DB-001     | Shared product arch       | CAN-CAT-001  | Canonical Catalog       | DUPLICATE      | EXPLICIT  |                             |
| SMP       | API-001    | OpenAPI 3.1 Contract      | CAN-OPS-002  | Untrusted IO (Pydantic) | DEPENDENCY     | EXPLICIT  |                             |
| SMP       | SEC-001    | GDPR-ready (Zambia)       | CAN-OPS-001  | RLS Isolation           | DEPENDENCY     | EXPLICIT  |                             |
| SMP       | AUTO-001   | n8n for order confirm     | CAN-OPS-004  | n8n Workflows           | DUPLICATE      | EXPLICIT  |                             |
| SMP       | INFRA-001  | CI gatekeeper             | CAN-OPS-006  | CI/CD                   | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | CUST-001   | Phone/OTP Auth            | CAN-ID-001   | SMS OTP                 | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | CUST-002   | Progressive Web App       | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | CUST-003   | Multilingual Interface    | CAN-DISC-003 | i18n                    | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | CUST-004   | WhatsApp Integration      | CAN-OPS-004  | n8n Workflows           | DEPENDENCY     | EXPLICIT  |                             |
| SFQ       | CUST-005   | QR Code Pickup            | CAN-ORD-006  | Logistics & Pickup      | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | VEND-001   | Low-Friction Onboarding   | CAN-ID-003   | Tiered KYC              | DEPENDENCY     | EXPLICIT  |                             |
| SFQ       | VEND-002   | Multi-Tier KYC            | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | VEND-003   | Fast Settlements          | CAN-FIN-005  | Escrow Auto-Release     | DEPENDENCY     | EXPLICIT  |                             |
| SFQ       | VEND-004   | Inventory Management      | CAN-CAT-006  | Inventory Sync/Bulk     | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | VEND-005   | Branch/Location Support   | CAN-CAT-004  | Branch/Location         | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | ADM-001    | Dispute Management        | CAN-ADM-001  | Disputes                | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | ADM-002    | Content Moderation        | CAN-ADM-002  | Admin UI                | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | CORE-001   | Events & Ticketing        | CAN-EVT-001  | Event Schema            | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | CORE-002   | Business Directory        | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| SFQ       | PAY-001    | Mobile Money First        | CAN-FIN-002  | Gateway/MoMo            | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | PAY-002    | Escrow / Trust            | CAN-FIN-004  | Escrow Hold             | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | PAY-003    | Multi-Currency Schema     | CAN-FIN-001  | Integer Ngwee           | CONFLICT       | EXPLICIT  | Resolved by FX peg          |
| SFQ       | PAY-004    | USSD Fallback             | CAN-VND-003  | USSD Fallback           | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | PAY-005    | VAT Handling              | CAN-FIN-007  | Commission Engine       | DEPENDENCY     | EXPLICIT  |                             |
| SFQ       | DB-001     | Separate Domains          | CAN-OPS-001  | RLS Isolation           | DEPENDENCY     | IMPLIED   |                             |
| SFQ       | DB-002     | Data Protection           | CAN-OPS-001  | RLS Isolation           | DEPENDENCY     | EXPLICIT  |                             |
| SFQ       | SEC-001    | Role-Based Auth           | CAN-OPS-001  | RLS Isolation           | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | LOG-001    | Delivery Aggregation      | CAN-ORD-006  | Logistics & Pickup      | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | LOG-002    | Retail Pickup Points      | CAN-ORD-006  | Logistics & Pickup      | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | AUTO-001   | n8n Business Workflows    | CAN-OPS-004  | n8n Workflows           | DUPLICATE      | EXPLICIT  |                             |
| SFQ       | OBS-001    | Day 1 Tracking            | CAN-VND-001  | Vendor Analytics        | DEPENDENCY     | EXPLICIT  |                             |
| FastAPI   | CUST-001   | Social Commerce (V1)      | CAN-SOC-001  | Social Inquiries        | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | CUST-002   | Social Exclusions         | CAN-SOC-002  | Social Restrictions     | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | CUST-003   | Wholesale Visibility      | CAN-CAT-003  | B2B Visibility          | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | CUST-004   | Geo-Discovery             | CAN-DISC-002 | Geo-Proximity           | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | VEND-001   | Branch-Aware Stock        | CAN-CAT-004  | Branch/Location         | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | VEND-002   | Licence Verification      | CAN-ID-003   | Tiered KYC              | DEPENDENCY     | EXPLICIT  |                             |
| FastAPI   | VEND-003   | Storefront Analytics      | CAN-VND-001  | Vendor Analytics        | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | VEND-004   | Wholesale RFQ             | CAN-CAT-003  | B2B Visibility          | DEPENDENCY     | EXPLICIT  |                             |
| FastAPI   | CORE-001   | Product Classes           | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| FastAPI   | CORE-002   | Cart Writes               | CAN-ORD-002  | Cart Sec                | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | CORE-003   | Checkout Derivation       | CAN-ORD-003  | Checkout Derivation     | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | API-001    | Input Trust               | CAN-OPS-002  | Untrusted IO            | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | PAY-001    | Integer Math              | CAN-FIN-001  | Integer Ngwee           | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | PAY-002    | Lenco Drills              | CAN-FIN-002  | Gateway/MoMo            | SPECIALIZATION | EXPLICIT  |                             |
| FastAPI   | UX-001     | Browser-Led Grade A       | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | LOC-001    | Zambian Languages         | CAN-DISC-003 | i18n                    | DUPLICATE      | EXPLICIT  |                             |
| FastAPI   | DB-001     | RLS Impersonation         | CAN-OPS-001  | RLS Isolation           | SPECIALIZATION | EXPLICIT  |                             |
| Roadmap   | AUTH-001   | Custom User Model & OTP   | CAN-ID-001   | SMS OTP                 | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | VEND-001   | KYC Workflow              | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | CAT-001    | Hierarchical Categories   | CAN-CAT-001  | Canonical Catalog       | SUBSET         | EXPLICIT  |                             |
| Roadmap   | PROD-001   | Product CRUD & Variants   | CAN-CAT-001  | Canonical Catalog       | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | IMG-001    | Cloudinary Pipeline       | CAN-UX-003   | Media Optimization      | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | SRCH-001   | Meilisearch Integration   | CAN-DISC-001 | Hybrid Search           | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | CART-001   | Multi-Vendor Cart         | CAN-ORD-001  | Multi-Vendor Split      | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | CHK-001    | Order Splitting           | CAN-ORD-001  | Multi-Vendor Split      | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | PAY-001    | DPO Pay & Mobile Money    | CAN-FIN-002  | Gateway/MoMo            | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | ESC-001    | Escrow System             | CAN-FIN-004  | Escrow Hold             | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | ORD-001    | Order State Machine       | CAN-ORD-001  | Multi-Vendor Split      | DEPENDENCY     | EXPLICIT  |                             |
| Roadmap   | DEL-001    | Delivery & QR Verif.      | CAN-ORD-006  | Logistics & Pickup      | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | MOD-001    | RBAC & Admin Moderation   | CAN-ADM-002  | Admin UI                | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | FIN-001    | Commission & Ledgers      | CAN-FIN-007  | Commission Engine       | DUPLICATE      | EXPLICIT  |                             |
| Roadmap   | NOT-001    | Omnichannel Notifs        | CAN-OPS-004  | n8n Workflows           | DUPLICATE      | EXPLICIT  |                             |
| Events    | DATA-01    | Event Entity              | CAN-EVT-001  | Event Schema            | DUPLICATE      | EXPLICIT  |                             |
| Events    | DATA-02    | Event Instance            | CAN-EVT-001  | Event Schema            | SUBSET         | EXPLICIT  |                             |
| Events    | DATA-03    | Ticket Type               | CAN-EVT-001  | Event Schema            | SUBSET         | EXPLICIT  |                             |
| Events    | DATA-04    | Ticket Entity             | CAN-EVT-001  | Event Schema            | SUBSET         | EXPLICIT  |                             |
| Events    | DISC-01    | Time-First Default        | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Events    | DISC-02    | Discovery Lenses          | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Events    | DISC-03    | Time Decay Ranking        | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Events    | DISC-04    | Sell-Through Badge        | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Events    | CAP-01     | Hierarchical Capacity     | CAN-CAT-005  | Stock Reservation       | SPECIALIZATION | EXPLICIT  |                             |
| Events    | TICK-01    | Dynamic QR                | CAN-EVT-002  | Dynamic QR              | DUPLICATE      | EXPLICIT  |                             |
| Events    | TICK-02    | Offline Scanner           | CAN-EVT-005  | Offline Scanning        | DUPLICATE      | EXPLICIT  |                             |
| Events    | TICK-03    | PIN Backup (Q33)          | CAN-EVT-002  | Dynamic QR              | DEPENDENCY     | EXPLICIT  |                             |
| Events    | TICK-04    | Ticket Transfer           | CAN-EVT-004  | Ticket Transfer         | DUPLICATE      | EXPLICIT  |                             |
| Events    | FIN-01     | Inclusive Display         | CAN-FIN-001  | Integer Ngwee           | DEPENDENCY     | EXPLICIT  |                             |
| Events    | FIN-02     | Standard Escrow           | CAN-EVT-003  | Event Escrow            | DUPLICATE      | EXPLICIT  |                             |
| Events    | FIN-03     | Advanced Escrow           | CAN-EVT-003  | Event Escrow            | DUPLICATE      | EXPLICIT  |                             |
| Events    | VND-01     | Tier 1 Organiser          | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Events    | VND-02     | Tier 2 Organiser          | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Events    | VND-03     | Team Access Roles         | CAN-OPS-001  | RLS Isolation           | DEPENDENCY     | EXPLICIT  |                             |
| Events    | FRD-01     | First-Scan-Wins           | CAN-EVT-002  | Dynamic QR              | DEPENDENCY     | EXPLICIT  |                             |
| Events    | FRD-02     | Pre-event Auth Call       | CAN-ADM-002  | Admin UI                | DEPENDENCY     | EXPLICIT  |                             |
| Product   | ARCH-001   | Nullable Product FK       | CAN-CAT-002  | Unique Items            | DUPLICATE      | EXPLICIT  |                             |
| Product   | ARCH-002   | Product Class Enum        | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | ARCH-003   | Variant Support           | CAN-CAT-001  | Canonical Catalog       | SUBSET         | EXPLICIT  |                             |
| Product   | PRC-001    | Pricing Mode Enum         | CAN-ORD-003  | Checkout Derivation     | DEPENDENCY     | EXPLICIT  |                             |
| Product   | PRC-002    | Unit Normalization        | CAN-ORD-003  | Checkout Derivation     | DEPENDENCY     | EXPLICIT  |                             |
| Product   | PRC-003    | USD Pegging               | CAN-ORD-004  | FX Peg                  | DUPLICATE      | EXPLICIT  |                             |
| Product   | PRC-004    | FX Lock on Order          | CAN-ORD-004  | FX Peg                  | DUPLICATE      | EXPLICIT  |                             |
| Product   | INV-001    | Stock Modes               | CAN-CAT-005  | Stock Reservation       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | INV-002    | Checkout Reservation      | CAN-CAT-005  | Stock Reservation       | DUPLICATE      | EXPLICIT  |                             |
| Product   | INV-003    | Cancel Rate Sweeper       | CAN-OPS-004  | n8n Workflows           | DEPENDENCY     | EXPLICIT  |                             |
| Product   | VEN-001    | Search & Attach           | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | VEN-002    | Canonical Submission      | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | VEN-003    | Canonical Reward          | CAN-FIN-007  | Commission Engine       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | VEN-004    | Quick-list Commodity      | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | VEN-005    | Unique Item Listing       | CAN-CAT-002  | Unique Items            | DUPLICATE      | EXPLICIT  |                             |
| Product   | VEN-006    | CSV Bulk Import           | CAN-CAT-006  | Inventory Sync/Bulk     | DUPLICATE      | EXPLICIT  |                             |
| Product   | VEN-007    | Stock Sync API            | CAN-CAT-006  | Inventory Sync/Bulk     | DUPLICATE      | EXPLICIT  |                             |
| Product   | TNS-001    | Condition Enum            | CAN-FIN-006  | Used Escrow             | DEPENDENCY     | EXPLICIT  |                             |
| Product   | TNS-002    | Extended Escrow           | CAN-FIN-006  | Used Escrow             | DUPLICATE      | EXPLICIT  |                             |
| Product   | TNS-003    | Evidence Uploads          | CAN-FIN-006  | Used Escrow             | DEPENDENCY     | EXPLICIT  |                             |
| Product   | TNS-004    | Tier-Gating               | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Product   | TNS-005    | Brand Claiming            | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| Product   | TNS-006    | Fake Reporting            | CAN-ADM-002  | Admin UI                | DEPENDENCY     | EXPLICIT  |                             |
| Product   | DIS-001    | In-Stock Boost            | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Product   | DIS-002    | Price Comp Boost          | CAN-DISC-001 | Hybrid Search           | DEPENDENCY     | EXPLICIT  |                             |
| Product   | DIS-003    | Geo-Proximity             | CAN-DISC-002 | Geo-Proximity           | DUPLICATE      | EXPLICIT  |                             |
| Product   | CAT-RULE   | ZAMRA / ERB gating        | CAN-ID-003   | Tiered KYC              | SPECIALIZATION | EXPLICIT  |                             |
| Pipelines | CUST-001   | PWA Architecture          | CAN-UX-001   | PWA/Offline             | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | CUST-002   | Unified Discovery         | CAN-DISC-001 | Hybrid Search           | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | CUST-003   | Canonical Comparison      | CAN-CAT-001  | Canonical Catalog       | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | CUST-004   | Multi-Vendor Cart         | CAN-ORD-001  | Multi-Vendor Split      | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | CUST-005   | Profile & Toggles         | CAN-ID-002   | Multi-Hat Sessions      | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | VEND-001   | Archetype Onboarding      | CAN-ID-002   | Multi-Hat Sessions      | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | VEND-002   | Dual-Prong UI             | CAN-UX-001   | PWA/Offline             | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | VEND-003   | Multi-Hat Accounts        | CAN-ID-002   | Multi-Hat Sessions      | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | VEND-004   | Goods-Received Flow       | CAN-CAT-004  | Branch/Location         | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | B2B-001    | Schema Latency (Ph 1)     | CAN-CAT-003  | B2B Visibility          | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | B2B-002    | PACRA Gating              | CAN-ID-003   | Tiered KYC              | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | INV-001    | Multi-Warehouse Routing   | CAN-CAT-004  | Branch/Location         | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | INV-002    | Stock Reservation         | CAN-CAT-005  | Stock Reservation       | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | INV-003    | Lot/Batch FIFO            | CAN-CAT-004  | Branch/Location         | SUBSET         | EXPLICIT  |                             |
| Pipelines | PAY-001    | 4-Step Escrow Trust       | CAN-FIN-004  | Escrow Hold             | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | PAY-002    | Escrow Release            | CAN-FIN-005  | Escrow Auto-Release     | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | PAY-003    | Mobile Money / USSD       | CAN-FIN-002  | Gateway/MoMo            | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | ADM-001    | Operations UI             | CAN-ADM-002  | Admin UI                | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | ADM-002    | n8n / AI Integration      | CAN-OPS-004  | n8n Workflows           | DUPLICATE      | EXPLICIT  |                             |
| Pipelines | SEC-001    | Concurrent Transactions   | CAN-CAT-005  | Stock Reservation       | DUPLICATE      | IMPLIED   |                             |
| Pipelines | SEC-002    | Trust/Safety Suspend      | CAN-ADM-002  | Admin UI                | DEPENDENCY     | EXPLICIT  |                             |
| Pipelines | OPS-001    | Conservative Lead Times   | CAN-ORD-001  | Multi-Vendor Split      | DEPENDENCY     | EXPLICIT  |                             |

---

## DEC-001…004 traceability (Batch 0 / 0.5 resolved)

| Decision         | Canonical themes           | Repository evidence                                 | Classification          |
| ---------------- | -------------------------- | --------------------------------------------------- | ----------------------- |
| DEC-001 Backend  | CAN-OPS-002 (Pydantic)     | `services/api/pyproject.toml`, `app/main.py`        | CONFIRMED_BY_REPOSITORY |
| DEC-002 AuthZ    | CAN-OPS-001                | RLS migrations + `auth.py` + `tests/rls/`           | CONFIRMED_BY_REPOSITORY |
| DEC-003 Payments | CAN-FIN-002                | `payments/lenco/`; DPO absent                       | CONFIRMED_BY_REPOSITORY |
| DEC-004 Search   | CAN-DISC-001, CAN-DISC-004 | `0009_search.sql`, `search_rrf`; Meilisearch absent | CONFIRMED_BY_REPOSITORY |

---

_See [MASTER_REQUIREMENTS.md](./MASTER_REQUIREMENTS.md) for full canonical definitions and acceptance criteria._

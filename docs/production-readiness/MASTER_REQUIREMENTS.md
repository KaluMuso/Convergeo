# Master Requirements — Convergeo Canonical Registry

**Ingest date:** 2026-08-06 (Batch 0.5)  
**Authority:** Operator-supplied **CONVERGEO PRE-CURSOR CANONICAL REQUIREMENTS REGISTRY** (verbatim ingest; no reinterpretation)  
**Repository SHA at ingest:** `fcf2b1918256bd3d8680741b17cf928cde8576c5`  
**Registry integrity:** 9 source documents · 225 source requirements (header) · **223 matrix rows ingested** · 34 canonical requirements · REG-001 documents 2-row S1 gap

**Status fields in this document** (`Rep Status`) reflect registry baseline at ingest — not live audit conclusions. See [AUDIT_LEDGER.md](./AUDIT_LEDGER.md) for implementation / deployment / runtime verification.

---

## Source document index

| Alias     | Document Name                     | Source Reqs |
| --------- | --------------------------------- | ----------- |
| S1        | Strategy Brief (August 05)        | 53          |
| S2        | Vergeo Super-App Blueprint        | 25          |
| S3        | 60-Day Development Roadmap        | 15          |
| S4        | Events Strategy & Ticketing       | 21          |
| S5        | Product Strategy (5-Class)        | 27          |
| S6        | Business, Pipelines & 3-Frontend  | 22          |
| S7        | Strategic Master Plan (SMP)       | 19          |
| S8        | Strategic Foundation Quest. (SFQ) | 26          |
| S9        | Operational Log & Directives      | 17          |
| **TOTAL** |                                   | **225**     |

---

## WS-ID: Identity, Auth & KYC

| Canonical ID   | Domain | Business Invariant                                                                          | Source IDs                     | Auth | Proposed Implementation                               | Pri | Launch Scope | Blocks? | Rep Status    |
| -------------- | ------ | ------------------------------------------------------------------------------------------- | ------------------------------ | ---- | ----------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-ID-001** | Auth   | Authentication must rely on Zambian phone numbers and OTP; passwords are not allowed.       | S1, S2, S3, S7, S8             | E    | SMS OTP via Africa's Talking. JWT sessions.           | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-ID-002** | Auth   | Users must be able to act as both consumers and vendors using a single underlying identity. | S1, S2, S6                     | E    | Multi-hat session state; UI toggle switches context.  | P1  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-ID-003** | KYC    | Regulated categories (e.g., Pharma, B2B) must strictly block unauthorized vendors.          | S1, S2, S3, S4, S5, S6, S8, S9 | E    | Tiered KYC (T1 NRC, T2 PACRA). Admin manual approval. | P0  | VENDOR       | YES     | `NOT_AUDITED` |

### Acceptance criteria — WS-ID

- **CAN-ID-001:** User can log in using only a phone number and a temporary OTP. **Evidence expected:** Auth router, OTP generation logic, JWT issuance endpoint.
- **CAN-ID-002:** State transitions between Buyer/Seller dashboards occur without forcing re-authentication. **Evidence expected:** Shared user DB entity, role-aware frontend layout wrappers.
- **CAN-ID-003:** A Tier 1 vendor attempting to publish a regulated item (e.g., Medicine) receives a 403 Forbidden. **Evidence expected:** Middleware/Pydantic validator blocking regulated `category_id` updates for T1 users.

---

## WS-CAT: Catalog, Inventory & Visibility

| Canonical ID    | Domain    | Business Invariant                                                                        | Source IDs                 | Auth | Proposed Implementation                                 | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | --------- | ----------------------------------------------------------------------------------------- | -------------------------- | ---- | ------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-CAT-001** | Catalog   | The platform must prevent duplicate identical listings to ensure clean comparison views.  | S1, S2, S3, S5, S6, S7, S9 | E    | Shared Canonical Product entity → N Vendor Listings.    | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-CAT-002** | Catalog   | Unique, custom, or used items must exist without polluting the global canonical catalog.  | S5                         | E    | Nullable `product_id` FK on Listing table.              | P1  | RETAIL       | YES     | `NOT_AUDITED` |
| **CAN-CAT-003** | B2B       | Wholesale pricing and listings must be absolutely invisible to standard retail consumers. | S5, S6, S9                 | E    | `404 Not Found` response at API level for retail users. | P0  | B2B          | NO      | `NOT_AUDITED` |
| **CAN-CAT-004** | Inventory | Vendor stock must be tied to specific physical locations for accurate logistics.          | S1, S5, S6, S8, S9         | E    | Branch/Warehouse locations with GPS/Hours.              | P1  | VENDOR       | YES     | `NOT_AUDITED` |
| **CAN-CAT-005** | Inventory | Stock must be reliably reserved during checkout to prevent overselling.                   | S4, S5, S6                 | E    | Atomic 10–15 minute DB-level reservation lock.          | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-CAT-006** | Inventory | Vendors must be able to synchronize stock in bulk to avoid manual entry bottlenecks.      | S5, S8                     | E    | CSV Parser endpoint or API ingest for POS systems.      | P2  | VENDOR       | NO      | `NOT_AUDITED` |

### Acceptance criteria — WS-CAT

- **CAN-CAT-001:** Multiple vendors selling the same item appear under a single product detail page. **Evidence expected:** DB schema separating Products and VendorListings.
- **CAN-CAT-003:** Unauthenticated or retail-only users requesting a B2B listing URL receive a 404 status code, leaking zero pricing data. **Evidence expected:** API listing fetch controller enforcing RLS or application-level visibility logic.
- **CAN-CAT-005:** Two users placing the last item in their carts simultaneously results in only one successful reservation. **Evidence expected:** DB row lock (`SELECT FOR UPDATE`) or Redis reservation TTL.

---

## WS-ORD: Cart, Checkout, Logistics & Reviews

| Canonical ID    | Domain   | Business Invariant                                                                       | Source IDs     | Auth | Proposed Implementation                                          | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | -------- | ---------------------------------------------------------------------------------------- | -------------- | ---- | ---------------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-ORD-001** | Cart     | A single checkout spanning multiple vendors must generate distinct fulfillment orders.   | S1, S2, S3, S6 | E    | Master Order splits into distinct Vendor SubOrders.              | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-ORD-002** | Cart Sec | Clients must never have direct write access to manipulate cart states or pricing.        | S9             | E    | `cart_items` RLS blocks client. Writes route via `service_role`. | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-ORD-003** | Checkout | The server must independently calculate all final totals, ignoring client-provided sums. | S5, S9         | E    | API re-derives line items, Tier Pricing, and MOQs from DB.       | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-ORD-004** | Checkout | Cross-border goods must not expose vendors to currency fluctuation post-checkout.        | S5             | E    | Dynamic ZMW/USD peg locks permanently on Order creation.         | P0  | RETAIL       | YES     | `NOT_AUDITED` |
| **CAN-ORD-005** | Reviews  | Reviews must strictly require a completed purchase to prevent manipulation.              | S1, S3, S6     | E    | Review creation endpoint validates completed SubOrder ID.        | P1  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-ORD-006** | Delivery | Delivery mechanisms must support hybrid models (courier vs. physical pickup points).     | S3, S8         | E    | Yango API integration + QR-code verified Retail Pickups.         | P1  | RETAIL       | YES     | `NOT_AUDITED` |

### Acceptance criteria — WS-ORD

- **CAN-ORD-002:** A client attempting to execute a direct Supabase INSERT into `cart_items` receives a 403 error. **Evidence expected:** RLS policy blocking INSERT/UPDATE for authenticated users on `cart_items`.
- **CAN-ORD-003:** A client sending a manipulated cart total in a checkout POST request is ignored; the server charges the correct DB-derived amount. **Evidence expected:** Checkout initialization service re-querying VendorListings prices.
- **CAN-ORD-005:** Attempting to POST a review without a valid, delivered `order_id` belonging to the user fails. **Evidence expected:** Pydantic validator / endpoint authorization logic.

---

## WS-FIN: Financials, Ledger & Escrow

| Canonical ID    | Domain  | Business Invariant                                                                            | Source IDs                 | Auth | Proposed Implementation                                        | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | ------- | --------------------------------------------------------------------------------------------- | -------------------------- | ---- | -------------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-FIN-001** | Ledger  | Currency calculations must be exact and immune to floating-point rounding errors.             | S4, S7, S9                 | E    | Integer minor units (`ngwee`) across DB, API, and UI.          | P0  | PAYMENTS     | YES     | `NOT_AUDITED` |
| **CAN-FIN-002** | Gateway | Primary payment rail must align with Zambian unbanked infrastructure.                         | S1, S2, S3, S6, S7, S8, S9 | E    | Native Mobile Money integrations via Lenco/DPO.                | P0  | PAYMENTS     | YES     | `NOT_AUDITED` |
| **CAN-FIN-003** | Webhook | Payment systems must be immune to replay attacks or duplicate webhooks.                       | S1, S6                     | I    | Mandatory signature verification + Idempotency keys in DB.     | P0  | PAYMENTS     | YES     | `NOT_AUDITED` |
| **CAN-FIN-004** | Escrow  | Funds must never route directly to vendors. Held in platform float until fulfillment.         | S1, S2, S3, S6, S7, S8     | E    | Double-entry ledger holds funds in Escrow status.              | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-FIN-005** | Escrow  | Escrow must release automatically if buyer is silent post-delivery (avoid vendor starvation). | S1, S2, S6                 | E    | Scheduled worker (Celery/Cron) auto-releases after 48h.        | P0  | VENDOR       | YES     | `NOT_AUDITED` |
| **CAN-FIN-006** | Escrow  | Higher-risk used goods must provide an extended inspection window for buyers.                 | S1, S5                     | E    | 72h auto-release hold specifically for 'Used' condition items. | P1  | RETAIL       | YES     | `NOT_AUDITED` |
| **CAN-FIN-007** | Ledger  | Platform must accurately deduct variable commission rates based on category and vendor tier.  | S2, S3, S5, S7             | E    | Commission calculation engine runs prior to Escrow settlement. | P0  | ADMIN        | YES     | `NOT_AUDITED` |

### Acceptance criteria — WS-FIN

- **CAN-FIN-001:** Financial DB columns do not accept decimal values. **Evidence expected:** Postgres schema using INTEGER or BIGINT for all price/ledger columns.
- **CAN-FIN-003:** Resending an identical payment success webhook does not credit the vendor twice. **Evidence expected:** Unique constraint on `transaction_id` or explicit idempotency middleware.
- **CAN-FIN-004:** A successful payment sets order status to `PAID_IN_ESCROW`, not `SETTLED`. **Evidence expected:** Order state machine logic and ledger double-entry creation.

---

## WS-DISC: Search, Discovery & Localization

| Canonical ID     | Domain | Business Invariant                                                                        | Source IDs             | Auth | Proposed Implementation                                          | Pri | Launch Scope | Blocks? | Rep Status    |
| ---------------- | ------ | ----------------------------------------------------------------------------------------- | ---------------------- | ---- | ---------------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-DISC-001** | Search | Search must accommodate Zambian colloquialisms, synonyms, and typos.                      | S1, S2, S3, S4, S5, S6 | E    | Meilisearch / pgvector / Postgres Native Text Search.            | P1  | RETAIL       | YES     | `NOT_AUDITED` |
| **CAN-DISC-002** | Geo    | The platform must sort supply by proximity without incurring unsustainable mapping costs. | S1, S2, S5, S9         | E    | Frugal PostGIS distance sorting. No expensive map SDKs.          | P1  | RETAIL       | YES     | `NOT_AUDITED` |
| **CAN-DISC-003** | i18n   | The platform must support local vernacular languages alongside English.                   | S1, S7, S8, S9         | E    | `next-intl` dictionaries for Bemba and Nyanja.                   | P1  | PLATFORM     | NO      | `NOT_AUDITED` |
| **CAN-DISC-004** | Index  | The search index must reflect real-time inventory and pricing updates.                    | S1                     | E    | Background ingestion workers to sync DB changes to search index. | P0  | PLATFORM     | YES     | `NOT_AUDITED` |

### Acceptance criteria — WS-DISC

- **CAN-DISC-002:** Users can sort results by distance based on their provided coordinates. **Evidence expected:** Geospatial query logic (`ST_Distance`) in the search API.
- **CAN-DISC-003:** Changing the user locale updates UI strings without breaking layouts or exposing missing translation keys. **Evidence expected:** Complete next-intl dictionary files.

---

## WS-EVT: Events & Ticketing

| Canonical ID    | Domain | Business Invariant                                                                        | Source IDs | Auth | Proposed Implementation                                        | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | ------ | ----------------------------------------------------------------------------------------- | ---------- | ---- | -------------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-EVT-001** | Data   | Events require distinct logic from physical products (dates, venue capacity).             | S2, S4, S8 | E    | Parallel entity: Event → Instance → TicketType → Ticket.       | P1  | EVENTS       | NO      | `NOT_AUDITED` |
| **CAN-EVT-002** | Entry  | Digital tickets must be immune to screenshots, scalping, and offline validation failures. | S2, S3, S4 | E    | Dynamic HMAC-signed QR codes refreshing every 60s.             | P1  | EVENTS       | NO      | `NOT_AUDITED` |
| **CAN-EVT-003** | Escrow | Event funds must be managed according to event dates, not a standard 48h delivery rule.   | S4         | E    | T-7 / T+1 milestone payouts for >14 day events.                | P1  | EVENTS       | NO      | `NOT_AUDITED` |
| **CAN-EVT-004** | Entry  | Buyers must be able to transfer tickets to others securely prior to event cutoff times.   | S4         | E    | Transfer API revoking old QR seed and issuing new one via SMS. | P2  | EVENTS       | NO      | `NOT_AUDITED` |
| **CAN-EVT-005** | Entry  | Door staff must be able to validate tickets even during local internet outages.           | S4         | E    | Offline-first Scanner PWA syncing cached hashes.               | P1  | EVENTS       | NO      | `NOT_AUDITED` |

### Acceptance criteria — WS-EVT

- **CAN-EVT-002:** A screenshot of a QR code fails validation if scanned after 60 seconds. **Evidence expected:** Client-side TOTP/HMAC generation and server-side time-window validation.

---

## WS-VND: Vendor Experience & Storefronts

| Canonical ID    | Domain | Business Invariant                                                                    | Source IDs | Auth | Proposed Implementation                                        | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | ------ | ------------------------------------------------------------------------------------- | ---------- | ---- | -------------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-VND-001** | Stats  | Vendors require accurate insights into their store performance excluding bot traffic. | S1, S9     | E    | Analytics API returning genuine impressions and conversions.   | P2  | VENDOR       | NO      | `NOT_AUDITED` |
| **CAN-VND-002** | Store  | Vendors must be able to curate distinct storefronts to differentiate their brand.     | S1         | E    | Custom storefront UI configs (logos, colors, collections).     | P2  | VENDOR       | NO      | `NOT_AUDITED` |
| **CAN-VND-003** | Ops    | Informal vendors must be able to accept orders without requiring a smartphone.        | S1         | E    | USSD/SMS fallback integration for basic vendor status updates. | P2  | VENDOR       | NO      | `NOT_AUDITED` |

### Acceptance criteria — WS-VND

- **CAN-VND-003:** A vendor can reply to a platform SMS to mark an order as packed. **Evidence expected:** Africa's Talking two-way SMS webhook listener parsing vendor text commands.

---

## WS-ADM: Administration & Moderation

| Canonical ID    | Domain | Business Invariant                                                                      | Source IDs     | Auth | Proposed Implementation                                      | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | ------ | --------------------------------------------------------------------------------------- | -------------- | ---- | ------------------------------------------------------------ | --- | ------------ | ------- | ------------- |
| **CAN-ADM-001** | Admin  | The platform must provide a mechanism to halt escrow releases in the event of disputes. | S1, S6, S8     | E    | Admin API to pause escrow timer and review dispute evidence. | P0  | ADMIN        | YES     | `NOT_AUDITED` |
| **CAN-ADM-002** | Admin  | Admins must be able to vet content, approve KYC, and override automated systems.        | S2, S3, S6, S8 | E    | Secure Admin UI with Role-Based Access Control (RBAC).       | P1  | ADMIN        | YES     | `NOT_AUDITED` |

### Acceptance criteria — WS-ADM

- **CAN-ADM-001:** An admin clicking "Freeze" on a transaction successfully prevents the 48h settlement cron job from processing it. **Evidence expected:** Dispute status enum overriding standard Escrow state logic.

---

## WS-OPS: Security, Infrastructure & UX

| Canonical ID    | Domain | Business Invariant                                                                           | Source IDs                 | Auth | Proposed Implementation                                          | Pri | Launch Scope | Blocks? | Rep Status    |
| --------------- | ------ | -------------------------------------------------------------------------------------------- | -------------------------- | ---- | ---------------------------------------------------------------- | --- | ------------ | ------- | ------------- |
| **CAN-OPS-001** | Sec    | Tenants (Vendors) must be cryptographically isolated from accessing each other's data.       | S1, S4, S6, S7, S8, S9     | E    | Supabase Row Level Security (RLS) policies.                      | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-OPS-002** | Sec    | All inbound data (webhooks, user text, AI outputs) must be treated as hostile and untrusted. | S7, S9                     | E    | Strict Pydantic v2 validation schemas on all FastAPI routes.     | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-OPS-003** | Sec    | Admin/System actions must be fully traceable for financial compliance.                       | S1, S2, S3, S4, S6         | E    | Immutable audit log table recording user, action, and timestamp. | P1  | ADMIN        | YES     | `NOT_AUDITED` |
| **CAN-OPS-004** | Auto   | Business workflows (emails, marketing) must be decoupled from the core transaction engine.   | S1, S2, S3, S5, S6, S7, S8 | E    | Webhook emissions to a self-hosted n8n instance.                 | P1  | PLATFORM     | NO      | `NOT_AUDITED` |
| **CAN-OPS-005** | Infra  | The financial database must be protected against catastrophic regional failures.             | S1, S3, S8                 | E    | Automated Point-in-Time Recovery (PITR) backups on Postgres.     | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-OPS-006** | CI/CD  | Code must not enter production without passing foundational correctness checks.              | S7                         | E    | GitHub Actions enforcing linting, type-checking, and tests.      | P0  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-UX-001**  | UX     | The platform must gracefully handle low-bandwidth and offline-edge scenarios (PWA).          | S1, S2, S6, S7, S8, S9     | E    | Next.js PWA Service Workers, explicit skeletons, empty states.   | P1  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-UX-002**  | SEO    | Products and Events must be easily indexable by external search engines for organic growth.  | S1, S3, S4                 | E    | SSR / JSON-LD Structured markup generation.                      | P1  | PLATFORM     | NO      | `NOT_AUDITED` |
| **CAN-UX-003**  | Media  | High-resolution user uploads must not consume excessive bandwidth for downstream buyers.     | S3, S8                     | E    | Cloudinary/CDN integration enforcing image compression/WebP.     | P1  | PLATFORM     | YES     | `NOT_AUDITED` |
| **CAN-SOC-001** | Social | Customers must be able to engage in listing-anchored inquiries to facilitate trust.          | S9                         | E    | Threads tied to specific `listing_id`s. Official API messaging.  | P1  | SOCIAL       | NO      | `NOT_AUDITED` |
| **CAN-SOC-002** | Social | The platform must prevent unmoderated P2P abuse (No DMs, no public feeds).                   | S9                         | E    | Strict API exclusion of general user-to-user messaging.          | P0  | SOCIAL       | YES     | `NOT_AUDITED` |

### Acceptance criteria — WS-OPS

- **CAN-OPS-001:** An authenticated vendor attempting to query `/api/orders` only receives orders linked to their `vendor_id`. **Evidence expected:** Supabase RLS policy `USING (auth.uid() = vendor_id)`.
- **CAN-OPS-002:** An API request missing a required field or containing the wrong data type is rejected with a 422 before executing any business logic. **Evidence expected:** Pydantic schemas defined for all route inputs.
- **CAN-UX-001:** If a user's connection drops, the UI displays cached content and a graceful "offline" indicator rather than crashing. **Evidence expected:** Service worker registration and caching strategies in frontend config.

---

## Registry conflicts (source documents)

Four source requirements flagged **CONFLICT** in the registry (resolved to repository verification, not rewritten):

| Source | ID      | Conflict                         | Resolution note                            |
| ------ | ------- | -------------------------------- | ------------------------------------------ |
| S1     | PAY-005 | Multi-currency vs integer ngwee  | Handled by dynamic ZMW peg (CAN-ORD-004)   |
| S2     | PAY-004 | Zero subscriptions vs commission | Handled by commission engine (CAN-FIN-007) |
| S7     | PAY-001 | DPO vs Lenco                     | **DEC-003:** Lenco confirmed in repository |
| S8     | PAY-003 | Multi-currency schema            | Resolved by FX peg (CAN-ORD-004)           |

Repository architecture decisions **DEC-001…DEC-004** are documented in [DECISIONS.md](./DECISIONS.md).

---

## Audit batch sequence (from registry)

| Batch | Focus                                                                                              |
| ----- | -------------------------------------------------------------------------------------------------- |
| 0     | Repository truth & architecture baseline                                                           |
| 0.5   | Runtime truth, migration truth & requirements ingest                                               |
| 1     | Authentication, authorization, tenant isolation (CAN-ID-001, CAN-ID-002, CAN-OPS-001, CAN-OPS-002) |
| 2     | Money representation, payment intake & webhook safety (CAN-FIN-001…003)                            |
| 3     | Catalogue, listing & visibility (CAN-CAT-001…003)                                                  |
| 4     | Inventory reservation, cart & checkout derivation (CAN-CAT-005, CAN-ORD-002, CAN-ORD-003)          |
| 5     | Orders, ledger, escrow & settlement                                                                |
| 6     | Vendor/KYC/admin controls                                                                          |
| 7     | Search/discovery/geo                                                                               |
| 8     | Operations, CI/CD, observability, backups                                                          |

_Full source-to-canonical mapping: [REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md)._

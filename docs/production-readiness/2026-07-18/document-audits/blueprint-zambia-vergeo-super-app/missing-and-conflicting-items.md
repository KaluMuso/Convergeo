# Missing & Conflicting Items — blueprint-zambia-vergeo-super-app

**Audit date:** 2026-07-18 · READ-ONLY  
**Source:** TurboScribe transcript Parts 1–2 (37 pages). Wireframe/dashboard figures are **not** treated as production master data.

---

## a. Missing production records

| Fact IDs   | Expected record                                                        | Live evidence                                           | Notes                                                  |
| ---------- | ---------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| F017, F018 | ~840 vendors / ~12,400 products                                        | 3 vendors, 150 products, 134 listings (all demo images) | Projections only — **do not seed** to “close the gap.” |
| F030       | Multi-vertical services (plumbing, catering, solar, etc.)              | 1 demo service (`Laptop & Phone Repair`)                | Services GTM inventory absent.                         |
| F031       | RFQ jobs + quotes                                                      | `jobs=0`, `job_quotes=0`                                | API exists; no operational RFQs.                       |
| F032       | Events + ticket inventory (24 events / 12k attendees claimed)          | `events=0`, `tickets=0`                                 | Public `/events` total 0.                              |
| F038, F039 | Orders, payments, payouts, ledger lines supporting GMV/payout examples | All money/ops tables **0**                              | Mulenga Fashion payout example has no matching vendor. |
| F014, F015 | KYC submission audit trail                                             | `kyc_records=0` while 3 vendors show `kyc_tier=2`       | Tier badges without records — integrity gap.           |

---

## b. Missing fields / schema support

| Fact IDs   | Claimed capability                              | Schema / live finding                               | Notes                                                                      |
| ---------- | ----------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------- |
| F016, F040 | Tier3 paid customisation / B2B API monetisation | `feature_flags.paid_tiers=false`                    | Intentionally off; aligns with D3 OUT for subscription billing.            |
| F035       | City Guides / AI trip planner entities          | No city-guide tables/API paths                      | Also **OUT of v1** in locked decisions.                                    |
| F036       | Yango / courier API integration fields          | No Yango routes; delivery is zone + manual dispatch | D16 forbids courier API v1.                                                |
| F006, F043 | Celery/Upstash job plane                        | Not in locked stack; n8n is the automation plane    | Schema N/A — wrong architecture in source.                                 |
| —          | Foundation drift (context)                      | Live missing migrations `0051`, `0053`–`0055`       | Not asserted by this transcript, but affects role-hook/services readiness. |

No transcript-required column was found “missing” merely by guessing a table name: core `products` / `vendor_listings` / escrow config keys **do** exist.

---

## c. Configuration / workflow gaps

| Fact IDs   | Expected workflow                             | Live state                                                                                                                                                     | Severity                     |
| ---------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| F027, F041 | Escrow 48h auto-release automation            | `release_after_delivered_hours=48` config OK; API `/internal/release-job/tick` present; **n8n release workflow absent** (only dispatch + payment recon active) | **P0**                       |
| F033       | Ticket issuance after paid order              | API `/internal/tickets/issue-tick` present; **n8n tickets-issue absent**; `tickets=0`                                                                          | **P0**                       |
| F024       | MoMo rails including Zamtel collections       | `zamtel_collections=false`; payments via Lenco (not direct telco APIs)                                                                                         | P1 policy alignment          |
| F044       | Open public launch implied by scale narrative | `public_launch=false`                                                                                                                                          | Expected for demo; not a bug |
| F005       | Realtime push notifications                   | Outbox + WhatsApp/SMS path; Realtime not evidenced as notification plane                                                                                       | P2 architecture hygiene      |

---

## d. UI / customer / vendor / admin gaps

| Fact IDs           | UI claim                                          | Evidence                                                                         | Gap                                              |
| ------------------ | ------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------ |
| F013               | PWA Install → home screen                         | Manifest 200 + install copy; `sw.js` / `serwist/sw.js` **404**                   | Service worker delivery incomplete               |
| F025               | Visible escrow tracker                            | Escrow / “Held by” / MoMo copy on `/en`                                          | Live money tracker not exercised (0 orders)      |
| F020               | Comparison “N vendors selling this”               | Canonical model supports it; named examples absent; anonymous deep UI not proven | Comparison UX **NOT_AUDITABLE**                  |
| F021, F022         | Vendor mobile daily-driver + desktop GMV          | Vendor app login-gated; no audit session                                         | **NOT_AUDITABLE** without test vendor JWT        |
| F038               | Admin GMV/payout command center with live metrics | Admin Cloudflare Access gated; DB shows 0 orders                                 | Metrics cannot be live; Access blocks UI confirm |
| F030–F032          | Services/events richness in customer tabs         | `/en/services` & `/en/events` return 200 but thin/empty data                     | Content gap, not necessarily missing routes      |
| Sell CTA (related) | Vendor acquisition                                | `/en/sell` shows unavailable (env unset per foundation)                          | P1 acquisition break                             |

---

## e. Conflicting data

| Fact IDs                              | Source claim                      | Production / locked SoT                                                 | Resolution stance                           |
| ------------------------------------- | --------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------- |
| F003                                  | Django REST API                   | Live FastAPI; **D18 FastAPI**                                           | Source superseded — do **not** build Django |
| F005                                  | Supabase Realtime notifications   | Outbox + WhatsApp Cloud API (**D15**)                                   | Source superseded                           |
| F006                                  | Celery + Upstash Redis            | n8n + internal ticks (**D21**)                                          | Source superseded                           |
| F024                                  | Direct Airtel/MTN/Zamtel APIs     | **D11 Lenco** aggregator; live webhook `/webhooks/lenco`                | Source superseded                           |
| F036                                  | Yango API + own logistics network | **D16** manual dispatch; no courier APIs v1                             | Source superseded for v1                    |
| F045                                  | Cards as afterthought             | Card session endpoints + Lenco cards in stack                           | MoMo-primary OK; cards exist                |
| F017, F018, F032, F038, F039          | Scale/GMV/payout examples         | Demo catalogue + **zero** money rows                                    | Treat as wireframe fiction                  |
| Naming (F001)                         | Vergio / Virgeo / Convergio       | Live **Vergeo5**                                                        | Brand SoT = Vergeo5                         |
| Commission example ~8.3% (K152/K1840) | Implied flat take                 | Category rates vary (fashion_beauty 1000 bps; default 800; tickets 500) | Example ≠ configured matrix                 |

---

## f. Access / evidence limitations

| Limitation                             | Blocks                                                | Needed for upgrade                                    |
| -------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------- |
| No vendor/admin authenticated session  | F021, F022, F038 UI verification                      | Least-privilege test accounts (no real money)         |
| Env secret values not read             | F012 Africa's Talking/OTP delivery; Lenco live config | Dashboard confirmation of env **names** + sandbox OTP |
| No sandbox prepaid MoMo/card run       | F023, F025, F027, F028, F033, F034 deduction proof    | Controlled sandbox payment → ledger → payout          |
| Admin Cloudflare Access                | Admin dashboard empty-state vs wireframe              | Access-approved auditor or redacted screenshot policy |
| API container SHA unknown (foundation) | Exact backend commit vs frontend `8cc1fa0`            | Host `API_IMAGE_TAG` / GHCR digest                    |
| External 78% mobile statistic          | F010                                                  | Cite primary research source                          |
| Comparison page deep link              | F020                                                  | Public product URL with ≥2 active listings            |

**Rule followed:** “Not found” is backed by scoped counts (`events=0`, `payments=0`, n8n workflow list length 2). No missing records were created.

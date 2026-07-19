# Source Conflicts and Decisions — Vergeo5 / Convergeo

**Date:** 2026-07-18  
**Purpose:** Separate **strategic aspiration**, **committed production requirement**, and **open founder decisions**. Do not invent answers.  
**Authority hierarchy:** live evidence → applied migrations/infra → repository → documentation (`../foundation/document-audit-contract.md`). Locked product decisions: `docs/plan/00-decisions.md`.

Related: `master-reconciliation-register.md` §0 · six audits under `../document-audits/*`

---

## 1. How to use this file

| Class                | Meaning                                                | Engineering action                                      |
| -------------------- | ------------------------------------------------------ | ------------------------------------------------------- |
| **LOCKED**           | Recorded in `00-decisions.md` or VERIFIED live posture | Build/ops must follow; treat opposing doc text as stale |
| **SUPERSEDED (DOC)** | Older strategy docs conflict with locked decisions     | Do not implement; add SoT banners (MR-L02)              |
| **ASPIRATION**       | Post-v1 / growth vision; not a launch gate             | Track as P2/roadmap unless founder elevates             |
| **OPEN DECISION**    | Business/founder choice required                       | Block only the gated surfaces; do not invent schema/UI  |
| **GENUINE GAP**      | Committed requirement missing or unproven              | Track as MR-* with P0/P1                                |

---

## 2. Strategic aspiration vs committed production requirement

### Aspiration (not launch-blocking unless elevated)

| Aspiration (source)                                                                                                                          | Why not committed for v1                                         | Track as                            |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------- |
| 75–100 / 200–500 / 840 vendors; K184k GMV (product Day60; master Q57; blueprint wireframes)                                                  | Wireframe/traction fiction vs 3 demo vendors, 0 money rows       | ASPIRATION + MR-D01 hygiene         |
| Five product classes A–E, six pricing modes, rich used-goods evidence (product strategy)                                                     | Phase-1 can be Class A branded/new-goods if founder scopes       | ASPIRATION / scope-gated MR-S05–S07 |
| Five event types incl. `multi_day`; PWYW; promo/affiliate; offline QR; co-organiser RBAC (events strategy)                                   | Paid-events launch needs money/n8n first; extras are Phase gates | ASPIRATION / P1–P2 events backlog   |
| City Guides, referrals, AR/try-on, WhatsApp commerce, USSD ordering, multi-currency, Zimbabwe, Tier3 API monetisation (master/SFQ/blueprint) | Explicitly OUT or post-v1 in locked decisions / research         | ASPIRATION                          |
| Subscriptions, promoted listings, AI recommendations (master Layer2/4)                                                                       | `paid_tiers=false`; OUT for launch                               | ASPIRATION                          |
| Yango/own logistics network; 10-province ops (blueprint/master)                                                                              | D16 = manual Lusaka + nationwide pickup                          | SUPERSEDED logistics                |
| AI Ask after ≥10k transactions (product)                                                                                                     | Quotas exist; grounding gate is P2                               | ASPIRATION / MR-O06-adjacent        |

### Committed production requirements (must be true for real-money launch)

| Requirement                                             | Source of commitment                           | Current maturity                                         |
| ------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------- |
| FastAPI + Supabase + Next.js 3-app topology             | D18–D24; live VERIFIED topology                | PRODUCTION_VERIFIED shells                               |
| Lenco-only payments; integer ngwee ledger/escrow        | D11; CLAUDE.md money rules                     | CODE_COMPLETE (#274/#288/#294); **not** STAGING_VERIFIED |
| Escrow trust path + auto-release automation             | D decisions + ops registry; events/product P0s | Release code CODE_COMPLETE; **n8n MISSING** (MR-W01)     |
| Ticket issuance for paid events                         | Events strategy + ops                          | APIs PARTIAL; **n8n MISSING** (MR-W02)                   |
| WhatsApp → SMS → email outbox (not Realtime-as-primary) | D15                                            | Dispatch workflow live; volume unproven                  |
| Manual Lusaka dispatch + nationwide pickup              | D16                                            | Admin UX honesty CODE_COMPLETE (#290)                    |
| COD ≤ K500                                              | D decisions; master Q25 VERIFIED pattern       | Schema/config; unexercised                               |
| English-first launch; vernacular follow                 | D27                                            | EN live; Bemba/Nyanja P1                                 |
| Invite / `public_launch` gate until ready               | Live flag `public_launch=false` VERIFIED       | Keep until P0 gates pass                                 |
| KYC-backed privileged vendor capabilities               | Trust model; blueprint BL-P0-05                | CODE_COMPLETE (#293); migration/rollout open             |
| RLS on money/PII tables; admin Access                   | Security conventions                           | PARTIAL (FORCE RLS gaps; role hook unapplied)            |
| Monitoring, backups, rollback evidence                  | Roadmap W8 / ops gates                         | MISSING / NOT_AUDITABLE                                  |
| Legal counsel on DPA / NPS escrow posture               | SFQ F4 / SFQ-04                                | NOT_AUDITABLE (MR-L01)                                   |

---

## 3. Conflict register with resolution stance

### 3.1 Stack / provider conflicts → SUPERSEDED (DOC)

| ID             | Document claim                  | Locked / live                               | Sources                                                 | Founder action needed?                                            |
| -------------- | ------------------------------- | ------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------- |
| C-STACK-BE     | Django + DRF                    | FastAPI + Supabase                          | blueprint F003; master Q9; sfq E1; roadmap F003         | No — confirm SoT banners                                          |
| C-STACK-SEARCH | Meilisearch                     | Postgres FTS/trgm/pgvector RRF (D22)        | events F025; product F018; master Q15; roadmap F006     | No — fix doc copy (MR-L02); improve search quality separately     |
| C-STACK-HOST   | Railway/Render                  | OCI/Hetzner + Caddy + Cloudflare + Supabase | master Q11; roadmap F004                                | No                                                                |
| C-STACK-ASYNC  | Celery + Redis/Upstash          | n8n + outbox                                | blueprint F006; master Q17–18; sfq E8; roadmap F007–008 | No                                                                |
| C-STACK-NOTIF  | Supabase Realtime notifications | WhatsApp/SMS/email outbox                   | blueprint F005; master Q14                              | No                                                                |
| C-PAY-PROVIDER | DPO / DPO+Lenco                 | Lenco only (D11)                            | roadmap F005; master Q19; sfq E2                        | **Confirm once** in writing that DPO is abandoned (roadmap BL-01) |
| C-LOGISTICS    | Yango API / own fleet           | Manual Lusaka + pickup (D16)                | blueprint F036; master Q43/47; sfq E5                   | No — keep courier labels as book+paste only                       |
| C-RETURNS      | “No returns MVP”                | Two-lane returns (D17)                      | master Q48                                              | No — mark master plan stale                                       |
| C-BRAND        | Convergeo/Vergio spelling drift | Vergeo5 live                                | blueprint F001; roadmap F001                            | Hygiene only                                                      |

### 3.2 Genuine gaps / conflicts needing product or ops work

| ID            | Conflict                                                    | Gap type                        | Owner            | Blocks                    |
| ------------- | ----------------------------------------------------------- | ------------------------------- | ---------------- | ------------------------- |
| C-MIG-DRIFT   | Live DB ≠ git (`0051`, `0053`–`0056`; `0052` key skew)      | Ops/DB                          | DB/Ops           | G0, G9, KYC/role features |
| C-DEMO-PUBLIC | Public demo catalogue vs D25 / real-marketplace positioning | Merch + eng                     | Founder/Merch    | G11, public positioning   |
| C-KYC-TIER    | Live orphaned tiers vs auditable KYC requirement            | Data + rollout                  | Ops + API        | G12; privileges           |
| C-CONDITION   | Used/open-box brief vs `new\|refurbished` CHECK             | Schema (if used goods in scope) | Product          | Class D launch only       |
| C-ESCROW-HOLD | 72h used vs flat 48h                                        | Config (if used goods)          | Product/Payments | Class D launch only       |
| C-EVENT-TYPE  | `multi_day` vs live four types                              | Product decision                | Founder/Product  | Events taxonomy honesty   |

### 3.3 Open founder / business decisions (do not invent)

| Decision ID | Question                                   | Options                                                                                            | Why it matters                    | Related MR / gate      |
| ----------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------- | --------------------------------- | ---------------------- |
| **FD-01**   | Zamtel collections at launch?              | (a) Keep off (`zamtel_collections=false`) + hide UI (b) Pursue F9a then enable                     | Checkout honesty; C-PAY-ZAMTEL    | MR-L04; G14            |
| **FD-02**   | Admin RBAC model                           | (a) Single `admin` + Access (supersede roadmap superadmin/moderator) (b) Additive roles + RLS + UI | Authz matrix; avoid fabricated UI | MR-A02; G15; ADM-01    |
| **FD-03**   | Role provisioning path                     | (a) Apply `0051` + Auth custom access token hook (b) Written manual-grant exception                | JWT/role consistency              | MR-S02; G0             |
| **FD-04**   | Demo catalogue posture before public money | (a) Label demo (b) Exclude from public search (c) Replace via controlled import                    | Trust/SEO                         | MR-D01; G11; CUST-02   |
| **FD-05**   | Event type `multi_day`                     | (a) Add enum (b) Accept `standard` + `ends_at` and update docs                                     | Schema/UI honesty                 | MR-S08; events BL-007  |
| **FD-06**   | Phase-1 catalogue scope                    | (a) Class A branded/new only (b) Claim A–E / used goods (triggers MR-S05/S06/V05)                  | Prevent false product claims      | MR-S05/S06             |
| **FD-07**   | FORCE RLS on ticket tier tables            | (a) Enable `relforcerowsecurity` (b) Signed security exception                                     | Ticket money isolation            | MR-R01; G0             |
| **FD-08**   | Legal counsel sign-off                     | Engage counsel; record written DPA/NPS escrow posture                                              | Real-money legality               | MR-L01; G13            |
| **FD-09**   | DPO abandonment confirmation               | Confirm Lenco-only supersedes roadmap DPO                                                          | Stop dual-provider thrash         | C-PAY-PROVIDER; MR-L03 |
| **FD-10**   | Vendor staff RBAC in v1?                   | Default **OUT** (VEND-10); reverse only via ADR                                                    | Scope control                     | MR-V06                 |
| **FD-11**   | When to flip `public_launch=true`          | Only after release-gates GO                                                                        | Open marketplace                  | G10–G16                |
| **FD-12**   | Orphaned KYC repair policy                 | Manual controlled repair only (never auto-upgrade) — confirm ops ownership                         | Matches #293 non-actions          | MR-D02                 |

---

## 4. Document-by-document SoT notes

| Document audit                                  | Treat as                                                    | Primary conflicts                                          | Use for                                            |
| ----------------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------- |
| `convergeo-events-strategy`                     | Requirements/spec (rank-4 intent) with many PARTIAL/MISSING | `multi_day`; Meilisearch wording; FORCE RLS                | Events Phase backlog after money gates             |
| `convergeo-product-strategy-april-2026`         | Requirements/spec                                           | condition enum; product_class; Meilisearch; vendor targets | Catalogue Phase-1 scope decisions                  |
| `blueprint-zambia-vergeo-super-app`             | Derivative TurboScribe / wireframes — **non-authoritative** | Django/Celery/Yango/traction numbers                       | UX inspiration only; never seed to match           |
| `strategic-master-plan-v1`                      | Pre-lock founder plan — often superseded                    | Stack, DPO, languages, returns                             | Historical context; cite `00-decisions` instead    |
| `strategic-foundation-questionnaire-april-2026` | Blank questionnaire + prompts                               | Same stack conflicts; legal NOT_AUDITABLE                  | Decision checklist (SFQ→D mapping)                 |
| `convergeo-60-day-development-roadmap`          | Early plan at 0% — not a completion record                  | Entire early stack                                         | Ops gate reminders (payments, monitoring, backups) |

---

## 5. Decision log template (for founder responses)

Record answers here (or in `00-decisions.md`) — do not leave as tribal knowledge:

```text
FD-XX:
  decision:
  date:
  decided_by:
  supersedes:
  engineering impact:
  related MR-IDs:
  related gates:
```

---

## 6. Explicit non-decisions (agents must not invent)

1. Do not invent superadmin/moderator roles without FD-02.
2. Do not enable Zamtel collections without FD-01 + technical proof.
3. Do not expand condition/`product_class` for launch marketing without FD-06.
4. Do not treat blueprint GMV/vendor projections as targets to seed.
5. Do not mark legal posture PASS without a written counsel artifact (FD-08).
6. Do not claim STAGING_VERIFIED / PRODUCTION_VERIFIED from CODE_COMPLETE merges alone.

---

_When a conflict is resolved, update this file and the conflict ledger in `master-reconciliation-register.md` §0 in the same docs PR._

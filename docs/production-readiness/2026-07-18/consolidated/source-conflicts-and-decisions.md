# Source Conflicts and Founder Decisions — Vergeo5 / Convergeo

**Date:** 2026-07-18  
**Role:** Audit Consolidation Lead  
**Mode:** Documentation only  
**Authority order:** Live evidence (rank-1) → `docs/plan/00-decisions.md` D1–D28 (rank-2) → foundation/register (rank-3) → strategy PDFs/transcripts (rank-4 intent only)

This file separates **document conflicts** (do not engineer against) from **open founder/business decisions** (Cursor must not invent). Companion: `master-reconciliation-register.md` §0.

---

## 1. How to use this file

| Stance                | Meaning                                       | Engineering action                                      |
| --------------------- | --------------------------------------------- | ------------------------------------------------------- |
| **DOC_SUPERSEDED**    | Strategy doc obsolete vs locked decisions     | Banner / annotate docs; **do not build** obsolete stack |
| **PRODUCTION_AHEAD**  | Live/locked ahead of early doc                | Update doc; keep production behaviour                   |
| **OPEN_FOUNDER**      | Requires human business/legal decision        | Block feature enablement until recorded                 |
| **OPEN_PRODUCT**      | Product/scope decision (may be founder or PM) | Scope-gate P0s; do not silently expand Phase-1          |
| **GENUINE_GAP**       | Doc/live conflict that is a real defect       | Tracked as MR-* with evidence ladder                    |
| **WIREFRAME_FICTION** | Illustrative numbers/UX not claims            | Never seed; never publish as live metrics               |

---

## 2. Stack & architecture conflicts (DOC_SUPERSEDED)

Do **not** open infra tickets to “restore” these. SoT: D18–D24.

| ID             | Document claim                                     | Locked / live value                               | Sources                                                 | Stance           | Owner                               |
| -------------- | -------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------- | ---------------- | ----------------------------------- |
| C-STACK-BE     | Django + DRF                                       | FastAPI + Supabase (D18)                          | blueprint F003; master Q9; sfq E1; roadmap F003         | DOC_SUPERSEDED   | —                                   |
| C-STACK-SEARCH | Meilisearch (+pgvector)                            | Postgres FTS + pg_trgm + pgvector RRF (D22)       | events F025; product F018; master Q15; roadmap F006     | DOC_SUPERSEDED   | Search quality = MR-B07 (separate)  |
| C-STACK-HOST   | Railway / Render                                   | OCI/Hetzner + Caddy + Supabase + Cloudflare (D21) | master Q11; roadmap F004                                | DOC_SUPERSEDED   | —                                   |
| C-STACK-ASYNC  | Celery + Redis / Upstash                           | n8n + outbox (D18/D21)                            | blueprint F006; master Q17–18; sfq E8; roadmap F007–008 | DOC_SUPERSEDED   | —                                   |
| C-STACK-NOTIF  | Supabase Realtime notifications                    | WhatsApp → SMS → email outbox (D15)               | blueprint F005; master Q14                              | DOC_SUPERSEDED   | —                                   |
| C-PAY-PROVIDER | DPO Pay / DPO+Lenco                                | **Lenco only** (D11); 0 DPO code refs             | roadmap F005; master Q19; sfq E2                        | DOC_SUPERSEDED   | Founder confirm once for doc banner |
| C-LOGISTICS    | Yango API + own fleet / 10-province ship           | Manual Lusaka dispatch + nationwide pickup (D16)  | blueprint F036; master Q43/47; sfq E5                   | DOC_SUPERSEDED   | Copy audit CUST-07                  |
| C-LAYOUT       | `*-app/` dirs / `AI_CONTEXT.md`                    | `apps/*` + `CLAUDE.md`                            | roadmap; master                                         | DOC_SUPERSEDED   | —                                   |
| C-RETURNS      | “No returns MVP” (master plan)                     | Two-lane returns (D17)                            | master Q48                                              | PRODUCTION_AHEAD | Doc stale                           |
| C-PHASE1-SCOPE | Master plan excludes Events/directory/AI/RFQ/Lenco | v1 **includes** (D2)                              | master                                                  | PRODUCTION_AHEAD | Doc stale                           |
| C-BRAND        | Convergeo / Vergio / Virgeo / Convergio            | Live **Vergeo5** (`vergeo5.com`)                  | blueprint F001; roadmap F001                            | DOC_SUPERSEDED   | Naming hygiene                      |
| C-BUDGET       | $62/mo ceiling (some docs)                         | $50/mo ceiling (locked)                           | master                                                  | DOC_SUPERSEDED   | —                                   |

**Required doc hygiene (P2, MR-L02/L03):** Add “SUPERSEDED — see `docs/plan/00-decisions.md`” banners to Master Plan, Blueprint transcript, 60-day roadmap, and Product Strategy Meilisearch claims. Annotate DPO as superseded by D11.

---

## 3. Open founder / business decisions (do not invent)

| Decision ID                                | Question                                      | Options                                                                                | Current evidence                                                   | Blocks                        | Recommended default (non-binding)                               |
| ------------------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------- | --------------------------------------------------------------- |
| **FD-ZAMTEL** (C-PAY-ZAMTEL / F9a)         | Enable Zamtel collections at launch?          | (a) Keep OFF / payout-only until proven (b) Enable when Lenco ready                    | Flag `zamtel_collections=false`; roadmap claims launch collections | G14, MR-L04, checkout methods | **(a)** hide Zamtel at checkout until F9a VERIFIED              |
| **FD-ADMIN-ROLES** (C-ADMIN-ROLES)         | Require superadmin + moderator?               | (a) Supersede roadmap; single `admin` + Access (b) Additive roles + RLS + UI           | CHECK `customer\|vendor\|admin` only                               | G15, ADM-01/02, MR-A02        | Founder must choose; Cursor must not expand CHECK without ADR   |
| **FD-LEGAL** (MR-L01 / F4)                 | DPA + NPS Act 2026 escrow counsel sign-off?   | Written sign-off path only                                                             | NOT_AUDITABLE — no artifact                                        | G13, real-money GO            | **Block real money** until written artifact                     |
| **FD-DEMO-MERCH** (MR-D01 / C-DEMO-PUBLIC) | How to treat 134 demo listings publicly?      | (a) Label demo banner (b) Exclude from public search (c) Replace via controlled import | All public images `demo/`; D25 intent conflict                     | G11, CUST-02                  | **(a) or (b)** before any marketing push; never seed fake scale |
| **FD-PUBLIC-LAUNCH**                       | Flip `public_launch=true`?                    | Keep false until P0 pack PASS                                                          | Flag false VERIFIED                                                | Open launch                   | Keep **false**                                                  |
| **FD-PREPAID-ENABLE**                      | Enable live prepaid collections?              | Keep kill-switch OFF until G3/G4/G5/G12/G13 prod PASS                                  | 0 payments; #274/#294 code-only                                    | Real-money GO                 | Keep **OFF**                                                    |
| **FD-SELLER-CTA-ENV**                      | Set `NEXT_PUBLIC_VENDOR_APP_URL`?             | Set to `https://vendor.vergeo5.com`                                                    | CTA unavailable; fail-closed                                       | G10, CUST-01, MR-C01          | **Set + redeploy** (ops/founder)                                |
| **FD-SENTRY**                              | Create Vergeo5 Sentry projects + DSNs?        | Create / defer                                                                         | No Vergeo5 projects                                                | G6, MR-O01                    | Create before real money                                        |
| **FD-BRANCH-PROTECTION**                   | Require blocking secret-scan on `master`?     | Enable / accept risk                                                                   | `continue-on-error: true`                                          | G8, MR-R05                    | Enable before real money                                        |
| **FD-ACCESS-AUDITOR**                      | Grant Cloudflare Access for admin deep audit? | Approve auditor                                                                        | Admin NOT_AUDITABLE deep UI                                        | ADM-10, MR-A06                | Approve for audit pack                                          |

Cursor agents **must stop** and surface these IDs rather than inventing policy.

---

## 4. Open product / scope decisions

| Decision ID          | Question                                    | Options                                       | Sources                  | Blocks if claimed             | Stance                                    |
| -------------------- | ------------------------------------------- | --------------------------------------------- | ------------------------ | ----------------------------- | ----------------------------------------- |
| **PD-EVENT-TYPE**    | Add `multi_day` event type?                 | (a) Add enum (b) Accept `standard`+`ends_at`  | events F006 / BL-007     | Schema churn                  | OPEN_PRODUCT — record in `00-decisions`   |
| **PD-PRODUCT-CLASS** | Launch claims Class A–E?                    | (a) Phase-1 Class A branded only (b) Full A–E | product RB-PS-001        | MR-S05 becomes hard P0 if (b) | Prefer **(a)** for launch                 |
| **PD-CONDITION**     | Expand condition beyond `new\|refurbished`? | Expand before Class D / keep Phase-1 new-only | product F009 / RB-PS-002 | MR-S06 hard P0 if used goods  | Prefer new-only until Class D             |
| **PD-USED-ESCROW**   | 72h escrow for used goods?                  | Config path vs flat 48h                       | product F010             | MR-B02                        | Only if used goods enabled                |
| **PD-PRODUCT-RFQ**   | Product quote-only vs reuse services RFQ?   | Dedicated vs reuse                            | product F034             | API design                    | OPEN_PRODUCT                              |
| **PD-FX**            | Multi-currency / FX peg now?                | Defer (ZMW-only) vs seam now                  | product F008; sfq E4     | Scope                         | **Defer** (locked ZMW ngwee)              |
| **PD-VERNACULAR**    | Bemba/Nyanja at launch?                     | EN-only (D27) vs early vernacular             | sfq E3; `0053` unapplied | i18n rollout                  | **D27 holds** — vernacular P1 after money |
| **PD-FREE-TIER-CAP** | Free listing cap 20 vs 30?                  | Align to D3                                   | master vs D3             | Pricing copy                  | Follow **D3**                             |
| **PD-TOP-TIER-NAME** | Platinum vs Gold top tier?                  | Naming only                                   | master                   | Marketing                     | Follow locked naming                      |
| **PD-CO-ORG**        | Co-organiser Owner/Manager/Door in v1?      | Ship / defer                                  | events BL-008            | MR-S09/V06                    | Defer unless events GTM requires Door     |

---

## 5. Genuine gaps (not “doc wrong”)

These are real production defects or unproven committed requirements — tracked in the master register, not resolvable by doc banners alone.

| ID                | Conflict / gap                                         | Register        | Evidence ladder note                                         |
| ----------------- | ------------------------------------------------------ | --------------- | ------------------------------------------------------------ |
| C-MIG-DRIFT       | Live DB ≠ git tip (`0051`, `0053`–`0056`; `0052` skew) | MR-S01          | GENUINE_GAP — backup then apply                              |
| C-KYC-TIER        | Live `kyc_tier=2` with `kyc_records=0`                 | MR-D02          | Live VERIFIED; **code DONE** #293 — migrate/repair remaining |
| C-DEMO-PUBLIC     | Public demo catalogue vs D25 intent                    | MR-D01          | GENUINE_GAP + FD-DEMO-MERCH                                  |
| C-FORCE-RLS       | FORCE RLS false on ticket allocation/price tiers       | MR-R01          | GENUINE_GAP or signed exception                              |
| Money unproven    | Prepaid/release unproven live despite #274/#294        | MR-B01, MR-B01b | Code DONE; staging/prod FAIL                                 |
| Workflows missing | Escrow release + tickets-issue not live                | MR-W01, MR-W02  | Repo JSON ≠ production                                       |

---

## 6. Aspiration vs committed production requirement

### Committed for real-money / events launch (must clear gates)

- Prepaid MoMo/card → ledger → escrow hold → release accounting → payout path
- Escrow auto-release + ticket issuance automations (for claimed scopes)
- KYC auditable trail (no bare-tier privilege)
- Migration parity + RLS posture decided
- Monitoring, backup/restore, rollback evidence
- Legal F4 before real money
- Invite gate / `public_launch=false` until GO
- Lenco-only; COD ≤K500; ZMW ngwee; manual Lusaka dispatch
- Demo honesty (label or exclude)

### Strategic aspiration (Phase 2+ / wireframe — not launch defects)

| Aspiration                                                       | Sources            | Treatment                      |
| ---------------------------------------------------------------- | ------------------ | ------------------------------ |
| 75–100 / 840 vendors; 12.4k products; K184k GMV                  | product; blueprint | WIREFRAME_FICTION — never seed |
| Class C produce, Class D salaula/used vehicles, Class E MTO      | product            | ASPIRATION until PD-*          |
| PWYW, promo/affiliate, high-value ID-match, venue comps          | events             | ASPIRATION                     |
| City Guides, Tier3 API monetisation, own logistics, Yango        | blueprint; master  | OUT v1                         |
| Subscription billing, referrals, promoted listings, AR, Zimbabwe | master             | Deferred by decision           |
| Super-app airtime/bills, vendor financing, retail-chain pickup   | sfq                | Deferred                       |
| Meilisearch, Django, Celery, DPO, Railway                        | multiple           | DOC_SUPERSEDED                 |
| International concerts / pre-event verification calls >K100k     | events             | ASPIRATION                     |

---

## 7. Decision log template (for founder)

When a decision closes, append a row here and update `00-decisions.md` if durable:

| Date                               | Decision ID | Choice | Artifact | Closes |
| ---------------------------------- | ----------- | ------ | -------- | ------ |
| _(none closed this consolidation)_ | —           | —      | —        | —      |

Example:

```text
| 2026-07-XX | FD-ZAMTEL | Keep OFF until F9a sandbox proven | ADR-00X / decisions note | G14 |
```

---

## 8. Explicit non-decisions for agents

1. Do not choose admin two-tier roles without **FD-ADMIN-ROLES**.
2. Do not enable Zamtel collections without **FD-ZAMTEL**.
3. Do not expand condition/`product_class` without **PD-CONDITION** / **PD-PRODUCT-CLASS**.
4. Do not flip `public_launch` or prepaid kill-switch without gate pack + founder.
5. Do not treat TurboScribe Blueprint GMV or Mulenga Fashion tiles as requirements.
6. Do not “fix” stack CONFLICTS by rebuilding Django/Meilisearch/DPO.

---

_Related:_ `master-reconciliation-register.md` · `release-gates.md` · `implementation-wave-plan.md` · `docs/plan/00-decisions.md`

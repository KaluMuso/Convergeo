# Founder Decision Brief — FD-01 through FD-12

**Date:** 2026-07-19  
**Audience:** Kaluba (founder)  
**Source:** `source-conflicts-and-decisions.md` §3.3 (OPEN DECISION only)  
**Related:** `release-gates.md` · `master-reconciliation-register.md` §0 · locked product decisions in `docs/plan/00-decisions.md`

## How to use this brief

- Each item is an **open business decision**. Engineering must not invent answers.
- **Recommended** options below are engineering/ops leanings grounded in locked decisions (D11, D16, D25, F4/F9a) and live evidence — **not** recorded founder decisions.
- After you choose, log the answer with the template in `source-conflicts-and-decisions.md` §5 (and update `00-decisions.md` where it supersedes product scope).
- Strategic aspirations (vendor GMV targets, Class A–E catalogue, Yango fleet, etc.) remain **ASPIRATION** unless you explicitly elevate them here — they are not treated as committed launch features in this brief.

### Blocking legend

| Level               | Meaning                                                                       |
| ------------------- | ----------------------------------------------------------------------------- |
| **Staging**         | Blocks safe staging schema/authz/money drills (S0–S6 / G0)                    |
| **Controlled beta** | Blocks real-money invite/beta (P0 gates G0–G9 + G13 legal)                    |
| **Open launch**     | Blocks flipping `public_launch=true` / open marketplace positioning (G10–G17) |

### At-a-glance

| ID    | Topic                        | Recommended lean                | Blocks                         | Decide by          |
| ----- | ---------------------------- | ------------------------------- | ------------------------------ | ------------------ |
| FD-01 | Zamtel collections           | Keep off + hide UI              | Open launch (G14); honesty     | 2026-07-24         |
| FD-02 | Admin RBAC model             | Single `admin` + Access         | Open launch (G15)              | 2026-07-31         |
| FD-03 | Role provisioning path       | Apply `0051` + Auth hook        | Staging + controlled beta (G0) | 2026-07-22         |
| FD-04 | Demo catalogue posture       | Exclude from public search      | Open launch (G11); trust       | 2026-07-24         |
| FD-05 | Event type `multi_day`       | Accept `standard` + `ends_at`   | Open launch (events honesty)   | 2026-07-31         |
| FD-06 | Phase-1 catalogue scope      | Class A branded/new only        | Open launch (catalogue claims) | 2026-07-31         |
| FD-07 | FORCE RLS on ticket tiers    | Enable `relforcerowsecurity`    | Staging + controlled beta (G0) | 2026-07-22         |
| FD-08 | Legal counsel sign-off       | Engage counsel; written posture | Controlled beta + open launch  | 2026-07-29         |
| FD-09 | DPO abandonment              | Confirm Lenco-only (D11)        | Doc thrash / payment messaging | 2026-07-22         |
| FD-10 | Vendor staff RBAC in v1      | Keep **OUT**                    | None if OUT stays              | 2026-07-31         |
| FD-11 | When to flip `public_launch` | Only after release-gates GO     | Open launch only               | After G10–G17 PASS |
| FD-12 | Orphaned KYC repair policy   | Manual controlled repair only   | Controlled beta + open (G12)   | 2026-07-29         |

---

## FD-01 — Zamtel collections at launch?

**Question requiring Kaluba’s decision:**  
At launch / controlled beta, should Vergeo5 offer **Zamtel as a collection (pay-in) rail**, or keep collections limited to rails that are proven in the Lenco contract and live flag posture?

**Why it matters:**  
Live flag is `zamtel_collections=false`. Lenco distilled docs treat Zamtel collections as unverified (F9a); payouts may still include Zamtel. Showing Zamtel in checkout without a working rail is a **false-success / honesty** failure (MR-L04, G14, C-PAY-ZAMTEL).

**Options (mutually exclusive):**

1. **Keep off** — leave `zamtel_collections=false` and ensure checkout/API hide Zamtel collections until F9a proves support.
2. **Pursue F9a then enable** — obtain written Lenco confirmation + sandbox proof, then flip flag and ship UI/API method.
3. **Market Zamtel now, enable later** — _(rejected by gates)_ claim the rail in copy while flag stays off.

**Recommended:** Option **1**. Matches live config, D11 “build what Lenco proves,” and avoids checkout lies. Option 2 remains the path **after** F9a — do not schedule UI work until confirmation exists. Option 3 must not be chosen.

**Affected components:**

| Surface  | Impact                                                   |
| -------- | -------------------------------------------------------- |
| Customer | Checkout payment-method list / MoMo rail labels          |
| Vendor   | Payout destination copy (Zamtel payout ≠ collection)     |
| Admin    | Feature-flag display honesty                             |
| API      | Payment method eligibility gated on `zamtel_collections` |

**Blocks:** **Open launch** (G14). Does **not** block staging money drills on MTN/Airtel/card. Soft-blocks controlled-beta marketing that claims “all Zambian MoMo.”

**Decide by:** **2026-07-24** (before checkout method freeze for beta UAT).

---

## FD-02 — Admin RBAC model

**Question requiring Kaluba’s decision:**  
Is v1 admin authorization a **single `admin` role** behind Cloudflare Access, or do we need **additive roles** (e.g. roadmap superadmin/moderator) with RLS + admin UI?

**Why it matters:**  
Live schema CHECK is single `admin`. Roadmap language about superadmin/moderator is **not** implemented. Fabricating role-management UI without a decision creates false security (MR-A02, G15, ADM-01). Agents are forbidden from inventing roles without this decision.

**Options (mutually exclusive):**

1. **Single `admin` + Access** — supersede roadmap multi-tier admin for v1; rely on Cloudflare Access + existing `admin` role for all privileged ops.
2. **Additive roles + RLS + UI** — define moderator/superadmin (or equivalent), migrate CHECK/RLS, ship grant/revoke API + admin UI, expand authz matrix tests.
3. **Defer naming; keep Access-only with no in-app roles** — Access gate only, no `user_roles` admin path _(weaker; conflicts with API role checks already in use)._

**Recommended:** Option **1** for v1. Lowest authz surface, matches live CHECK, unblocks admin honesty work without inventing CRUD. Choose 2 only if you need least-privilege human operators before open launch (larger eng + RLS cost).

**Affected components:**

| Surface  | Impact                                                      |
| -------- | ----------------------------------------------------------- |
| Customer | None directly                                               |
| Vendor   | None directly (vendor staff is FD-10)                       |
| Admin    | Users/roles UI presence or absence; KYC/dispute actor model |
| API      | Role CHECK, RLS policies, admin router authz matrix         |

**Blocks:** **Open launch** (G15). Staging KYC drills can proceed with a single Access-protected admin tester if option 1 is chosen. Option 2 blocks ADM-01/02 implementation until specified.

**Decide by:** **2026-07-31** (before any admin role UI or open-launch ops staffing).

---

## FD-03 — Role provisioning path

**Question requiring Kaluba’s decision:**  
How should production/staging JWTs carry roles — **apply migration `0051` + Supabase Auth custom access token hook**, or run under a **written manual-grant exception**?

**Why it matters:**  
`0051` and the Auth hook are **unapplied/absent** live (MR-S02, G0). Without a consistent path, customer/vendor/admin isolation tests and staging role drills are not trustworthy. This is a staging schema/auth decision, not a product feature wish.

**Options (mutually exclusive):**

1. **Apply `0051` + enable Auth custom access token hook** — JWT claims match `user_roles`; isolation tests become the source of truth.
2. **Written manual-grant exception** — document who grants roles how, expiry, residual risk; accept no hook until a later date.
3. **Leave undefined** — continue ad-hoc grants with no ADR _(not acceptable for G0 PASS)._

**Recommended:** Option **1**, sequenced after backup proof and staging-first apply (MR-S01). Use option 2 only if staging apply is blocked by Access/Auth constraints you accept in writing with an expiry.

**Affected components:**

| Surface  | Impact                                                           |
| -------- | ---------------------------------------------------------------- |
| Customer | Session role claims for buyer flows                              |
| Vendor   | Vendor JWT / capability gates                                    |
| Admin    | Admin role presence in JWT; Access still required                |
| API      | Auth dependencies, RLS `auth.jwt()` role reads, isolation suites |

**Blocks:** **Staging** (S0/S5 role drills) and **controlled beta** (G0). Not itself the open-launch flip.

**Decide by:** **2026-07-22** (before agreed migration apply order for `0051`).

---

## FD-04 — Demo catalogue posture before public money

**Question requiring Kaluba’s decision:**  
What must be true of the **demo catalogue** (live: demo vendors / `demo/%` imagery) before broader public positioning or real-money traffic?

**Why it matters:**  
D25 already requires demo inventory to be **clearly flagged and excluded from public search**. Today the demo catalogue can be mistaken for a real marketplace (MR-D01, G11, CUST-02) — trust and SEO risk.

**Options (mutually exclusive):**

1. **Label demo** — disclosure banners / badges on demo vendors and listings; remain in search/browse.
2. **Exclude from public search** — remove demo inventory from public discovery/search (aligns with D25 exclusion); pitch/demo routes may still show labelled fixtures.
3. **Replace via controlled import** — remove or replace demo rows with reviewed real (or clearly sandbox) inventory before public positioning.

**Recommended:** Option **2** as the launch posture (matches D25). Option 1 alone is weaker if demo still ranks in search. Option 3 is best long-term merch quality but is a heavier ops path — use after 2 if you want zero demo rows in prod.

**Affected components:**

| Surface  | Impact                                                        |
| -------- | ------------------------------------------------------------- |
| Customer | PLP/search/home/SEO; disclosure UI                            |
| Vendor   | Demo vendor accounts / listing visibility                     |
| Admin    | Merch tools; flags; possible import review                    |
| API      | Search filters, listing visibility rules, seed/import scripts |

**Blocks:** **Open launch** (G11). Invite/demo browse can continue with `public_launch=false`, but **trust/SEO** still wants a decision before wider promotion.

**Decide by:** **2026-07-24** (before invite-beta positioning beyond internal demo).

---

## FD-05 — Event type `multi_day`

**Question requiring Kaluba’s decision:**  
Should the product claim a distinct **`multi_day` event type**, or treat multi-day schedules as **`standard` (or existing types) plus `ends_at`**?

**Why it matters:**  
Events strategy docs mention five types including `multi_day`; live CHECK is four types (`standard|recurring|free_rsvp|private`) (MR-S08, C-EVENT-TYPE). Schema/UI/docs must not disagree.

**Options (mutually exclusive):**

1. **Add `multi_day` enum** — additive migration + vendor/admin/customer copy for a fifth type.
2. **Accept `standard` + `ends_at`** — update strategy docs; no enum change; multi-day is a date-range of an existing type.
3. **Ship UI copy for `multi_day` without schema** — _(rejected)_ label without CHECK support.

**Recommended:** Option **2** for Phase-1. Avoids schema churn before paid-events money/n8n gates (MR-W01/W02). Elevate to option 1 only if organisers cannot describe multi-day events honestly with `ends_at`.

**Affected components:**

| Surface  | Impact                                      |
| -------- | ------------------------------------------- |
| Customer | Events discovery filters / event detail     |
| Vendor   | Organiser create/edit event type picker     |
| Admin    | Events moderation labels                    |
| API      | Event type CHECK, OpenAPI enums, validators |

**Blocks:** **Open launch** honesty for events taxonomy. Does **not** block staging prepaid/ledger drills. Does **not** make five event-type aspirations a committed launch feature.

**Decide by:** **2026-07-31** (before public events marketing claims).

---

## FD-06 — Phase-1 catalogue scope

**Question requiring Kaluba’s decision:**  
Is Phase-1 catalogue marketing limited to **Class A branded/new goods**, or do we **claim Classes A–E / used goods** at launch?

**Why it matters:**  
Product-strategy A–E classes and rich used-goods evidence are largely **ASPIRATION** relative to live schema (`condition` CHECK `new|refurbished`; no `product_class`) (MR-S05/S06). Claiming used/open-box breadth without schema triggers false product claims. Locked OUT list already excludes salaula / used phones / etc.

**Options (mutually exclusive):**

1. **Class A branded/new only** — Phase-1 scope; do not expand condition/`product_class` for launch marketing; used/Class D remains post-v1 unless separately elevated.
2. **Claim A–E / used goods for launch** — accept triggers MR-S05/S06/V05 (schema, evidence, facets, escrow-hold rules such as C-ESCROW-HOLD).
3. **Silent mismatch** — market A–E while schema stays narrow _(rejected by honesty gates)._

**Recommended:** Option **1**. Protects trust and matches current CHECK + D8 category constraints. Option 2 is a deliberate scope elevation with explicit eng cost — not an implied commitment from strategy PDFs.

**Affected components:**

| Surface  | Impact                                                         |
| -------- | -------------------------------------------------------------- |
| Customer | Facets, PDP condition copy, category promises                  |
| Vendor   | Listing create condition/class fields; evidence uploads        |
| Admin    | Moderation rules for used goods                                |
| API      | Schema CHECKs, search facets, escrow hold config if used goods |

**Blocks:** **Open launch** catalogue claims. Class D / used-goods path only if option 2 is chosen. Does not block MTN/Airtel sandbox money drills.

**Decide by:** **2026-07-31** (before public catalogue positioning beyond Class A / new+refurbished).

---

## FD-07 — FORCE RLS on ticket tier tables

**Question requiring Kaluba’s decision:**  
Must `ticket_type_instances` and `ticket_type_price_tiers` run with **`relforcerowsecurity = true`**, or do you accept a **signed security exception**?

**Why it matters:**  
Live inventory shows FORCE RLS **false** on those ticket money tables while most money/PII tables force RLS (MR-R01, G0). Ticket price/allocation isolation is a real-money boundary for paid events.

**Options (mutually exclusive):**

1. **Enable FORCE RLS** — set `relforcerowsecurity` true; fix any broken service-role/table-owner assumptions; re-run advisor + isolation tests.
2. **Signed security exception** — written residual-risk acceptance with owner, expiry, and compensating controls (why table owner bypass is required).
3. **Ignore until after launch** — _(rejected for G0 PASS)._

**Recommended:** Option **1**, unless a staging prove-out shows a hard platform constraint that only option 2 can cover. Prefer fixing policies over waiving money-table FORCE RLS.

**Affected components:**

| Surface  | Impact                                                             |
| -------- | ------------------------------------------------------------------ |
| Customer | Ticket purchase paths (indirect)                                   |
| Vendor   | Organiser ticket tier management                                   |
| Admin    | Support queries on ticket tiers                                    |
| API / DB | RLS policies, service-role access patterns, events money isolation |

**Blocks:** **Staging** (G0 evidence) and **controlled beta** (paid tickets / real money). Open launch inherits the same FAIL until closed.

**Decide by:** **2026-07-22** (with staging security review before money ticket drills).

---

## FD-08 — Legal counsel sign-off

**Question requiring Kaluba’s decision:**  
Will Vergeo5 obtain **written Zambian counsel posture** on DPA + NPS Act escrow (Lenco-held funds) **before** enabling real prepaid money, or accept that real-money beta remains **NO-GO**?

**Why it matters:**  
F4 / SFQ-04 / MR-L01 / G13: legal is **NOT_AUDITABLE** without a written artifact. Engineering cannot mark legal PASS from code. This is a committed real-money gate, not a strategy aspiration.

**Options (mutually exclusive):**

1. **Engage counsel now** — obtain written DPA/NPS escrow posture; attach artifact to release evidence pack before real-money enablement.
2. **Defer real money** — keep prepaid collections disabled / sandbox-only until counsel delivers; no waiver.
3. **Founder waiver without counsel** — written time-boxed waiver accepting residual legal risk _(gates treat this as exceptional; still not a counsel PASS)._

**Recommended:** Option **1** (or 2 until 1 completes). Do **not** treat option 3 as clearing G13. Matches F4: counsel is a gate before real-money public use.

**Affected components:**

| Surface  | Impact                                                  |
| -------- | ------------------------------------------------------- |
| Customer | Escrow trust copy must match legal posture              |
| Vendor   | Settlement/payout expectations                          |
| Admin    | Dispute/refund policy references                        |
| API      | No code substitute — release pack `legal_signoff` field |

**Blocks:** **Controlled beta** (real money) and **Open launch** (G13). Does not block staging **sandbox** drills that never touch customer funds.

**Decide by:** **2026-07-29** (engagement kicked off earlier; written artifact required before any live prepaid enablement).

---

## FD-09 — DPO abandonment confirmation

**Question requiring Kaluba’s decision:**  
Do you **confirm in writing** that roadmap/master-plan **DPO / DPO+Lenco** language is abandoned, and **Lenco-only (D11)** is the sole payment provider for v1?

**Why it matters:**  
Older docs still mention DPO (C-PAY-PROVIDER, MR-L03). Dual-provider thrash wastes eng cycles and confuses checkout/ops. D11 already locks Lenco; this is a one-time founder confirmation so SoT banners can retire DPO as required.

**Options (mutually exclusive):**

1. **Confirm Lenco-only** — DPO abandoned for v1; annotate superseded docs; no DPO integration work.
2. **Re-open dual provider** — explicitly reverse/amend D11; accept provider-abstraction + dual ops cost before launch.
3. **Leave docs conflicting** — _(rejected)_ continue silent DPO mentions.

**Recommended:** Option **1**. Aligns with locked D11 and live Lenco-oriented code. Option 2 is a strategic reversal — only if you intend to fund dual-provider work.

**Affected components:**

| Surface  | Impact                                 |
| -------- | -------------------------------------- |
| Customer | Payment provider copy                  |
| Vendor   | Payout/provider messaging              |
| Admin    | Ops runbooks                           |
| API      | Payment adapter scope (no DPO adapter) |

**Blocks:** Does **not** hard-block staging sandbox. Soft-blocks clean **payment messaging** and doc SoT (MR-L03). Decide early to stop thrash.

**Decide by:** **2026-07-22** (written one-liner is enough).

---

## FD-10 — Vendor staff RBAC in v1?

**Question requiring Kaluba’s decision:**  
Does v1 include **vendor staff / multi-user RBAC** (invite staff, door roles beyond single owner), or does **single-owner vendor** remain the model?

**Why it matters:**  
Default is **OUT** (VEND-10, MR-V06). Panel work correctly shipped no staff UI. Reversing without an ADR recreates scope creep and authz surface before money gates are green.

**Options (mutually exclusive):**

1. **Keep OUT of v1** — single-owner vendor only; staff/co-organiser RBAC stays post-v1 (co-organiser schema remains separate events backlog).
2. **Reverse via ADR for v1** — write ADR, define roles, schema, API, vendor UI, tests; accept slip on other P0s.
3. **Partial UI without API** — _(rejected)_ invite screens without backend.

**Recommended:** Option **1**. Confirms existing OUT. Choose 2 only with a dated ADR and explicit trade-off against money/KYC/n8n P0s.

**Affected components:**

| Surface  | Impact                                             |
| -------- | -------------------------------------------------- |
| Customer | None                                               |
| Vendor   | Staff invite/roles UI (only if option 2)           |
| Admin    | Possible vendor-user support tools                 |
| API      | Vendor membership tables/routes (only if option 2) |

**Blocks:** **None** if option 1 stands. Option 2 becomes an open-launch (or pre-launch) scope adder — not a staging money blocker today.

**Decide by:** **2026-07-31** (confirm OUT in writing, or file ADR if reversing).

---

## FD-11 — When to flip `public_launch=true`

**Question requiring Kaluba’s decision:**  
Under what evidence condition may ops set **`public_launch=true`** (open marketplace), versus keeping the invite gate?

**Why it matters:**  
Live flag is `public_launch=false` (VERIFIED). Flipping early opens SEO/traffic against unfinished money, KYC, demo, and legal gates (G10–G16). This decision is a **release policy**, not a feature build.

**Options (mutually exclusive):**

1. **Only after release-gates GO** — require real-money beta GO + G10–G17 PASS per `release-gates.md` before flip.
2. **Flip for marketing while money stays off** — open browse/sign-up with prepaid still disabled and demo remediated — still requires G11/G10 honesty; does **not** equal real-money GO.
3. **Flip now** — _(rejected)_ while P0/P1 gates FAIL.

**Recommended:** Option **1** for true open launch. If you need broader browse earlier, treat option 2 as a **separate, explicit** “open browse / closed money” posture with written limits — never silently equate it to production-ready commerce.

**Affected components:**

| Surface  | Impact                                           |
| -------- | ------------------------------------------------ |
| Customer | Invite gate, discovery indexing, signup openness |
| Vendor   | Public acquisition funnel                        |
| Admin    | Flag toggle; beta invite tooling                 |
| API      | Feature-flag reads enforcing invite vs public    |

**Blocks:** **Open launch** only. Staging and controlled invite-beta should keep `public_launch=false`.

**Decide by:** **After G10–G17 PASS** (do not pre-schedule a calendar flip). Earliest responsible review checkpoint: **2026-08-15**, and only if gates are green.

---

## FD-12 — Orphaned KYC repair policy

**Question requiring Kaluba’s decision:**  
Who owns repair of live vendors with **`kyc_tier` set and `kyc_records` missing**, and do you confirm **manual controlled repair only** (never auto-upgrade)?

**Why it matters:**  
PR #293 freezes privileged capabilities without an auditable approved KYC record and reports orphans — it does **not** auto-heal data (MR-D02, G12). Without ops ownership, orphaned tiers linger and G12 cannot PASS after `0056` apply.

**Options (mutually exclusive):**

1. **Manual controlled repair only** — ops owns ticket-per-orphan: create proper KYC submission + guarded approve, or clear tier via guarded admin path; never `UPDATE vendors SET kyc_tier=…` without a record; never auto-upgrade.
2. **Automated upgrade/backfill** — scripts that set approved records or tiers without human review _(conflicts with #293 non-actions; rejected for trust)._
3. **Leave orphans indefinitely** — report-only forever _(blocks G12 / privileged vendor launch)._

**Recommended:** Option **1**, with named ops owner (founder or designee) before `0056` production apply. Matches KYC integrity report and blueprint trust model.

**Affected components:**

| Surface  | Impact                                                            |
| -------- | ----------------------------------------------------------------- |
| Customer | Storefront verification badges (honesty)                          |
| Vendor   | Capability freeze until auditable KYC                             |
| Admin    | Orphan report queue; guarded KYC transitions                      |
| API / DB | `0056` rollout; eligibility resolver; `/admin/kyc/orphaned-tiers` |

**Blocks:** **Controlled beta** (privileged vendor capabilities) and **Open launch** (G12). Staging S5 should exercise the same policy on staging data first.

**Decide by:** **2026-07-29** (before production `0056` apply / orphan repair window).

---

## Response log (fill after Kaluba decides)

Copy into `source-conflicts-and-decisions.md` §5 / `00-decisions.md` as appropriate:

```text
FD-XX:
  decision:
  date:
  decided_by: Kaluba
  supersedes:
  engineering impact:
  related MR-IDs:
  related gates:
```

## Explicit non-actions for agents (until decisions land)

1. Do not invent superadmin/moderator roles without FD-02.
2. Do not enable Zamtel collections without FD-01 + F9a technical proof.
3. Do not expand condition/`product_class` for launch marketing without FD-06.
4. Do not treat blueprint GMV/vendor projections as seed targets.
5. Do not mark legal posture PASS without a written counsel artifact (FD-08).
6. Do not flip `public_launch=true` without FD-11 conditions.
7. Do not auto-upgrade orphaned KYC tiers (FD-12).
8. Do not claim STAGING_VERIFIED / PRODUCTION_VERIFIED from CODE_COMPLETE merges alone.

---

_Source of open questions: `source-conflicts-and-decisions.md`. When Kaluba answers, update that file and the conflict ledger in `master-reconciliation-register.md` §0 in the same docs PR._

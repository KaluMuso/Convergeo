# Output 2 — Open Questions

**Date:** 2026-07-19 · **Companion:** `01-audit-findings.md`, `03-waves-and-phases.md`
**Principle:** never silently pick an interpretation. Each question states a **DEFAULT** to assume if forced to proceed,
so the wave plan is never stalled waiting on an answer. Most map to the already-documented **FD-01…FD-12**
(`../2026-07-18/consolidated/founder-decision-brief.md`); the recommended lean there is adopted as the default here.
New questions (B-5, NB-1, NB-6…NB-10) come from this audit's fresh live/Drive evidence.

---

## BLOCKING — answer before dispatching the affected wave (the answer changes plan scope/sequence)

### B-1 · Release strategy: staging-first vs controlled live-beta? *(NEW — from PR #302)* — ✅ **LOCKED 2026-07-19: HYBRID live-beta (`docs/plan/00-decisions.md` D30)**
- **Why:** `implementation-wave-plan.md` sequences everything through a **staging plane** (S0–S7). But open PR **#302
  (2026-07-19)** pivots to a **controlled customer live-beta with "staging provisioning PAUSED."** These are different
  spines: staging-first proves money in a sandbox stack before touching prod; live-beta hardens prod discovery honesty
  and defers money. The wave plan's ordering depends on which is authoritative.
- **Options:** (a) staging-first (prove S1–S6 on a separable stack, then promote); (b) live-beta-first (promote honest
  discovery to prod behind `public_launch=false`, keep money sandbox-only, stand up staging later); (c) hybrid.
- **DEFAULT (hybrid, recommended):** Adopt **live-beta for the no-money discovery surface** (promote #298/#302, fix
  categories, set vendor CTA env) **in parallel with** a **minimal Lenco *sandbox* money proof** that does **not**
  require a full separable staging stack (sandbox creds + a throwaway DB branch). Do **not** enable prod real money
  until S1–S6 pass somewhere isolated. This lets Wave 1 (deploy) and Wave 2 (money verify) run without waiting on a
  full staging plane. **Blocks:** sequencing of Waves 1–2.

### B-2 · Role provisioning path — apply `0051` + Auth hook, or written manual-grant exception? *(FD-03)*
- **Why:** `0051` (custom access token role hook) is **unapplied live**; JWT roles lag `user_roles`. G0 role-isolation
  can't be trustworthy until a path is chosen. Determines the content of the auth/security pebble.
- **DEFAULT (FD-03 rec):** **Apply `0051` + enable the Supabase Auth custom-access-token hook**, sequenced after a
  backup and staging-first apply. Fall back to a written, time-boxed manual-grant exception only if Auth-dashboard
  access blocks the hook. **Blocks:** VM-C security pebbles; G0. **Decide by 2026-07-22.**

### B-3 · FORCE RLS on ticket-tier tables — enable, or signed exception? *(FD-07)*
- **Why:** `ticket_type_instances`, `ticket_type_price_tiers` (and `product_relations`) run **FORCE RLS = false** — a
  real-money isolation boundary for paid events. Determines whether the security pebble ships a migration or a waiver.
- **DEFAULT (FD-07 rec):** **Enable `relforcerowsecurity`** and fix any table-owner/service-role assumptions; re-run
  advisor + isolation tests. Signed exception only if a hard platform constraint is proven on staging. **Blocks:** VM-C;
  G0. **Decide by 2026-07-22.**

### B-4 · Admin RBAC model — single `admin`, or additive roles + UI? *(FD-02)*
- **Why:** Live CHECK is single `admin`; roadmap mentions superadmin/moderator (unbuilt). This decides whether **BG-2
  (admin user/role-management UI)** is a *build* pebble (new schema + RLS + CRUD UI + authz-matrix tests) or a *docs*
  pebble (manual-ops runbook). Agents are forbidden from inventing roles without this.
- **DEFAULT (FD-02 rec):** **Single `admin` + Cloudflare Access for v1**; BG-2 becomes a documented manual-ops path, not
  a CRUD build. Revisit additive roles only if human least-privilege is needed before open launch. **Blocks:** BG-2
  scope; G15. **Decide by 2026-07-31.**

### B-5 · Phase-1 catalogue scope — Class A branded/new only, or claim A–E / used goods? *(FD-06)*
- **Why:** Live schema is narrow (`condition ∈ new|refurbished`, no `product_class`). Claiming A–E/used-goods pulls
  **MR-S05/S06/V05 + C-ESCROW-HOLD** (schema, evidence uploads, facets, 72h escrow) **into scope**. This decides whether
  a whole product-model expansion enters the plan.
- **DEFAULT (FD-06 rec):** **Class A branded/new (+refurbished) only for Phase-1.** Used-goods / A–E stays OUT (BG-7) unless
  explicitly elevated. Keeps the plan lean. **Blocks:** whether MR-S05/S06 pebbles exist. **Decide by 2026-07-31.**

---

## NON-BLOCKING — proceed on the default; flag and revisit (answer does not change what we build now)

| # | Question (map) | DEFAULT to proceed on | Blocks (if wrong) |
| - | -------------- | --------------------- | ----------------- |
| NB-1 | **Locale strategy — why is `zh` (Chinese) fully live and French ahead of Bemba/Nyanja?** `zh`/`fr` = 17 full namespaces; `bem`/`nya` = stubs. `zh` isn't a stated market language (D27 order is EN→Bemba/Nyanja→French). Is `zh` an intended market (Chinese wholesale traders), or a full-fidelity QA/pseudo-locale left routable by accident? | Treat **`zh` as a QA/pseudo locale**: keep it building but **de-route it from public locale switcher** until a market decision; prioritise **Bemba/Nyanja** fill (BG-1) per D27. | i18n honesty; wasted translation spend |
| NB-2 | **Zamtel collections at launch?** *(FD-01)* | **Keep `zamtel_collections=false` + hide Zamtel in checkout/API** until F9a proof. Payout-only copy only. | Open launch (G14); checkout honesty |
| NB-3 | **Demo catalogue posture before public money?** *(FD-04)* | **Exclude demo (134 `demo/%`) from public search/browse** (D25); labelled fixtures only on demo routes; keep `public_launch=false`. | Open launch (G11); trust/SEO |
| NB-4 | **Event `multi_day` type?** *(FD-05)* | **Accept `standard` + `ends_at`**; update events docs; no enum churn before money/n8n gates. | Events taxonomy honesty (open launch) |
| NB-5 | **Legal / DPA / NPS-Act escrow sign-off?** *(FD-08)* | **Keep prepaid money sandbox-only** until written Zambian-counsel posture exists; do **not** flip real money on a founder waiver. | Real-money beta (G13) |
| NB-6 | **Live-site walk could not be independently repeated** — this session's egress denies `*.vergeo5.com`. Live UX behaviour is taken from the 07-18 `production-evidence` probes + 07-19 Vercel/DB, not a fresh unauth walk. | Trust the documented probes + Vercel prod SHA (`cc4a824`, categories 500). Re-run the exact WebFetch walk from an unrestricted environment during Wave 1 verification. | Confidence in live-UX findings |
| NB-7 | **WAHA on the shared brand/VM vs the locked ban** *(Drive C-1).* Vergeo5 app code is WAHA-clean, but `waha.vergeo.company` runs on the same VM/brand (agency/ZedApply?). | Assume WAHA is **not** in the Vergeo5 notification path (code proves it) but treat the **shared WhatsApp number/brand as a ban-risk**; confirm the official Cloud API sender is a **separate number** from any WAHA sender before launch messaging. | WhatsApp ban contaminating Vergeo5 notifications |
| NB-8 | **Shared OCI Always-Free VM contention** *(Drive C-2).* Same `n8n-vnic-vergeo5` VM hosts Vergeo5 api/caddy/n8n **+ WAHA + ZedApply `zedcv-backend`**. | Assume **noisy-neighbor risk is real**; add it to the capacity/observability plan; plan to **move Vergeo5 API/n8n to an isolated host** (or separate compartment) before real-money load. Do not assume the $50/mo single-VM budget holds under contention. | Prod stability under load; blast radius |
| NB-9 | **Brand/domain/account authority** *(Drive C-3).* `vergeo5.com` vs `vergeo.company`; planning owned by `prosper2kaluba@gmail.com`, audited account `convergeozambia@gmail.com`; "Convergeo" also = an automation agency. | Treat the **repo `docs/plan/00-decisions.md` as the authoritative marketplace SoT** (Drive holds nothing newer). Note the agency business model is out-of-scope for Vergeo5 v1. | Where decisions are recorded |
| NB-10 | **Growth-data governance** *(Drive B-2).* Un-mirrored 2026-07-01 WhatsApp group + `zambian_numbers.csv` harvest. | Do **not** use harvested lists for launch nudges without consent basis; route all customer messaging through the consent-aware outbox + opt-in. | Zambia DPA + WhatsApp ToS exposure |
| NB-11 | **DPO abandonment confirmation** *(FD-09)* | **Confirm Lenco-only (D11)**; annotate superseded DPO docs; no DPO adapter work. | Doc thrash / payment messaging |
| NB-12 | **Vendor staff RBAC in v1?** *(FD-10)* | **Keep OUT** (single-owner vendor); reverse only via dated ADR. | Scope creep |
| NB-13 | **When to flip `public_launch=true`?** *(FD-11)* | **Only after release-gates GO** (real-money beta GO + G10–G17). No calendar flip. | Open launch |
| NB-14 | **Orphaned-KYC repair ownership** *(FD-12)* | **Manual controlled repair only** (never auto-upgrade), named ops owner before `0056` prod apply. | Controlled beta (G12) |

---

## Decision log (fill as answers land — mirror into `docs/plan/00-decisions.md` + `source-conflicts-and-decisions.md` §5)

```text
Q-ID: B-1 (release strategy)
decision: HYBRID controlled live-beta — promote the no-money discovery surface to prod behind public_launch=false (Wave 1 / VM-A) IN PARALLEL with a Lenco sandbox money proof on an isolated target (Wave 2 / VM-B); real money stays OFF until S1–S6 + all P0 gates PASS. A full separable staging plane is NOT a prerequisite.
date: 2026-07-19
decided_by: Kaluba
supersedes: staging-first sequencing in ../2026-07-18/consolidated/implementation-wave-plan.md
engineering impact: Wave 1 and Wave 2 may run in parallel; neither waits on a staging stack. VE-P08 env-isolation tracked as Wave 4, not a prerequisite. public_launch/prepaid/zamtel stay off.
related MR-/G-IDs: G1/G3/G4/G17; S1–S6; release-gates Go/No-Go. Recorded as D30 in docs/plan/00-decisions.md.
```

Template for the remaining decisions (B-2…B-5, NB-*):

```text
Q-ID:            # B-2..B-5 or NB-1..NB-14 (and the FD-ID it maps to)
decision:
date:
decided_by: Kaluba
supersedes:
engineering impact:
related MR-/G-IDs:
```

**Explicit non-actions until answers land** (inherited from the 07-18 corpus): do not invent superadmin/moderator roles
(B-4); do not enable Zamtel collections (NB-2); do not expand `product_class`/used-goods for marketing (B-5); do not seed
fake vendors/GMV; do not mark legal PASS without a counsel artifact (NB-5); do not flip `public_launch=true` (NB-13); do
not auto-upgrade orphaned KYC tiers (NB-14); do not claim STAGING/PRODUCTION_VERIFIED from CODE_COMPLETE alone.

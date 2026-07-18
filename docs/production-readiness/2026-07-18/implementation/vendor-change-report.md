# Vendor panel change report — 2026-07-18

**Branch:** `cursor/panel-vendor-6470`  
**Scope:** `apps/vendor` + `packages/i18n` vendor messages (en/fr/zh)  
**Out of scope:** DB schema, payments/config, customer/admin apps, deploy

## Verdict

Shipped the highest-priority **frontend-only** vendor readiness work that is backed by verified API contracts and has **no unresolved backend dependency**: KYC badge honesty (VEND-01 UI half), onboarding/profile/catalogue/inventory async integrity, real-data analytics empty states (VEND-08 honesty), and explicit OUT for staff RBAC (VEND-10).

Items that still require API/admin/ops were **not** presented as working.

## Backlog mapping

| ID                | Pri | Status this PR     | Notes                                                                                                                                                       |
| ----------------- | --- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| VEND-01           | P0  | **Partial (UI)**   | Vendor UI no longer treats bare `kyc_tier` as verified; approved UI requires auditable `kyc_record_id`. API freeze / seed repair still **MR-D02 / ADM-03**. |
| VEND-02           | P1  | Deferred           | Needs sandbox JWT + private storage + admin review path.                                                                                                    |
| VEND-03           | P1  | Partial            | Create-flow blockers fixed (KYC load error, wholesale gate honesty, post-create → listings). Full timed attach audit still needs test JWT.                  |
| VEND-04 / VEND-06 | P1  | Blocked            | Schema/API gated (`unique` / `made_to_order` / evidence).                                                                                                   |
| VEND-05 / VEND-07 | P1  | Blocked            | Ticket issuance / n8n (MR-W02).                                                                                                                             |
| VEND-08           | P1  | Done (UI)          | Analytics empty/zero honesty; home takings caption when 0; no fabricated GMV. Ledger-backed organiser fees still MR-B01.                                    |
| VEND-09           | P2  | Blocked            | Schema MR-S09.                                                                                                                                              |
| VEND-10           | P2  | **Documented OUT** | No staff/RBAC UI added; single-owner vendor model only.                                                                                                     |

## What changed

### KYC integrity (VEND-01 UI)

- `kyc-client` no longer defaults missing tiers to `1`.
- Maps `kyc_record_id` / `kyc_record_status`.
- Helpers in `_lib/kyc-integrity.ts`: `isAuditableApproved`, `effectiveKycTier`, `canUseWholesaleCapabilities`, `shouldShowPreferredBadge`.
- Status screen uses `resolveHonestStatusVariant` — **approved without record → pending**.
- Preferred badge on profile only when API `preferred_badge === true` (never from tier).
- Listing create wholesale toggle only when auditable approved **and** tier ≥ 2.

### Onboarding / profile

- After KYC submit/resubmit, best-effort `PATCH /vendor/profile` with onboarding `businessName` (was localStorage-only).
- Auth/permission failures no longer fall back to a silent local draft.
- Profile load failure no longer renders an empty editable form; shared `ErrorState` + retry.

### Catalogue / inventory

- Listings manage: `EmptyState` / `ErrorState` + retry, create CTA, clear status badges, stock ±1 unchanged (API-backed).
- Listing edit: load retry, auth/permission classification, visible status badge.
- Listing create: KYC fetch failure surfaces error + retry (no silent tier-1); KYC gate banner; success navigates to `/listings`.

### Home / analytics honesty

- Vendor quick nav (home / listings / orders / profile) — capability-based owner UI only.
- Home KYC banner when not auditable-approved; zero takings caption; empty needs-action via `EmptyState`.
- Analytics: empty state when all series are zero (“never invent GMV”); error + retry.

### Shared patterns

- `_components/async-state.tsx` wraps `@vergeo/ui` `EmptyState` / `ErrorState`.
- `_lib/vendor-errors.ts` classifies 401/403/404/network for vendor-scoped copy.

## Tests & gates run

```bash
pnpm --filter vendor lint      # pass
pnpm --filter vendor typecheck # pass
pnpm --filter vendor test      # 82 pass
pnpm --filter vendor build     # pass
```

New/extended tests: `kyc-integrity.test.ts`, `vendor-errors.test.ts`, onboarding honest-status, listings wholesale gate.

## Explicitly not claimed working

- Seed vendors with `kyc_tier=2` and `kyc_records=0` remain a **backend/data** defect (MR-D02).
- Wholesale server enforcement still reads `vendors.kyc_tier` directly — UI is stricter; API should eventually require record trail.
- Payments, payouts, escrow balances, organiser GMV, offline scanner sync, event publish, evidence photos, staff roles.

## Backend / admin dependencies (remaining)

| Dependency                                              | Blocks                        | Owner         |
| ------------------------------------------------------- | ----------------------------- | ------------- |
| MR-D02 — freeze / repair KYC tier without `kyc_records` | Full VEND-01 / G12            | API + admin   |
| ADM-03 — guarded KYC review transitions                 | VEND-02 sandbox E2E           | Admin + API   |
| Private storage + test vendor JWT                       | VEND-02 / VEND-03 timed audit | Ops           |
| MR-B06 / MR-S05 — `unique` / `made_to_order` modes      | VEND-04                       | API + schema  |
| MR-S06 — used-goods evidence                            | VEND-06                       | Schema        |
| MR-W02 — tickets-issue active                           | VEND-05 / VEND-07             | n8n / ops     |
| MR-B01 — prepaid → ledger                               | VEND-08 organiser money stats | Payments      |
| MR-S09 — co-organiser / door roles                      | VEND-09                       | Schema + auth |
| Founder — VEND-10 stays OUT unless ADR reverses         | Staff RBAC                    | Founder       |

## VEND-10 decision note

Vendor staff RBAC remains **OUT of v1** (foundation R6 / MR-V05). This PR adds no invite/member/role UI. Capability UI is limited to what owner-scoped vendor APIs already support.

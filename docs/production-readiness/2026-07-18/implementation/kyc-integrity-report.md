# KYC integrity report — 2026-07-18

**Branch:** `cursor/kyc-integrity-8081`  
**IDs:** MR-D02 · VEND-01 (API half) · ADM-03 · BL-P0-05 · C-KYC-TIER  
**Scope:** `supabase/migrations/0056_kyc_integrity.sql`, `services/api` KYC/eligibility/capability gates, admin KYC review UI contract, vendor status honesty, orphaned-tier report  
**Out of scope:** Applying migration to production, seeding/repairing live KYC rows, weakening RLS, granting roles

## Verdict

Implemented an auditable KYC record lifecycle with guarded admin transitions, immutable decision evidence, and backend-derived vendor capabilities so a bare `vendors.kyc_tier` can no longer unlock verified / wholesale / privileged access. Legacy orphaned tiers are **reported only** — never auto-upgraded.

## Evidence (pre-change)

| Finding                                                                    | Source                                                                 |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Live vendors with `kyc_tier=2` and `kyc_records=0`                         | foundation / master register MR-D02                                    |
| Vendor UI already refused bare tier (VEND-01 UI)                           | `apps/vendor/.../kyc-integrity.ts`                                     |
| API wholesale / events / directory / caps still trusted `vendors.kyc_tier` | `vendor_listings.py`, `organiser_events.py`, `directory.py`, `caps.py` |
| Admin approve/reject existed; no under_review / suspend / revoke           | `admin_kyc.py` + state machine                                         |
| Decision evidence lived only in `audit_log` / `reviewer_notes`             | `kyc_records` schema in `0002`                                         |

## Design (implemented)

### Lifecycle

`submitted` → `under_review` → `approved` | `rejected` → `suspended` | `revoked`

- Legacy DB value `pending` is migrated to `submitted` in `0056`.
- Application status enum exposes the same labels to clients.
- Approve/reject accepted from `submitted` or `under_review`.

### Immutable decision evidence

On approve/reject the API persists:

| Field             | Meaning                                |
| ----------------- | -------------------------------------- |
| `reviewed_by`     | Reviewer user id                       |
| `reviewed_at`     | Decision timestamp (UTC)               |
| `decision_reason` | Reason / notes at decision time        |
| `tier`            | Record tier (immutable after decision) |

Trigger `guard_kyc_record_integrity` blocks rewriting evidence / tier / doc paths after review starts. Suspend/revoke update `status` + `lifecycle_reason` without clearing approval evidence. Full prior-state trail remains in `audit_log` (`kyc.*` + `admin.kyc.*`).

### Backend-derived eligibility

`app/services/kyc/eligibility.py` is the single capability source:

- Requires an **approved** `kyc_records` row (highest tier wins).
- `stored_kyc_tier` alone ⇒ `orphaned_tier=true`, `effective_tier=null`.
- Wired into wholesale create/manage, organiser events, directory `verified`, listing/payout quotas, tier upgrade.

### Guarded admin endpoints

| Method | Path                               | Auth                                    |
| ------ | ---------------------------------- | --------------------------------------- |
| GET    | `/admin/kyc`                       | admin (queue: submitted + under_review) |
| GET    | `/admin/kyc/orphaned-tiers`        | admin (report only)                     |
| GET    | `/admin/kyc/{id}`                  | admin                                   |
| POST   | `/admin/kyc/{id}/start-review`     | admin + audit                           |
| POST   | `/admin/kyc/{id}/approve`          | admin + audit                           |
| POST   | `/admin/kyc/{id}/reject`           | admin + audit                           |
| POST   | `/admin/kyc/{id}/request-resubmit` | admin + audit                           |
| POST   | `/admin/kyc/{id}/suspend`          | admin + audit                           |
| POST   | `/admin/kyc/{id}/revoke`           | admin + audit                           |

Router inherits `require_role("admin")` from `/admin`. Vendors cannot self-approve (no owner UPDATE policy on `kyc_records`; mutating routes are admin-only).

### Vendor status contract

`GET /kyc/status` now returns:

- `effective_tier`, `is_auditable_approved`, `orphaned_tier`
- `capabilities.{wholesale,organise_events,directory_verified}`
- `kyc_tier` is **null** when orphaned (never echoes a bare privilege tier)

### RLS / storage

Unchanged posture, reinforced:

- Owner SELECT own `kyc_records` only; admin ALL; no owner INSERT/UPDATE.
- Integrity trigger is defense-in-depth against policy drift.
- Private `kyc-docs` bucket remains service-role signed URL only (vendor upload sign path-pinned; admin detail TTL ≤300s).
- `kyc_orphaned_tier_report` view: `security_invoker`, granted to authenticated/service_role, revoked from anon.

## Migration / rollout plan (DO NOT APPLY FROM THIS PR)

**Migration file:** `supabase/migrations/0056_kyc_integrity.sql`  
**Separate review required before production.** This PR lands the SQL in-repo only.

### Pre-flight (read-only)

1. Count orphaned vendors:
   ```sql
   select count(*) from public.vendors v
   where v.kyc_tier is not null
     and not exists (
       select 1 from public.kyc_records kr
       where kr.vendor_id = v.id and kr.status = 'approved'
     );
   ```
2. Inventory `kyc_records.status` distribution (expect mostly empty / pending historically).
3. Confirm no open admin KYC UI sessions that assume status=`pending` only.

### Apply order (staging → production)

1. Deploy API that understands both `pending` (read-normalized) and new statuses.
2. Apply `0056_kyc_integrity.sql` (expands CHECK, migrates `pending`→`submitted`, adds columns/trigger/view).
3. Deploy admin/vendor clients that call start-review / suspend / revoke and show honest eligibility.
4. Run `GET /admin/kyc/orphaned-tiers` and file ops tickets for each orphan — **manual controlled repair only** (create proper KYC submission + guarded approve, or clear tier via guarded admin path). Never `UPDATE vendors SET kyc_tier=…` without a record.

### Rollback

- Drop trigger `kyc_records_guard_integrity`.
- Drop view `kyc_orphaned_tier_report`.
- Drop columns `reviewed_by`, `reviewed_at`, `decision_reason`, `lifecycle_reason`.
- Restore status CHECK to include prior labels if needed; data rows with `under_review`/`suspended`/`revoked` must be mapped before tightening.

### Explicit non-actions

- Do **not** auto-create `kyc_records` for orphaned demo/seed vendors.
- Do **not** grant admin roles or mutate production KYC from this agent run.
- Do **not** weaken RLS or open the private KYC storage bucket.

## Tests

| Suite                                         | Coverage                                                                                                                                                                         |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `services/api/tests/test_kyc_integrity.py`    | orphaned tier freeze; approve evidence + audit; suspend/revoke capability removal; vendor self-approve 403; unauthorized admin 403; cross-vendor status isolation; orphan report |
| `services/api/tests/test_admin_kyc.py`        | queue uses submitted; approve persists reviewer evidence                                                                                                                         |
| Existing listing/events/caps/csv/payout seeds | updated to include approved `kyc_records` where T2 privileges are expected                                                                                                       |
| `supabase/tests/0056_kyc_integrity.test.sql`  | schema/trigger/view presence                                                                                                                                                     |

## Files touched (high level)

- `supabase/migrations/0056_kyc_integrity.sql` + SQL test
- `services/api/app/services/kyc/{state_machine,eligibility,caps,__init__}.py`
- `services/api/app/routers/{admin_kyc,kyc,vendor_listings,vendor_listings_manage,organiser_events,directory}.py`
- `services/api/app/services/payouts/eligibility.py`
- `packages/types/src/db.ts`
- `apps/admin/.../kyc/_components/{api.ts,DecisionPanel.tsx}`
- `apps/vendor/.../onboarding` status mapping
- `packages/i18n/messages/{en,fr,zh}/admin.json`

## Residual risks

- Production orphaned tiers remain until ops repairs them; after deploy they simply lose privilege claims (intended).
- Directory `verified` now ignores bare tier — vendors with only preferred badge still show verified.
- WhatsApp templates for `kyc_under_review` / `kyc_suspended` / `kyc_revoked` may need Meta approval; outbox still enqueues for ops visibility.

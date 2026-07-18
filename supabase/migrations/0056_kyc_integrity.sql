-- 0056: KYC integrity — auditable lifecycle, immutable decision evidence, orphan report.
--
-- Addresses MR-D02 / VEND-01 / ADM-03:
--   * Expand kyc_records.status: submitted → under_review → approved|rejected
--     → suspended|revoked (legacy `pending` rows migrated to `submitted`).
--   * Persist immutable approval/rejection evidence (reviewer, timestamps, reason).
--   * Report orphaned vendors.kyc_tier without an approved kyc_records trail.
--     Do NOT auto-upgrade or rewrite those tiers.
--
-- Additive; reversible (see docs/production-readiness/2026-07-18/implementation/kyc-integrity-report.md).
-- Do NOT apply to production from this PR without the separately reviewed rollout plan.

-- ---------------------------------------------------------------------------
-- 1. Lifecycle statuses
-- ---------------------------------------------------------------------------

alter table public.kyc_records
  drop constraint if exists kyc_records_status_check;

-- Temporarily allow both legacy and new labels so the data migration can run.
alter table public.kyc_records
  add constraint kyc_records_status_check
  check (status in (
    'pending',
    'submitted',
    'under_review',
    'approved',
    'rejected',
    'suspended',
    'revoked'
  ));

update public.kyc_records
set status = 'submitted'
where status = 'pending';

alter table public.kyc_records
  drop constraint if exists kyc_records_status_check;

alter table public.kyc_records
  add constraint kyc_records_status_check
  check (status in (
    'submitted',
    'under_review',
    'approved',
    'rejected',
    'suspended',
    'revoked'
  ));

alter table public.kyc_records
  alter column status set default 'submitted';

comment on column public.kyc_records.status is
  'KYC lifecycle: submitted → under_review → approved|rejected → suspended|revoked. Writes only via guarded API transitions.';

-- ---------------------------------------------------------------------------
-- 2. Immutable decision evidence + lifecycle reason
-- ---------------------------------------------------------------------------

alter table public.kyc_records
  add column if not exists reviewed_by uuid references public.profiles (id) on delete set null;

alter table public.kyc_records
  add column if not exists reviewed_at timestamptz;

alter table public.kyc_records
  add column if not exists decision_reason text;

alter table public.kyc_records
  add column if not exists lifecycle_reason text;

comment on column public.kyc_records.reviewed_by is
  'Admin/reviewer who approved or rejected; immutable once set.';
comment on column public.kyc_records.reviewed_at is
  'UTC timestamp of approve/reject decision; immutable once set.';
comment on column public.kyc_records.decision_reason is
  'Approve/reject reason captured at decision time; immutable once set.';
comment on column public.kyc_records.lifecycle_reason is
  'Latest suspend/revoke (or start-review) reason; may change on controlled lifecycle transitions.';

create index if not exists kyc_records_status_updated_at_idx
  on public.kyc_records (status, updated_at);

create index if not exists kyc_records_vendor_id_approved_idx
  on public.kyc_records (vendor_id)
  where status = 'approved';

-- Block client-side mutation of decision evidence and illegal status rewrites.
-- service_role / admin / superusers may change status for controlled suspend/revoke
-- but cannot alter reviewed_by / reviewed_at / decision_reason once recorded.
create or replace function public.guard_kyc_record_integrity()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
  is_privileged boolean := false;
begin
  if session_user in ('postgres', 'supabase_admin') then
    is_privileged := true;
  elsif jwt_role = 'service_role' or public.has_role('admin') then
    is_privileged := true;
  end if;

  -- Non-privileged callers must never mutate KYC rows (RLS already denies;
  -- this is defense-in-depth for any future policy drift).
  if not is_privileged then
    raise exception 'kyc_records are server-controlled';
  end if;

  if tg_op = 'UPDATE' then
    -- Immutable approval/rejection evidence once recorded.
    if old.reviewed_at is not null then
      if new.reviewed_by is distinct from old.reviewed_by
        or new.reviewed_at is distinct from old.reviewed_at
        or new.decision_reason is distinct from old.decision_reason then
        raise exception 'kyc decision evidence is immutable';
      end if;
    end if;

    -- Tier on a decided record is part of the audit trail.
    if old.status in ('approved', 'rejected', 'suspended', 'revoked')
      and new.tier is distinct from old.tier then
      raise exception 'kyc_records.tier is immutable after a decision';
    end if;

    -- Document paths must not be rewritten after submission/decision.
    if old.status in ('under_review', 'approved', 'rejected', 'suspended', 'revoked')
      and new.doc_storage_paths is distinct from old.doc_storage_paths then
      raise exception 'kyc document paths are immutable after review starts';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists kyc_records_guard_integrity on public.kyc_records;
create trigger kyc_records_guard_integrity
  before update on public.kyc_records
  for each row
  execute function public.guard_kyc_record_integrity();

revoke all on function public.guard_kyc_record_integrity() from public;
grant execute on function public.guard_kyc_record_integrity() to postgres, service_role;

-- ---------------------------------------------------------------------------
-- 3. Orphaned tier report (identify only — never auto-repair)
-- ---------------------------------------------------------------------------

create or replace view public.kyc_orphaned_tier_report
with (security_invoker = true)
as
select
  v.id as vendor_id,
  v.slug,
  v.display_name,
  v.status as vendor_status,
  v.kyc_tier as stored_kyc_tier,
  v.updated_at as vendor_updated_at,
  (
    select count(*)::int
    from public.kyc_records kr
    where kr.vendor_id = v.id
  ) as kyc_record_count,
  (
    select count(*)::int
    from public.kyc_records kr
    where kr.vendor_id = v.id
      and kr.status = 'approved'
  ) as approved_kyc_record_count
from public.vendors v
where v.kyc_tier is not null
  and not exists (
    select 1
    from public.kyc_records kr
    where kr.vendor_id = v.id
      and kr.status = 'approved'
  );

comment on view public.kyc_orphaned_tier_report is
  'Vendors with a non-null kyc_tier but no approved kyc_records row. Report-only; do not auto-upgrade.';

-- View inherits vendors/kyc_records RLS via security_invoker. Admins can read
-- the full report; owners see only their own vendor if it qualifies. Revoke anon.
grant select on public.kyc_orphaned_tier_report to authenticated, service_role;
revoke all on public.kyc_orphaned_tier_report from anon, public;

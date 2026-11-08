-- B1: seed the chart of accounts the ledger engine resolves at post time.
--
-- Background: `services/api/app/services/ledger/engine.py::resolve_account_id`
-- looks up `public.ledger_accounts` by (kind, vendor_id). No migration ever
-- inserted those rows, so every prepaid SUCCESS failed with
-- `ledger account not found` and never reached SUCCESS. This migration:
--
--   1. Inserts the four platform accounts (vendor_id IS NULL):
--        platform_cash, escrow, commission_revenue, fees
--      with deterministic ids (stable across environments and identical to the
--      ids the API test-suite fixtures already use, so fixture inserts keyed
--      `ON CONFLICT (id) DO NOTHING` stay no-ops).
--   2. Backfills per-vendor accounts (vendor_payable + cod_receivable) for every
--      existing vendor.
--   3. Extends `public.approve_kyc_vendor` so a newly approved vendor gets both
--      vendor accounts in the SAME transaction as the KYC approval / activation /
--      role grant / audit (atomic: all commit or none do). Re-approval is
--      idempotent and also repairs missing accounts.
--
-- Idempotent: every insert is `ON CONFLICT DO NOTHING` against the partial
-- unique indexes from 0006_money.sql (ledger_accounts_kind_platform_key,
-- ledger_accounts_kind_vendor_id_key). Safe to re-run.
--
-- Additive only: no column/table changes. The function body is the
-- 20260813150000 definition plus one helper call on each success path.
--
-- Down (manual, only while no posting references the rows — ledger_postings
-- has ON DELETE RESTRICT so this fails closed once money has moved):
--   1. Re-apply supabase/migrations/20260813150000_kyc_approve_vendor_atomic.sql
--      (restores the previous approve_kyc_vendor body).
--   2. drop function if exists public.ensure_vendor_ledger_accounts(uuid);
--   3. delete from public.ledger_accounts la
--      where not exists (select 1 from public.ledger_postings lp where lp.account_id = la.id);
--   Rows that already carry postings are financial history and are NOT deleted.

-- ---------------------------------------------------------------------------
-- 1. Platform accounts
-- ---------------------------------------------------------------------------
insert into public.ledger_accounts (id, kind)
values
  ('c1000000-0000-0000-0000-000000000001', 'platform_cash'),
  ('c2000000-0000-0000-0000-000000000002', 'escrow'),
  ('c3000000-0000-0000-0000-000000000003', 'commission_revenue'),
  ('c4000000-0000-0000-0000-000000000004', 'fees')
on conflict (kind) where vendor_id is null do nothing;

-- ---------------------------------------------------------------------------
-- 2. Per-vendor account helper (idempotent)
-- ---------------------------------------------------------------------------
create or replace function public.ensure_vendor_ledger_accounts(p_vendor_id uuid)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_inserted integer;
begin
  if p_vendor_id is null then
    raise exception 'vendor_id is required'
      using errcode = '22023', message = 'validation_error:vendor_id';
  end if;

  insert into public.ledger_accounts (kind, vendor_id)
  select k.kind, p_vendor_id
  from (values ('vendor_payable'), ('cod_receivable')) as k(kind)
  on conflict (kind, vendor_id) where vendor_id is not null do nothing;

  get diagnostics v_inserted = row_count;
  return v_inserted;
end;
$$;

comment on function public.ensure_vendor_ledger_accounts(uuid) is
  'Idempotently create vendor_payable + cod_receivable ledger accounts for a vendor. Returns rows inserted. service_role/postgres only.';

revoke all on function public.ensure_vendor_ledger_accounts(uuid) from public;
revoke execute on function public.ensure_vendor_ledger_accounts(uuid) from public, anon, authenticated;
grant execute on function public.ensure_vendor_ledger_accounts(uuid) to postgres, service_role;

-- ---------------------------------------------------------------------------
-- 3. Backfill existing vendors
-- ---------------------------------------------------------------------------
insert into public.ledger_accounts (kind, vendor_id)
select k.kind, v.id
from public.vendors v
cross join (values ('vendor_payable'), ('cod_receivable')) as k(kind)
on conflict (kind, vendor_id) where vendor_id is not null do nothing;

-- ---------------------------------------------------------------------------
-- 4. Atomic KYC approval now provisions the vendor's ledger accounts
-- ---------------------------------------------------------------------------
create or replace function public.approve_kyc_vendor(
  p_actor_id uuid,
  p_kyc_record_id uuid,
  p_tier integer,
  p_reviewer_notes text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_kyc public.kyc_records%rowtype;
  v_vendor public.vendors%rowtype;
  v_owner uuid;
  v_now timestamptz := timezone('utc', now());
  v_momo_matched boolean;
  v_role_outcome text;
  v_before jsonb;
  v_after jsonb;
  v_kyc_slice jsonb;
  v_vendor_slice jsonb;
  v_role_slice jsonb;
  v_normalized_status text;
  v_accounts_created integer;
begin
  if session_user not in ('postgres', 'supabase_admin')
     and coalesce(current_setting('request.jwt.claim.role', true), '') is distinct from 'service_role' then
    raise exception 'approve_kyc_vendor requires service role'
      using errcode = '42501';
  end if;

  if p_actor_id is null then
    raise exception 'actor_id is required'
      using errcode = '22023', message = 'validation_error:actor_id';
  end if;

  if p_tier is null or p_tier not in (1, 2, 3) then
    raise exception 'KYC tier must be 1, 2, or 3'
      using errcode = '22023', message = 'validation_error:tier';
  end if;

  select *
  into v_kyc
  from public.kyc_records kr
  where kr.id = p_kyc_record_id
  for update;

  if not found then
    raise exception 'KYC record not found'
      using errcode = 'P0002', message = 'not_found:kyc_record';
  end if;

  select *
  into v_vendor
  from public.vendors v
  where v.id = v_kyc.vendor_id
  for update;

  if not found then
    raise exception 'Vendor not found'
      using errcode = 'P0002', message = 'not_found:vendor';
  end if;

  v_owner := v_vendor.owner_user_id;
  if v_owner is null then
    raise exception 'Vendor has no owner_user_id'
      using errcode = '22023', message = 'vendor_role_missing_owner';
  end if;

  if p_tier is distinct from v_kyc.tier then
    raise exception 'Approval tier must match the KYC record tier'
      using errcode = '22023', message = 'validation_error:tier_mismatch';
  end if;

  v_momo_matched := coalesce((v_kyc.momo_name_match ->> 'matched')::boolean, true);
  if v_momo_matched is false then
    raise exception 'KYC cannot be approved while MoMo name-match is flagged'
      using errcode = '22023', message = 'kyc_name_match_required';
  end if;

  v_normalized_status := case
    when v_kyc.status = 'pending' then 'submitted'
    else v_kyc.status
  end;

  v_kyc_slice := jsonb_build_object(
    'id', v_kyc.id,
    'status', v_normalized_status,
    'tier', v_kyc.tier,
    'reviewed_by', v_kyc.reviewed_by,
    'reviewed_at', v_kyc.reviewed_at,
    'decision_reason', v_kyc.decision_reason,
    'lifecycle_reason', v_kyc.lifecycle_reason
  );

  v_vendor_slice := jsonb_build_object(
    'id', v_vendor.id,
    'status', v_vendor.status,
    'kyc_tier', v_vendor.kyc_tier
  );

  v_before := jsonb_build_object(
    'vendor', v_vendor_slice,
    'kyc_record', v_kyc_slice
  );

  -- Idempotent re-approval: already approved + active vendor.
  if v_normalized_status = 'approved' and v_vendor.status = 'active' then
    insert into public.user_roles as ur (user_id, role)
    values (v_owner, 'vendor')
    on conflict (user_id, role) do nothing
    returning user_id into v_owner;

    if found then
      v_role_outcome := 'granted';
    else
      v_role_outcome := 'already_present';
    end if;

    -- Repair path: vendors approved before ledger provisioning existed.
    v_accounts_created := public.ensure_vendor_ledger_accounts(v_vendor.id);

    v_role_slice := jsonb_build_object(
      'user_id', v_vendor.owner_user_id,
      'role', 'vendor',
      'outcome', v_role_outcome,
      'vendor_id', v_vendor.id
    );

    v_after := jsonb_build_object(
      'vendor', v_vendor_slice,
      'kyc_record', v_kyc_slice,
      'vendor_role', v_role_slice,
      'ledger_accounts_created', v_accounts_created
    );

    return v_after;
  end if;

  if v_normalized_status not in ('submitted', 'under_review') then
    raise exception 'Cannot transition from % to approved', v_normalized_status
      using errcode = '22023', message = 'kyc_invalid_transition';
  end if;

  update public.kyc_records kr
  set
    status = 'approved',
    reviewed_by = p_actor_id,
    reviewed_at = v_now,
    decision_reason = p_reviewer_notes,
    reviewer_notes = coalesce(p_reviewer_notes, kr.reviewer_notes),
    updated_at = v_now
  where kr.id = p_kyc_record_id
    and kr.status in ('submitted', 'under_review', 'pending');

  if not found then
    raise exception 'Concurrent transition changed KYC record state'
      using errcode = '22023', message = 'kyc_transition_conflict';
  end if;

  update public.vendors v
  set
    status = 'active',
    kyc_tier = p_tier,
    updated_at = v_now
  where v.id = v_vendor.id
    and v.status = v_vendor.status;

  if not found then
    raise exception 'Concurrent transition changed vendor state'
      using errcode = '22023', message = 'kyc_transition_conflict';
  end if;

  insert into public.user_roles as ur (user_id, role)
  values (v_owner, 'vendor')
  on conflict (user_id, role) do nothing
  returning user_id into v_owner;

  if found then
    v_role_outcome := 'granted';
  else
    v_role_outcome := 'already_present';
  end if;

  -- Same transaction as activation: an active vendor always has its payable /
  -- COD receivable accounts, so release_to_vendor / payout / clawback can post.
  v_accounts_created := public.ensure_vendor_ledger_accounts(v_vendor.id);

  v_kyc_slice := jsonb_build_object(
    'id', v_kyc.id,
    'status', 'approved',
    'tier', v_kyc.tier,
    'reviewed_by', p_actor_id,
    'reviewed_at', v_now,
    'decision_reason', p_reviewer_notes,
    'lifecycle_reason', v_kyc.lifecycle_reason
  );

  v_vendor_slice := jsonb_build_object(
    'id', v_vendor.id,
    'status', 'active',
    'kyc_tier', p_tier
  );

  v_role_slice := jsonb_build_object(
    'user_id', v_vendor.owner_user_id,
    'role', 'vendor',
    'outcome', v_role_outcome,
    'vendor_id', v_vendor.id
  );

  v_after := jsonb_build_object(
    'vendor', v_vendor_slice,
    'kyc_record', v_kyc_slice,
    'vendor_role', v_role_slice,
    'ledger_accounts_created', v_accounts_created
  );

  insert into public.audit_log (
    actor,
    action,
    entity_type,
    entity_id,
    before,
    after
  ) values (
    p_actor_id,
    'kyc.approve',
    'kyc_record',
    p_kyc_record_id,
    v_before,
    v_after
  );

  return v_after;
end;
$$;

comment on function public.approve_kyc_vendor(uuid, uuid, integer, text) is
  'Atomically approve KYC, activate vendor, grant vendors.owner_user_id the vendor role, provision vendor ledger accounts, and append audit_log. service_role only.';

revoke all on function public.approve_kyc_vendor(uuid, uuid, integer, text) from public;
revoke execute on function public.approve_kyc_vendor(uuid, uuid, integer, text) from public, anon, authenticated;
grant execute on function public.approve_kyc_vendor(uuid, uuid, integer, text) to postgres, service_role;

-- ---------------------------------------------------------------------------
-- 5. C1 owner decision (2026-11-07): services take 100% upfront for the pilot.
--    There is no balance checkout yet, so a <100% deposit would leave a balance
--    that is never collected. `do nothing` keeps any value an admin has already
--    set explicitly; the API also defaults to 100 when the key is unset and
--    refuses to confirm (or release) any job whose balance was never collected.
--    Down (manual): delete from public.platform_config where key = 'service_deposit_pct';
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  (
    'service_deposit_pct',
    '100'::jsonb,
    'Service job deposit % collected at quote accept (1..100). Pilot = 100: no balance checkout exists, so anything below 100 cannot be confirmed/released.'
  )
on conflict (key) do nothing;

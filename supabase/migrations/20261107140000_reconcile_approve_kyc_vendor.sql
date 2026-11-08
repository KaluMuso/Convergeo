-- Reconcile approve_kyc_vendor after #718 (error contract) and #759 (ledger seed).
--
-- 20261107130000_seed_ledger_accounts redefined approve_kyc_vendor from the
-- 20260813150000 body, silently reverting #718's error contract
-- (20260924071905: single-emit error codes, verified JWT role accessor).
-- This redefinition is the 20260924071905 body verbatim plus #759's
-- `public.ensure_vendor_ledger_accounts(vendor_id)` call on both success paths
-- (fresh approval and idempotent re-approval) in the same transaction, and
-- the `ledger_accounts_created` key in the returned/audited `after` payload.
--
-- Additive: same signature and ACL. Neither earlier migration is edited.
-- Down: re-apply the function from
-- supabase/migrations/20261107130000_seed_ledger_accounts.sql (or from
-- 20260924071905 to drop ledger provisioning as well).

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
     and coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'approve_kyc_vendor requires service role'
      using errcode = '42501';
  end if;

  if p_actor_id is null then
    raise exception using errcode = '22023', message = 'validation_error:actor_id';
  end if;

  if p_tier is null or p_tier not in (1, 2, 3) then
    raise exception using errcode = '22023', message = 'validation_error:tier';
  end if;

  select *
  into v_kyc
  from public.kyc_records kr
  where kr.id = p_kyc_record_id
  for update;

  if not found then
    raise exception using errcode = 'P0002', message = 'not_found:kyc_record';
  end if;

  select *
  into v_vendor
  from public.vendors v
  where v.id = v_kyc.vendor_id
  for update;

  if not found then
    raise exception using errcode = 'P0002', message = 'not_found:vendor';
  end if;

  v_owner := v_vendor.owner_user_id;
  if v_owner is null then
    raise exception using errcode = '22023', message = 'vendor_role_missing_owner';
  end if;

  if p_tier is distinct from v_kyc.tier then
    raise exception using errcode = '22023', message = 'validation_error:tier_mismatch';
  end if;

  v_momo_matched := coalesce((v_kyc.momo_name_match ->> 'matched')::boolean, true);
  if v_momo_matched is false then
    raise exception using errcode = '22023', message = 'kyc_name_match_required';
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

    -- Repair path (#759): vendors approved before ledger provisioning existed.
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
    raise exception using errcode = '22023', message = 'kyc_invalid_transition';
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
    raise exception using errcode = '22023', message = 'kyc_transition_conflict';
  end if;

  update public.vendors v
  set
    status = 'active',
    kyc_tier = p_tier,
    updated_at = v_now
  where v.id = v_vendor.id
    and v.status = v_vendor.status;

  if not found then
    raise exception using errcode = '22023', message = 'kyc_transition_conflict';
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

  -- Same transaction as activation (#759): an active vendor always has its
  -- payable / COD receivable accounts, so release / payout / clawback can post.
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
  'Atomically approve KYC, activate vendor, grant vendors.owner_user_id the vendor role, and append audit_log. service_role only.';

revoke all on function public.approve_kyc_vendor(uuid, uuid, integer, text) from public;
revoke execute on function public.approve_kyc_vendor(uuid, uuid, integer, text) from public, anon, authenticated;
grant execute on function public.approve_kyc_vendor(uuid, uuid, integer, text) to postgres, service_role;

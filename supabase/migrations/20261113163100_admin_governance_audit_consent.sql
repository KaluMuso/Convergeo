-- 2026-11 admin governance (founder decisions 2026-11-13: D2, S5, admin accounts,
-- delivery-partner consent). Additive: one constraint widened, four nullable/defaulted
-- columns, new triggers, one new table, two new service-role-only functions.
--
-- 1. admin_roles permissions: + finance.operate (D2), services.manage, support.manage,
--    logistics.manage, audit.read. `logistics.manage` is the name the logistics
--    blueprint (docs/plan/logistics, Phase 0) reserves; feat/logistics-phase1 must
--    union its own list with this one rather than replace it.
-- 2. audit_log enrichment (audit report S5): actor_roles (roles held at the time of
--    the action, filled from user_roles when the writer does not supply them),
--    outcome (success | denied | failed), request_id, reason. The table becomes
--    append-only for every role, service_role included: UPDATE, DELETE and TRUNCATE
--    raise. Nothing in the API, jobs or migrations updates or deletes audit rows.
-- 3. deactivate_admin_account(): "deactivate an administrator" = revoke every admin
--    role (D4) in one transaction, superadmin-only, never self, audited with reason.
--    The last-superadmin trigger still applies.
-- 4. privacy_consents: append-only per-user consent log (purpose, version, granted,
--    source, recorded_at). The latest row per (user, purpose) is the current answer.
--    dispatch_requests (third-party couriers) refuses an order whose customer has not
--    currently consented to `delivery_partner_share`. Pickup orders never dispatch.
--
-- Down (manual, in this order; the constraint step fails while any role uses a new
-- permission, which is the intended guard):
--   drop trigger if exists dispatch_requests_require_delivery_consent on public.dispatch_requests;
--   drop function if exists public.require_delivery_partner_consent();
--   drop function if exists public.has_delivery_partner_consent(uuid);
--   drop table if exists public.privacy_consents;
--   drop function if exists public.deactivate_admin_account(uuid, uuid, text, text);
--   drop trigger if exists audit_log_append_only_row on public.audit_log;
--   drop trigger if exists audit_log_append_only_truncate on public.audit_log;
--   drop trigger if exists audit_log_fill_actor_roles on public.audit_log;
--   drop function if exists public.audit_log_reject_mutation();
--   drop function if exists public.audit_log_fill_actor_roles();
--   drop index if exists public.audit_log_at_idx, public.audit_log_actor_at_idx,
--     public.audit_log_action_at_idx;
--   alter table public.audit_log drop column if exists reason,
--     drop column if exists request_id, drop column if exists outcome,
--     drop column if exists actor_roles;
--   alter table public.admin_roles drop constraint admin_roles_permissions_valid;
--   alter table public.admin_roles add constraint admin_roles_permissions_valid check (
--     permissions <@ array['finance.read','events.manage','products.manage',
--       'services.read','vendors.manage','ads.manage','analytics.read',
--       'inventory.read']::text[] and cardinality(permissions) > 0);

-- ---------------------------------------------------------------------------
-- 1. Permission vocabulary
-- ---------------------------------------------------------------------------
alter table public.admin_roles drop constraint if exists admin_roles_permissions_valid;
alter table public.admin_roles add constraint admin_roles_permissions_valid check (
  permissions <@ array[
    'finance.read', 'finance.operate', 'events.manage', 'products.manage',
    'services.read', 'services.manage', 'vendors.manage', 'ads.manage',
    'analytics.read', 'inventory.read', 'support.manage', 'logistics.manage',
    'audit.read'
  ]::text[] and cardinality(permissions) > 0
);

-- ---------------------------------------------------------------------------
-- 2. audit_log enrichment + append-only
-- ---------------------------------------------------------------------------
alter table public.audit_log
  add column if not exists actor_roles text[],
  add column if not exists outcome text not null default 'success',
  add column if not exists request_id text,
  add column if not exists reason text;

alter table public.audit_log drop constraint if exists audit_log_outcome_check;
alter table public.audit_log add constraint audit_log_outcome_check
  check (outcome in ('success', 'denied', 'failed'));
alter table public.audit_log drop constraint if exists audit_log_request_id_len_check;
alter table public.audit_log add constraint audit_log_request_id_len_check
  check (request_id is null or char_length(request_id) <= 128);
alter table public.audit_log drop constraint if exists audit_log_reason_len_check;
alter table public.audit_log add constraint audit_log_reason_len_check
  check (reason is null or char_length(reason) <= 1000);

comment on column public.audit_log.actor_roles is
  'Roles the actor held when the row was written (filled from user_roles if not supplied).';
comment on column public.audit_log.outcome is
  'success | denied (authorization refused) | failed (authorized but did not complete).';
comment on column public.audit_log.request_id is 'API X-Request-ID of the originating call.';
comment on column public.audit_log.reason is 'Operator-supplied reason, when the action takes one.';

create index if not exists audit_log_at_idx on public.audit_log (at desc);
create index if not exists audit_log_actor_at_idx on public.audit_log (actor, at desc);
create index if not exists audit_log_action_at_idx on public.audit_log (action, at desc);

create or replace function public.audit_log_fill_actor_roles() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.actor_roles is null and new.actor is not null then
    select coalesce(array_agg(r.role order by r.role), '{}'::text[])
      into new.actor_roles
      from public.user_roles r
     where r.user_id = new.actor;
  end if;
  return new;
end;
$$;
revoke all on function public.audit_log_fill_actor_roles() from public, anon, authenticated;

drop trigger if exists audit_log_fill_actor_roles on public.audit_log;
create trigger audit_log_fill_actor_roles before insert on public.audit_log
  for each row execute function public.audit_log_fill_actor_roles();

create or replace function public.audit_log_reject_mutation() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception 'audit_log is append-only (% refused)', tg_op using errcode = '42501';
end;
$$;
revoke all on function public.audit_log_reject_mutation() from public, anon, authenticated;

drop trigger if exists audit_log_append_only_row on public.audit_log;
create trigger audit_log_append_only_row before update or delete on public.audit_log
  for each row execute function public.audit_log_reject_mutation();
drop trigger if exists audit_log_append_only_truncate on public.audit_log;
create trigger audit_log_append_only_truncate before truncate on public.audit_log
  for each statement execute function public.audit_log_reject_mutation();

revoke update, delete, truncate on public.audit_log from service_role;
comment on table public.audit_log is
  'Append-only admin mutation audit trail (UPDATE/DELETE/TRUNCATE refused by trigger); '
  'service_role inserts and reads only — no client policies.';

-- ---------------------------------------------------------------------------
-- 3. Admin account deactivation = revoke every admin role (D4)
-- ---------------------------------------------------------------------------
create or replace function public.deactivate_admin_account(
  p_actor uuid, p_target uuid, p_reason text, p_request_id text default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_before text[];
begin
  perform pg_catalog.pg_advisory_xact_lock(724, 1);
  if not exists (
    select 1 from public.user_roles where user_id = p_actor and role = 'superadmin'
  ) then
    raise exception 'Superadmin role required' using errcode = '42501';
  end if;
  if p_target is null or p_target = p_actor then
    raise exception 'A superadmin cannot deactivate their own account' using errcode = '22023';
  end if;
  if p_reason is null or char_length(btrim(p_reason)) not between 3 and 500 then
    raise exception 'A reason of 3 to 500 characters is required' using errcode = '22023';
  end if;
  select coalesce(array_agg(role order by role), '{}'::text[]) into v_before
    from public.user_roles
   where user_id = p_target
     and (role in ('superadmin', 'admin', 'moderator') or role like 'rbac\_%');
  if cardinality(v_before) = 0 then
    raise exception 'Account holds no admin role' using errcode = 'P0002';
  end if;
  -- protect_last_superadmin() still fires per row and refuses the last one.
  delete from public.user_roles
   where user_id = p_target
     and (role in ('superadmin', 'admin', 'moderator') or role like 'rbac\_%');
  insert into public.audit_log(
    actor, action, entity_type, entity_id, before, after, outcome, request_id, reason
  ) values (
    p_actor, 'admin.account.deactivate', 'admin_account', p_target,
    jsonb_build_object('roles', to_jsonb(v_before)),
    jsonb_build_object('roles', '[]'::jsonb),
    'success', p_request_id, btrim(p_reason)
  );
  return jsonb_build_object('user_id', p_target, 'revoked', to_jsonb(v_before));
end;
$$;
revoke all on function public.deactivate_admin_account(uuid, uuid, text, text)
  from public, anon, authenticated;
grant execute on function public.deactivate_admin_account(uuid, uuid, text, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- 4. Customer consent to share delivery details with third-party couriers
-- ---------------------------------------------------------------------------
create table if not exists public.privacy_consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  purpose text not null,
  version text not null,
  granted boolean not null,
  source text not null,
  recorded_at timestamptz not null default now(),
  constraint privacy_consents_purpose_check check (purpose in ('delivery_partner_share')),
  constraint privacy_consents_version_check check (version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  constraint privacy_consents_source_check check (source in ('settings', 'checkout'))
);
create index if not exists privacy_consents_user_purpose_recorded_idx
  on public.privacy_consents (user_id, purpose, recorded_at desc, id desc);

alter table public.privacy_consents enable row level security;
alter table public.privacy_consents force row level security;
revoke all on public.privacy_consents from public, anon, authenticated;
grant select on public.privacy_consents to authenticated;
grant select, insert on public.privacy_consents to service_role;

drop policy if exists privacy_consents_owner_select on public.privacy_consents;
create policy privacy_consents_owner_select on public.privacy_consents
  for select to authenticated using (user_id = (select auth.uid()));

-- History is evidence: no one rewrites it (withdrawal is a new row with granted=false).
drop trigger if exists privacy_consents_append_only on public.privacy_consents;
create trigger privacy_consents_append_only before update or delete on public.privacy_consents
  for each row
  when (pg_trigger_depth() = 0)
  execute function public.audit_log_reject_mutation();

comment on table public.privacy_consents is
  'Append-only consent log (Zambia DPA 2021). Latest row per (user_id, purpose) is current. '
  'Written by the API as service_role; owners read their own rows. Rows go with the account '
  '(on delete cascade) when the account is erased.';

create or replace function public.has_delivery_partner_consent(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select c.granted from public.privacy_consents c
     where c.user_id = p_user and c.purpose = 'delivery_partner_share'
     order by c.recorded_at desc, c.id desc
     limit 1
  ), false)
$$;
revoke all on function public.has_delivery_partner_consent(uuid) from public, anon, authenticated;
grant execute on function public.has_delivery_partner_consent(uuid) to service_role;

create or replace function public.require_delivery_partner_consent() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_customer uuid;
begin
  select o.customer_id into v_customer from public.orders o where o.id = new.order_id;
  if v_customer is null or not public.has_delivery_partner_consent(v_customer) then
    raise exception 'Customer has not consented to sharing delivery details with a courier'
      using errcode = '23514', constraint = 'dispatch_requests_delivery_consent';
  end if;
  return new;
end;
$$;
revoke all on function public.require_delivery_partner_consent() from public, anon, authenticated;

drop trigger if exists dispatch_requests_require_delivery_consent on public.dispatch_requests;
create trigger dispatch_requests_require_delivery_consent
  before insert on public.dispatch_requests
  for each row execute function public.require_delivery_partner_consent();

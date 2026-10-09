-- Restricted administrator roles extend the existing public.user_roles source of truth.
-- This migration contains no account grants. Live application requires separate approval.
create table public.admin_roles (
  key text primary key check (key ~ '^rbac_[a-z][a-z0-9_]{2,39}$'),
  name text not null check (length(trim(name)) between 3 and 80),
  permissions text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint admin_roles_permissions_valid check (
    permissions <@ array[
      'finance.read', 'events.manage', 'products.manage', 'services.read',
      'vendors.manage', 'ads.manage', 'analytics.read', 'inventory.read'
    ]::text[] and cardinality(permissions) > 0
  )
);

create trigger admin_roles_set_updated_at before update on public.admin_roles
  for each row execute function public.set_updated_at();
alter table public.admin_roles enable row level security;
alter table public.admin_roles force row level security;
revoke all on public.admin_roles from public, anon, authenticated;
grant select, insert, update, delete on public.admin_roles to service_role;
comment on table public.admin_roles is
  'Restricted admin role definitions; user_roles remains the assignment source. Service role only.';

alter table public.user_roles drop constraint user_roles_role_check;
alter table public.user_roles add constraint user_roles_role_check check (
  role in ('customer', 'vendor', 'admin', 'superadmin', 'moderator')
  or role ~ '^rbac_[a-z][a-z0-9_]{2,39}$'
);

create function public.validate_admin_role_assignment() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.role like 'rbac_%' and not exists (
    select 1 from public.admin_roles where key = new.role
  ) then
    raise exception 'Unknown restricted admin role' using errcode = '23514';
  end if;
  return new;
end;
$$;
create trigger validate_admin_role_assignment before insert or update of role on public.user_roles
  for each row execute function public.validate_admin_role_assignment();
revoke all on function public.validate_admin_role_assignment() from public, anon, authenticated;

create function public.protect_assigned_admin_role() returns trigger
language plpgsql set search_path = '' as $$
begin
  if exists (select 1 from public.user_roles where role = old.key) then
    raise exception 'Assigned role cannot be changed or deleted' using errcode = '23503';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
create trigger protect_assigned_admin_role before delete or update of key on public.admin_roles
  for each row execute function public.protect_assigned_admin_role();
revoke all on function public.protect_assigned_admin_role() from public, anon, authenticated;

-- Serialize removals so two concurrent revocations cannot each observe the other
-- superadmin and leave the installation without one.
create function public.protect_last_superadmin() returns trigger
language plpgsql set search_path = '' as $$
begin
  if old.role = 'superadmin' and (tg_op = 'DELETE' or new.role <> 'superadmin') then
    perform pg_catalog.pg_advisory_xact_lock(724, 1);
    if (select count(*) from public.user_roles where role = 'superadmin') <= 1 then
      raise exception 'Cannot remove the last superadmin' using errcode = '23514';
    end if;
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
create trigger protect_last_superadmin before delete or update of role on public.user_roles
  for each row execute function public.protect_last_superadmin();
revoke all on function public.protect_last_superadmin() from public, anon, authenticated;

-- API invokes this service-role-only transaction after verifying the caller's JWT.
-- Rechecks superadmin from user_roles, locks concurrent changes, and records the
-- before/after state in the same transaction as the role or assignment change.
create function public.manage_admin_role(
  p_actor uuid, p_action text, p_key text, p_name text default null,
  p_permissions text[] default null, p_target uuid default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_before jsonb;
  v_after jsonb;
  v_entity uuid;
begin
  perform pg_catalog.pg_advisory_xact_lock(724, 1);
  if not exists (select 1 from public.user_roles where user_id = p_actor and role = 'superadmin') then
    raise exception 'Superadmin role required' using errcode = '42501';
  end if;
  if p_action in ('create', 'update', 'delete') then
    if p_key !~ '^rbac_[a-z][a-z0-9_]{2,39}$' then
      raise exception 'Invalid restricted role key' using errcode = '22023';
    end if;
    select to_jsonb(r) into v_before from public.admin_roles r where key = p_key for update;
    if p_action = 'create' then
      insert into public.admin_roles(key, name, permissions)
      values (p_key, p_name, p_permissions);
    elsif p_action = 'update' then
      if v_before is null then raise exception 'Role does not exist' using errcode = 'P0002'; end if;
      update public.admin_roles set name = p_name, permissions = p_permissions where key = p_key;
    else
      if exists (select 1 from public.user_roles where role = p_key) then
        raise exception 'Assigned role cannot be deleted' using errcode = '23503';
      end if;
      delete from public.admin_roles where key = p_key;
    end if;
    select to_jsonb(r) into v_after from public.admin_roles r where key = p_key;
  elsif p_action in ('assign', 'revoke') then
    if p_target is null or (p_key <> 'superadmin' and not exists (
      select 1 from public.admin_roles where key = p_key
    )) then
      raise exception 'Invalid role assignment' using errcode = '22023';
    end if;
    select to_jsonb(r) into v_before from public.user_roles r
      where user_id = p_target and role = p_key for update;
    if p_action = 'assign' then
      insert into public.user_roles(user_id, role) values (p_target, p_key)
        on conflict (user_id, role) do nothing;
    else
      delete from public.user_roles where user_id = p_target and role = p_key;
    end if;
    select to_jsonb(r) into v_after from public.user_roles r
      where user_id = p_target and role = p_key;
    v_entity := p_target;
  else
    raise exception 'Invalid role action' using errcode = '22023';
  end if;
  insert into public.audit_log(actor, action, entity_type, entity_id, before, after)
    values (p_actor, 'admin.role.' || p_action, 'admin_role', v_entity,
      jsonb_build_object('key', p_key, 'value', v_before),
      jsonb_build_object('key', p_key, 'value', v_after));
  return jsonb_build_object('key', p_key, 'before', v_before, 'after', v_after);
end;
$$;
revoke all on function public.manage_admin_role(uuid,text,text,text,text[],uuid)
  from public, anon, authenticated;
grant execute on function public.manage_admin_role(uuid,text,text,text,text[],uuid)
  to service_role;

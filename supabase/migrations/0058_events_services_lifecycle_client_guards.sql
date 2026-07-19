-- 0058: Block PostgREST self-publish of events and self-activate of services
-- without a verified/active vendor (D9: NO unverified public listings).
--
-- Gap (0004): organisers/providers may INSERT/UPDATE status freely via RLS owner
-- policies. Public SELECT only checks events.status='published' /
-- services.status='active' — not vendors.status='active'. Same class of hole
-- fixed for vendors in 0057.
--
-- Additive: INSERT+UPDATE status guards + tighten public SELECT policies.
-- Privileged paths (service_role / admin / superuser) unchanged — organiser
-- publish and vendor service activation stay on the API (service_role).
-- Reversible: drop the four triggers/functions; restore prior policy USING
-- clauses (status-only, no vendor join).

-- ---------------------------------------------------------------------------
-- 1. Events: clients may only INSERT as draft; status mutations server-only
-- ---------------------------------------------------------------------------

create or replace function public.guard_event_lifecycle_insert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from 'draft' then
    raise exception 'event status is server-controlled';
  end if;

  return new;
end;
$$;

drop trigger if exists events_guard_lifecycle_insert on public.events;
create trigger events_guard_lifecycle_insert
  before insert on public.events
  for each row
  execute function public.guard_event_lifecycle_insert();

comment on function public.guard_event_lifecycle_insert() is
  'Owners may INSERT only draft events; publish/cancel via admin/service_role.';

revoke all on function public.guard_event_lifecycle_insert() from public;
revoke execute on function public.guard_event_lifecycle_insert() from public, anon, authenticated;
grant execute on function public.guard_event_lifecycle_insert() to postgres, service_role;

create or replace function public.guard_event_lifecycle_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from old.status then
    raise exception 'event status is server-controlled';
  end if;

  return new;
end;
$$;

drop trigger if exists events_guard_lifecycle_update on public.events;
create trigger events_guard_lifecycle_update
  before update on public.events
  for each row
  execute function public.guard_event_lifecycle_update();

comment on function public.guard_event_lifecycle_update() is
  'Owners must not mutate event status via PostgREST; admins/service bypass.';

revoke all on function public.guard_event_lifecycle_update() from public;
revoke execute on function public.guard_event_lifecycle_update() from public, anon, authenticated;
grant execute on function public.guard_event_lifecycle_update() to postgres, service_role;

-- ---------------------------------------------------------------------------
-- 2. Services: clients may only INSERT as draft; status mutations server-only
-- ---------------------------------------------------------------------------

create or replace function public.guard_service_lifecycle_insert()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from 'draft' then
    raise exception 'service status is server-controlled';
  end if;

  return new;
end;
$$;

drop trigger if exists services_guard_lifecycle_insert on public.services;
create trigger services_guard_lifecycle_insert
  before insert on public.services
  for each row
  execute function public.guard_service_lifecycle_insert();

comment on function public.guard_service_lifecycle_insert() is
  'Owners may INSERT only draft services; activate/pause via admin/service_role.';

revoke all on function public.guard_service_lifecycle_insert() from public;
revoke execute on function public.guard_service_lifecycle_insert() from public, anon, authenticated;
grant execute on function public.guard_service_lifecycle_insert() to postgres, service_role;

create or replace function public.guard_service_lifecycle_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from old.status then
    raise exception 'service status is server-controlled';
  end if;

  return new;
end;
$$;

drop trigger if exists services_guard_lifecycle_update on public.services;
create trigger services_guard_lifecycle_update
  before update on public.services
  for each row
  execute function public.guard_service_lifecycle_update();

comment on function public.guard_service_lifecycle_update() is
  'Owners must not mutate service status via PostgREST; admins/service bypass.';

revoke all on function public.guard_service_lifecycle_update() from public;
revoke execute on function public.guard_service_lifecycle_update() from public, anon, authenticated;
grant execute on function public.guard_service_lifecycle_update() to postgres, service_role;

-- ---------------------------------------------------------------------------
-- 3. Public SELECT: require organiser/provider vendor status = active (D9)
-- ---------------------------------------------------------------------------

drop policy if exists events_public_published_select on public.events;
create policy events_public_published_select
  on public.events
  for select
  using (
    status = 'published'
    and exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.status = 'active'
    )
  );

comment on policy events_public_published_select on public.events is
  'Published events are public only when the organiser vendor storefront is active.';

drop policy if exists services_public_active_select on public.services;
create policy services_public_active_select
  on public.services
  for select
  using (
    status = 'active'
    and exists (
      select 1
      from public.vendors v
      where v.id = services.vendor_id
        and v.status = 'active'
    )
  );

comment on policy services_public_active_select on public.services is
  'Active services are public only when the provider vendor storefront is active.';

-- Child public reads keyed off published events — same vendor-active gate.
drop policy if exists event_instances_public_published_select on public.event_instances;
create policy event_instances_public_published_select
  on public.event_instances
  for select
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and e.status = 'published'
        and v.status = 'active'
    )
  );

comment on policy event_instances_public_published_select on public.event_instances is
  'Instances are public only when the parent event is published and organiser is active.';

drop policy if exists ticket_types_public_published_select on public.ticket_types;
create policy ticket_types_public_published_select
  on public.ticket_types
  for select
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and e.status = 'published'
        and v.status = 'active'
    )
  );

comment on policy ticket_types_public_published_select on public.ticket_types is
  'Ticket types are public only when the parent event is published and organiser is active.';

drop policy if exists ticket_type_instances_public_published_select
  on public.ticket_type_instances;
create policy ticket_type_instances_public_published_select
  on public.ticket_type_instances
  for select
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and e.status = 'published'
        and v.status = 'active'
    )
  );

comment on policy ticket_type_instances_public_published_select
  on public.ticket_type_instances is
  'Allocations are public only for published events with an active organiser.';

drop policy if exists ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers;
create policy ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers
  for select
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and e.status = 'published'
        and v.status = 'active'
    )
  );

comment on policy ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers is
  'Price tiers are public only for published events with an active organiser.';

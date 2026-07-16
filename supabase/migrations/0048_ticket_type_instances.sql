-- Events Phase-2 Wave A / M10-P13 (decision D29): per-instance tier allocation.
--
-- A ticket_type attaches to the EVENT, not a specific instance, so today a
-- type's qty_cap applies uniformly to every instance of a multi-date event.
-- This table lets an organiser cap how many of a given type are sold PER
-- instance (e.g. 10 VIP on night 1, 5 on night 2). When a (ticket_type,
-- instance) row exists, its `allocation` is enforced in the oversell-safe claim
-- (services/tickets/inventory.py) as a fourth cap alongside instance.capacity,
-- ticket_type.qty_cap and per_customer_cap. Absence of a row = no per-instance
-- cap (behaviour falls back to those existing limits), so this migration is
-- purely additive and changes nothing until an organiser sets allocations.
--
-- No denormalised "sold" counter: the claim counts live issued tickets per
-- (instance, type) — the same count already used to enforce qty_cap — which is
-- drift-free. The organiser UI reads that live count too. A maintained counter
-- would have to be kept consistent across every claim/void/release path or it
-- would mis-gate oversell.
--
-- Additive + reversible. Down:
--   drop trigger ticket_type_instances_same_event on public.ticket_type_instances;
--   drop function public.guard_ticket_type_instance_same_event();
--   drop table public.ticket_type_instances;  -- cascades the updated_at trigger + policies

create table public.ticket_type_instances (
  ticket_type_id uuid not null references public.ticket_types (id) on delete cascade,
  instance_id uuid not null references public.event_instances (id) on delete cascade,
  allocation int not null check (allocation >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (ticket_type_id, instance_id)
);

comment on table public.ticket_type_instances is
  'Per-(ticket_type, event_instance) sale allocation (M10-P13). A present row caps '
  'that type to `allocation` tickets for that instance, enforced in the '
  'oversell-safe claim; an absent row means no per-instance cap.';
comment on column public.ticket_type_instances.allocation is
  'Max tickets of this type sellable for this instance (>= 0). 0 closes the type '
  'for that instance.';

create index ticket_type_instances_instance_idx
  on public.ticket_type_instances (instance_id);

create trigger ticket_type_instances_set_updated_at
  before update on public.ticket_type_instances
  for each row
  execute function public.set_updated_at();

-- Integrity: the type and the instance must belong to the same event. A cross-
-- event row is inert (the claim joins on both ids, and purchase already checks
-- type<->event<->instance consistency) but is nonsense data — reject it at the
-- source. Belt-and-suspenders with the organiser endpoint's own validation.
create or replace function public.guard_ticket_type_instance_same_event()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_type_event uuid;
  v_instance_event uuid;
begin
  select event_id into v_type_event
  from public.ticket_types where id = new.ticket_type_id;
  select event_id into v_instance_event
  from public.event_instances where id = new.instance_id;
  if v_type_event is null
     or v_instance_event is null
     or v_type_event <> v_instance_event then
    raise exception
      'ticket_type_instances: ticket_type % and instance % are not on the same event',
      new.ticket_type_id, new.instance_id;
  end if;
  return new;
end;
$$;

comment on function public.guard_ticket_type_instance_same_event() is
  'Rejects a ticket_type_instances row whose ticket_type and instance belong to '
  'different events.';

create trigger ticket_type_instances_same_event
  before insert or update on public.ticket_type_instances
  for each row
  execute function public.guard_ticket_type_instance_same_event();

-- RLS: public read only when the parent event is published (so the purchase UI
-- can show remaining stock); organisers manage rows for events they own; admins
-- all. Mirrors public.ticket_types. Writes flow through the service role in the
-- organiser API, but the policies keep client access correct in depth.
alter table public.ticket_type_instances enable row level security;

create policy ticket_type_instances_public_published_select
  on public.ticket_type_instances
  for select
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      where tt.id = ticket_type_instances.ticket_type_id
        and e.status = 'published'
    )
  );

comment on policy ticket_type_instances_public_published_select
  on public.ticket_type_instances is
  'Allocations are public only when the parent event is published.';

create policy ticket_type_instances_organiser_select
  on public.ticket_type_instances
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_instances_organiser_insert
  on public.ticket_type_instances
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_instances_organiser_update
  on public.ticket_type_instances
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy ticket_type_instances_organiser_delete
  on public.ticket_type_instances
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy ticket_type_instances_organiser_select
  on public.ticket_type_instances is
  'Organisers may read allocations for their events regardless of publish status.';
comment on policy ticket_type_instances_organiser_insert
  on public.ticket_type_instances is
  'Organisers may create allocations for events they own.';
comment on policy ticket_type_instances_organiser_update
  on public.ticket_type_instances is
  'Organisers may update allocations for events they own.';
comment on policy ticket_type_instances_organiser_delete
  on public.ticket_type_instances is
  'Organisers may delete allocations for events they own.';

create policy ticket_type_instances_admin_all
  on public.ticket_type_instances
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy ticket_type_instances_admin_all
  on public.ticket_type_instances is
  'Platform admins may manage every allocation row.';

grant select, insert, update, delete
  on table public.ticket_type_instances to authenticated, service_role;
grant select on table public.ticket_type_instances to anon;

-- Events strategy hardening: keep non-public event data out of the public Data
-- API and make cancellation terminal for active ticket credentials.
--
-- This migration deliberately does not move refund money. Cancellation refunds
-- still require the separately audited payout/job state machine; this change
-- only makes access and ticket validity fail closed.
--
-- Rollback notes:
--   * Restore the five public policies from 0058 if non-public rows must again
--     be exposed through PostgREST (not recommended).
--   * Drop tickets_require_published_event, events_cancel_active_tickets, and
--     their functions to remove the lifecycle guards.
--   * Ticket rows voided by cancellation are not automatically reversible:
--     restoring credentials requires an explicit, audited reissue operation.

-- A hash is useful only while an event is private. Keeping an old hash after a
-- private -> public/unlisted transition needlessly retains a credential digest.
update public.events
set access_code_hash = null
where visibility <> 'private'
  and access_code_hash is not null;

alter table public.events
  drop constraint if exists events_access_code_hash_private_check;

alter table public.events
  add constraint events_access_code_hash_private_check
  check (visibility = 'private' or access_code_hash is null) not valid;

alter table public.events
  validate constraint events_access_code_hash_private_check;

comment on constraint events_access_code_hash_private_check on public.events is
  'Access-code digests may be retained only while visibility is private.';

-- Complete the end-time rollout without breaking older writers. Inserts that
-- omit an end retain the documented legacy two-hour duration. A start-only
-- reschedule preserves the row's previous duration instead of leaving a stale
-- absolute end time behind.
create or replace function public.normalize_event_instance_ends_at()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_duration interval;
begin
  if tg_op = 'UPDATE'
    and new.starts_at is distinct from old.starts_at
    and new.ends_at is not distinct from old.ends_at then
    v_duration := coalesce(old.ends_at - old.starts_at, interval '2 hours');
    new.ends_at := new.starts_at + v_duration;
  elsif new.ends_at is null then
    new.ends_at := new.starts_at + interval '2 hours';
  end if;

  if new.ends_at <= new.starts_at then
    raise exception using
      errcode = '23514',
      message = 'event instance ends_at must be after starts_at';
  end if;

  return new;
end;
$$;

drop trigger if exists event_instances_normalize_ends_at on public.event_instances;
create trigger event_instances_normalize_ends_at
  before insert or update on public.event_instances
  for each row
  execute function public.normalize_event_instance_ends_at();

update public.event_instances
set ends_at = starts_at + interval '2 hours'
where ends_at is null;

alter table public.event_instances
  alter column ends_at set not null;

comment on column public.event_instances.ends_at is
  'Required event-instance end time (UTC); legacy writers that omit it receive a two-hour duration.';

revoke all on function public.normalize_event_instance_ends_at() from public;
revoke execute on function public.normalize_event_instance_ends_at()
  from public, anon, authenticated;
grant execute on function public.normalize_event_instance_ends_at()
  to postgres, service_role;

-- Public table SELECT policies must expose listed events only. Unlisted/private
-- detail access is mediated by the service API; allowing those rows here would
-- make them enumerable and expose private schedules/pricing (and the code hash).
drop policy if exists events_public_published_select on public.events;
create policy events_public_published_select
  on public.events
  for select
  to anon, authenticated
  using (
    status = 'published'
    and visibility = 'public'
    and exists (
      select 1
      from public.vendors v
      where v.id = events.organiser_vendor_id
        and v.status = 'active'
    )
  );

comment on policy events_public_published_select on public.events is
  'Listed published events are public only when the organiser storefront is active.';

drop policy if exists event_instances_public_published_select on public.event_instances;
create policy event_instances_public_published_select
  on public.event_instances
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = event_instances.event_id
        and e.status = 'published'
        and e.visibility = 'public'
        and v.status = 'active'
    )
  );

comment on policy event_instances_public_published_select on public.event_instances is
  'Instances are public only for listed published events with an active organiser.';

drop policy if exists ticket_types_public_published_select on public.ticket_types;
create policy ticket_types_public_published_select
  on public.ticket_types
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.events e
      join public.vendors v on v.id = e.organiser_vendor_id
      where e.id = ticket_types.event_id
        and e.status = 'published'
        and e.visibility = 'public'
        and v.status = 'active'
    )
  );

comment on policy ticket_types_public_published_select on public.ticket_types is
  'Ticket types are public only for listed published events with an active organiser.';

drop policy if exists ticket_type_instances_public_published_select
  on public.ticket_type_instances;
create policy ticket_type_instances_public_published_select
  on public.ticket_type_instances
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_instances.ticket_type_id
        and e.status = 'published'
        and e.visibility = 'public'
        and v.status = 'active'
    )
  );

comment on policy ticket_type_instances_public_published_select
  on public.ticket_type_instances is
  'Allocations are public only for listed published events with an active organiser.';

drop policy if exists ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers;
create policy ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.ticket_types tt
      join public.events e on e.id = tt.event_id
      join public.vendors v on v.id = e.organiser_vendor_id
      where tt.id = ticket_type_price_tiers.ticket_type_id
        and e.status = 'published'
        and e.visibility = 'public'
        and v.status = 'active'
    )
  );

comment on policy ticket_type_price_tiers_public_published_select
  on public.ticket_type_price_tiers is
  'Price tiers are public only for listed published events with an active organiser.';

-- Any issued credential must belong to a currently published event. Locking the
-- parent event row closes the issue-vs-cancel race: either issuance finishes and
-- the cancellation trigger voids it, or issuance observes the cancelled state.
create or replace function public.require_published_event_for_issued_ticket()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_event_status text;
begin
  if new.status <> 'issued' then
    return new;
  end if;

  select e.status
  into v_event_status
  from public.event_instances ei
  join public.events e on e.id = ei.event_id
  where ei.id = new.instance_id
  for share of e;

  if v_event_status is null then
    raise exception using
      errcode = '23503',
      message = 'ticket event instance does not exist';
  end if;

  if v_event_status <> 'published' then
    raise exception using
      errcode = '23514',
      message = 'tickets may be issued only for published events';
  end if;

  return new;
end;
$$;

drop trigger if exists tickets_require_published_event on public.tickets;
create trigger tickets_require_published_event
  before insert or update on public.tickets
  for each row
  execute function public.require_published_event_for_issued_ticket();

comment on function public.require_published_event_for_issued_ticket() is
  'Rejects issued ticket credentials unless their parent event is published.';

revoke all on function public.require_published_event_for_issued_ticket() from public;
revoke execute on function public.require_published_event_for_issued_ticket()
  from public, anon, authenticated;
grant execute on function public.require_published_event_for_issued_ticket()
  to postgres, service_role;

-- Cancellation is a terminal ticket-validity transition. Pending transfers are
-- cancelled before tickets are voided to match the transfer claim lock order and
-- reduce deadlock risk. Checked-in tickets remain unchanged as immutable audit.
create or replace function public.cancel_active_tickets_for_event()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.status = 'cancelled' and old.status is distinct from new.status then
    update public.ticket_transfers tt
    set
      status = 'cancelled',
      cancelled_at = coalesce(tt.cancelled_at, timezone('utc', now()))
    from public.tickets t
    join public.event_instances ei on ei.id = t.instance_id
    where tt.ticket_id = t.id
      and ei.event_id = new.id
      and tt.status = 'pending';

    update public.tickets t
    set status = 'void'
    from public.event_instances ei
    where ei.id = t.instance_id
      and ei.event_id = new.id
      and t.status in ('issued', 'transferred');
  end if;

  return new;
end;
$$;

drop trigger if exists events_cancel_active_tickets on public.events;
create trigger events_cancel_active_tickets
  before update of status on public.events
  for each row
  execute function public.cancel_active_tickets_for_event();

comment on function public.cancel_active_tickets_for_event() is
  'Atomically cancels pending transfers and voids active credentials when an event is cancelled.';

revoke all on function public.cancel_active_tickets_for_event() from public;
revoke execute on function public.cancel_active_tickets_for_event()
  from public, anon, authenticated;
grant execute on function public.cancel_active_tickets_for_event()
  to postgres, service_role;

-- Repair rows created before the trigger existed.
update public.ticket_transfers tt
set
  status = 'cancelled',
  cancelled_at = coalesce(tt.cancelled_at, timezone('utc', now()))
from public.tickets t
join public.event_instances ei on ei.id = t.instance_id
join public.events e on e.id = ei.event_id
where tt.ticket_id = t.id
  and e.status = 'cancelled'
  and tt.status = 'pending';

update public.tickets t
set status = 'void'
from public.event_instances ei
join public.events e on e.id = ei.event_id
where ei.id = t.instance_id
  and e.status = 'cancelled'
  and t.status in ('issued', 'transferred');

-- Admin catalog control (hide / block / restore) + typed ad placement targets.
--
-- Additive only: one new table, three functions, four guard triggers, two
-- nullable columns + one CHECK on ad_placements. No existing row or object is
-- altered in place.
--
-- 1. catalog_moderation_holds — one ACTIVE hold per (entity_kind, entity_id)
--    records WHY an admin took an entity off the customer surfaces, the status
--    it had before (restore target) and who did it. Service-role only.
-- 2. public.moderate_catalog_entity(...) / public.release_catalog_moderation(...)
--    are the ONLY paths that move an entity's status for admin moderation
--    (convention 4: guarded transitions, never raw status UPDATEs). They lock
--    the entity row, validate the edge, write/close the hold and flip status
--    under the `app.catalog_moderation` GUC. The API writes the admin
--    audit_log row through its audited route class.
-- 3. guard_catalog_moderation_hold() — while an active hold exists, no other
--    writer (vendor API on the service role, PostgREST owner, n8n) can move the
--    entity back to its customer-visible status. Search projections follow the
--    status change through the existing search_sync_* triggers.
-- 4. ad_placements.target_kind/target_id — typed target (listing, product,
--    service, event, vendor). The API drops a live placement whose target or
--    advertiser vendor is no longer customer-visible.
--
-- Edges (mirrors the python helpers in app/routers/admin_flags.py):
--   listing  hide  active|paused         -> paused
--   listing  block active|paused|draft   -> removed   (removed is admin-only)
--   service  hide|block active|paused|draft -> paused
--   event    hide|block published|draft  -> draft
--   vendor   block active|suspended      -> suspended
--   release  -> hold.from_status (vendor: -> active, only with approved KYC)
--
-- Down (manual, reversible — no existing data is touched):
--   drop trigger if exists vendor_listings_guard_moderation_hold on public.vendor_listings;
--   drop trigger if exists services_guard_moderation_hold on public.services;
--   drop trigger if exists events_guard_moderation_hold on public.events;
--   drop trigger if exists vendors_guard_moderation_hold on public.vendors;
--   drop function if exists public.guard_catalog_moderation_hold();
--   drop function if exists public.release_catalog_moderation(text, uuid, uuid, text);
--   drop function if exists public.moderate_catalog_entity(text, uuid, text, uuid, text);
--   drop table if exists public.catalog_moderation_holds;
--   alter table public.ad_placements drop constraint if exists ad_placements_target_pair;
--   alter table public.ad_placements drop column if exists target_id;
--   alter table public.ad_placements drop column if exists target_kind;

-- ---------------------------------------------------------------------------
-- catalog_moderation_holds
-- ---------------------------------------------------------------------------
create table public.catalog_moderation_holds (
  id uuid primary key default gen_random_uuid(),
  entity_kind text not null check (entity_kind in ('listing', 'service', 'event', 'vendor')),
  entity_id uuid not null,
  action text not null check (action in ('hide', 'block')),
  from_status text not null,
  reason text not null check (length(trim(reason)) between 3 and 500),
  actor uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  released_at timestamptz,
  released_by uuid,
  release_reason text check (release_reason is null or length(release_reason) <= 500)
);

create unique index catalog_moderation_holds_active_uidx
  on public.catalog_moderation_holds (entity_kind, entity_id)
  where released_at is null;

create index catalog_moderation_holds_entity_idx
  on public.catalog_moderation_holds (entity_kind, entity_id, created_at desc);

create trigger catalog_moderation_holds_set_updated_at
  before update on public.catalog_moderation_holds
  for each row execute function public.set_updated_at();

alter table public.catalog_moderation_holds enable row level security;
alter table public.catalog_moderation_holds force row level security;
revoke all on public.catalog_moderation_holds from public, anon, authenticated;
grant select, insert, update on public.catalog_moderation_holds to service_role;

comment on table public.catalog_moderation_holds is
  'Admin hide/block holds on listings, services, events and vendors. Written only by '
  'moderate_catalog_entity / release_catalog_moderation. Service role only.';

-- ---------------------------------------------------------------------------
-- Guard: an active hold pins the entity off its customer-visible status
-- ---------------------------------------------------------------------------
create function public.guard_catalog_moderation_hold() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  kind text := tg_argv[0];
  public_status text := tg_argv[1];
begin
  if new.status is distinct from old.status
     and new.status = public_status
     and coalesce(current_setting('app.catalog_moderation', true), '') <> 'on'
     and exists (
       select 1 from public.catalog_moderation_holds h
       where h.entity_kind = kind and h.entity_id = new.id and h.released_at is null
     ) then
    raise exception 'catalog_moderation_hold: % % is held by an admin', kind, new.id
      using errcode = '42501';
  end if;
  return new;
end;
$$;
revoke all on function public.guard_catalog_moderation_hold() from public, anon, authenticated;

create trigger vendor_listings_guard_moderation_hold
  before update of status on public.vendor_listings
  for each row execute function public.guard_catalog_moderation_hold('listing', 'active');
create trigger services_guard_moderation_hold
  before update of status on public.services
  for each row execute function public.guard_catalog_moderation_hold('service', 'active');
create trigger events_guard_moderation_hold
  before update of status on public.events
  for each row execute function public.guard_catalog_moderation_hold('event', 'published');
create trigger vendors_guard_moderation_hold
  before update of status on public.vendors
  for each row execute function public.guard_catalog_moderation_hold('vendor', 'active');

-- ---------------------------------------------------------------------------
-- Internal: read + lock an entity's status
-- ---------------------------------------------------------------------------
create function public.catalog_entity_status_for_update(p_kind text, p_entity_id uuid)
returns text
language plpgsql security definer set search_path = '' as $$
declare
  current_status text;
begin
  if p_kind = 'listing' then
    select status into current_status from public.vendor_listings where id = p_entity_id for update;
  elsif p_kind = 'service' then
    select status into current_status from public.services where id = p_entity_id for update;
  elsif p_kind = 'event' then
    select status into current_status from public.events where id = p_entity_id for update;
  elsif p_kind = 'vendor' then
    select status into current_status from public.vendors where id = p_entity_id for update;
  else
    raise exception 'Unsupported catalog entity kind %', p_kind using errcode = '22023';
  end if;
  if current_status is null then
    raise exception 'Catalog entity not found' using errcode = 'P0002';
  end if;
  return current_status;
end;
$$;
revoke all on function public.catalog_entity_status_for_update(text, uuid)
  from public, anon, authenticated;

create function public.catalog_entity_set_status(p_kind text, p_entity_id uuid, p_status text)
returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform pg_catalog.set_config('app.catalog_moderation', 'on', true);
  if p_kind = 'listing' then
    update public.vendor_listings set status = p_status where id = p_entity_id;
  elsif p_kind = 'service' then
    update public.services set status = p_status where id = p_entity_id;
  elsif p_kind = 'event' then
    update public.events set status = p_status where id = p_entity_id;
  elsif p_kind = 'vendor' then
    update public.vendors set status = p_status where id = p_entity_id;
  end if;
  perform pg_catalog.set_config('app.catalog_moderation', 'off', true);
end;
$$;
revoke all on function public.catalog_entity_set_status(text, uuid, text)
  from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- moderate_catalog_entity — hide / block (escalating an existing hide is allowed)
-- ---------------------------------------------------------------------------
create function public.moderate_catalog_entity(
  p_kind text,
  p_entity_id uuid,
  p_action text,
  p_actor uuid,
  p_reason text
)
returns public.catalog_moderation_holds
language plpgsql security definer set search_path = '' as $$
declare
  current_status text;
  target_status text;
  allowed_from text[];
  existing public.catalog_moderation_holds;
  result public.catalog_moderation_holds;
begin
  if p_reason is null or length(trim(p_reason)) < 3 then
    raise exception 'A moderation reason is required' using errcode = '22023';
  end if;
  if p_action not in ('hide', 'block') then
    raise exception 'Unsupported moderation action %', p_action using errcode = '22023';
  end if;

  current_status := public.catalog_entity_status_for_update(p_kind, p_entity_id);

  if p_kind = 'listing' then
    if p_action = 'hide' then
      allowed_from := array['active', 'paused']; target_status := 'paused';
    else
      allowed_from := array['active', 'paused', 'draft', 'removed']; target_status := 'removed';
    end if;
  elsif p_kind = 'service' then
    allowed_from := array['active', 'paused', 'draft']; target_status := 'paused';
  elsif p_kind = 'event' then
    allowed_from := array['published', 'draft']; target_status := 'draft';
  else
    if p_action <> 'block' then
      raise exception 'Vendors can only be blocked (suspended)' using errcode = '22023';
    end if;
    allowed_from := array['active', 'suspended']; target_status := 'suspended';
  end if;

  select * into existing from public.catalog_moderation_holds
   where entity_kind = p_kind and entity_id = p_entity_id and released_at is null
   for update;

  if found then
    if existing.action = 'block' or p_action = 'hide' then
      raise exception 'Entity is already moderated' using errcode = '23505';
    end if;
    -- Escalate hide -> block; keep the original restore target.
    if not (current_status = any(allowed_from)) then
      raise exception 'Invalid moderation transition % -> %', current_status, target_status
        using errcode = '23514';
    end if;
    update public.catalog_moderation_holds
       set action = 'block', reason = trim(p_reason), actor = p_actor
     where id = existing.id
    returning * into result;
  else
    if not (current_status = any(allowed_from)) or current_status = 'removed' then
      raise exception 'Invalid moderation transition % -> %', current_status, target_status
        using errcode = '23514';
    end if;
    insert into public.catalog_moderation_holds
      (entity_kind, entity_id, action, from_status, reason, actor)
    values (p_kind, p_entity_id, p_action, current_status, trim(p_reason), p_actor)
    returning * into result;
  end if;

  if current_status is distinct from target_status then
    perform public.catalog_entity_set_status(p_kind, p_entity_id, target_status);
  end if;
  return result;
end;
$$;

-- ---------------------------------------------------------------------------
-- release_catalog_moderation — restore to the pre-hold status
-- ---------------------------------------------------------------------------
create function public.release_catalog_moderation(
  p_kind text,
  p_entity_id uuid,
  p_actor uuid,
  p_reason text
)
returns public.catalog_moderation_holds
language plpgsql security definer set search_path = '' as $$
declare
  current_status text;
  target_status text;
  hold public.catalog_moderation_holds;
  latest_kyc text;
begin
  if p_reason is null or length(trim(p_reason)) < 3 then
    raise exception 'A restore reason is required' using errcode = '22023';
  end if;

  current_status := public.catalog_entity_status_for_update(p_kind, p_entity_id);

  select * into hold from public.catalog_moderation_holds
   where entity_kind = p_kind and entity_id = p_entity_id and released_at is null
   for update;

  if p_kind = 'vendor' then
    -- Reinstate also covers a flag-escalated suspension (no hold row). Never
    -- reactivate a vendor whose KYC is not currently approved (KYC suspend /
    -- revoke must be resolved through the KYC state machine).
    if hold.id is null and current_status <> 'suspended' then
      raise exception 'Vendor is not suspended' using errcode = 'P0002';
    end if;
    select status into latest_kyc from public.kyc_records
     where vendor_id = p_entity_id order by created_at desc limit 1;
    if coalesce(latest_kyc, '') <> 'approved' then
      raise exception 'Vendor KYC is not approved' using errcode = '23514';
    end if;
    target_status := 'active';
    if hold.id is null then
      insert into public.catalog_moderation_holds
        (entity_kind, entity_id, action, from_status, reason, actor)
      values ('vendor', p_entity_id, 'block', current_status, 'Suspended outside catalog control', null)
      returning * into hold;
    end if;
  else
    if hold.id is null then
      raise exception 'No active moderation hold' using errcode = 'P0002';
    end if;
    target_status := hold.from_status;
  end if;

  update public.catalog_moderation_holds
     set released_at = now(), released_by = p_actor, release_reason = trim(p_reason)
   where id = hold.id
  returning * into hold;

  if current_status is distinct from target_status then
    perform public.catalog_entity_set_status(p_kind, p_entity_id, target_status);
  end if;
  return hold;
end;
$$;

revoke all on function public.moderate_catalog_entity(text, uuid, text, uuid, text)
  from public, anon, authenticated;
grant execute on function public.moderate_catalog_entity(text, uuid, text, uuid, text)
  to service_role;
revoke all on function public.release_catalog_moderation(text, uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function public.release_catalog_moderation(text, uuid, uuid, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- ad_placements: typed target
-- ---------------------------------------------------------------------------
alter table public.ad_placements
  add column target_kind text
    check (target_kind is null or target_kind in ('listing', 'product', 'service', 'event', 'vendor')),
  add column target_id uuid;

alter table public.ad_placements
  add constraint ad_placements_target_pair
  check ((target_kind is null) = (target_id is null));

comment on column public.ad_placements.target_kind is
  'What the ad promotes. When set, the placement is served only while the target '
  '(and its owning vendor) is customer-visible.';

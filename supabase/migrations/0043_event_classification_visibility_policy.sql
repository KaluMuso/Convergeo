-- Events Phase-2 Wave A / M10-P10 (decision D29): event classification,
-- visibility & policy foundation.
--
-- Adds the schema everything else in Wave A keys off:
--   * event_type  — the full behavioural driver (D29): standard | recurring |
--     free_rsvp | private. Drives discovery, escrow timing (P14) and UX. All
--     per-type behaviour lives in services/events/type_policy.py — no consumer
--     branches on event_type inline.
--   * visibility  — the access-control axis: public (listed) | unlisted (hidden
--     from browse/search, reachable by direct link) | private (access-code
--     gated). Discovery + search read this column directly.
--   * access_code_hash — salted hash of a private event's access code
--     (services/events/access.py); NULL until an organiser sets one.
--   * refund_policy_key / age_restriction / terms — additive policy fields, no
--     launch-behaviour enforcement (UX/i18n only for now).
--
-- Money-free by design: escrow is NOT wired to event_type here (that is P14).
-- Defaults ('standard' / 'public') preserve today's behaviour exactly, so this
-- migration is additive + non-breaking.
--
-- Additive + reversible. Down:
--   alter table public.events
--     drop column event_type, drop column visibility, drop column access_code_hash,
--     drop column refund_policy_key, drop column age_restriction, drop column terms;
--   drop index events_status_visibility_idx;
--   -- and restore the 0039 search_upsert_event body (drop the visibility gate).

alter table public.events
  add column event_type text not null default 'standard'
    check (event_type in ('standard', 'recurring', 'free_rsvp', 'private'));

alter table public.events
  add column visibility text not null default 'public'
    check (visibility in ('public', 'unlisted', 'private'));

alter table public.events
  add column access_code_hash text;

alter table public.events
  add column refund_policy_key text;

alter table public.events
  add column age_restriction int
    check (age_restriction is null or (age_restriction >= 0 and age_restriction <= 120));

alter table public.events
  add column terms text;

-- Browse filters status='published' AND visibility='public'; index the pair.
create index events_status_visibility_idx on public.events (status, visibility);

comment on column public.events.event_type is
  'Full behavioural driver (D29): standard|recurring|free_rsvp|private. Governs '
  'discovery, escrow settlement timing (via services/events/type_policy.py, P14) '
  'and UX. Never branched on inline — read the policy map.';
comment on column public.events.visibility is
  'Access-control axis: public (listed) | unlisted (hidden from browse/search, '
  'reachable by direct link) | private (access-code gated via access_code_hash).';
comment on column public.events.access_code_hash is
  'Salted hash (services/events/access.py) of a private event''s access code; '
  'NULL until set. A private event with no code is unreachable publicly.';
comment on column public.events.refund_policy_key is
  'Organiser-selected refund policy key (UX/i18n); no launch-time enforcement.';
comment on column public.events.age_restriction is
  'Minimum attendee age (years); NULL = no restriction. UX/display only at launch.';
comment on column public.events.terms is
  'Organiser event terms/conditions text; UX/display only at launch.';

-- ---------------------------------------------------------------------------
-- Search: exclude non-public events from the index. search_upsert_event is
-- trigger-driven on every events change (0009), so a visibility change
-- propagates automatically. Body is 0039's (category_path = events/<slug>) plus
-- the visibility gate. Down: restore the 0039 body.
-- ---------------------------------------------------------------------------

create or replace function public.search_upsert_event(p_event_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
  v_price_min bigint;
  v_price_max bigint;
begin
  select
    e.id,
    e.title,
    e.description,
    e.venue,
    e.lat,
    e.lng,
    e.category_slug,
    e.status as event_status,
    e.visibility as event_visibility,
    v.status as vendor_status,
    v.display_name as vendor_name
  into v_row
  from public.events e
  join public.vendors v on v.id = e.organiser_vendor_id
  where e.id = p_event_id;

  if not found then
    perform public.search_remove_document('event', p_event_id);
    return;
  end if;

  if v_row.event_status <> 'published'
     or v_row.vendor_status <> 'active'
     or v_row.event_visibility <> 'public' then
    perform public.search_mark_unpublished('event', p_event_id);
    return;
  end if;

  select min(tt.price_ngwee), max(tt.price_ngwee)
  into v_price_min, v_price_max
  from public.ticket_types tt
  where tt.event_id = p_event_id;

  insert into public.search_documents (
    entity_kind,
    entity_id,
    title,
    body,
    category_path,
    price_min_ngwee,
    price_max_ngwee,
    lat,
    lng,
    locale_terms,
    boost_signals,
    is_public
  )
  values (
    'event',
    v_row.id,
    v_row.title,
    trim(both ' ' from coalesce(v_row.description, '') || ' ' || coalesce(v_row.venue, '') || ' ' || coalesce(v_row.vendor_name, '')),
    coalesce('events/' || v_row.category_slug, 'events'),
    v_price_min,
    v_price_max,
    v_row.lat,
    v_row.lng,
    null,
    jsonb_build_object(
      'in_stock', true,
      'verified', true,
      'below_median', false
    ),
    true
  )
  on conflict (entity_kind, entity_id) do update
  set
    title = excluded.title,
    body = excluded.body,
    category_path = excluded.category_path,
    price_min_ngwee = excluded.price_min_ngwee,
    price_max_ngwee = excluded.price_max_ngwee,
    lat = excluded.lat,
    lng = excluded.lng,
    locale_terms = excluded.locale_terms,
    boost_signals = excluded.boost_signals,
    is_public = true,
    updated_at = timezone('utc', now());
end;
$$;

-- Reindex: drop any now-non-public published events out of the index.
select public.search_upsert_event(id) from public.events where status = 'published';

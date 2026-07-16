-- 0041: Events Phase-2 Wave A (M10-P10) — event classification, visibility & policy.
--
-- D29 opens the Events Phase-2 expansion. This is the money-free foundation pebble:
-- it adds the columns everything downstream keys off, with NO change to escrow,
-- pricing, or ticketing behavior (those are P11–P14).
--
-- New columns on public.events:
--   * event_type   — behavioral driver consumed by the guarded policy map
--                    (services/events/policy.py); drives discovery + (later) escrow + UX.
--                    Enum is a CHECK so a future type is an additive widen. Default 'single'
--                    preserves every existing event's current behavior.
--   * visibility   — public (browsable) | unlisted (hidden from browse, link works) |
--                    private (access-code required). Default 'public'.
--   * access_code  — required iff visibility='private' (enforced by CHECK below).
--   * refund_policy_key / age_restriction / terms — additive event policy fields,
--                    no launch-behavior change.
--
-- Also: private events must never leak (row or access_code) to anonymous direct DB
-- reads, so the public read RLS policy is tightened to exclude private. The /events
-- API reads via the service-role client and enforces link/code access in-code.
--
-- Additive + reversible. Down: drop the columns + constraint and restore the policy
-- USING clause to `status = 'published'`.

alter table public.events
  add column if not exists event_type text not null default 'single'
    check (event_type in ('single', 'multi_day', 'experience', 'free')),
  add column if not exists visibility text not null default 'public'
    check (visibility in ('public', 'unlisted', 'private')),
  add column if not exists access_code text,
  add column if not exists refund_policy_key text,
  add column if not exists age_restriction int
    check (age_restriction is null or age_restriction >= 0),
  add column if not exists terms text;

-- Private visibility is meaningless without a code to gate it. Existing rows default
-- to 'public', so this constraint validates cleanly at add time.
alter table public.events
  drop constraint if exists events_private_requires_access_code_chk;
alter table public.events
  add constraint events_private_requires_access_code_chk
  check (
    visibility <> 'private'
    or (access_code is not null and length(trim(access_code)) > 0)
  );

-- Defense-in-depth: hide private events (and their access_code) from anonymous /
-- non-owner direct DB reads. Organisers still read their own via events_organiser_select;
-- the service-role API path handles unlisted-by-link and private-by-code.
alter policy events_public_published_select
  on public.events
  using (status = 'published' and visibility <> 'private');

comment on policy events_public_published_select on public.events is
  'Anonymous and authenticated clients may read published, non-private events only.';

-- search_upsert_event: keep the 0039 category-path projection, but only index PUBLIC
-- published events. Unlisted/private events are reachable by link/code but must not
-- surface in browse/search. (Body copied from 0039 with the visibility guard added.)
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
    e.visibility,
    e.status as event_status,
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
     or v_row.visibility <> 'public' then
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

-- Reindex published events so any already-unlisted/private ones drop out of search.
-- (At apply time every event is 'public', so this is a no-op beyond re-touching rows.)
select public.search_upsert_event(id) from public.events where status = 'published';

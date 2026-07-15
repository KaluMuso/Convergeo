-- D2 follow-up: index events under their real category in search.
--
-- search_upsert_event (0009_search.sql) hardcoded category_path = 'events' for
-- every event, so category-filtered search never worked for events. Now that
-- events.category_slug exists (0036), project a hierarchical 'events/<slug>'
-- path — matching how products/listings/services carry a real category_path.
--
-- The search category filter is a prefix match (`category_path like f || '%'`),
-- so a bare 'events' filter still matches every event: backward compatible.
--
-- create-or-replace (additive) + a reindex of existing published events.
-- Down: restore the 0009 body (category_path literal 'events').

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

  if v_row.event_status <> 'published' or v_row.vendor_status <> 'active' then
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

-- Reindex existing published events so their category_path is corrected.
select public.search_upsert_event(id) from public.events where status = 'published';

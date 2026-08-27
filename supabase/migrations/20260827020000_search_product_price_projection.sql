-- PR-F2 (E2E run #52, RC-4): a canonical multiseller product's search
-- document has always carried price_min_ngwee/price_max_ngwee = NULL —
-- public.search_upsert_product() (0009_search.sql) hardcoded both to `null`
-- in the INSERT rather than deriving them from the product's listings. The
-- customer search results card falls back to `?? 0` when both are absent
-- (apps/customer/.../_components/search/results-tabs.tsx), so a real,
-- in-stock, multi-vendor product renders "K0.00" in search — confirmed live
-- against staging (product `stg-rv-20260719-product-a`: search_documents
-- carried NULL/NULL while its two listing documents correctly showed
-- 12500/14900) and root-caused to this function via
-- `grep -rn "search_upsert_product" supabase/migrations` (defined once, in
-- 0009_search.sql, never redefined since).
--
-- ─── Eligible-listing price policy ──────────────────────────────────────────
-- A listing counts toward its product's price_min_ngwee/price_max_ngwee iff
--   vendor_listings.status = 'active' AND vendors.status = 'active'
-- — exactly the same predicate public.search_upsert_listing() already uses
-- to decide whether that listing's OWN document is published (is_public=
-- true) vs. unpublished. No additional filter by stock, wholesale, or
-- product_class:
--   * search_upsert_listing() already publishes an out-of-stock listing with
--     its real price (0040_listing_below_median.sql tags in_stock=false in
--     boost_signals rather than nulling the price or excluding the row), so
--     product-level aggregation matches that rather than being stricter than
--     the listing document it is built from.
--   * The live search_query_facets wholesale exclusion
--     (0068_search_query_facets_wholesale_and_kinds.sql, `not p.exclude_
--     wholesale or sd.entity_kind <> 'listing' or not exists (...)`) is
--     scoped to entity_kind='listing' rows only — the `sd.entity_kind <>
--     'listing'` branch always short-circuits it true for product rows.
--     Current release architecture treats wholesale exclusion as a
--     listing-row, query-time concern, never a product-aggregate one.
--   * Class D/E listings can never carry product_id (`enforce_product_
--     strategy_listing_policy`, 20260813064106), so they can never join to a
--     product here regardless. Class C cannot be status='active' while
--     `product_class_c_customer_release` stays disabled (current release
--     state) — both are already excluded structurally; no extra predicate
--     needed.
-- When no listing is eligible, `min()`/`max()` over the empty set is NULL by
-- ordinary Postgres aggregate semantics — an honest no-offer, not a
-- fabricated K0.00 — and the product document's is_public stays governed
-- solely by products.status, exactly as before this migration.

create or replace function public.search_upsert_product(p_product_id uuid)
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
    p.id,
    p.name,
    p.brand,
    p.spec,
    p.aliases,
    p.status,
    c.path as category_path
  into v_row
  from public.products p
  left join public.categories c on c.id = p.category_id
  where p.id = p_product_id;

  if not found then
    perform public.search_remove_document('product', p_product_id);
    return;
  end if;

  if v_row.status <> 'active' then
    perform public.search_mark_unpublished('product', p_product_id);
    return;
  end if;

  select min(vl.price_ngwee), max(vl.price_ngwee)
  into v_price_min, v_price_max
  from public.vendor_listings vl
  join public.vendors v on v.id = vl.vendor_id
  where vl.product_id = p_product_id
    and vl.status = 'active'
    and v.status = 'active';

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
    'product',
    v_row.id,
    v_row.name,
    trim(both ' ' from coalesce(v_row.brand, '') || ' ' || coalesce(v_row.spec::text, '')),
    v_row.category_path,
    v_price_min,
    v_price_max,
    null,
    null,
    v_row.aliases,
    '{}'::jsonb,
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

-- ─── Synchronization: a listing write can now change its product's price ──
-- range, so the listing sync trigger must also refresh the affected
-- product document(s), not only its own. Refreshing the product doc is
-- skipped when nothing that can move the aggregate changed (a pure
-- stock/title/wholesale-only edit still refreshes the listing doc as
-- before, but not the product) — "avoid unnecessary duplicate work".
create or replace function public.search_sync_listings_trigger()
returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if tg_op = 'DELETE' then
    perform public.search_remove_document('listing', old.id);
    if old.product_id is not null then
      perform public.search_upsert_product(old.product_id);
    end if;
    return old;
  end if;

  perform public.search_upsert_listing(new.id);

  if tg_op = 'INSERT' then
    if new.product_id is not null then
      perform public.search_upsert_product(new.product_id);
    end if;
    return new;
  end if;

  -- UPDATE: refresh the (possibly new) product whenever price, publication
  -- status, or product assignment changed; separately refresh the OLD
  -- product only when the listing actually moved off it (already covered by
  -- the block above when it stayed on the same product).
  if new.product_id is not null
     and (
       new.product_id is distinct from old.product_id
       or new.price_ngwee is distinct from old.price_ngwee
       or new.status is distinct from old.status
     ) then
    perform public.search_upsert_product(new.product_id);
  end if;

  if old.product_id is not null and old.product_id is distinct from new.product_id then
    perform public.search_upsert_product(old.product_id);
  end if;

  return new;
end;
$$;

-- ─── Synchronization: vendor status gates listing eligibility too ─────────
-- A vendor publish/suspend can shrink, grow, or clear a product's price
-- range even though the product row itself never changed, so the vendor
-- child-cascade must also refresh affected product documents. DISTINCT
-- product ids avoid refreshing the same product once per listing when a
-- vendor carries several listings on it. No recursion: search_upsert_product
-- never touches vendors or re-enters this cascade.
create or replace function public.search_cascade_vendor_children(p_vendor_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_listing_id uuid;
  v_service_id uuid;
  v_event_id uuid;
  v_product_id uuid;
begin
  for v_listing_id in
    select vl.id from public.vendor_listings vl where vl.vendor_id = p_vendor_id
  loop
    perform public.search_upsert_listing(v_listing_id);
  end loop;

  for v_service_id in
    select s.id from public.services s where s.vendor_id = p_vendor_id
  loop
    perform public.search_upsert_service(v_service_id);
  end loop;

  for v_event_id in
    select e.id from public.events e where e.organiser_vendor_id = p_vendor_id
  loop
    perform public.search_upsert_event(v_event_id);
  end loop;

  for v_product_id in
    select distinct vl.product_id
    from public.vendor_listings vl
    where vl.vendor_id = p_vendor_id
      and vl.product_id is not null
  loop
    perform public.search_upsert_product(v_product_id);
  end loop;
end;
$$;

-- ─── Backfill ───────────────────────────────────────────────────────────
-- Redefining the functions above only fixes FUTURE writes. Repair every
-- already-projected product document in place, under the corrected
-- function, so this migration alone (no manual production SQL step) fixes
-- live search results. Idempotent: search_upsert_product() is itself an
-- ON CONFLICT DO UPDATE upsert, so replaying this migration (or this loop)
-- converges to the same state every time.
do $$
declare
  v_product_id uuid;
begin
  for v_product_id in select id from public.products loop
    perform public.search_upsert_product(v_product_id);
  end loop;
end;
$$;

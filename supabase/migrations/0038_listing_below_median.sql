-- 0038: Make the `below_median` search boost signal real for vendor listings.
-- (Renumbered from 0034 → 0038: master merged 0034_search_rating_boost + 0035–0037
--  while this branch was open. That 0034 wired the *rating* boost into
--  search_apply_boost and kept the below_median term; this migration is the
--  complementary fix that finally *populates* below_median in the projection.)
--
-- Background: 0009's `search_apply_boost` multiplies a listing's RRF score by
-- +0.05 when `boost_signals->>'below_median'` is true, but every projection
-- function hard-coded the signal to `false`. The boost was therefore dead — the
-- cheaper offers on a canonical product never received the intended ranking
-- lift, which directly undercuts the D24 price-comparison moat
-- ("N vendors selling this product").
--
-- Fix: `below_median` is now computed per listing as "priced below the median of
-- all active, publishable listings for the SAME canonical product". This is the
-- only peer set that carries a price for comparison — standalone listings
-- (product_id IS NULL) have no canonical peers and no category_path in the
-- projection, so they keep `below_median = false`.
--
-- Semantics preserved from 0009: this rebuilds boost_signals on every upsert
-- (in_stock / verified / below_median), exactly as before; the 0028 rating merge
-- continues to re-apply on the next review recompute (unchanged design). Only the
-- `below_median` value changes from a constant to a computed one.
--
-- Staleness note: the signal is computed at projection time, so a listing's flag
-- reflects the peer prices as of its last publish/update. When a *sibling's*
-- price changes, this listing is not re-projected until it is next touched. At
-- launch scale (few vendors per product) this is acceptable and self-corrects on
-- the next edit; a periodic full re-projection job can tighten it later if needed.

create or replace function public.search_upsert_listing(p_listing_id uuid)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row record;
  v_in_stock boolean;
  v_verified boolean;
  v_below_median boolean;
  v_median double precision;
begin
  select
    vl.id,
    vl.product_id,
    vl.title_override,
    vl.price_ngwee,
    vl.condition,
    vl.stock_mode,
    vl.stock_qty,
    vl.status as listing_status,
    v.status as vendor_status,
    v.display_name as vendor_name,
    v.kyc_tier,
    v.preferred_badge,
    p.name as product_name,
    p.aliases as product_aliases,
    c.path as category_path,
    loc.lat,
    loc.lng
  into v_row
  from public.vendor_listings vl
  join public.vendors v on v.id = vl.vendor_id
  left join public.products p on p.id = vl.product_id
  left join public.categories c on c.id = p.category_id
  left join lateral (
    select vl2.lat, vl2.lng
    from public.vendor_locations vl2
    where vl2.vendor_id = vl.vendor_id
    order by vl2.created_at
    limit 1
  ) loc on true
  where vl.id = p_listing_id;

  if not found then
    perform public.search_remove_document('listing', p_listing_id);
    return;
  end if;

  if v_row.listing_status <> 'active' or v_row.vendor_status <> 'active' then
    perform public.search_mark_unpublished('listing', p_listing_id);
    return;
  end if;

  v_in_stock := v_row.stock_mode = 'always_available'
    or coalesce(v_row.stock_qty, 0) > 0;
  v_verified := coalesce(v_row.kyc_tier, 0) >= 2 or coalesce(v_row.preferred_badge, false);

  -- below_median: cheaper than the median active/publishable offer for the same
  -- canonical product. Only meaningful when attached to a canonical product.
  v_below_median := false;
  if v_row.product_id is not null then
    select percentile_cont(0.5) within group (order by vl2.price_ngwee)
    into v_median
    from public.vendor_listings vl2
    join public.vendors v2 on v2.id = vl2.vendor_id
    where vl2.product_id = v_row.product_id
      and vl2.status = 'active'
      and v2.status = 'active';

    v_below_median := v_median is not null and v_row.price_ngwee < v_median;
  end if;

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
    'listing',
    v_row.id,
    coalesce(nullif(trim(v_row.title_override), ''), v_row.product_name, 'Listing'),
    trim(both ' ' from coalesce(v_row.vendor_name, '') || ' ' || coalesce(v_row.condition, '')),
    v_row.category_path,
    v_row.price_ngwee,
    v_row.price_ngwee,
    v_row.lat,
    v_row.lng,
    v_row.product_aliases,
    jsonb_build_object(
      'in_stock', v_in_stock,
      'verified', v_verified,
      'below_median', v_below_median
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

-- One-time, non-destructive backfill: set the correct below_median on every
-- already-projected active listing document WITHOUT clobbering in_stock /
-- verified / rating_* keys (merge via `||`, right-wins on the single key). This
-- avoids a catalog-wide rating-signal wipe that calling the rebuild function on
-- every listing would cause at migration apply.
update public.search_documents sd
set boost_signals = sd.boost_signals || jsonb_build_object('below_median', bm.below_median),
    updated_at = timezone('utc', now())
from (
  select
    vl.id as listing_id,
    (m.median is not null and vl.price_ngwee < m.median) as below_median
  from public.vendor_listings vl
  join public.vendors v on v.id = vl.vendor_id
  join lateral (
    select percentile_cont(0.5) within group (order by vl2.price_ngwee) as median
    from public.vendor_listings vl2
    join public.vendors v2 on v2.id = vl2.vendor_id
    where vl2.product_id = vl.product_id
      and vl2.status = 'active'
      and v2.status = 'active'
  ) m on vl.product_id is not null
  where vl.status = 'active'
    and v.status = 'active'
) bm
where sd.entity_kind = 'listing'
  and sd.entity_id = bm.listing_id;

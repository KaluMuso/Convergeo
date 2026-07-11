-- M15-P02: Bayesian review aggregation (per product / listing / vendor) + search boost sync.
--
-- Single source of truth for star ratings on cards + PDP + vendor pages. The aggregate is
-- recomputed from published `reviews` (0007) — incrementally on every review write (trigger)
-- and in bulk nightly (recompute_all_review_aggregates). Both paths call the SAME
-- recompute_review_aggregate(kind, id) function, so incremental and nightly converge by
-- construction. The Bayesian shrinkage (m = platform mean prior, C = confidence weight) stops
-- a single 5-star review from gaming the ranking.
--
-- REVERSAL (additive + reversible):
--   drop trigger reviews_recompute_aggregate on public.reviews;
--   drop function public.reviews_recompute_aggregate_trigger();
--   drop function public.recompute_all_review_aggregates();
--   drop function public.recompute_review_aggregate_for_order_item(uuid);
--   drop function public.recompute_review_aggregate(text, uuid);
--   drop function public.review_bayes_value(integer, integer);
--   drop table public.review_aggregates;
--   delete from public.platform_config
--     where key in ('review_bayes_prior_m', 'review_bayes_confidence_c');

-- ---------------------------------------------------------------------------
-- Aggregate storage — one row per (entity_kind, entity_id).
-- count/sum are exact integers (no float drift); the Bayesian value is numeric.
-- ---------------------------------------------------------------------------
create table public.review_aggregates (
  entity_kind text not null check (entity_kind in ('product', 'listing', 'vendor')),
  entity_id uuid not null,
  rating_count integer not null default 0 check (rating_count >= 0),
  rating_sum integer not null default 0 check (rating_sum >= 0),
  rating_bayes numeric(4, 3) not null default 0,
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (entity_kind, entity_id)
);

comment on table public.review_aggregates is
  'Bayesian-weighted review aggregate per product/listing/vendor — the single source of star '
  'ratings on cards, PDP, and vendor pages. Public read; service_role / trigger write only.';

create trigger review_aggregates_set_updated_at
  before update on public.review_aggregates
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Bayesian config (admin-tunable via platform_config; read-with-default in the fn).
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  (
    'review_bayes_prior_m',
    '4.0'::jsonb,
    'Bayesian review prior mean m — platform-wide baseline star rating (1-5) new items shrink toward (M15-P02)'
  ),
  (
    'review_bayes_confidence_c',
    '10'::jsonb,
    'Bayesian confidence weight C — pseudo-count of prior reviews; higher = more shrinkage toward m (M15-P02)'
  )
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Bayesian average:  bayes = (C*m + rating_sum) / (C + rating_count)
--   0 reviews  → m (the prior); 1 five-star review → shrunk toward m (anti-gaming);
--   many reviews → converges to the true mean.
-- ---------------------------------------------------------------------------
create or replace function public.review_bayes_value(
  p_rating_sum integer,
  p_rating_count integer
)
returns numeric
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_m numeric;
  v_c numeric;
  v_denominator numeric;
begin
  select coalesce((value #>> '{}')::numeric, 4.0) into v_m
  from public.platform_config where key = 'review_bayes_prior_m';
  if v_m is null then
    v_m := 4.0;
  end if;

  select coalesce((value #>> '{}')::numeric, 10) into v_c
  from public.platform_config where key = 'review_bayes_confidence_c';
  if v_c is null then
    v_c := 10;
  end if;

  v_denominator := v_c + coalesce(p_rating_count, 0);
  if v_denominator = 0 then
    return round(v_m, 3);
  end if;
  return round((v_c * v_m + coalesce(p_rating_sum, 0)) / v_denominator, 3);
end;
$$;

comment on function public.review_bayes_value(integer, integer) is
  'Bayesian-shrunk mean rating: (C*m + rating_sum)/(C + rating_count); m/C read from platform_config.';

-- ---------------------------------------------------------------------------
-- Recompute one entity from source (published reviews) and merge into search boost.
-- ---------------------------------------------------------------------------
create or replace function public.recompute_review_aggregate(
  p_entity_kind text,
  p_entity_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer := 0;
  v_sum integer := 0;
  v_bayes numeric;
begin
  if p_entity_kind = 'product' then
    select count(*)::int, coalesce(sum(r.rating), 0)::int
      into v_count, v_sum
    from public.reviews r
    join public.order_item_products oip on oip.order_item_id = r.order_item_id
    where r.status = 'published' and oip.product_id = p_entity_id;
  elsif p_entity_kind = 'listing' then
    select count(*)::int, coalesce(sum(r.rating), 0)::int
      into v_count, v_sum
    from public.reviews r
    join public.order_item_products oip on oip.order_item_id = r.order_item_id
    where r.status = 'published' and oip.listing_id = p_entity_id;
  elsif p_entity_kind = 'vendor' then
    select count(*)::int, coalesce(sum(r.rating), 0)::int
      into v_count, v_sum
    from public.reviews r
    join public.order_items oi on oi.id = r.order_item_id
    join public.orders o on o.id = oi.order_id
    where r.status = 'published' and o.vendor_id = p_entity_id;
  else
    raise exception 'unknown review aggregate entity_kind: %', p_entity_kind;
  end if;

  v_bayes := public.review_bayes_value(v_sum, v_count);

  insert into public.review_aggregates (
    entity_kind, entity_id, rating_count, rating_sum, rating_bayes, updated_at
  )
  values (
    p_entity_kind, p_entity_id, v_count, v_sum, v_bayes, timezone('utc', now())
  )
  on conflict (entity_kind, entity_id) do update
  set rating_count = excluded.rating_count,
      rating_sum = excluded.rating_sum,
      rating_bayes = excluded.rating_bayes,
      updated_at = timezone('utc', now());

  -- MERGE (not clobber) the rating signal into the search projection's boost_signals.
  -- `||` preserves in_stock / verified / below_median written by 0009's upsert functions.
  update public.search_documents
  set boost_signals = boost_signals || jsonb_build_object(
        'rating_bayes', v_bayes,
        'rating_count', v_count
      ),
      updated_at = timezone('utc', now())
  where entity_kind = p_entity_kind
    and entity_id = p_entity_id;
end;
$$;

comment on function public.recompute_review_aggregate(text, uuid) is
  'Recompute a single product/listing/vendor aggregate from published reviews; merges the '
  'rating signal into search_documents.boost_signals without clobbering other keys.';

-- Resolve the product / listing / vendor touched by an order_item, then recompute each.
create or replace function public.recompute_review_aggregate_for_order_item(
  p_order_item_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_listing_id uuid;
  v_product_id uuid;
  v_vendor_id uuid;
begin
  select oip.listing_id, oip.product_id
    into v_listing_id, v_product_id
  from public.order_item_products oip
  where oip.order_item_id = p_order_item_id;

  select o.vendor_id
    into v_vendor_id
  from public.order_items oi
  join public.orders o on o.id = oi.order_id
  where oi.id = p_order_item_id;

  if v_product_id is not null then
    perform public.recompute_review_aggregate('product', v_product_id);
  end if;
  if v_listing_id is not null then
    perform public.recompute_review_aggregate('listing', v_listing_id);
  end if;
  if v_vendor_id is not null then
    perform public.recompute_review_aggregate('vendor', v_vendor_id);
  end if;
end;
$$;

comment on function public.recompute_review_aggregate_for_order_item(uuid) is
  'Incremental-on-write entry point: recompute the product/listing/vendor aggregates '
  'affected by a single review''s order_item.';

-- Nightly full recompute over every entity that has at least one published review.
create or replace function public.recompute_all_review_aggregates()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
  v_total integer := 0;
begin
  for v_id in
    select distinct oip.product_id
    from public.reviews r
    join public.order_item_products oip on oip.order_item_id = r.order_item_id
    where r.status = 'published' and oip.product_id is not null
  loop
    perform public.recompute_review_aggregate('product', v_id);
    v_total := v_total + 1;
  end loop;

  for v_id in
    select distinct oip.listing_id
    from public.reviews r
    join public.order_item_products oip on oip.order_item_id = r.order_item_id
    where r.status = 'published' and oip.listing_id is not null
  loop
    perform public.recompute_review_aggregate('listing', v_id);
    v_total := v_total + 1;
  end loop;

  for v_id in
    select distinct o.vendor_id
    from public.reviews r
    join public.order_items oi on oi.id = r.order_item_id
    join public.orders o on o.id = oi.order_id
    where r.status = 'published' and o.vendor_id is not null
  loop
    perform public.recompute_review_aggregate('vendor', v_id);
    v_total := v_total + 1;
  end loop;

  return v_total;
end;
$$;

comment on function public.recompute_all_review_aggregates() is
  'Nightly bulk recompute of every product/listing/vendor review aggregate; returns entities touched.';

-- ---------------------------------------------------------------------------
-- Incremental-on-write trigger — fires on every review status change.
-- ---------------------------------------------------------------------------
create or replace function public.reviews_recompute_aggregate_trigger()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'DELETE' then
    perform public.recompute_review_aggregate_for_order_item(old.order_item_id);
    return old;
  end if;
  perform public.recompute_review_aggregate_for_order_item(new.order_item_id);
  return new;
end;
$$;

create trigger reviews_recompute_aggregate
  after insert or update or delete on public.reviews
  for each row
  execute function public.reviews_recompute_aggregate_trigger();

-- ---------------------------------------------------------------------------
-- Row level security — public read (cards/PDP need it), service_role write only.
-- ---------------------------------------------------------------------------
alter table public.review_aggregates enable row level security;
alter table public.review_aggregates force row level security;

create policy review_aggregates_public_select
  on public.review_aggregates
  for select
  to anon, authenticated
  using (true);

comment on policy review_aggregates_public_select on public.review_aggregates is
  'Anyone may read review aggregates — they are the public star-rating source for cards and PDP.';

create policy review_aggregates_service_role_all
  on public.review_aggregates
  for all
  to service_role
  using (true)
  with check (true);

comment on policy review_aggregates_service_role_all on public.review_aggregates is
  'Only service_role (aggregate service + recompute triggers) may write aggregates; clients cannot inject ratings.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
grant select on table public.review_aggregates to anon, authenticated;
grant select, insert, update, delete on table public.review_aggregates to service_role;

grant execute on function public.review_bayes_value(integer, integer) to service_role;
grant execute on function public.recompute_review_aggregate(text, uuid) to service_role;
grant execute on function public.recompute_review_aggregate_for_order_item(uuid) to service_role;
grant execute on function public.recompute_all_review_aggregates() to service_role;

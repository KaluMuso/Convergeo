-- Return stock when an order is cancelled or vendor-rejected (order-integrity
-- follow-up #2).
--
-- Order creation now records, per order line, exactly what it took from stock:
-- the pooled or branch quantity whose checkout hold it consumed, and the variant
-- quantity consume_listing_variant_stock decremented. When an order moves to
-- 'cancelled' from a pre-dispatch status (placed / confirmed / processing /
-- ready), a trigger in the SAME transaction as the guarded status update marks
-- each unreleased line released and puts that stock back, then writes one
-- audit_log row. The released_at guard (row-locked UPDATE ... WHERE released_at
-- IS NULL) makes the restore exactly-once even if the trigger ran twice; a
-- cancellation after 'shipped' restores nothing because the goods left the
-- vendor.
--
-- Orders placed before this migration have no consumption rows and therefore
-- restore nothing: which branch their stock came from was not recorded.
--
-- Additive only.
--
-- Reversible rollback:
--   DROP TRIGGER IF EXISTS orders_release_cancelled_stock ON public.orders;
--   DROP FUNCTION IF EXISTS public.release_cancelled_order_stock();
--   DROP TABLE IF EXISTS public.order_item_stock_consumption;

create table if not exists public.order_item_stock_consumption (
  order_item_id uuid primary key references public.order_items (id) on delete cascade,
  order_id uuid not null references public.orders (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  -- Quantity taken from vendor_listings.stock_qty (location_id NULL) or from
  -- listing_location_stock (location_id set) when the checkout hold was claimed.
  listing_qty integer not null default 0 check (listing_qty >= 0),
  -- No FK: a closed branch must not rewrite history; release skips missing rows.
  location_id uuid,
  listing_variant_id uuid references public.vendor_listing_variants (id) on delete set null,
  variant_qty integer not null default 0 check (variant_qty >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  released_at timestamptz
);

create index if not exists order_item_stock_consumption_order_id_idx
  on public.order_item_stock_consumption (order_id)
  where released_at is null;

comment on table public.order_item_stock_consumption is
  'Stock each order line consumed at placement; released_at set once when a pre-dispatch cancellation returns it.';

alter table public.order_item_stock_consumption enable row level security;
alter table public.order_item_stock_consumption force row level security;
-- No client policies: written by order creation, released by the trigger below.
revoke all on table public.order_item_stock_consumption from public, anon, authenticated;
grant select, insert, update, delete on table public.order_item_stock_consumption to service_role;

create or replace function public.release_cancelled_order_stock()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_lines jsonb;
  v_actor uuid;
begin
  if new.status <> 'cancelled'
     or old.status not in ('placed', 'confirmed', 'processing', 'ready') then
    return new;
  end if;

  -- Lock the stock rows this release will touch in a fixed order (pooled
  -- listings, then branches, then variants, each by id — variants in the same
  -- order order creation locks them) so concurrent cancellations / placements
  -- over overlapping listings queue instead of deadlocking.
  perform 1 from public.vendor_listings vl
  where vl.id in (
    select c.listing_id from public.order_item_stock_consumption c
    where c.order_id = new.id and c.released_at is null
      and c.location_id is null and c.listing_qty > 0)
  order by vl.id
  for update;
  perform 1 from public.listing_location_stock lls
  where (lls.listing_id, lls.location_id) in (
    select c.listing_id, c.location_id from public.order_item_stock_consumption c
    where c.order_id = new.id and c.released_at is null
      and c.location_id is not null and c.listing_qty > 0)
  order by lls.listing_id, lls.location_id
  for update;
  perform 1 from public.vendor_listing_variants v
  where v.id in (
    select c.listing_variant_id from public.order_item_stock_consumption c
    where c.order_id = new.id and c.released_at is null and c.variant_qty > 0)
  order by v.id
  for update;

  with released as (
    update public.order_item_stock_consumption c
    set released_at = timezone('utc', now())
    where c.order_id = new.id
      and c.released_at is null
    returning c.order_item_id, c.listing_id, c.listing_qty, c.location_id,
              c.listing_variant_id, c.variant_qty
  ),
  branch_restock as (
    update public.listing_location_stock lls
    set stock_qty = lls.stock_qty + s.qty
    from (
      select listing_id, location_id, sum(listing_qty)::integer as qty
      from released
      where location_id is not null and listing_qty > 0
      group by listing_id, location_id
    ) s
    where lls.listing_id = s.listing_id and lls.location_id = s.location_id
    returning lls.listing_id
  ),
  pooled_restock as (
    update public.vendor_listings vl
    set stock_qty = vl.stock_qty + s.qty
    from (
      select listing_id, sum(listing_qty)::integer as qty
      from released
      where location_id is null and listing_qty > 0
      group by listing_id
    ) s
    where vl.id = s.listing_id
      and vl.stock_mode = 'tracked'
      and vl.stock_qty is not null
    returning vl.id
  ),
  variant_restock as (
    update public.vendor_listing_variants v
    set stock_qty = v.stock_qty + s.qty,
        updated_at = timezone('utc', now())
    from (
      select listing_variant_id, sum(variant_qty)::integer as qty
      from released
      where listing_variant_id is not null and variant_qty > 0
      group by listing_variant_id
    ) s
    where v.id = s.listing_variant_id
      and v.stock_qty is not null
    returning v.id
  )
  select jsonb_agg(
           jsonb_build_object(
             'order_item_id', r.order_item_id,
             'listing_id', r.listing_id,
             'listing_qty', r.listing_qty,
             'location_id', r.location_id,
             'listing_variant_id', r.listing_variant_id,
             'variant_qty', r.variant_qty
           ) order by r.order_item_id
         )
  into v_lines
  -- Data-modifying CTEs always run to completion, read or not.
  from released r;

  if v_lines is not null then
    begin
      v_actor := nullif(current_setting('app.order_actor', true), '')::uuid;
    exception when invalid_text_representation then
      v_actor := null;
    end;
    insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
    values (
      v_actor, 'order.stock_released', 'order', new.id,
      jsonb_build_object('status', old.status),
      jsonb_build_object('status', new.status, 'lines', v_lines)
    );
  end if;
  return new;
end;
$$;

revoke execute on function public.release_cancelled_order_stock() from public, anon, authenticated;

drop trigger if exists orders_release_cancelled_stock on public.orders;
create trigger orders_release_cancelled_stock
  after update of status on public.orders
  for each row
  when (new.status = 'cancelled' and old.status is distinct from new.status)
  execute function public.release_cancelled_order_stock();

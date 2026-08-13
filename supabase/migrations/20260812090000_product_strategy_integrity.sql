-- Product-strategy integrity hardening.
--
-- Migrations 0085/0087 introduced per-measure, used, and Class D/E listing
-- shapes. The API validates those shapes, but authenticated vendors can also
-- address exposed tables through PostgREST. These database guards keep the
-- critical invariants true even when a client bypasses the application API.

-- New and updated rows must keep D/E standalone. This is NOT VALID so a
-- pre-existing manually-created violation does not make deployment destructive;
-- it still protects every new row and every row touched after this migration.
alter table public.vendor_listings
  add constraint vendor_listings_standalone_class_check
  check (product_class not in ('D', 'E') or product_id is null)
  not valid;

alter table public.vendor_listings
  add constraint vendor_listings_standalone_title_check
  check (
    product_class not in ('D', 'E')
    or nullif(btrim(title_override), '') is not null
  )
  not valid;

-- R02-P16 explicitly defers per-measure wholesale tiers. Enforce that deferral
-- below the API so direct PostgREST writes cannot create an unsupported price
-- path.
alter table public.vendor_listings
  add constraint vendor_listings_per_measure_wholesale_check
  check (sale_unit = 'each' or wholesale = false)
  not valid;

-- Explicit Class E offers must have enough weekly capacity to accept at least
-- one minimum-sized cart line. Legacy non-E made-to-order rows from migration
-- 0085 remain valid; product-class migration is a separate audited operation.
alter table public.vendor_listings
  add constraint vendor_listings_class_e_capacity_floor_check
  check (
    product_class <> 'E'
    or vendor_capacity_per_week >= greatest(min_steps, moq)
  )
  not valid;

-- Checkout serializes Class-E capacity on the listing row, then totals this
-- listing's current-week order items. Keep that authoritative purchase-boundary
-- query index-backed as order history grows.
create index if not exists order_item_products_listing_id_idx
  on public.order_item_products (listing_id);

create or replace function public.enforce_active_used_listing_evidence()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  current_condition text;
  current_status text;
begin
  -- Read final transaction state. This makes a same-transaction image insert
  -- valid while still rejecting an active used listing with no real image.
  select condition, status
  into current_condition, current_status
  from public.vendor_listings
  where id = new.id;

  if current_condition = 'used'
     and current_status = 'active'
     and not exists (
       select 1
       from public.listing_images
       where listing_id = new.id
     ) then
    raise exception 'active used listing % requires at least one listing image', new.id
      using errcode = 'check_violation';
  end if;

  return null;
end;
$$;

revoke execute on function public.enforce_active_used_listing_evidence()
  from public, anon, authenticated;

create constraint trigger vendor_listings_active_used_evidence_guard
  after insert or update of condition, status on public.vendor_listings
  deferrable initially deferred
  for each row
  execute function public.enforce_active_used_listing_evidence();

create or replace function public.enforce_used_listing_image_floor()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  -- Deferred execution observes the final transaction state: replacing the
  -- last photo in one transaction is allowed, but committing with zero is not.
  -- A cascading listing delete is also safe because the parent no longer exists.
  -- Lock the parent before counting so two concurrent deletions cannot each
  -- observe the other's image and commit a write-skew violation.
  perform 1
  from public.vendor_listings
  where id = old.listing_id
    and condition = 'used'
    and status = 'active'
  for update;

  if found and not exists (
       select 1
       from public.listing_images
       where listing_id = old.listing_id
     ) then
    raise exception 'active used listing % must retain at least one listing image', old.listing_id
      using errcode = 'check_violation';
  end if;

  return null;
end;
$$;

revoke execute on function public.enforce_used_listing_image_floor()
  from public, anon, authenticated;

create constraint trigger listing_images_used_evidence_delete_guard
  after delete on public.listing_images
  deferrable initially deferred
  for each row
  execute function public.enforce_used_listing_image_floor();

create constraint trigger listing_images_used_evidence_move_guard
  after update of listing_id on public.listing_images
  deferrable initially deferred
  for each row
  execute function public.enforce_used_listing_image_floor();

comment on constraint vendor_listings_standalone_class_check on public.vendor_listings is
  'Class D/E offers are standalone and cannot attach to a canonical product. NOT VALID pending an explicit legacy-row audit.';
comment on constraint vendor_listings_standalone_title_check on public.vendor_listings is
  'Standalone Class D/E offers carry their own non-empty title. NOT VALID pending an explicit legacy-row audit.';
comment on constraint vendor_listings_per_measure_wholesale_check on public.vendor_listings is
  'Per-measure wholesale tiers are deferred by R02-P16. NOT VALID pending an explicit legacy-row audit.';
comment on constraint vendor_listings_class_e_capacity_floor_check on public.vendor_listings is
  'Class E weekly capacity must cover at least one minimum-sized purchase. NOT VALID pending an explicit legacy-row audit.';
comment on index public.order_item_products_listing_id_idx is
  'Supports current-week committed-quantity checks for serialized Class E checkout capacity.';

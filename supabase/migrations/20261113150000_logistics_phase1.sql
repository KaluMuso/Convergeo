-- Logistics phase 1 (founder-approved blueprint items 1-7, 2026-11-13).
--
-- Reuses courier dispatch v1, the order state machine, the outbox and the
-- ledger; nothing is rebuilt. All changes are additive:
--
--   1. platform_config: automatic free-delivery rule (K15,000 retail basket,
--      < 500 kg, commission-funded), courier cash cap (K1,500), alert timers.
--      The old per-vendor "free above K200" key is retired (kept, unused).
--   2. vendors.free_delivery_all / free_delivery_method and
--      vendor_listings.free_delivery / weight_grams: vendor-funded free
--      delivery (the vendor bears the courier fee, or self-delivers).
--   3. orders.delivery_funding / delivery_funded_ngwee: who pays the delivery
--      fee (customer by default); ready_at; pickup_location_id; deliver_together.
--   4. dispatch_requests: direction (delivery|return), attempt_no (max 2),
--      failure_code, pickup_location_id, actual courier cost, rider cash custody
--      (cod_collected_*), remittance link. 'vendor_ack' proof for returns.
--   5. courier_remittances: rider cash handed to Convergeo (mobile money etc.).
--   6. admin_roles permissions + 'logistics.manage', 'cod.reconcile';
--      public.has_admin_permission(uuid, text).
--   7. release_cancelled_order_stock(): also restocks shipped -> cancelled when
--      the API primes app.order_return_restock (return-to-vendor acknowledged).
--   8. Partial index on delivery orders by (status, created_at).
--
-- Down (manual; safe while unused — data in the new columns is lost):
--   drop function if exists public.has_admin_permission(uuid, text);
--   restore release_cancelled_order_stock() from 20261113071000;
--   drop trigger if exists orders_set_ready_at on public.orders;
--   drop function if exists public.set_order_ready_at();
--   drop trigger if exists dispatch_requests_guard_custody on public.dispatch_requests;
--   drop function if exists public.guard_dispatch_custody_update();
--   alter table public.dispatch_requests drop column remittance_id, drop column cod_collected_at,
--     drop column cod_collected_method, drop column cod_collected_ngwee, drop column cost_recorded_by,
--     drop column cost_recorded_at, drop column actual_cost_ngwee, drop column pickup_location_id,
--     drop column failure_code, drop column attempt_no, drop column direction;
--   restore dispatch_requests_delivered_via_check / one_delivered_per_order from 20261109100000;
--   drop table public.courier_remittances;
--   alter table public.orders drop column deliver_together, drop column pickup_location_id,
--     drop column ready_at, drop column delivery_funded_ngwee, drop column delivery_funding;
--   alter table public.vendor_listings drop column weight_grams, drop column free_delivery;
--   alter table public.vendors drop column free_delivery_method, drop column free_delivery_all;
--   restore admin_roles_permissions_valid from 20261009100000 (after removing the new grants);
--   delete from public.platform_config where key in (<keys inserted below>);

-- ---------------------------------------------------------------------------
-- 1. Settings (editable without a deploy)
-- ---------------------------------------------------------------------------

insert into public.platform_config (key, value, description) values
  ('auto_free_delivery_threshold_ngwee', '1500000'::jsonb,
   'Automatic free delivery: retail checkout subtotal at or above this (ngwee). Default K15,000.'),
  ('auto_free_delivery_max_weight_grams', '500000'::jsonb,
   'Automatic free delivery only when the basket weighs less than this (grams). Default 500 kg.'),
  ('auto_free_delivery_commission_share_bps', '5000'::jsonb,
   'Automatic free delivery is funded from at most this share of the basket commission (bps).'),
  ('courier_cash_cap_ngwee', '150000'::jsonb,
   'Most cash one courier may hold before new cash jobs are blocked (ngwee). Default K1,500.'),
  ('dispatch_stale_accepted_minutes', '45'::jsonb,
   'Alert when a dispatch stays accepted (not picked up) longer than this.'),
  ('dispatch_stale_picked_up_minutes', '120'::jsonb,
   'Alert when a dispatch stays picked up (not delivered) longer than this.'),
  ('vendor_confirm_sla_minutes', '120'::jsonb,
   'Alert operations when a vendor has not confirmed a placed order within this.'),
  ('delivery_cutoffs', '["11:00", "15:00"]'::jsonb,
   'Daily delivery cut-offs (Africa/Lusaka): order by 11:00 -> by 15:00, by 15:00 -> by 19:00.')
on conflict (key) do nothing;

update public.platform_config
set description = 'RETIRED 2026-11-13 (logistics phase 1): per-vendor free delivery above this '
                  'is no longer applied. See auto_free_delivery_* keys.'
where key = 'free_delivery_threshold_ngwee';

-- ---------------------------------------------------------------------------
-- 2. Vendor-funded free delivery
-- ---------------------------------------------------------------------------

alter table public.vendors
  add column if not exists free_delivery_all boolean not null default false,
  add column if not exists free_delivery_method text not null default 'platform_courier';

alter table public.vendors drop constraint if exists vendors_free_delivery_method_check;
alter table public.vendors add constraint vendors_free_delivery_method_check
  check (free_delivery_method in ('platform_courier', 'self_delivery'));

comment on column public.vendors.free_delivery_all is
  'Vendor offers free delivery on every order: the vendor bears the delivery cost.';
comment on column public.vendors.free_delivery_method is
  'How a vendor-funded free delivery travels: platform_courier (fee charged to the vendor) '
  'or self_delivery (vendor''s own rider / Yango; nothing charged).';

alter table public.vendor_listings
  add column if not exists free_delivery boolean not null default false,
  add column if not exists weight_grams integer;

alter table public.vendor_listings drop constraint if exists vendor_listings_weight_grams_check;
alter table public.vendor_listings add constraint vendor_listings_weight_grams_check
  check (weight_grams is null or (weight_grams > 0 and weight_grams <= 10000000));

comment on column public.vendor_listings.free_delivery is
  'Listing marked "free delivery": when every line of the vendor''s order is free delivery, '
  'the vendor bears the delivery cost.';
comment on column public.vendor_listings.weight_grams is
  'Shipping weight per unit (grams). Unknown weight never qualifies for automatic free delivery.';

-- ---------------------------------------------------------------------------
-- 3. Orders: delivery funding, readiness, pickup branch
-- ---------------------------------------------------------------------------

alter table public.orders
  add column if not exists delivery_funding text not null default 'customer',
  add column if not exists delivery_funded_ngwee bigint not null default 0,
  add column if not exists ready_at timestamptz,
  add column if not exists pickup_location_id uuid
    references public.vendor_locations (id) on delete set null,
  add column if not exists deliver_together boolean not null default true;

alter table public.orders drop constraint if exists orders_delivery_funding_check;
alter table public.orders add constraint orders_delivery_funding_check check (
  delivery_funding in ('customer', 'vendor', 'vendor_self', 'platform')
  and delivery_funded_ngwee >= 0
  -- Only the customer pays a fee on the order itself.
  and (delivery_funding = 'customer' or delivery_fee_ngwee = 0)
  -- Only vendor / platform funding carries an amount to book to delivery_revenue.
  and (delivery_funding in ('vendor', 'platform') or delivery_funded_ngwee = 0)
);

comment on column public.orders.delivery_funding is
  'Who pays delivery: customer (fee on the order), vendor (free delivery charged to the '
  'vendor payable), vendor_self (vendor delivers itself), platform (automatic free delivery '
  'funded from commission).';
comment on column public.orders.delivery_funded_ngwee is
  'Delivery fee booked to delivery_revenue from the vendor payable or commission (ngwee).';

create or replace function public.set_order_ready_at()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if new.status = 'ready' and old.status is distinct from 'ready' and new.ready_at is null then
    new.ready_at := timezone('utc', now());
  end if;
  return new;
end;
$$;

drop trigger if exists orders_set_ready_at on public.orders;
create trigger orders_set_ready_at
  before update of status on public.orders
  for each row execute function public.set_order_ready_at();

revoke execute on function public.set_order_ready_at() from public, anon, authenticated;

create index if not exists orders_delivery_status_created_at_idx
  on public.orders (status, created_at)
  where fulfilment = 'delivery';

-- ---------------------------------------------------------------------------
-- 4. Rider cash remittances
-- ---------------------------------------------------------------------------

create table if not exists public.courier_remittances (
  id uuid primary key default gen_random_uuid(),
  courier_partner_id uuid not null references public.courier_partners (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  method text not null,
  reference text not null,
  received_at timestamptz not null default timezone('utc', now()),
  recorded_by uuid references auth.users (id) on delete set null,
  note text,
  created_at timestamptz not null default timezone('utc', now()),
  constraint courier_remittances_method_check
    check (method in ('mobile_money', 'bank_transfer', 'lenco', 'cash_deposit')),
  constraint courier_remittances_reference_check
    check (char_length(btrim(reference)) between 3 and 120),
  constraint courier_remittances_note_len_check
    check (note is null or char_length(note) <= 500)
);

create unique index if not exists courier_remittances_method_reference_key
  on public.courier_remittances (method, lower(btrim(reference)));
create index if not exists courier_remittances_courier_received_idx
  on public.courier_remittances (courier_partner_id, received_at desc);

alter table public.courier_remittances enable row level security;
alter table public.courier_remittances force row level security;
drop policy if exists courier_remittances_admin_select on public.courier_remittances;
create policy courier_remittances_admin_select
  on public.courier_remittances for select to authenticated
  using (public.has_role('admin'));
revoke all on table public.courier_remittances from anon, authenticated;
grant select on table public.courier_remittances to authenticated;
grant select, insert, update, delete on table public.courier_remittances to service_role;

comment on table public.courier_remittances is
  'Cash a courier handed to Convergeo (same-day mobile money etc.). Written by the API only; '
  'matched to dispatch_requests.remittance_id. Rows are never edited (corrections are new rows).';

-- ---------------------------------------------------------------------------
-- 5. Dispatch: attempts, returns, cost, cash custody
-- ---------------------------------------------------------------------------

alter table public.dispatch_requests
  add column if not exists direction text not null default 'delivery',
  add column if not exists attempt_no smallint not null default 1,
  add column if not exists failure_code text,
  add column if not exists pickup_location_id uuid
    references public.vendor_locations (id) on delete set null,
  add column if not exists actual_cost_ngwee bigint,
  add column if not exists cost_recorded_at timestamptz,
  add column if not exists cost_recorded_by uuid references auth.users (id) on delete set null,
  add column if not exists cod_collected_ngwee bigint,
  add column if not exists cod_collected_method text,
  add column if not exists cod_collected_at timestamptz,
  add column if not exists remittance_id uuid
    references public.courier_remittances (id) on delete restrict;

alter table public.dispatch_requests drop constraint if exists dispatch_requests_logistics_check;
alter table public.dispatch_requests add constraint dispatch_requests_logistics_check check (
  direction in ('delivery', 'return')
  and attempt_no between 1 and 2
  and (direction = 'delivery' or (attempt_no = 1 and cod_amount_ngwee = 0))
  and (failure_code is null or failure_code in (
    'customer_unavailable', 'customer_refused', 'wrong_address', 'vendor_not_ready',
    'courier_no_show', 'damaged', 'other'))
  and (actual_cost_ngwee is null or actual_cost_ngwee >= 0)
  and (cod_collected_ngwee is null or cod_collected_ngwee >= 0)
  and (cod_collected_method is null or cod_collected_method in ('cash', 'mobile_money'))
  and ((cod_collected_ngwee is null) = (cod_collected_at is null))
  and (remittance_id is null or cod_collected_ngwee is not null)
);

alter table public.dispatch_requests drop constraint if exists dispatch_requests_delivered_via_check;
alter table public.dispatch_requests add constraint dispatch_requests_delivered_via_check
  check (delivered_via is null or delivered_via in ('handover_code', 'pod_photo', 'vendor_ack'));

-- A return is "delivered" when the shop acknowledges the goods; it must not
-- block (or be blocked by) the one delivered *delivery* per order.
drop index if exists public.dispatch_requests_one_delivered_per_order;
create unique index if not exists dispatch_requests_one_delivered_per_order
  on public.dispatch_requests (order_id)
  where status = 'delivered' and direction = 'delivery';
create unique index if not exists dispatch_requests_one_return_per_order
  on public.dispatch_requests (order_id)
  where direction = 'return' and status in ('requested', 'accepted', 'picked_up', 'delivered');
create index if not exists dispatch_requests_custody_open_idx
  on public.dispatch_requests (courier_partner_id)
  where cod_collected_ngwee is not null and remittance_id is null;

-- Cash custody facts are write-once: once recorded, a collected amount or a
-- remittance link can never be changed or cleared (corrections are a person's
-- decision recorded elsewhere, not an UPDATE).
create or replace function public.guard_dispatch_custody_update()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if old.cod_collected_ngwee is not null and (
       new.cod_collected_ngwee is distinct from old.cod_collected_ngwee
       or new.cod_collected_method is distinct from old.cod_collected_method
       or new.cod_collected_at is distinct from old.cod_collected_at) then
    raise exception 'dispatch cash custody is write-once' using errcode = '23514';
  end if;
  if old.remittance_id is not null and new.remittance_id is distinct from old.remittance_id then
    raise exception 'dispatch remittance link is write-once' using errcode = '23514';
  end if;
  if new.direction is distinct from old.direction or new.attempt_no is distinct from old.attempt_no then
    raise exception 'dispatch direction/attempt are immutable' using errcode = '23514';
  end if;
  return new;
end;
$$;

drop trigger if exists dispatch_requests_guard_custody on public.dispatch_requests;
create trigger dispatch_requests_guard_custody
  before update on public.dispatch_requests
  for each row execute function public.guard_dispatch_custody_update();

revoke execute on function public.guard_dispatch_custody_update() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 6. Limited logistics / cash permissions
-- ---------------------------------------------------------------------------

alter table public.admin_roles drop constraint if exists admin_roles_permissions_valid;
alter table public.admin_roles add constraint admin_roles_permissions_valid check (
  permissions <@ array[
    'finance.read', 'events.manage', 'products.manage', 'services.read',
    'vendors.manage', 'ads.manage', 'analytics.read', 'inventory.read',
    'logistics.manage', 'cod.reconcile'
  ]::text[] and cardinality(permissions) > 0
);

create or replace function public.has_admin_permission(p_user uuid, p_permission text)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select exists (
    select 1 from public.user_roles ur
    where ur.user_id = p_user and ur.role in ('admin', 'superadmin')
  ) or exists (
    select 1
    from public.user_roles ur
    join public.admin_roles ar on ar.key = ur.role
    where ur.user_id = p_user and p_permission = any (ar.permissions)
  );
$$;

revoke execute on function public.has_admin_permission(uuid, text) from public, anon, authenticated;
grant execute on function public.has_admin_permission(uuid, text) to service_role;

comment on function public.has_admin_permission(uuid, text) is
  'True for full admins, or a restricted admin whose rbac_* role grants the permission.';

-- ---------------------------------------------------------------------------
-- 7. Return-to-vendor restock (shipped -> cancelled, explicit only)
-- ---------------------------------------------------------------------------

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
  -- Logistics phase 1: a shipped order whose goods physically came back to the
  -- shop (return-to-vendor dispatch acknowledged) restocks too, but ONLY when
  -- the API primed app.order_return_restock in the same transaction. Any other
  -- shipped -> cancelled (goods may still be with the customer) restores nothing.
  if new.status <> 'cancelled'
     or not (
       old.status in ('placed', 'confirmed', 'processing', 'ready')
       or (old.status = 'shipped'
           and coalesce(current_setting('app.order_return_restock', true), '') = 'on')
     ) then
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

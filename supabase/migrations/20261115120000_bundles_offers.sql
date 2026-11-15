-- W8 Bundles & offers (feature flag `bundles`, default OFF).
--
-- Vendor-created offers on their own products, services and events:
--   bxgy         buy `buy_qty` of the trigger items, get `get_qty` of the reward free
--   bundle       anchor + add-ons sold together: `addon_percent_off` on the add-ons
--                or a fixed `bundle_price_ngwee` for the whole set
--   buy_n_pay_m  for every `buy_n` eligible units pay for `pay_m` (cheapest free)
--   free_gift    buy a trigger item, get the reward free while gift stock lasts
--
-- Money (D-money convention): integer ngwee only. The API pricing engine
-- (services/api/app/services/offers) allocates a discount pro-rata across the
-- order lines with deterministic largest-remainder rounding and writes the
-- result ONTO the order lines at placement (offer_snapshot, list price,
-- discount). Nothing downstream recomputes from a live offer. Commission is
-- computed from the discounted unit price, so it is charged on what was paid.
--
-- Gift lines are priced 0 (`is_offer_gift`), carry a reference list price for
-- the vendor, and are not refundable on their own (API guard). Gift stock is a
-- per-offer pool: `gift_stock_reserved` is incremented by a conditional UPDATE
-- inside the order transaction (never past `gift_stock_total`), recorded in
-- `offer_gift_reservations`, and released exactly once by a trigger when the
-- order is cancelled before dispatch, or when its unpaid checkout expires /
-- is abandoned (expire_checkout_group_if_unpaid).
--
--   offers                   vendor-owned offer header (+ admin pause)
--   offer_items              items of an offer (product | service | event)
--   offer_gift_reservations  gift units held by an order (service-role only)
--   order_items              + offer_id, offer_snapshot, list_unit_price_ngwee,
--                              offer_discount_ngwee, is_offer_gift,
--                              offer_parent_item_id; unit price may be 0 only
--                              on a gift line
--
-- Additive only. Reversible (manual, safe while the flag has never been on —
-- otherwise first confirm no order_items row has is_offer_gift = true, since
-- restoring the strict unit-price check would reject those rows):
--   drop trigger if exists checkout_groups_release_offer_gifts on public.checkout_groups;
--   drop function if exists public.release_expired_checkout_offer_gifts();
--   drop trigger if exists orders_release_cancelled_offer_gifts on public.orders;
--   drop function if exists public.release_cancelled_offer_gifts();
--   drop function if exists public.release_offer_gift_reservations(uuid, text, jsonb, jsonb);
--   alter table public.order_items drop constraint if exists order_items_unit_price_ngwee_check;
--   alter table public.order_items add constraint order_items_unit_price_ngwee_check
--     check (unit_price_ngwee > 0);
--   alter table public.order_items
--     drop column if exists offer_parent_item_id, drop column if exists is_offer_gift,
--     drop column if exists offer_discount_ngwee, drop column if exists list_unit_price_ngwee,
--     drop column if exists offer_snapshot, drop column if exists offer_id;
--   drop table if exists public.offer_gift_reservations;
--   drop table if exists public.offer_items;
--   drop table if exists public.offers;
--   drop function if exists public.offer_items_guard();
--   drop function if exists public.offers_guard_client_write();
--   delete from public.feature_flags where flag = 'bundles';
--   delete from public.platform_config where key in ('bundles_max_discount_pct', 'bundles_max_active_offers_per_vendor');
--   delete from private.rate_counter_scope_manifest
--     where scope in ('vendor_offers_write', 'offers_public_read_ip');
--   -- then re-create rate_counters_scope_check without those two scopes (optional:
--   -- a wider allowed set is harmless).

-- ---------------------------------------------------------------------------
-- 1. offers
-- ---------------------------------------------------------------------------

create table if not exists public.offers (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  offer_type text not null,
  status text not null default 'draft',
  title text not null,
  starts_at timestamptz not null default timezone('utc', now()),
  ends_at timestamptz,
  buy_qty integer,
  get_qty integer,
  bundle_pricing text,
  addon_percent_off integer,
  bundle_price_ngwee bigint,
  buy_n integer,
  pay_m integer,
  gift_stock_total integer,
  gift_stock_reserved integer not null default 0,
  max_applications_per_order integer not null default 1,
  per_customer_limit integer,
  paused_by_admin boolean not null default false,
  admin_note text,
  created_by uuid references auth.users (id) on delete set null,
  updated_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint offers_type_check
    check (offer_type in ('bxgy', 'bundle', 'buy_n_pay_m', 'free_gift')),
  constraint offers_status_check
    check (status in ('draft', 'active', 'paused', 'archived')),
  constraint offers_title_len_check
    check (char_length(btrim(title)) between 1 and 120),
  constraint offers_window_check
    check (ends_at is null or ends_at > starts_at),
  constraint offers_buy_qty_check check (buy_qty is null or buy_qty between 1 and 100),
  constraint offers_get_qty_check check (get_qty is null or get_qty between 1 and 100),
  constraint offers_bundle_pricing_check
    check (bundle_pricing is null or bundle_pricing in ('addon_percent_off', 'fixed_price')),
  -- Hard ceiling; the admin-editable abuse cap (platform_config
  -- bundles_max_discount_pct) is enforced by the API at or below this.
  constraint offers_addon_percent_check
    check (addon_percent_off is null or addon_percent_off between 1 and 95),
  constraint offers_bundle_price_check
    check (bundle_price_ngwee is null or bundle_price_ngwee > 0),
  constraint offers_buy_n_check check (buy_n is null or buy_n between 2 and 100),
  constraint offers_pay_m_check
    check (pay_m is null or (pay_m >= 1 and buy_n is not null and pay_m < buy_n)),
  constraint offers_gift_stock_check
    check (
      gift_stock_reserved >= 0
      and (gift_stock_total is null or (gift_stock_total >= 0
           and gift_stock_reserved <= gift_stock_total))
    ),
  constraint offers_max_applications_check
    check (max_applications_per_order between 1 and 20),
  constraint offers_per_customer_limit_check
    check (per_customer_limit is null or per_customer_limit between 1 and 1000),
  constraint offers_admin_note_len_check
    check (admin_note is null or char_length(admin_note) <= 500),
  -- Shape per type (the API validates the same rules with field errors).
  constraint offers_shape_check
    check (
      case offer_type
        when 'bxgy' then buy_qty is not null and get_qty is not null
                         and gift_stock_total is not null
        when 'free_gift' then gift_stock_total is not null
        when 'bundle' then
          (bundle_pricing = 'addon_percent_off' and addon_percent_off is not null
             and bundle_price_ngwee is null)
          or (bundle_pricing = 'fixed_price' and bundle_price_ngwee is not null
             and addon_percent_off is null)
        when 'buy_n_pay_m' then buy_n is not null and pay_m is not null
        else false
      end
    )
);

create index if not exists offers_vendor_status_idx
  on public.offers (vendor_id, status, starts_at);
create index if not exists offers_active_window_idx
  on public.offers (status, starts_at, ends_at)
  where status = 'active' and paused_by_admin = false;

drop trigger if exists offers_set_updated_at on public.offers;
create trigger offers_set_updated_at
  before update on public.offers
  for each row execute function public.set_updated_at();

comment on table public.offers is
  'W8 vendor offers (bxgy | bundle | buy_n_pay_m | free_gift). Pricing at order time is '
  'snapshotted on order_items; gift_stock_reserved only moves inside the order transaction '
  'and the cancel trigger (client writes to it are rejected).';

-- Clients (vendor owner / admin via PostgREST) may not move the gift pool
-- counter or the admin pause; only the service role (order tx, API) can.
create or replace function public.offers_guard_client_write()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  if current_user not in ('anon', 'authenticated') then
    return new;
  end if;
  if tg_op = 'INSERT' then
    if new.gift_stock_reserved <> 0 or new.paused_by_admin then
      raise exception 'offers: gift_stock_reserved / paused_by_admin are server-managed'
        using errcode = '42501';
    end if;
    return new;
  end if;
  if new.gift_stock_reserved is distinct from old.gift_stock_reserved
     or new.vendor_id is distinct from old.vendor_id
     or (new.paused_by_admin is distinct from old.paused_by_admin
         and not public.has_role('admin')) then
    raise exception 'offers: server-managed column changed by a client'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

revoke execute on function public.offers_guard_client_write() from public, anon, authenticated;

drop trigger if exists offers_guard_client_write on public.offers;
create trigger offers_guard_client_write
  before insert or update on public.offers
  for each row execute function public.offers_guard_client_write();

-- ---------------------------------------------------------------------------
-- 2. offer_items
-- ---------------------------------------------------------------------------

create table if not exists public.offer_items (
  id uuid primary key default gen_random_uuid(),
  offer_id uuid not null references public.offers (id) on delete cascade,
  role text not null,
  item_kind text not null,
  listing_id uuid references public.vendor_listings (id) on delete cascade,
  service_id uuid references public.services (id) on delete cascade,
  event_id uuid references public.events (id) on delete cascade,
  qty integer not null default 1,
  sort_order integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint offer_items_role_check
    check (role in ('trigger', 'reward', 'anchor', 'addon', 'eligible')),
  constraint offer_items_kind_check
    check (item_kind in ('product', 'service', 'event')),
  constraint offer_items_qty_check check (qty between 1 and 100),
  constraint offer_items_sort_check check (sort_order between 0 and 1000),
  constraint offer_items_target_check
    check (
      (item_kind = 'product' and listing_id is not null and service_id is null and event_id is null)
      or (item_kind = 'service' and service_id is not null and listing_id is null and event_id is null)
      or (item_kind = 'event' and event_id is not null and listing_id is null and service_id is null)
    )
);

create unique index if not exists offer_items_offer_role_target_key
  on public.offer_items (offer_id, role, coalesce(listing_id, service_id, event_id));
create index if not exists offer_items_listing_idx
  on public.offer_items (listing_id) where listing_id is not null;
create index if not exists offer_items_service_idx
  on public.offer_items (service_id) where service_id is not null;
create index if not exists offer_items_event_idx
  on public.offer_items (event_id) where event_id is not null;

drop trigger if exists offer_items_set_updated_at on public.offer_items;
create trigger offer_items_set_updated_at
  before update on public.offer_items
  for each row execute function public.set_updated_at();

comment on table public.offer_items is
  'Items of an offer. Every item must belong to the offer''s vendor (offer_items_guard).';

-- Cross-vendor items are refused for every writer, the service role included.
create or replace function public.offer_items_guard()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_offer_vendor uuid;
  v_target_vendor uuid;
begin
  if new.offer_id is null then
    return new;  -- NOT NULL / RLS reject it; nothing to cross-check
  end if;
  select o.vendor_id into v_offer_vendor from public.offers o where o.id = new.offer_id;
  if v_offer_vendor is null then
    raise exception 'OFFER_ITEM_OFFER_NOT_FOUND' using errcode = '23503';
  end if;
  if new.item_kind = 'product' then
    select vl.vendor_id into v_target_vendor from public.vendor_listings vl where vl.id = new.listing_id;
  elsif new.item_kind = 'service' then
    select s.vendor_id into v_target_vendor from public.services s where s.id = new.service_id;
  else
    select e.organiser_vendor_id into v_target_vendor from public.events e where e.id = new.event_id;
  end if;
  if v_target_vendor is distinct from v_offer_vendor then
    raise exception 'OFFER_ITEM_CROSS_VENDOR' using errcode = '42501';
  end if;
  return new;
end;
$$;

revoke execute on function public.offer_items_guard() from public, anon, authenticated;

drop trigger if exists offer_items_guard on public.offer_items;
create trigger offer_items_guard
  before insert or update on public.offer_items
  for each row execute function public.offer_items_guard();

-- ---------------------------------------------------------------------------
-- 3. offer_gift_reservations (service-role only)
-- ---------------------------------------------------------------------------

create table if not exists public.offer_gift_reservations (
  id uuid primary key default gen_random_uuid(),
  offer_id uuid not null references public.offers (id) on delete restrict,
  order_id uuid not null references public.orders (id) on delete cascade,
  order_item_id uuid not null references public.order_items (id) on delete cascade,
  qty integer not null,
  status text not null default 'reserved',
  created_at timestamptz not null default timezone('utc', now()),
  released_at timestamptz,
  constraint offer_gift_reservations_qty_check check (qty > 0),
  constraint offer_gift_reservations_status_check check (status in ('reserved', 'released')),
  constraint offer_gift_reservations_released_check
    check ((status = 'released') = (released_at is not null)),
  constraint offer_gift_reservations_order_item_key unique (order_item_id)
);

create index if not exists offer_gift_reservations_order_idx
  on public.offer_gift_reservations (order_id) where status = 'reserved';
create index if not exists offer_gift_reservations_offer_idx
  on public.offer_gift_reservations (offer_id);

comment on table public.offer_gift_reservations is
  'Gift units an order took from an offer''s pool; released once on pre-dispatch cancel.';

-- ---------------------------------------------------------------------------
-- 4. order_items: offer snapshot columns (pricing is stored, never recomputed)
-- ---------------------------------------------------------------------------

alter table public.order_items
  add column if not exists offer_id uuid references public.offers (id) on delete set null,
  add column if not exists offer_snapshot jsonb not null default '{}'::jsonb,
  add column if not exists list_unit_price_ngwee bigint,
  add column if not exists offer_discount_ngwee bigint not null default 0,
  add column if not exists is_offer_gift boolean not null default false,
  add column if not exists offer_parent_item_id uuid references public.order_items (id) on delete set null;

alter table public.order_items drop constraint if exists order_items_list_unit_price_check;
alter table public.order_items add constraint order_items_list_unit_price_check
  check (list_unit_price_ngwee is null or list_unit_price_ngwee > 0);
alter table public.order_items drop constraint if exists order_items_offer_discount_check;
alter table public.order_items add constraint order_items_offer_discount_check
  check (offer_discount_ngwee >= 0);
alter table public.order_items drop constraint if exists order_items_offer_gift_check;
alter table public.order_items add constraint order_items_offer_gift_check
  check (not is_offer_gift or (offer_id is not null and unit_price_ngwee = 0));
-- A paid line keeps the original > 0 rule; only a gift line may be 0.
alter table public.order_items drop constraint if exists order_items_unit_price_ngwee_check;
alter table public.order_items add constraint order_items_unit_price_ngwee_check
  check (unit_price_ngwee > 0 or (is_offer_gift and unit_price_ngwee = 0));

create index if not exists order_items_offer_id_idx
  on public.order_items (offer_id) where offer_id is not null;
create index if not exists order_items_offer_parent_idx
  on public.order_items (offer_parent_item_id) where offer_parent_item_id is not null;

-- ---------------------------------------------------------------------------
-- 5. Release gift stock exactly once: on cancellation (same tx as the guarded
--    status update) and when an unpaid checkout expires / is abandoned
-- ---------------------------------------------------------------------------

create or replace function public.release_offer_gift_reservations(
  p_order_id uuid,
  p_action text,
  p_before jsonb,
  p_after jsonb
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_lines jsonb;
  v_actor uuid;
begin
  -- Lock the offers in id order (order creation locks them in the same order).
  perform 1 from public.offers o
  where o.id in (
    select r.offer_id from public.offer_gift_reservations r
    where r.order_id = p_order_id and r.status = 'reserved')
  order by o.id
  for update;

  with released as (
    update public.offer_gift_reservations r
    set status = 'released', released_at = timezone('utc', now())
    where r.order_id = p_order_id and r.status = 'reserved'
    returning r.offer_id, r.order_item_id, r.qty
  ),
  pool as (
    update public.offers o
    set gift_stock_reserved = greatest(0, o.gift_stock_reserved - s.qty)
    from (select offer_id, sum(qty)::integer as qty from released group by offer_id) s
    where o.id = s.offer_id
    returning o.id
  )
  select jsonb_agg(jsonb_build_object('offer_id', r.offer_id, 'order_item_id', r.order_item_id,
                                      'qty', r.qty) order by r.order_item_id)
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
    values (v_actor, p_action, 'order', p_order_id, p_before,
            p_after || jsonb_build_object('gifts', v_lines));
  end if;
end;
$$;

revoke execute on function public.release_offer_gift_reservations(uuid, text, jsonb, jsonb)
  from public, anon, authenticated;

create or replace function public.release_cancelled_offer_gifts()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if new.status <> 'cancelled'
     or old.status not in ('placed', 'confirmed', 'processing', 'ready') then
    return new;
  end if;
  perform public.release_offer_gift_reservations(
    new.id,
    'order.offer_gifts_released',
    jsonb_build_object('status', old.status),
    jsonb_build_object('status', new.status)
  );
  return new;
end;
$$;

revoke execute on function public.release_cancelled_offer_gifts() from public, anon, authenticated;

drop trigger if exists orders_release_cancelled_offer_gifts on public.orders;
create trigger orders_release_cancelled_offer_gifts
  after update of status on public.orders
  for each row
  when (new.status = 'cancelled' and old.status is distinct from new.status)
  execute function public.release_cancelled_offer_gifts();

-- An unpaid checkout that expires (payment timeout) or is abandoned never
-- ships; its still-`placed` orders give their gifts back to the pool.
-- expire_checkout_group_if_unpaid refuses once a payment succeeded, so a paid
-- order never loses its gift here.
create or replace function public.release_expired_checkout_offer_gifts()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_order record;
begin
  for v_order in
    select o.id from public.orders o
    where o.checkout_group_id = new.id and o.status = 'placed'
    order by o.id
  loop
    perform public.release_offer_gift_reservations(
      v_order.id,
      'order.offer_gifts_released_unpaid',
      jsonb_build_object('checkout_status', old.status),
      jsonb_build_object('checkout_status', new.status)
    );
  end loop;
  return new;
end;
$$;

revoke execute on function public.release_expired_checkout_offer_gifts()
  from public, anon, authenticated;

drop trigger if exists checkout_groups_release_offer_gifts on public.checkout_groups;
create trigger checkout_groups_release_offer_gifts
  after update of status on public.checkout_groups
  for each row
  when (new.status in ('expired', 'abandoned') and old.status is distinct from new.status)
  execute function public.release_expired_checkout_offer_gifts();

-- ---------------------------------------------------------------------------
-- 6. RLS: vendor owns offers; public reads active offers; admin has full access
-- ---------------------------------------------------------------------------

alter table public.offers enable row level security;
alter table public.offers force row level security;
alter table public.offer_items enable row level security;
alter table public.offer_items force row level security;
alter table public.offer_gift_reservations enable row level security;
alter table public.offer_gift_reservations force row level security;

drop policy if exists offers_public_select on public.offers;
create policy offers_public_select
  on public.offers
  for select
  to anon, authenticated
  using (
    status = 'active'
    and not paused_by_admin
    and starts_at <= timezone('utc', now())
    and (ends_at is null or ends_at > timezone('utc', now()))
    and exists (
      select 1 from public.vendors v
      where v.id = offers.vendor_id and v.status = 'active'
    )
  );

drop policy if exists offers_owner_all on public.offers;
create policy offers_owner_all
  on public.offers
  for all
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = offers.vendor_id and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  )
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = offers.vendor_id and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  );

drop policy if exists offer_items_public_select on public.offer_items;
create policy offer_items_public_select
  on public.offer_items
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.offers o
      join public.vendors v on v.id = o.vendor_id
      where o.id = offer_items.offer_id
        and o.status = 'active'
        and not o.paused_by_admin
        and o.starts_at <= timezone('utc', now())
        and (o.ends_at is null or o.ends_at > timezone('utc', now()))
        and v.status = 'active'
    )
  );

drop policy if exists offer_items_owner_all on public.offer_items;
create policy offer_items_owner_all
  on public.offer_items
  for all
  to authenticated
  using (
    exists (
      select 1
      from public.offers o
      join public.vendors v on v.id = o.vendor_id
      where o.id = offer_items.offer_id and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  )
  with check (
    exists (
      select 1
      from public.offers o
      join public.vendors v on v.id = o.vendor_id
      where o.id = offer_items.offer_id and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  );

revoke all on public.offers from anon, authenticated;
grant select, insert, update, delete on public.offers to authenticated;
grant select on public.offers to anon;
grant select, insert, update, delete on public.offers to service_role;

revoke all on public.offer_items from anon, authenticated;
grant select, insert, update, delete on public.offer_items to authenticated;
grant select on public.offer_items to anon;
grant select, insert, update, delete on public.offer_items to service_role;

-- Written by order creation, released by the cancel trigger: no client grant.
revoke all on public.offer_gift_reservations from public, anon, authenticated;
grant select, insert, update, delete on public.offer_gift_reservations to service_role;

-- ---------------------------------------------------------------------------
-- 7. Flag, admin abuse limits, rate-limit scopes
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  (
    'bundles',
    false,
    'W8 bundles & offers (buy X get Y, bundle price, buy N pay M, free gift). Default OFF.'
  )
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  ('bundles_max_discount_pct', '90'::jsonb,
   'Abuse cap: the largest discount (percent of list value) a vendor offer may give.'),
  ('bundles_max_active_offers_per_vendor', '20'::jsonb,
   'Abuse cap: active offers a single vendor may run at once.')
on conflict (key) do nothing;

insert into private.rate_counter_scope_manifest (scope) values
  ('vendor_offers_write'),
  ('offers_public_read_ip'),
  -- Hotfix 20261114050000 scopes, repeated so either order of landing converges.
  ('checkout_group_read_user'),
  ('notifications_read'),
  ('notifications_write'),
  ('web_push_subscribe')
on conflict (scope) do nothing;

-- The constraint MUST list every manifest scope or bump_rate_counter 500s.
alter table public.rate_counters drop constraint if exists rate_counters_scope_check;

alter table public.rate_counters add constraint rate_counters_scope_check check (
  scope in (
    'admin_support_actor', 'admin_support_ip', 'analytics_collect_ip', 'ask_ip',
    'auth_ip', 'auth_number', 'beta_feedback_ip', 'beta_redeem_ip',
    'checkout_group_read_user', 'clip_comment', 'clip_like', 'clip_link',
    'clip_report', 'clip_view', 'discovery_read_ip', 'enquiries_ip_close',
    'enquiries_ip_create', 'enquiries_ip_message', 'enquiries_user_close',
    'enquiries_user_create', 'enquiries_user_message', 'event_access_unlock_ip',
    'intake_link_mint', 'intake_link_redeem', 'internal_cron', 'invoice_download',
    'job_complete_ip', 'job_complete_user', 'job_confirm_ip', 'job_confirm_user',
    'jobs_ip', 'jobs_user', 'listing_report_ip', 'listing_report_user',
    'notifications_read', 'notifications_write', 'offers_public_read_ip', 'otp_ip',
    'otp_number', 'quotes_ip',
    'quotes_user', 'returns_ip', 'returns_user', 'reviews_ip_reply',
    'reviews_ip_submit', 'reviews_user_reply', 'reviews_user_submit', 'rfq_accept_ip',
    'rfq_accept_user', 'rfq_ip_create', 'rfq_ip_message', 'rfq_ip_quote',
    'rfq_user_create', 'rfq_user_message', 'rfq_user_quote', 'search_geo_ip',
    'service_book_ip', 'service_book_user', 'service_reviews_ip_reply',
    'service_reviews_ip_submit', 'service_reviews_user_reply',
    'service_reviews_user_submit', 'telemetry_frontend_errors_ip',
    'telemetry_views_ip', 'ticket_transfer_cancel_ip', 'ticket_transfer_cancel_user',
    'ticket_transfer_claim_ip', 'ticket_transfer_claim_user',
    'ticket_transfer_initiate_ip', 'ticket_transfer_initiate_user', 'ticket_verify_ip',
    'ticket_verify_user', 'vendor_collections_write', 'vendor_follow',
    'vendor_licence_apply', 'vendor_offers_write', 'vendor_payout_method_change',
    'vendor_payouts_read', 'web_push_subscribe', 'webhook_cloudinary',
    'webhook_waha_intake', 'write_admin', 'write_payment', 'write_sensitive',
    'write_standard'
  )
);

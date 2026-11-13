-- Coupons (products), gift orders and birthday greetings — founder-approved growth
-- features (docs: logistics/growth-features-blueprint.md §3). Every surface is
-- behind a feature flag that defaults OFF: `coupons`, `gift_orders`,
-- `birthday_greetings`. Cash-value gift cards are deliberately NOT built (legal
-- review pending under the National Payment System Act, 2026).
--
-- Money model (integer ngwee everywhere):
--   * A coupon discounts ITEMS only (never the delivery fee).
--   * platform-funded: the customer pays items + delivery − discount; at
--     collection escrow is topped up by a `coupon_funding` posting
--     (debit marketing_expense, credit escrow) so the vendor's release is
--     computed on the full price exactly as without a coupon.
--   * vendor-funded: the order is simply smaller. Escrow holds what the
--     customer paid, commission is charged on the discounted price (the
--     purchase-time commission snapshot is scaled at order creation) and the
--     vendor's release gross is items − discount.
--   * Refunds return what the customer paid; a platform-funded discount share
--     goes back to marketing_expense inside the same refund transaction.
--
-- Redemptions are reserved inside the order-creation transaction under a
-- row lock on the coupon (`reserve_coupon_redemption`), so total and per-user
-- limits cannot be overused under concurrency. Payment success applies them;
-- checkout expiry/abandonment releases them. Every transition goes through
-- `coupon_redemption_transition` and is written to audit_log.
--
-- Additive only. Down (manual, only while no ledger posting references
-- marketing_expense and no order carries a coupon):
--   drop trigger if exists checkout_groups_release_coupon_redemptions on public.checkout_groups;
--   drop trigger if exists payments_coupon_gift_on_success on public.payments;
--   drop function if exists private.checkout_groups_release_coupon_redemptions();
--   drop function if exists private.payments_coupon_gift_on_success();
--   drop function if exists public.reserve_coupon_redemption(uuid, uuid, uuid, bigint);
--   drop function if exists public.coupon_redemption_transition(uuid, text, uuid, text);
--   drop function if exists public.issue_birthday_greeting(uuid, int, date, text, bigint, bigint, int);
--   drop table if exists public.birthday_greetings, public.profile_birthdays,
--     public.gift_details, public.coupon_redemptions, public.promo_budgets, public.coupons;
--   alter table public.orders drop column if exists coupon_redemption_id,
--     drop column if exists coupon_discount_ngwee, drop column if exists coupon_funder,
--     drop column if exists is_gift;
--   alter table public.checkout_groups drop column if exists coupon_id,
--     drop column if exists coupon_code, drop column if exists discount_ngwee;
--   delete from public.feature_flags where flag in ('coupons','gift_orders','birthday_greetings');
--   delete from public.platform_config where key in
--     ('promo_monthly_budget_ngwee','vendor_coupon_max_percent_bps','birthday_coupon');
--   delete from public.ledger_accounts where kind = 'marketing_expense' and vendor_id is null;
--   (then restore ledger_accounts_kind_check from 20261113120500)

-- ---------------------------------------------------------------------------
-- 0. Flags + config (all default OFF / conservative)
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  ('coupons', false,
   'General product coupons (platform- and vendor-funded). Default OFF.'),
  ('gift_orders', false,
   'Buy-for-someone-else gift orders (prepaid only, recipient pickup PIN). Default OFF.'),
  ('birthday_greetings', false,
   'Daily consented birthday greeting + single-use personal coupon. Default OFF.')
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  ('promo_monthly_budget_ngwee', '0'::jsonb,
   'Hard monthly cap (ngwee) on platform-funded coupon discounts. 0 = no platform coupons apply.'),
  ('vendor_coupon_max_percent_bps', '5000'::jsonb,
   'Largest percentage a vendor may give on its own coupon (basis points; 5000 = 50%).'),
  ('birthday_coupon',
   '{"value_ngwee": 2000, "min_spend_ngwee": 20000, "valid_days": 14, "require_completed_order": true}'::jsonb,
   'Birthday coupon: fixed value, minimum basket, validity in days, completed-order requirement.')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- 1. Ledger: marketing_expense (platform account)
-- ---------------------------------------------------------------------------

alter table public.ledger_accounts drop constraint if exists ledger_accounts_kind_check;
alter table public.ledger_accounts add constraint ledger_accounts_kind_check
  check (kind in (
    'platform_cash', 'escrow', 'commission_revenue',
    'vendor_payable', 'cod_receivable', 'fees',
    'delivery_revenue', 'marketing_expense'
  ));

insert into public.ledger_accounts (id, kind)
values ('c8000000-0000-0000-0000-000000000008', 'marketing_expense')
on conflict (kind) where vendor_id is null do nothing;

-- ---------------------------------------------------------------------------
-- 2. Coupons
-- ---------------------------------------------------------------------------

create table public.coupons (
  id uuid primary key default gen_random_uuid(),
  code text not null check (code ~ '^[A-Z0-9][A-Z0-9-]{2,31}$'),
  title text check (title is null or char_length(title) <= 80),
  kind text not null check (kind in ('percent', 'fixed')),
  percent_bps int check (percent_bps is null or (percent_bps between 1 and 10000)),
  amount_ngwee bigint check (amount_ngwee is null or amount_ngwee > 0),
  max_discount_ngwee bigint check (max_discount_ngwee is null or max_discount_ngwee > 0),
  funder text not null check (funder in ('platform', 'vendor')),
  vendor_id uuid references public.vendors (id) on delete restrict,
  scope text not null default 'all' check (scope in ('all', 'vendor', 'category', 'listing')),
  scope_vendor_id uuid references public.vendors (id) on delete restrict,
  scope_category_id uuid references public.categories (id) on delete restrict,
  scope_listing_id uuid references public.vendor_listings (id) on delete restrict,
  min_spend_ngwee bigint not null default 0 check (min_spend_ngwee >= 0),
  starts_at timestamptz not null,
  ends_at timestamptz,
  total_limit int check (total_limit is null or total_limit > 0),
  per_user_limit int not null default 1 check (per_user_limit > 0),
  uses_count int not null default 0 check (uses_count >= 0),
  personal_user_id uuid references auth.users (id) on delete cascade,
  source text not null default 'admin' check (source in ('admin', 'vendor', 'birthday')),
  status text not null default 'active' check (status in ('active', 'paused', 'archived')),
  created_by uuid,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint coupons_kind_value_check check (
    (kind = 'percent' and percent_bps is not null and amount_ngwee is null)
    or (kind = 'fixed' and amount_ngwee is not null and percent_bps is null)
  ),
  constraint coupons_funder_vendor_check check (
    (funder = 'vendor' and vendor_id is not null)
    or (funder = 'platform' and vendor_id is null)
  ),
  -- A vendor-funded coupon can only ever discount that vendor's own items.
  constraint coupons_vendor_scope_check check (
    funder = 'platform'
    or (scope = 'vendor' and scope_vendor_id = vendor_id)
    or (scope = 'listing' and scope_listing_id is not null)
  ),
  constraint coupons_scope_target_check check (
    (scope = 'all' and scope_vendor_id is null and scope_category_id is null
      and scope_listing_id is null)
    or (scope = 'vendor' and scope_vendor_id is not null)
    or (scope = 'category' and scope_category_id is not null)
    or (scope = 'listing' and scope_listing_id is not null)
  ),
  constraint coupons_window_check check (ends_at is null or ends_at > starts_at)
);

create unique index coupons_code_key on public.coupons (code);
create index coupons_vendor_id_idx on public.coupons (vendor_id) where vendor_id is not null;
create index coupons_personal_user_idx on public.coupons (personal_user_id)
  where personal_user_id is not null;

create trigger coupons_set_updated_at
  before update on public.coupons
  for each row execute function public.set_updated_at();

comment on table public.coupons is
  'Product coupons. Writes are API/service-role only; codes are never publicly listable.';

create table public.promo_budgets (
  month date primary key check (extract(day from month) = 1),
  cap_ngwee bigint not null check (cap_ngwee >= 0),
  committed_ngwee bigint not null default 0 check (committed_ngwee >= 0),
  updated_at timestamptz not null default timezone('utc', now())
);

comment on table public.promo_budgets is
  'Monthly platform-funded discount budget (Africa/Lusaka month). committed = reserved + applied.';

create table public.coupon_redemptions (
  id uuid primary key default gen_random_uuid(),
  coupon_id uuid not null references public.coupons (id) on delete restrict,
  user_id uuid not null references auth.users (id) on delete restrict,
  checkout_group_id uuid not null references public.checkout_groups (id) on delete restrict,
  funder text not null check (funder in ('platform', 'vendor')),
  discount_ngwee bigint not null check (discount_ngwee > 0),
  budget_month date,
  status text not null default 'reserved' check (status in ('reserved', 'applied', 'released')),
  created_at timestamptz not null default timezone('utc', now()),
  applied_at timestamptz,
  released_at timestamptz,
  constraint coupon_redemptions_coupon_checkout_key unique (coupon_id, checkout_group_id)
);

create index coupon_redemptions_coupon_status_idx
  on public.coupon_redemptions (coupon_id, status);
create index coupon_redemptions_user_idx on public.coupon_redemptions (user_id, coupon_id);
create index coupon_redemptions_checkout_idx on public.coupon_redemptions (checkout_group_id);

alter table public.checkout_groups
  add column if not exists coupon_id uuid references public.coupons (id) on delete restrict,
  add column if not exists coupon_code text,
  add column if not exists discount_ngwee bigint not null default 0
    check (discount_ngwee >= 0);

alter table public.orders
  add column if not exists coupon_redemption_id uuid
    references public.coupon_redemptions (id) on delete restrict,
  add column if not exists coupon_discount_ngwee bigint not null default 0
    check (coupon_discount_ngwee >= 0),
  add column if not exists coupon_funder text
    check (coupon_funder is null or coupon_funder in ('platform', 'vendor')),
  add column if not exists is_gift boolean not null default false;

alter table public.orders drop constraint if exists orders_coupon_consistency_check;
alter table public.orders add constraint orders_coupon_consistency_check check (
  (coupon_discount_ngwee = 0 and coupon_funder is null)
  or (coupon_discount_ngwee > 0 and coupon_funder is not null
      and coupon_redemption_id is not null and cod = false)
);

-- Guarded redemption state machine + audit.
create or replace function public.coupon_redemption_transition(
  p_redemption_id uuid,
  p_to text,
  p_actor uuid,
  p_reason text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row public.coupon_redemptions%rowtype;
begin
  if nullif(btrim(p_reason), '') is null then
    raise exception 'coupon redemption transition reason is required';
  end if;
  select * into v_row from public.coupon_redemptions
  where id = p_redemption_id for update;
  if not found then
    raise exception 'coupon redemption % not found', p_redemption_id;
  end if;
  if v_row.status = p_to then
    return false; -- idempotent replay
  end if;
  if not (
    (v_row.status = 'reserved' and p_to in ('applied', 'released'))
    or (v_row.status = 'applied' and p_to = 'released')
  ) then
    raise exception 'illegal coupon redemption transition % -> %', v_row.status, p_to;
  end if;

  update public.coupon_redemptions
  set status = p_to,
      applied_at = case when p_to = 'applied' then timezone('utc', now()) else applied_at end,
      released_at = case when p_to = 'released' then timezone('utc', now()) else released_at end
  where id = p_redemption_id;

  if p_to = 'released' then
    -- Give the use back (and the platform budget it held).
    update public.coupons
    set uses_count = greatest(uses_count - 1, 0)
    where id = v_row.coupon_id;
    if v_row.funder = 'platform' and v_row.budget_month is not null then
      update public.promo_budgets
      set committed_ngwee = greatest(committed_ngwee - v_row.discount_ngwee, 0),
          updated_at = timezone('utc', now())
      where month = v_row.budget_month;
    end if;
  end if;

  insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
  values (
    p_actor, 'coupon_redemption.transition', 'coupon_redemption', p_redemption_id,
    jsonb_build_object('status', v_row.status),
    jsonb_build_object('status', p_to, 'reason', p_reason,
                       'discount_ngwee', v_row.discount_ngwee)
  );
  return true;
end;
$$;

-- Atomic reservation: the coupon row lock serialises every concurrent checkout
-- for the same code, so the limit checks and the insert are one decision.
-- Raises machine-readable markers the API maps to customer-facing errors.
create or replace function public.reserve_coupon_redemption(
  p_coupon_id uuid,
  p_user_id uuid,
  p_checkout_group_id uuid,
  p_discount_ngwee bigint
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_coupon public.coupons%rowtype;
  v_existing public.coupon_redemptions%rowtype;
  v_total int;
  v_user int;
  v_month date;
  v_cap bigint;
  v_budget public.promo_budgets%rowtype;
  v_id uuid;
begin
  if p_discount_ngwee is null or p_discount_ngwee <= 0 then
    raise exception 'COUPON_INVALID:zero_discount';
  end if;
  select * into v_coupon from public.coupons where id = p_coupon_id for update;
  if not found then
    raise exception 'COUPON_INVALID:not_found';
  end if;
  if v_coupon.status <> 'active' then
    raise exception 'COUPON_INVALID:inactive';
  end if;
  if now() < v_coupon.starts_at then
    raise exception 'COUPON_INVALID:not_started';
  end if;
  if v_coupon.ends_at is not null and now() >= v_coupon.ends_at then
    raise exception 'COUPON_INVALID:expired';
  end if;
  if v_coupon.personal_user_id is not null and v_coupon.personal_user_id <> p_user_id then
    raise exception 'COUPON_INVALID:not_found';
  end if;

  select * into v_existing from public.coupon_redemptions
  where coupon_id = p_coupon_id and checkout_group_id = p_checkout_group_id;
  if found then
    if v_existing.status = 'reserved' and v_existing.discount_ngwee = p_discount_ngwee then
      return v_existing.id; -- idempotent retry of the same checkout
    end if;
    raise exception 'COUPON_INVALID:already_used_on_checkout';
  end if;

  select count(*) into v_total from public.coupon_redemptions
  where coupon_id = p_coupon_id and status in ('reserved', 'applied');
  if v_coupon.total_limit is not null and v_total >= v_coupon.total_limit then
    raise exception 'COUPON_LIMIT:total';
  end if;
  select count(*) into v_user from public.coupon_redemptions
  where coupon_id = p_coupon_id and user_id = p_user_id and status in ('reserved', 'applied');
  if v_user >= v_coupon.per_user_limit then
    raise exception 'COUPON_LIMIT:user';
  end if;

  if v_coupon.funder = 'platform' then
    v_month := date_trunc('month', (now() at time zone 'Africa/Lusaka'))::date;
    select coalesce((value #>> '{}')::bigint, 0) into v_cap
    from public.platform_config where key = 'promo_monthly_budget_ngwee';
    insert into public.promo_budgets (month, cap_ngwee)
    values (v_month, coalesce(v_cap, 0))
    on conflict (month) do nothing;
    select * into v_budget from public.promo_budgets where month = v_month for update;
    if v_budget.committed_ngwee + p_discount_ngwee > v_budget.cap_ngwee then
      raise exception 'COUPON_BUDGET:exhausted';
    end if;
    update public.promo_budgets
    set committed_ngwee = committed_ngwee + p_discount_ngwee,
        updated_at = timezone('utc', now())
    where month = v_month;
  end if;

  insert into public.coupon_redemptions (
    coupon_id, user_id, checkout_group_id, funder, discount_ngwee, budget_month, status
  ) values (
    p_coupon_id, p_user_id, p_checkout_group_id, v_coupon.funder, p_discount_ngwee,
    v_month, 'reserved'
  ) returning id into v_id;

  update public.coupons set uses_count = uses_count + 1 where id = p_coupon_id;

  insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
  values (
    p_user_id, 'coupon_redemption.reserved', 'coupon_redemption', v_id, null,
    jsonb_build_object('coupon_id', p_coupon_id, 'checkout_group_id', p_checkout_group_id,
                       'discount_ngwee', p_discount_ngwee, 'funder', v_coupon.funder)
  );
  return v_id;
end;
$$;

revoke all on function public.reserve_coupon_redemption(uuid, uuid, uuid, bigint)
  from public, anon, authenticated;
grant execute on function public.reserve_coupon_redemption(uuid, uuid, uuid, bigint)
  to service_role;
revoke all on function public.coupon_redemption_transition(uuid, text, uuid, text)
  from public, anon, authenticated;
grant execute on function public.coupon_redemption_transition(uuid, text, uuid, text)
  to service_role;

-- Checkout expired / abandoned → give reserved uses back.
create or replace function private.checkout_groups_release_coupon_redemptions()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  for v_id in
    select id from public.coupon_redemptions
    where checkout_group_id = new.id and status = 'reserved'
    order by id
  loop
    perform public.coupon_redemption_transition(
      v_id, 'released', null, 'checkout_' || new.status);
  end loop;
  return new;
end;
$$;

revoke all on function private.checkout_groups_release_coupon_redemptions()
  from public, anon, authenticated;

create trigger checkout_groups_release_coupon_redemptions
  after update of status on public.checkout_groups
  for each row
  when (new.status in ('expired', 'abandoned') and old.status is distinct from new.status)
  execute function private.checkout_groups_release_coupon_redemptions();

-- ---------------------------------------------------------------------------
-- 3. Gift orders
-- ---------------------------------------------------------------------------

create table public.gift_details (
  checkout_group_id uuid primary key references public.checkout_groups (id) on delete cascade,
  buyer_id uuid not null references auth.users (id) on delete cascade,
  recipient_name text not null check (char_length(btrim(recipient_name)) between 1 and 80),
  recipient_phone text check (recipient_phone is null or recipient_phone ~ '^\+260[0-9]{9}$'),
  message text check (message is null or char_length(message) <= 200),
  -- DPA: the buyer confirms the recipient agreed to share their phone/address
  -- with Vergeo5 for this delivery only. Nothing is stored without it.
  buyer_attested_at timestamptz not null,
  recipient_notified_at timestamptz,
  recipient_opt_out_token_hash text,
  recipient_opted_out_at timestamptz,
  redacted_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint gift_details_redacted_check check (
    redacted_at is null or (recipient_phone is null and message is null)
  ),
  constraint gift_details_phone_check check (redacted_at is not null or recipient_phone is not null)
);

create trigger gift_details_set_updated_at
  before update on public.gift_details
  for each row execute function public.set_updated_at();

comment on table public.gift_details is
  'Gift recipient for one checkout. Payer stays the customer of record; recipient data is '
  'used only for this delivery/pickup and redacted after completion.';

-- Payment success → apply reserved coupon uses, send the one gift notice.
create or replace function private.payments_coupon_gift_on_success()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id uuid;
  v_gift public.gift_details%rowtype;
  v_sender text;
  v_shop text;
begin
  for v_id in
    select id from public.coupon_redemptions
    where checkout_group_id = new.checkout_group_id and status = 'reserved'
    order by id
  loop
    perform public.coupon_redemption_transition(v_id, 'applied', null, 'payment_success');
  end loop;

  select * into v_gift from public.gift_details
  where checkout_group_id = new.checkout_group_id for update;
  if found and v_gift.recipient_notified_at is null and v_gift.redacted_at is null
     and v_gift.recipient_phone is not null then
    select coalesce(nullif(btrim(p.display_name), ''), 'A friend') into v_sender
    from public.profiles p where p.id = v_gift.buyer_id;
    select v.display_name into v_shop
    from public.orders o join public.vendors v on v.id = o.vendor_id
    where o.checkout_group_id = new.checkout_group_id
    order by o.id limit 1;
    insert into public.notification_outbox (dedupe_key, channel, template, payload, status)
    values (
      'gift_recipient_notice:' || new.checkout_group_id || ':whatsapp',
      'whatsapp', 'gift_recipient_notice',
      jsonb_build_object(
        'to', v_gift.recipient_phone,
        'phone', v_gift.recipient_phone,
        'checkout_group_id', new.checkout_group_id,
        'sender_name', coalesce(v_sender, 'A friend'),
        'shop_name', coalesce(v_shop, 'Vergeo5'),
        'recipient_name', v_gift.recipient_name
      ),
      'pending'
    ) on conflict (dedupe_key) do nothing;
    update public.gift_details
    set recipient_notified_at = timezone('utc', now())
    where checkout_group_id = new.checkout_group_id;
  end if;
  return new;
end;
$$;

revoke all on function private.payments_coupon_gift_on_success() from public, anon, authenticated;

create trigger payments_coupon_gift_on_success
  after update of status on public.payments
  for each row
  when (new.status = 'success' and old.status is distinct from 'success')
  execute function private.payments_coupon_gift_on_success();

-- ---------------------------------------------------------------------------
-- 4. Birthdays (separate from profiles: optional, consented marketing data)
-- ---------------------------------------------------------------------------

create table public.profile_birthdays (
  user_id uuid primary key references auth.users (id) on delete cascade,
  birth_day smallint not null check (birth_day between 1 and 31),
  birth_month smallint not null check (birth_month between 1 and 12),
  birth_year smallint check (birth_year is null or birth_year between 1900 and 2100),
  consent_at timestamptz not null,
  adult_confirmed_at timestamptz not null,
  last_changed_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint profile_birthdays_valid_date check (
    make_date(coalesce(birth_year::int, 2000), birth_month::int, 1)
      + (birth_day::int - 1) < (make_date(coalesce(birth_year::int, 2000), birth_month::int, 1)
      + interval '1 month')
  )
);

create index profile_birthdays_day_month_idx on public.profile_birthdays (birth_month, birth_day);

create trigger profile_birthdays_set_updated_at
  before update on public.profile_birthdays
  for each row execute function public.set_updated_at();

comment on table public.profile_birthdays is
  'Optional birthday (day+month, optional year) with explicit marketing consent and an '
  '18+ confirmation. Deleting the row withdraws consent. Writes via API only.';

create table public.birthday_greetings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  greeting_year int not null check (greeting_year between 2000 and 2200),
  coupon_id uuid references public.coupons (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint birthday_greetings_user_year_key unique (user_id, greeting_year)
);

-- One greeting per user per calendar year: idempotent under re-runs and
-- concurrent ticks (the unique key decides; the loser does nothing).
create or replace function public.issue_birthday_greeting(
  p_user_id uuid,
  p_year int,
  p_today date,
  p_code text,
  p_value_ngwee bigint,
  p_min_spend_ngwee bigint,
  p_valid_days int
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_greeting uuid;
  v_coupon uuid;
  v_starts timestamptz;
  v_ends timestamptz;
begin
  insert into public.birthday_greetings (user_id, greeting_year)
  values (p_user_id, p_year)
  on conflict (user_id, greeting_year) do nothing
  returning id into v_greeting;
  if v_greeting is null then
    return null;
  end if;

  v_starts := (p_today::timestamp) at time zone 'Africa/Lusaka';
  v_ends := ((p_today + p_valid_days)::timestamp) at time zone 'Africa/Lusaka';
  insert into public.coupons (
    code, title, kind, amount_ngwee, funder, scope, min_spend_ngwee, starts_at, ends_at,
    total_limit, per_user_limit, personal_user_id, source, status
  ) values (
    p_code, 'Birthday', 'fixed', p_value_ngwee, 'platform', 'all', p_min_spend_ngwee,
    v_starts, v_ends, 1, 1, p_user_id, 'birthday', 'active'
  ) returning id into v_coupon;

  update public.birthday_greetings set coupon_id = v_coupon where id = v_greeting;

  insert into public.in_app_notifications (
    recipient_user_id, audience, type, i18n_key, params, link_path, dedupe_key
  ) values (
    p_user_id, 'customer', 'birthday_greeting',
    'notifications.inApp.customer.birthday_greeting',
    jsonb_build_object('code', p_code, 'amount_ngwee', p_value_ngwee,
                       'valid_days', p_valid_days),
    '/account', 'birthday:' || p_year
  ) on conflict on constraint in_app_notifications_recipient_dedupe_key do nothing;

  insert into public.notification_outbox (dedupe_key, channel, template, payload, status)
  values (
    'birthday_greeting:' || p_user_id || ':' || p_year || ':whatsapp',
    'whatsapp', 'birthday_greeting',
    jsonb_build_object('recipient_id', p_user_id, 'coupon_code', p_code,
                       'amount_ngwee', p_value_ngwee, 'min_spend_ngwee', p_min_spend_ngwee,
                       'valid_days', p_valid_days),
    'pending'
  ) on conflict (dedupe_key) do nothing;

  insert into public.audit_log (actor, action, entity_type, entity_id, before, after)
  values (null, 'birthday_greeting.issued', 'coupon', v_coupon, null,
          jsonb_build_object('user_id', p_user_id, 'year', p_year));
  return v_coupon;
end;
$$;

revoke all on function public.issue_birthday_greeting(uuid, int, date, text, bigint, bigint, int)
  from public, anon, authenticated;
grant execute on function public.issue_birthday_greeting(uuid, int, date, text, bigint, bigint, int)
  to service_role;

-- ---------------------------------------------------------------------------
-- 5. RLS (every new table; writes are service-role only)
-- ---------------------------------------------------------------------------

alter table public.coupons enable row level security;
alter table public.coupons force row level security;
alter table public.promo_budgets enable row level security;
alter table public.promo_budgets force row level security;
alter table public.coupon_redemptions enable row level security;
alter table public.coupon_redemptions force row level security;
alter table public.gift_details enable row level security;
alter table public.gift_details force row level security;
alter table public.profile_birthdays enable row level security;
alter table public.profile_birthdays force row level security;
alter table public.birthday_greetings enable row level security;
alter table public.birthday_greetings force row level security;

revoke all on public.coupons, public.promo_budgets, public.coupon_redemptions,
  public.gift_details, public.profile_birthdays, public.birthday_greetings
  from public, anon, authenticated;
grant select on public.coupons, public.coupon_redemptions, public.gift_details,
  public.profile_birthdays, public.birthday_greetings to authenticated;
grant select on public.promo_budgets to authenticated;
grant all on public.coupons, public.promo_budgets, public.coupon_redemptions,
  public.gift_details, public.profile_birthdays, public.birthday_greetings to service_role;

create policy coupons_admin_select on public.coupons
  for select to authenticated using (public.has_role('admin'));
create policy coupons_vendor_select_own on public.coupons
  for select to authenticated
  using (vendor_id is not null and exists (
    select 1 from public.vendors v
    where v.id = coupons.vendor_id and v.owner_user_id = (select auth.uid())
  ));
create policy coupons_personal_select_own on public.coupons
  for select to authenticated
  using (personal_user_id = (select auth.uid()));

create policy promo_budgets_admin_select on public.promo_budgets
  for select to authenticated using (public.has_role('admin'));

create policy coupon_redemptions_select_own on public.coupon_redemptions
  for select to authenticated using (user_id = (select auth.uid()));
create policy coupon_redemptions_admin_select on public.coupon_redemptions
  for select to authenticated using (public.has_role('admin'));

create policy gift_details_buyer_select on public.gift_details
  for select to authenticated using (buyer_id = (select auth.uid()));
create policy gift_details_admin_select on public.gift_details
  for select to authenticated using (public.has_role('admin'));

create policy profile_birthdays_select_own on public.profile_birthdays
  for select to authenticated using (user_id = (select auth.uid()));

create policy birthday_greetings_select_own on public.birthday_greetings
  for select to authenticated using (user_id = (select auth.uid()));

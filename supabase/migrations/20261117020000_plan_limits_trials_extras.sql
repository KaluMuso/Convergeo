-- Plans follow-up to 20261115100000 (founder decisions 2026-11-15).
--
-- 1. Listing limits = ACTIVE (published) listings per plan: Free 20, Starter 200,
--    Business and above unlimited (vendor_plans.max_listings, admin-editable in
--    the existing plan editor). Seeds touch only rows still at their previous
--    seed value (20261114030000: free 25, starter 150), so admin edits win.
--    Drafts are always allowed (the KYC trust cap still bounds draft/active/
--    paused admission); publishing or re-activating beyond the plan limit is
--    refused by `guard_vendor_listing_publish` (PT403 listing_plan_limit_reached).
--    Same flag as before: plan caps apply only while `vendor_plans` is on.
-- 2. Annual prepay discount: platform_config `plan_annual_discount_pct` = 15
--    (admin-editable). Annual price = floor(12 x monthly x (100 - pct) / 100) ngwee.
-- 3. Paid extras catalogue (`vendor_extras`, admin-editable) + vendor requests
--    (`vendor_extras_requests`; requested -> quoted/approved -> fulfilled |
--    cancelled via `transition_vendor_extras_request()`, history in
--    `vendor_extras_request_events`, admin + vendor in-app notifications).
--    No money is collected.
-- 4. Pilot free trial: `vendor_businesses.trial_ends_at` (the business is the
--    billing owner of every shop, #807). New businesses: created_at + 1 month
--    (trigger). Existing businesses: migration time + 1 month. While
--    trial_ends_at > now() the EFFECTIVE plan is Business (listing cap, staff
--    seats, shop limit...): vendor_plan_listing_cap() and business_plan_key()
--    resolve to it. The stored assignment is untouched; after the trial the
--    assigned plan (Free by default) applies again.
--    `vendor_plan_fee_accrues(vendor, at)` is the billing seam: no plan fee
--    accrues while the trial runs.
--
-- Reversal (no pre-existing object depends on the new ones):
--   drop trigger vendor_listing_publish_guard on public.vendor_listings;
--   drop function public.guard_vendor_listing_publish();
--   recreate guard_vendor_listing_admission() from 20261114030000 (plan cap on admission);
--   -- restore the pre-trial resolvers from 20261114030000 / 20261115100000
--   --   (vendor_plan_listing_cap, business_plan_key) before dropping the helpers below.
--   drop function public.vendor_plan_fee_accrues(uuid, timestamptz),
--     public.business_trial_ends_at(uuid), public.transition_vendor_extras_request(
--       uuid, text, uuid, text, text, bigint), private.in_app_from_extras_request() cascade;
--   drop trigger vendor_businesses_trial_default on public.vendor_businesses;
--   drop function public.vendor_business_trial_default();
--   drop table public.vendor_extras_request_events, public.vendor_extras_requests,
--     public.vendor_extras;
--   alter table public.vendor_businesses drop column trial_ends_at;
--   update public.vendor_plans set max_listings = 25 where key = 'free' and max_listings = 20;
--   update public.vendor_plans set max_listings = 150 where key = 'starter' and max_listings = 200;
--   delete from public.platform_config where key = 'plan_annual_discount_pct';
begin;

-- ---------------------------------------------------------------------------
-- 1. Listing limits
-- ---------------------------------------------------------------------------
update public.vendor_plans set max_listings = 20 where key = 'free' and max_listings = 25;
update public.vendor_plans set max_listings = 200 where key = 'starter' and max_listings = 150;

comment on column public.vendor_plans.max_listings is
  'Max ACTIVE (published) listings; NULL = unlimited. Drafts never count.';

-- Admission (draft/active/paused) keeps only the KYC trust cap: drafts are
-- always allowed under a plan. Body otherwise identical to 20261114030000.
create or replace function public.guard_vendor_listing_admission() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_tier integer;
  v_max integer;
  v_count bigint;
begin
  if new.status not in ('draft', 'active', 'paused') then return new; end if;
  if tg_op = 'UPDATE' then
    if old.vendor_id = new.vendor_id and old.status in ('draft', 'active', 'paused') then
      return new;
    end if;
  end if;
  if current_setting('transaction_isolation') <> 'read committed' then
    raise sqlstate '40001' using message = 'listing_admission_requires_read_committed';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('listing-admission:' || new.vendor_id::text, 0));
  select coalesce(max(tier), 1) into v_tier from public.kyc_records
    where vendor_id = new.vendor_id and status = 'approved';
  select max_listings into v_max from public.vendor_quotas where tier = v_tier;
  if v_max is null then
    raise sqlstate 'PT500' using message = 'listing_quota_missing';
  end if;
  -- Distinct listings only: stock_qty and variants never count.
  select count(*) into v_count from public.vendor_listings
    where vendor_id = new.vendor_id and status in ('draft', 'active', 'paused')
      and id <> new.id;
  if v_count >= v_max then
    raise sqlstate 'PT403' using message = 'listing_cap_exceeded';
  end if;
  return new;
end;
$$;

revoke all on function public.guard_vendor_listing_admission() from public, anon, authenticated;

-- Publish/activate guard: a listing entering 'active' must fit the plan's
-- active-listing limit. Existing active listings are never touched (a
-- downgrade leaves them live; only new publishes are refused).
create function public.guard_vendor_listing_publish() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_cap integer;
  v_count bigint;
begin
  if new.status <> 'active' then return new; end if;
  if tg_op = 'UPDATE' and old.status = 'active' and old.vendor_id = new.vendor_id then
    return new;
  end if;
  v_cap := public.vendor_plan_listing_cap(new.vendor_id);
  if v_cap is null then return new; end if;
  if current_setting('transaction_isolation') <> 'read committed' then
    raise sqlstate '40001' using message = 'listing_admission_requires_read_committed';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('listing-publish:' || new.vendor_id::text, 0));
  select count(*) into v_count from public.vendor_listings
    where vendor_id = new.vendor_id and status = 'active' and id <> new.id;
  if v_count >= v_cap then
    raise sqlstate 'PT403' using message = 'listing_plan_limit_reached',
      detail = json_build_object('max_listings', v_cap, 'active_listings', v_count)::text;
  end if;
  return new;
end;
$$;

revoke all on function public.guard_vendor_listing_publish() from public, anon, authenticated;

create trigger vendor_listing_publish_guard
  before insert or update of status, vendor_id on public.vendor_listings
  for each row execute function public.guard_vendor_listing_publish();

-- ---------------------------------------------------------------------------
-- 2. Annual prepay discount (admin-editable, percent)
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  ('plan_annual_discount_pct', '15'::jsonb,
   'Annual prepay discount on vendor plans, percent (annual = floor(12 x monthly x (100 - pct) / 100)).')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- 4. Pilot free trial (on the business = billing owner of every shop)
-- ---------------------------------------------------------------------------
-- The volatile default backfills existing rows with migration time + 1 month.
alter table public.vendor_businesses
  add column trial_ends_at timestamptz not null default (now() + interval '1 month');

comment on column public.vendor_businesses.trial_ends_at is
  'Free trial end: no plan fee accrues before it. Signup + 1 month; Business plan entitlements while it runs; admin may extend or end (audited).';

create function public.vendor_business_trial_default() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
  -- Signup + 1 month (created_at is the business/shop signup time).
  new.trial_ends_at := coalesce(new.created_at, now()) + interval '1 month';
  return new;
end;
$$;

create trigger vendor_businesses_trial_default
  before insert on public.vendor_businesses
  for each row execute function public.vendor_business_trial_default();

create function public.business_trial_ends_at(p_vendor_id uuid) returns timestamptz
language sql stable security definer set search_path = pg_catalog, public
as $$
  select b.trial_ends_at from public.vendors v
    join public.vendor_businesses b on b.id = v.business_id
   where v.id = p_vendor_id
$$;

-- Billing seam: a future subscription charge MUST check this first.
create function public.vendor_plan_fee_accrues(p_vendor_id uuid, p_at timestamptz default now())
returns boolean
language sql stable security definer set search_path = pg_catalog, public
as $$
  select coalesce(public.business_trial_ends_at(p_vendor_id) <= p_at, true)
$$;

-- Effective entitlements during the trial: Business. Replaces the resolvers
-- from 20261114030000 / 20261115100000 (same signatures; trial check added).
create or replace function public.vendor_plan_listing_cap(p_vendor_id uuid) returns integer
language plpgsql stable security definer set search_path = pg_catalog, public
as $$
declare
  v_enabled boolean;
  v_unlimited boolean;
  v_cap integer;
  v_trial_found boolean;
begin
  select ff.enabled into v_enabled from public.feature_flags ff where ff.flag = 'vendor_plans';
  if not coalesce(v_enabled, false) then
    return null;
  end if;

  -- Pilot trial: Business entitlements (unlimited listings) until trial_ends_at.
  if coalesce(public.business_trial_ends_at(p_vendor_id) > now(), false) then
    select p.max_listings, true into v_cap, v_trial_found
      from public.vendor_plans p where p.key = 'business';
    if coalesce(v_trial_found, false) then
      return v_cap;
    end if;
  end if;

  select o.unlimited_listings, o.max_listings into v_unlimited, v_cap
    from public.vendor_plan_overrides o
    where o.vendor_id = p_vendor_id and o.expires_at > now();
  if found then
    if v_unlimited then
      return null;
    end if;
    if v_cap is not null then
      return v_cap;
    end if;
  end if;

  select p.max_listings into v_cap
    from public.vendor_plan_assignments a
    join public.vendor_plans p on p.key = a.plan_key
    where a.vendor_id = p_vendor_id;
  if found then
    return v_cap;
  end if;

  select p.max_listings into v_cap from public.vendor_plans p where p.is_default;
  return v_cap;
end;
$$;

create or replace function public.business_plan_key(p_business_id uuid) returns text
language sql stable security definer set search_path = pg_catalog, public
as $$
  select case
    when exists (select 1 from public.vendor_businesses b
                  where b.id = p_business_id and b.trial_ends_at > now())
     and exists (select 1 from public.vendor_plans p where p.key = 'business')
      then 'business'
    else coalesce(
      (select a.plan_key from public.vendors v
         join public.vendor_plan_assignments a on a.vendor_id = v.id
        where v.business_id = p_business_id and v.is_primary_branch
        limit 1),
      (select p.key from public.vendor_plans p where p.is_default limit 1)
    )
  end
$$;

revoke all on function public.vendor_business_trial_default() from public, anon, authenticated;
revoke all on function public.business_trial_ends_at(uuid) from public, anon, authenticated;
revoke all on function public.vendor_plan_fee_accrues(uuid, timestamptz) from public, anon, authenticated;
grant execute on function public.business_trial_ends_at(uuid) to service_role;
grant execute on function public.vendor_plan_fee_accrues(uuid, timestamptz) to service_role;

-- ---------------------------------------------------------------------------
-- 3. Paid extras catalogue + requests
-- ---------------------------------------------------------------------------
create table public.vendor_extras (
  key text primary key check (key ~ '^[a-z][a-z0-9_]{1,47}$'),
  name text not null check (char_length(btrim(name)) between 1 and 80),
  description text not null default '' check (char_length(description) <= 500),
  -- fixed = price_ngwee; range = price_ngwee..price_max_ngwee;
  -- pay_as_you_go = optional "from" price_ngwee.
  pricing text not null default 'fixed' check (pricing in ('fixed', 'range', 'pay_as_you_go')),
  price_ngwee bigint check (price_ngwee is null or price_ngwee between 0 and 100000000),
  price_max_ngwee bigint check (price_max_ngwee is null or price_max_ngwee between 0 and 100000000),
  unit text not null default 'one_off' check (unit in ('one_off', 'per_month', 'per_item')),
  -- true = a starter price picked at seed time, still to be reviewed by an admin.
  price_is_placeholder boolean not null default false,
  active boolean not null default true,
  position integer not null default 0 check (position between 0 and 1000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_extras_price_shape check (
    (pricing = 'fixed' and price_ngwee is not null and price_max_ngwee is null)
    or (pricing = 'range' and price_ngwee is not null and price_max_ngwee is not null
        and price_max_ngwee > price_ngwee)
    or (pricing = 'pay_as_you_go' and price_max_ngwee is null)
  )
);

comment on table public.vendor_extras is
  'Admin-editable catalogue of paid vendor extras (display + request only; no money collected).';

create trigger vendor_extras_set_updated_at
  before update on public.vendor_extras
  for each row execute function public.set_updated_at();

create trigger vendor_extras_audit
  after insert or update or delete on public.vendor_extras
  for each row execute function public.audit_config_change();

-- Starter catalogue (ngwee). Store design is founder-priced (K500-K5,000);
-- every other price is a starter price flagged for admin review.
insert into public.vendor_extras
  (key, name, description, pricing, price_ngwee, price_max_ngwee, unit, price_is_placeholder, position)
values
  ('sponsored_listings', 'Sponsored listings',
   'Boost a listing to the top of search and category pages. Pay as you go, from K10 per listing per day.',
   'pay_as_you_go', 1000, null, 'per_item', true, 0),
  ('banner_ads', 'Banner ads',
   'A banner on the home or category pages. Pay as you go, from K150 per banner per week.',
   'pay_as_you_go', 15000, null, 'per_item', true, 1),
  ('store_design', 'Store design',
   'We design your storefront: logo, cover, colours and layout.',
   'range', 50000, 500000, 'one_off', false, 2),
  ('product_photography', 'Product photography and upload',
   'We photograph your products and upload them for you. Price per product.',
   'fixed', 2500, null, 'per_item', true, 3),
  ('market_insights', 'Market insight report',
   'Prices, demand and competitors in your category, as a short report.',
   'fixed', 15000, null, 'one_off', true, 4),
  ('whatsapp_credits', 'WhatsApp broadcast credits',
   'Extra WhatsApp broadcast messages to your followers. Price per 100 messages.',
   'fixed', 5000, null, 'per_item', true, 5),
  ('extra_staff_seats', 'Extra staff seats',
   'One more staff login beyond your plan.',
   'fixed', 2500, null, 'per_month', true, 6),
  ('extra_listings', 'Extra listings',
   'Publish 50 more active listings beyond your plan limit.',
   'fixed', 3000, null, 'per_month', true, 7),
  ('instant_payout', 'Instant payout',
   'Get a payout the same day instead of on the normal schedule. Price per payout.',
   'fixed', 500, null, 'per_item', true, 8),
  ('delivery_subscription', 'Delivery subscription',
   'Discounted Lusaka deliveries for your orders, billed monthly.',
   'fixed', 19900, null, 'per_month', true, 9),
  ('wholesale_access', 'Wholesale access',
   'Sell to verified business buyers with tier pricing and minimum order quantities.',
   'fixed', 9900, null, 'per_month', true, 10),
  ('custom_domain', 'Custom domain',
   'Your storefront on your own web address (domain registration not included).',
   'fixed', 7500, null, 'per_month', true, 11)
on conflict (key) do nothing;

create table public.vendor_extras_requests (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  extra_key text not null references public.vendor_extras (key) on delete restrict,
  requested_by uuid not null references public.profiles (id) on delete restrict,
  quantity integer not null default 1 check (quantity between 1 and 10000),
  note text check (note is null or char_length(note) <= 500),
  status text not null default 'requested'
    check (status in ('requested', 'quoted', 'approved', 'fulfilled', 'cancelled')),
  quoted_price_ngwee bigint check (quoted_price_ngwee is null or quoted_price_ngwee between 0 and 100000000),
  admin_note text check (admin_note is null or char_length(admin_note) <= 1000),
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_extras_requests_quote_present
    check (status <> 'quoted' or quoted_price_ngwee is not null)
);

-- One open request per shop and extra.
create unique index vendor_extras_requests_open_key
  on public.vendor_extras_requests (vendor_id, extra_key)
  where status in ('requested', 'quoted', 'approved');
create index vendor_extras_requests_status_idx
  on public.vendor_extras_requests (status, created_at desc);
create index vendor_extras_requests_vendor_idx
  on public.vendor_extras_requests (vendor_id, created_at desc);

create trigger vendor_extras_requests_set_updated_at
  before update on public.vendor_extras_requests
  for each row execute function public.set_updated_at();

create table public.vendor_extras_request_events (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.vendor_extras_requests (id) on delete cascade,
  from_status text,
  to_status text not null,
  actor uuid,
  actor_role text not null check (actor_role in ('vendor', 'admin')),
  note text check (note is null or char_length(note) <= 1000),
  quoted_price_ngwee bigint,
  created_at timestamptz not null default now()
);

create index vendor_extras_request_events_request_idx
  on public.vendor_extras_request_events (request_id, created_at);

-- Status changes only through transition_vendor_extras_request().
create function public.vendor_extras_request_status_guard() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'INSERT' then
    if new.status <> 'requested' then
      raise exception using errcode = '22023', message = 'extras_request_must_start_requested';
    end if;
    return new;
  end if;
  if (new.status is distinct from old.status
      or new.quoted_price_ngwee is distinct from old.quoted_price_ngwee)
     and coalesce(current_setting('convergeo.extras_transition', true), '') <> 'on' then
    raise exception using errcode = '42501', message = 'extras_request_status_guarded';
  end if;
  return new;
end;
$$;

create trigger vendor_extras_requests_status_guard
  before insert or update on public.vendor_extras_requests
  for each row execute function public.vendor_extras_request_status_guard();

create function public.transition_vendor_extras_request(
  p_request_id uuid, p_to text, p_actor uuid, p_actor_role text,
  p_note text default null, p_quoted_price_ngwee bigint default null
) returns jsonb
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_req public.vendor_extras_requests%rowtype;
  v_allowed boolean;
begin
  if p_actor_role not in ('vendor', 'admin') then
    raise exception using errcode = '22023', message = 'extras_invalid_actor';
  end if;
  select * into v_req from public.vendor_extras_requests where id = p_request_id for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'extras_request_not_found';
  end if;
  if p_actor_role = 'vendor' and not exists (
    select 1 from public.vendors v where v.id = v_req.vendor_id and v.owner_user_id = p_actor
  ) then
    raise exception using errcode = '42501', message = 'extras_request_not_owner';
  end if;

  v_allowed := case
    when p_actor_role = 'admin' then
      (v_req.status = 'requested' and p_to in ('quoted', 'approved', 'cancelled'))
      or (v_req.status = 'quoted' and p_to in ('quoted', 'approved', 'cancelled'))
      or (v_req.status = 'approved' and p_to in ('fulfilled', 'cancelled'))
    else
      -- The vendor may accept a quote or withdraw an open request.
      (v_req.status = 'quoted' and p_to = 'approved')
      or (v_req.status in ('requested', 'quoted') and p_to = 'cancelled')
  end;
  if not v_allowed then
    raise exception using errcode = '22023', message = 'extras_invalid_transition',
      detail = json_build_object('from', v_req.status, 'to', p_to)::text;
  end if;
  if p_to = 'quoted' and p_quoted_price_ngwee is null then
    raise exception using errcode = '22023', message = 'extras_quote_price_required';
  end if;
  if p_quoted_price_ngwee is not null and p_to <> 'quoted' then
    raise exception using errcode = '22023', message = 'extras_quote_price_unexpected';
  end if;

  perform set_config('convergeo.extras_transition', 'on', true);
  update public.vendor_extras_requests set
    status = p_to,
    quoted_price_ngwee = coalesce(p_quoted_price_ngwee, quoted_price_ngwee),
    admin_note = case when p_actor_role = 'admin' and nullif(btrim(p_note), '') is not null
                      then btrim(p_note) else admin_note end,
    decided_at = case when p_to in ('fulfilled', 'cancelled') then now() else decided_at end
  where id = p_request_id;
  perform set_config('convergeo.extras_transition', 'off', true);

  insert into public.vendor_extras_request_events
    (request_id, from_status, to_status, actor, actor_role, note, quoted_price_ngwee)
  values (p_request_id, v_req.status, p_to, p_actor, p_actor_role,
          nullif(btrim(p_note), ''), p_quoted_price_ngwee);

  return jsonb_build_object(
    'id', p_request_id, 'vendor_id', v_req.vendor_id, 'extra_key', v_req.extra_key,
    'from', v_req.status, 'to', p_to,
    'quoted_price_ngwee', coalesce(p_quoted_price_ngwee, v_req.quoted_price_ngwee)
  );
end;
$$;

revoke all on function public.vendor_extras_request_status_guard() from public, anon, authenticated;
revoke all on function public.transition_vendor_extras_request(uuid, text, uuid, text, text, bigint)
  from public, anon, authenticated;
grant execute on function public.transition_vendor_extras_request(uuid, text, uuid, text, text, bigint)
  to service_role;

-- In-app notifications: admins on a new request; the shop owner when an admin
-- moves it. Never blocks the write (same contract as 20261113130000).
create function private.in_app_from_extras_request() returns trigger
language plpgsql security definer set search_path = public, private
as $$
declare
  v_owner uuid;
  v_name text;
  v_params jsonb;
begin
  select e.name into v_name from public.vendor_extras e where e.key = new.extra_key;
  v_params := jsonb_build_object('name', left(coalesce(v_name, new.extra_key), 80));
  if tg_op = 'INSERT' then
    perform private.enqueue_admin_in_app_notification(
      'vendors.manage', 'extras_requested', v_params, '/extras',
      'extras_requested:' || new.id::text
    );
    -- Requested is also history.
    insert into public.vendor_extras_request_events
      (request_id, from_status, to_status, actor, actor_role, note)
    values (new.id, null, 'requested', new.requested_by, 'vendor', new.note);
    return null;
  end if;
  if new.status is distinct from old.status and new.status in ('quoted', 'approved', 'fulfilled', 'cancelled') then
    select v.owner_user_id into v_owner from public.vendors v where v.id = new.vendor_id;
    perform private.enqueue_in_app_notification(
      v_owner, 'vendor', 'extras_' || new.status, v_params, '/extras',
      'extras_' || new.status || ':' || new.id::text
    );
  end if;
  return null;
exception
  when others then
    raise warning 'in_app_from_extras_request skipped (sqlstate %): %', sqlstate, sqlerrm;
    return null;
end;
$$;

revoke all on function private.in_app_from_extras_request() from public, anon, authenticated;

create trigger vendor_extras_requests_in_app
  after insert or update of status on public.vendor_extras_requests
  for each row execute function private.in_app_from_extras_request();

-- ---------------------------------------------------------------------------
-- Row level security. Writes are API-only (service role). Vendors read the
-- active catalogue and their OWN shops' requests/history; admins read all.
-- ---------------------------------------------------------------------------
alter table public.vendor_extras enable row level security;
alter table public.vendor_extras_requests enable row level security;
alter table public.vendor_extras_request_events enable row level security;
alter table public.vendor_extras force row level security;
alter table public.vendor_extras_requests force row level security;
alter table public.vendor_extras_request_events force row level security;

revoke all on public.vendor_extras from public, anon, authenticated;
revoke all on public.vendor_extras_requests from public, anon, authenticated;
revoke all on public.vendor_extras_request_events from public, anon, authenticated;
grant select on public.vendor_extras to authenticated;
grant select on public.vendor_extras_requests to authenticated;
grant select on public.vendor_extras_request_events to authenticated;
grant all on public.vendor_extras to service_role;
grant all on public.vendor_extras_requests to service_role;
grant all on public.vendor_extras_request_events to service_role;

create policy vendor_extras_select
  on public.vendor_extras for select to authenticated
  using (active or public.has_role('admin'));

create policy vendor_extras_requests_select_own
  on public.vendor_extras_requests for select to authenticated
  using (
    public.has_role('admin')
    or exists (select 1 from public.vendors v
               where v.id = vendor_extras_requests.vendor_id and v.owner_user_id = (select auth.uid()))
  );

create policy vendor_extras_request_events_select_own
  on public.vendor_extras_request_events for select to authenticated
  using (
    public.has_role('admin')
    or exists (select 1 from public.vendor_extras_requests r
               join public.vendors v on v.id = r.vendor_id
               where r.id = vendor_extras_request_events.request_id
                 and v.owner_user_id = (select auth.uid()))
  );

commit;

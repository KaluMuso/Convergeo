-- W1 Multi-branch businesses (founder build queue 2026-11-15; flag `multi_branch`,
-- default OFF).
--
-- Extends the vendors model instead of duplicating it:
--   * A `vendors` row stays the STOREFRONT (= branch / shop). Everything keyed on
--     vendor_id keeps working unchanged: slug, listings, stock, orders, payout
--     MoMo (`vendors.payout_msisdn`), plan assignment (`vendor_plan_assignments`,
--     one per vendor, so every branch is billed separately), ledger accounts.
--   * `vendor_businesses` (new) is the LEGAL ENTITY: owner, legal name, PACRA
--     registration. Owner KYC is done once: a new branch inherits the business
--     owner's approved KYC tier when an admin approves the branch.
--   * `vendors.business_id` links a branch to its business. Backfill: every
--     existing vendor becomes a business (business.id = vendor.id) with one
--     primary, approved branch. A BEFORE INSERT trigger does the same for new
--     vendors created by the existing onboarding (KYC) flow.
--   * Branch location reuses `vendor_locations` (+ address, map link). Contacts
--     reuse `vendors.whatsapp_msisdn` (+ contact_phone / contact_email).
--
-- Anti-duplication (DB-enforced; the API mirrors each rule with friendly errors):
--   * PACRA number unique per business (normalised, partial unique index).
--   * Registered companies / business names need PACRA number + certificate.
--   * No PACRA number -> at most 1 shop (any time; not flag-dependent, because
--     only the flag-gated API can create a second shop).
--   * Shops per business <= plan allowance (vendor_plans.included_shops, or
--     unlimited where the plan sells extra shops as a paid add-on).
--   * With `multi_branch` on: a branch GPS must be >= platform_config
--     `branch_min_sibling_distance_m` (admin-editable, default 50 m) from its
--     sibling branches; a MoMo payout number is never shared across owners; a
--     number shared between branches of the SAME owner opens an admin review
--     flag and puts a payout hold on the branch until an admin clears it.
--   * Fuzzy duplicate scan (name trigram, phone, payout, GPS, storefront photo
--     sha256) -> `vendor_branch_flags` admin review queue.
--   * Branch onboarding status (`vendors.branch_status`) changes only through
--     `transition_vendor_branch()` (guarded state machine + history + audit).
--
-- Plans (builds on 20261114030000_vendor_plans): new ladder seeded as admin-
-- editable defaults (Free K0, Starter K49, Business K249, Chain K1,500 / 5 shops,
-- Enterprise K3,500 / 15 shops, Enterprise Plus K7,500 / unlimited; extra shop
-- add-on prices) + per-plan entitlements. Only shops and staff seats are
-- enforced now; the rest is stored for later. Money = integer ngwee. Seeds only
-- touch rows still at their 20261114030000 seed values (admin edits win).
--
-- Reversal (no pre-existing object depends on the new ones; the backfilled
-- businesses carry no data that is not derivable from vendors):
--   drop function public.create_vendor_branch(uuid, uuid, jsonb),
--     public.transition_vendor_branch(uuid, text, uuid, text),
--     public.vendor_branch_dedup_scan(uuid), public.business_shop_limit(uuid),
--     public.business_staff_seat_limit(uuid), public.business_owner_kyc(uuid),
--     public.branch_min_sibling_distance_m(), public.geo_distance_m(float8,float8,float8,float8),
--     public.normalize_zm_msisdn(text), public.multi_branch_enabled() cascade;
--   drop trigger vendors_branch_insert, vendors_branch_guard, vendors_branch_payout_guard
--     on public.vendors; drop trigger vendor_locations_branch_distance on public.vendor_locations;
--   drop table public.vendor_business_staff, public.vendor_branch_flags,
--     public.vendor_branch_events, public.vendor_branch_evidence;
--   alter table public.vendors drop column business_id, is_primary_branch, branch_kind,
--     branch_status, contact_phone, contact_email;
--   alter table public.vendor_locations drop column address, map_url;
--   alter table public.vendor_plan_assignments drop column branch_billing_role, addon_price_ngwee;
--   alter table public.vendor_plans drop column included_shops ... multi_branch_stock;
--   drop table public.vendor_businesses;
--   delete from public.vendor_plans where key in ('chain','enterprise','enterprise_plus');
--   delete from public.platform_config where key = 'branch_min_sibling_distance_m';
--   delete from public.feature_flags where flag = 'multi_branch';
begin;

insert into public.feature_flags (flag, enabled, description) values
  ('multi_branch', false,
   'Multi-branch businesses: business -> shops, branch verification queue, anti-duplication')
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  ('branch_min_sibling_distance_m', '50'::jsonb,
   'Minimum distance in metres between two branches of the same business (multi_branch).')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
create function public.multi_branch_enabled() returns boolean
language sql stable security definer set search_path = pg_catalog, public
as $$
  select coalesce((select ff.enabled from public.feature_flags ff where ff.flag = 'multi_branch'), false)
$$;

create function public.branch_min_sibling_distance_m() returns integer
language plpgsql stable security definer set search_path = pg_catalog, public
as $$
declare
  v_raw jsonb;
  v_value integer;
begin
  select pc.value into v_raw from public.platform_config pc
    where pc.key = 'branch_min_sibling_distance_m';
  begin
    v_value := (v_raw #>> '{}')::integer;
  exception when others then
    v_value := null;
  end;
  -- Fail closed to the founder default when unset or garbage.
  return coalesce(v_value, 50);
end;
$$;

-- Great-circle distance in metres (no PostGIS: ADR-R02-04-B).
create function public.geo_distance_m(
  p_lat1 double precision, p_lng1 double precision,
  p_lat2 double precision, p_lng2 double precision
) returns double precision
language sql immutable parallel safe set search_path = pg_catalog
as $$
  select 6371008.8 * 2 * asin(sqrt(
    power(sin(radians(p_lat2 - p_lat1) / 2), 2)
    + cos(radians(p_lat1)) * cos(radians(p_lat2)) * power(sin(radians(p_lng2 - p_lng1) / 2), 2)
  ))
$$;

-- E.164 digits without '+', for Zambian mobiles: 0977… / 977… / +260977… -> 260977…
create function public.normalize_zm_msisdn(p_raw text) returns text
language plpgsql immutable set search_path = pg_catalog
as $$
declare
  v_digits text := regexp_replace(coalesce(p_raw, ''), '[^0-9]', '', 'g');
begin
  if v_digits = '' then
    return null;
  end if;
  if length(v_digits) = 10 and left(v_digits, 1) = '0' then
    v_digits := '260' || substr(v_digits, 2);
  elsif length(v_digits) = 9 then
    v_digits := '260' || v_digits;
  end if;
  return v_digits;
end;
$$;

revoke all on function public.multi_branch_enabled() from public, anon;
revoke all on function public.branch_min_sibling_distance_m() from public, anon;
grant execute on function public.multi_branch_enabled() to authenticated, service_role;
grant execute on function public.branch_min_sibling_distance_m() to authenticated, service_role;
grant execute on function public.geo_distance_m(double precision, double precision, double precision, double precision)
  to authenticated, service_role;
grant execute on function public.normalize_zm_msisdn(text) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- vendor_businesses — the legal entity
-- ---------------------------------------------------------------------------
create table public.vendor_businesses (
  id uuid primary key default gen_random_uuid(),
  -- cascade: vendors.owner_user_id still restricts deleting a profile that owns a
  -- shop, so this only removes a business left with no shops.
  owner_user_id uuid not null references public.profiles (id) on delete cascade,
  legal_name text not null check (char_length(btrim(legal_name)) between 1 and 160),
  -- company / business_name = PACRA-registered; unregistered = market trader;
  -- unspecified = backfilled vendor that has not declared yet (treated as no PACRA).
  registration_type text not null default 'unspecified'
    check (registration_type in ('company', 'business_name', 'unregistered', 'unspecified')),
  -- Normalised by trigger: upper-case, no spaces.
  pacra_number text check (pacra_number is null or pacra_number ~ '^[A-Z0-9][A-Z0-9/-]{3,31}$'),
  -- Private Storage path (kyc-docs bucket), pinned under this business.
  pacra_cert_path text,
  pacra_verified_at timestamptz,
  pacra_verified_by uuid references public.profiles (id) on delete set null,
  status text not null default 'active' check (status in ('active', 'suspended')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_businesses_registered_needs_pacra check (
    registration_type not in ('company', 'business_name')
    or (pacra_number is not null and pacra_cert_path is not null)
  ),
  constraint vendor_businesses_unregistered_has_no_pacra check (
    registration_type <> 'unregistered' or pacra_number is null
  ),
  constraint vendor_businesses_cert_path_pinned check (
    pacra_cert_path is null
    or pacra_cert_path like ('businesses/' || id::text || '/%')
  )
);

comment on table public.vendor_businesses is
  'Legal entity behind one or more storefronts (vendors rows = branches). Owner KYC once; PACRA unique.';

create unique index vendor_businesses_pacra_number_key
  on public.vendor_businesses (pacra_number) where pacra_number is not null;
create index vendor_businesses_owner_user_id_idx on public.vendor_businesses (owner_user_id);

create function public.normalize_vendor_business() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
  if new.pacra_number is not null then
    new.pacra_number := nullif(upper(regexp_replace(new.pacra_number, '\s', '', 'g')), '');
  end if;
  new.legal_name := btrim(new.legal_name);
  if tg_op = 'UPDATE' and new.pacra_number is distinct from old.pacra_number then
    -- A changed PACRA number is a new claim: verification starts over.
    new.pacra_verified_at := null;
    new.pacra_verified_by := null;
  end if;
  return new;
end;
$$;

create trigger vendor_businesses_normalize
  before insert or update on public.vendor_businesses
  for each row execute function public.normalize_vendor_business();

create trigger vendor_businesses_set_updated_at
  before update on public.vendor_businesses
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- vendors (branches) + vendor_locations: additive columns
-- ---------------------------------------------------------------------------
alter table public.vendors
  add column business_id uuid references public.vendor_businesses (id) on delete restrict,
  add column is_primary_branch boolean not null default true,
  add column branch_kind text not null default 'physical'
    check (branch_kind in ('physical', 'online')),
  -- Per-branch onboarding status. Pre-existing vendors and every vendor created by
  -- the KYC onboarding flow are their business's primary branch: 'approved' (KYC
  -- covers them). Extra branches start at 'draft' and need admin verification.
  add column branch_status text not null default 'approved'
    check (branch_status in ('draft', 'pending_review', 'info_requested', 'approved', 'rejected')),
  add column contact_phone text check (contact_phone is null or contact_phone ~ '^[0-9]{9,15}$'),
  add column contact_email text
    check (contact_email is null or (char_length(contact_email) <= 254 and contact_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'));

alter table public.vendor_locations
  add column address text check (address is null or char_length(address) <= 300),
  add column map_url text
    check (map_url is null or (char_length(map_url) <= 500 and map_url ~ '^https://'));

-- Backfill: every existing vendor = a business (same id) with one primary branch.
insert into public.vendor_businesses (id, owner_user_id, legal_name, registration_type, created_at)
select v.id, v.owner_user_id, left(coalesce(nullif(btrim(v.display_name), ''), v.slug), 160),
       'unspecified', v.created_at
from public.vendors v
where v.business_id is null
on conflict (id) do nothing;

update public.vendors set business_id = id where business_id is null;

create unique index vendors_business_primary_key
  on public.vendors (business_id) where is_primary_branch;
create index vendors_business_id_idx on public.vendors (business_id);
create index vendors_payout_msisdn_norm_idx
  on public.vendors (public.normalize_zm_msisdn(payout_msisdn)) where payout_msisdn is not null;

comment on column public.vendors.business_id is
  'Legal entity (vendor_businesses) this storefront/branch belongs to. Backfilled 1:1.';
comment on column public.vendors.branch_status is
  'Branch onboarding status; changes only via transition_vendor_branch().';

-- BEFORE INSERT: attach a business; guard client inserts and branch rules.
create function public.vendor_branch_before_insert() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
  -- D1 (20261115140100): admins act through the API as service_role; a direct
  -- admin write is an ordinary client write here.
  v_privileged boolean := session_user in ('postgres', 'supabase_admin')
    or jwt_role = 'service_role';
  v_business public.vendor_businesses%rowtype;
  v_count integer;
  v_limit integer;
begin
  if not v_privileged then
    -- Clients never pick a business or a branch role; extra shops go through the
    -- flag-gated, verified branch flow in the API.
    if new.owner_user_id is distinct from auth.uid() then
      raise exception using errcode = '42501', message = 'vendor owner must be the caller';
    end if;
    if new.business_id is not null then
      raise exception using errcode = '42501', message = 'vendor business is server-controlled';
    end if;
    if exists (select 1 from public.vendors v where v.owner_user_id = new.owner_user_id) then
      raise exception using errcode = '42501', message = 'additional shops use the branch flow';
    end if;
    new.is_primary_branch := true;
    new.branch_status := 'approved';
  end if;

  if new.business_id is null then
    insert into public.vendor_businesses (id, owner_user_id, legal_name)
    values (new.id, new.owner_user_id,
            left(coalesce(nullif(btrim(new.display_name), ''), new.slug), 160))
    on conflict (id) do nothing;
    new.business_id := new.id;
    new.is_primary_branch := true;
    return new;
  end if;

  select * into v_business from public.vendor_businesses b where b.id = new.business_id for update;
  if not found then
    raise exception using errcode = '23503', message = 'vendor_business_not_found';
  end if;
  if v_business.owner_user_id <> new.owner_user_id then
    raise exception using errcode = '42501', message = 'branch_owner_mismatch';
  end if;
  if new.is_primary_branch then
    return new;
  end if;
  if new.branch_status <> 'draft' then
    raise exception using errcode = '22023', message = 'branch_must_start_as_draft';
  end if;

  select count(*) into v_count from public.vendors v
    where v.business_id = new.business_id and v.branch_status <> 'rejected';
  if v_business.pacra_number is null and v_count >= 1 then
    raise exception using errcode = 'P0001', message = 'branch_limit_unregistered';
  end if;
  v_limit := public.business_shop_limit(new.business_id);
  if v_limit is not null and v_count >= v_limit then
    raise exception using errcode = 'P0001', message = 'branch_limit_plan';
  end if;
  return new;
end;
$$;

-- BEFORE UPDATE: branch columns are server-controlled; status only via the
-- transition function; owner/business stay consistent.
create function public.vendor_branch_guard_update() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
  -- D1 (20261115140100): admins act through the API as service_role; a direct
  -- admin write is an ordinary client write here.
  v_privileged boolean := session_user in ('postgres', 'supabase_admin')
    or jwt_role = 'service_role';
begin
  if not v_privileged and (
    new.business_id is distinct from old.business_id
    or new.is_primary_branch is distinct from old.is_primary_branch
    or new.branch_kind is distinct from old.branch_kind
    or new.branch_status is distinct from old.branch_status
  ) then
    raise exception using errcode = '42501', message = 'vendor branch fields are server-controlled';
  end if;
  if new.branch_status is distinct from old.branch_status
     and coalesce(current_setting('convergeo.branch_transition', true), '') <> 'on' then
    raise exception using errcode = '22023', message = 'branch_status changes only via transition_vendor_branch';
  end if;
  if new.business_id is distinct from old.business_id then
    raise exception using errcode = '22023', message = 'branch_business_immutable';
  end if;
  return new;
end;
$$;

-- BEFORE INSERT/UPDATE OF payout_msisdn (flag on): never across owners; a
-- same-owner shared number opens a review flag and holds payouts until cleared.
create function public.vendor_branch_payout_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_norm text := public.normalize_zm_msisdn(new.payout_msisdn);
  v_sibling uuid;
begin
  if v_norm is null or not public.multi_branch_enabled() then
    return new;
  end if;
  if tg_op = 'UPDATE' and public.normalize_zm_msisdn(old.payout_msisdn) is not distinct from v_norm then
    return new;
  end if;
  if exists (
    select 1 from public.vendors v
    where public.normalize_zm_msisdn(v.payout_msisdn) = v_norm
      and v.owner_user_id <> new.owner_user_id
      and v.id <> new.id
  ) then
    raise exception using errcode = 'P0001', message = 'payout_msisdn_other_owner';
  end if;
  select v.id into v_sibling from public.vendors v
    where public.normalize_zm_msisdn(v.payout_msisdn) = v_norm
      and v.owner_user_id = new.owner_user_id
      and v.id <> new.id
    order by v.is_primary_branch desc, v.created_at
    limit 1;
  if v_sibling is not null and not exists (
    select 1 from public.vendor_branch_flags f
    where f.vendor_id = new.id and f.kind = 'payout_shared_same_owner'
      and f.matched_vendor_id = v_sibling and f.status = 'cleared'
      and f.details ->> 'payout_msisdn' = v_norm
  ) then
    -- Hold until an admin clears the shared-number review (cleared -> hold lifted by API).
    new.payout_hold_until := greatest(coalesce(new.payout_hold_until, now()), now() + interval '10 years');
  end if;
  return new;
end;
$$;

-- AFTER INSERT/UPDATE OF payout_msisdn: open the same-owner review flag (needs the row id).
create function public.vendor_branch_payout_flag() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_norm text := public.normalize_zm_msisdn(new.payout_msisdn);
  v_sibling uuid;
begin
  if v_norm is null or not public.multi_branch_enabled() then
    return null;
  end if;
  select v.id into v_sibling from public.vendors v
    where public.normalize_zm_msisdn(v.payout_msisdn) = v_norm
      and v.owner_user_id = new.owner_user_id
      and v.id <> new.id
    order by v.is_primary_branch desc, v.created_at
    limit 1;
  if v_sibling is null then
    return null;
  end if;
  insert into public.vendor_branch_flags (vendor_id, kind, matched_vendor_id, score, details)
  values (new.id, 'payout_shared_same_owner', v_sibling, 1.0,
          jsonb_build_object('payout_msisdn', v_norm))
  on conflict do nothing;
  return null;
end;
$$;

-- ---------------------------------------------------------------------------
-- Branch evidence, history, duplicate flags, staff seats
-- ---------------------------------------------------------------------------
create table public.vendor_branch_evidence (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  kind text not null check (kind in ('storefront_photo', 'premises_proof')),
  proof_type text check (proof_type is null or proof_type in ('lease', 'utility_bill', 'council_permit')),
  -- Private Storage path (kyc-docs bucket): branches/{business_id}/{vendor_id}/...
  storage_path text not null check (storage_path ~ '^branches/[0-9a-f-]{36}/[0-9a-f-]{36}/[A-Za-z0-9._-]{1,80}$'),
  content_sha256 text check (content_sha256 is null or content_sha256 ~ '^[0-9a-f]{64}$'),
  uploaded_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_branch_evidence_kind_key unique (vendor_id, kind),
  constraint vendor_branch_evidence_proof_type check (
    (kind = 'premises_proof') = (proof_type is not null)
  )
);

create index vendor_branch_evidence_sha_idx
  on public.vendor_branch_evidence (content_sha256) where content_sha256 is not null;

create trigger vendor_branch_evidence_set_updated_at
  before update on public.vendor_branch_evidence
  for each row execute function public.set_updated_at();

create table public.vendor_branch_events (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  from_status text,
  to_status text not null,
  actor uuid,
  note text check (note is null or char_length(note) <= 1000),
  created_at timestamptz not null default now()
);

create index vendor_branch_events_vendor_idx on public.vendor_branch_events (vendor_id, created_at desc);

create table public.vendor_branch_flags (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  kind text not null check (kind in (
    'name_similar', 'phone_match', 'payout_other_owner', 'payout_shared_same_owner',
    'gps_near_other_owner', 'image_duplicate'
  )),
  matched_vendor_id uuid references public.vendors (id) on delete set null,
  score numeric(4, 3) not null default 1 check (score between 0 and 1),
  details jsonb not null default '{}'::jsonb,
  status text not null default 'open' check (status in ('open', 'cleared', 'confirmed')),
  resolved_by uuid,
  resolved_at timestamptz,
  resolution_note text check (resolution_note is null or char_length(resolution_note) <= 1000),
  created_at timestamptz not null default now(),
  constraint vendor_branch_flags_resolution check (
    (status = 'open') = (resolved_at is null)
  )
);

-- One open flag per (branch, signal, match); resolved history is kept.
create unique index vendor_branch_flags_open_key
  on public.vendor_branch_flags (vendor_id, kind, coalesce(matched_vendor_id, '00000000-0000-0000-0000-000000000000'::uuid))
  where status = 'open';
create index vendor_branch_flags_status_idx on public.vendor_branch_flags (status, created_at desc);

create table public.vendor_business_staff (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.vendor_businesses (id) on delete cascade,
  user_id uuid references public.profiles (id) on delete set null,
  invite_msisdn text check (invite_msisdn is null or invite_msisdn ~ '^[0-9]{9,15}$'),
  display_name text not null check (char_length(btrim(display_name)) between 1 and 80),
  role text not null default 'staff' check (role in ('manager', 'staff')),
  -- Empty = every branch of the business.
  branch_ids uuid[] not null default '{}',
  status text not null default 'invited' check (status in ('invited', 'active', 'revoked')),
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_business_staff_identity check (user_id is not null or invite_msisdn is not null)
);

create index vendor_business_staff_business_idx on public.vendor_business_staff (business_id, status);
create unique index vendor_business_staff_msisdn_key
  on public.vendor_business_staff (business_id, invite_msisdn)
  where invite_msisdn is not null and status <> 'revoked';

create trigger vendor_business_staff_set_updated_at
  before update on public.vendor_business_staff
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Plans: entitlements + new ladder (admin-editable defaults)
-- ---------------------------------------------------------------------------
alter table public.vendor_plans
  -- Shops included in the plan (NULL = unlimited).
  add column included_shops integer default 1 check (included_shops is null or included_shops between 1 and 10000),
  -- Monthly price of each shop beyond included_shops (NULL = extra shops not sold).
  add column extra_shop_price_ngwee bigint check (extra_shop_price_ngwee is null or extra_shop_price_ngwee between 0 and 100000000),
  -- Staff seats besides the owner (NULL = unlimited).
  add column staff_seats integer default 0 check (staff_seats is null or staff_seats between 0 and 10000),
  -- Stored for later (not enforced yet).
  add column whatsapp_broadcasts_per_month integer not null default 0
    check (whatsapp_broadcasts_per_month between 0 and 10000000),
  add column integrations_level text not null default 'none'
    check (integrations_level in ('none', 'basic', 'sheets_webhooks', 'api')),
  add column ad_credit_ngwee bigint not null default 0 check (ad_credit_ngwee between 0 and 100000000),
  add column payout_speed text not null default 'standard'
    check (payout_speed in ('standard', 'fast', 'priority')),
  add column support_level text not null default 'standard'
    check (support_level in ('community', 'standard', 'priority', 'dedicated')),
  add column official_store_badge boolean not null default false,
  add column click_and_collect boolean not null default false,
  add column multi_branch_stock boolean not null default false;

comment on column public.vendor_plans.included_shops is 'Shops included (NULL = unlimited). Enforced with multi_branch.';
comment on column public.vendor_plans.extra_shop_price_ngwee is 'Add-on price per extra shop / month, ngwee; NULL = not sold.';
comment on column public.vendor_plans.staff_seats is 'Staff seats besides the owner (NULL = unlimited). Enforced with multi_branch.';

-- 08:35 founder pricing: Business and Pro merged into Business K249. Update the
-- 20261114030000 seeds only where an admin has not edited them since.
update public.vendor_plans set
  included_shops = 1, extra_shop_price_ngwee = null, staff_seats = 0,
  whatsapp_broadcasts_per_month = 0, integrations_level = 'none', ad_credit_ngwee = 0,
  payout_speed = 'standard', support_level = 'community'
where key = 'free' and price_ngwee = 0;

update public.vendor_plans set
  included_shops = 1, extra_shop_price_ngwee = 9900, staff_seats = 2,
  whatsapp_broadcasts_per_month = 100, integrations_level = 'basic', ad_credit_ngwee = 0,
  payout_speed = 'standard', support_level = 'standard', click_and_collect = true
where key = 'starter' and price_ngwee = 4900;

update public.vendor_plans set
  price_ngwee = 24900, max_listings = null, included_shops = 1, extra_shop_price_ngwee = 8900,
  staff_seats = 5, whatsapp_broadcasts_per_month = 500, integrations_level = 'sheets_webhooks',
  ad_credit_ngwee = 10000, payout_speed = 'fast', support_level = 'priority',
  click_and_collect = true, featured_slots = greatest(featured_slots, 5)
where key = 'business' and price_ngwee = 14900;

-- Pro is folded into Business: retire it (kept for any existing assignment).
update public.vendor_plans set active = false, name = 'Pro (merged into Business)'
where key = 'pro' and price_ngwee = 34900 and not is_default;

insert into public.vendor_plans
  (key, name, price_ngwee, max_listings, max_images_per_listing, featured_slots,
   analytics_depth, wholesale_tools, is_default, position,
   included_shops, extra_shop_price_ngwee, staff_seats, whatsapp_broadcasts_per_month,
   integrations_level, ad_credit_ngwee, payout_speed, support_level,
   official_store_badge, click_and_collect, multi_branch_stock)
values
  ('chain', 'Chain', 150000, null, 8, 15, 'advanced', true, false, 4,
   5, 15000, 25, 2000, 'api', 50000, 'fast', 'priority', true, true, true),
  ('enterprise', 'Enterprise', 350000, null, 8, 30, 'advanced', true, false, 5,
   15, 12000, 75, 5000, 'api', 150000, 'priority', 'dedicated', true, true, true),
  ('enterprise_plus', 'Enterprise Plus', 750000, null, 8, 60, 'advanced', true, false, 6,
   null, null, null, 15000, 'api', 400000, 'priority', 'dedicated', true, true, true)
on conflict (key) do nothing;

alter table public.vendor_plan_assignments
  -- standalone = a business's primary shop (or a single-shop vendor);
  -- included = extra shop covered by the business plan's included_shops;
  -- addon = extra shop billed at the plan's extra_shop_price_ngwee.
  add column branch_billing_role text not null default 'standalone'
    check (branch_billing_role in ('standalone', 'included', 'addon')),
  add column addon_price_ngwee bigint check (addon_price_ngwee is null or addon_price_ngwee between 0 and 100000000),
  add constraint vendor_plan_assignments_addon_price check (
    (branch_billing_role = 'addon') = (addon_price_ngwee is not null)
  );

-- ---------------------------------------------------------------------------
-- Resolvers
-- ---------------------------------------------------------------------------
-- The business plan = the primary branch's assigned plan, else the default plan.
create function public.business_plan_key(p_business_id uuid) returns text
language sql stable security definer set search_path = pg_catalog, public
as $$
  select coalesce(
    (select a.plan_key from public.vendors v
       join public.vendor_plan_assignments a on a.vendor_id = v.id
      where v.business_id = p_business_id and v.is_primary_branch
      limit 1),
    (select p.key from public.vendor_plans p where p.is_default limit 1)
  )
$$;

-- Max shops (NULL = unlimited). No PACRA number -> 1 shop.
create function public.business_shop_limit(p_business_id uuid) returns integer
language plpgsql stable security definer set search_path = pg_catalog, public
as $$
declare
  v_pacra text;
  v_included integer;
  v_extra bigint;
  v_found boolean;
begin
  select b.pacra_number into v_pacra from public.vendor_businesses b where b.id = p_business_id;
  if v_pacra is null then
    return 1;
  end if;
  select p.included_shops, p.extra_shop_price_ngwee, true into v_included, v_extra, v_found
    from public.vendor_plans p where p.key = public.business_plan_key(p_business_id);
  if not coalesce(v_found, false) then
    return 1;
  end if;
  if v_extra is not null or v_included is null then
    return null; -- extra shops are a paid add-on, or the plan is unlimited
  end if;
  return v_included;
end;
$$;

create function public.business_staff_seat_limit(p_business_id uuid) returns integer
language sql stable security definer set search_path = pg_catalog, public
as $$
  select p.staff_seats from public.vendor_plans p where p.key = public.business_plan_key(p_business_id)
$$;

-- Owner KYC is done once per business: the best approved tier on any branch.
create function public.business_owner_kyc(p_business_id uuid) returns uuid
language sql stable security definer set search_path = pg_catalog, public
as $$
  select k.id from public.kyc_records k
    join public.vendors v on v.id = k.vendor_id
   where v.business_id = p_business_id and k.status = 'approved'
   order by k.tier desc, k.updated_at desc
   limit 1
$$;

revoke all on function public.business_plan_key(uuid) from public, anon, authenticated;
revoke all on function public.business_shop_limit(uuid) from public, anon, authenticated;
revoke all on function public.business_staff_seat_limit(uuid) from public, anon, authenticated;
revoke all on function public.business_owner_kyc(uuid) from public, anon, authenticated;
grant execute on function public.business_plan_key(uuid) to service_role;
grant execute on function public.business_shop_limit(uuid) to service_role;
grant execute on function public.business_staff_seat_limit(uuid) to service_role;
grant execute on function public.business_owner_kyc(uuid) to service_role;

-- Staff seat cap (flag on).
create function public.vendor_business_staff_seat_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_limit integer;
  v_count integer;
begin
  if new.status = 'revoked' or not public.multi_branch_enabled() then
    return new;
  end if;
  if tg_op = 'UPDATE' and old.status <> 'revoked' then
    return new;
  end if;
  perform pg_advisory_xact_lock(hashtextextended('business-staff:' || new.business_id::text, 0));
  v_limit := public.business_staff_seat_limit(new.business_id);
  if v_limit is null then
    return new;
  end if;
  select count(*) into v_count from public.vendor_business_staff s
    where s.business_id = new.business_id and s.status <> 'revoked' and s.id <> new.id;
  if v_count >= v_limit then
    raise exception using errcode = 'P0001', message = 'staff_seat_limit';
  end if;
  return new;
end;
$$;

create trigger vendor_business_staff_seat_guard
  before insert or update of status on public.vendor_business_staff
  for each row execute function public.vendor_business_staff_seat_guard();

-- Sibling distance (flag on): a branch is >= N m from every other branch of its business.
create function public.vendor_location_branch_distance_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_business uuid;
  v_min integer;
  v_nearest double precision;
begin
  if not public.multi_branch_enabled() then
    return new;
  end if;
  select v.business_id into v_business from public.vendors v where v.id = new.vendor_id;
  if v_business is null then
    return new;
  end if;
  v_min := public.branch_min_sibling_distance_m();
  select min(public.geo_distance_m(new.lat, new.lng, l.lat, l.lng)) into v_nearest
    from public.vendor_locations l
    join public.vendors v on v.id = l.vendor_id
   where v.business_id = v_business and v.id <> new.vendor_id and v.branch_status <> 'rejected';
  if v_nearest is not null and v_nearest < v_min then
    raise exception using errcode = 'P0001', message = 'branch_too_close_to_sibling',
      detail = json_build_object('min_m', v_min, 'nearest_m', round(v_nearest))::text;
  end if;
  return new;
end;
$$;

create trigger vendor_locations_branch_distance
  before insert or update of lat, lng on public.vendor_locations
  for each row execute function public.vendor_location_branch_distance_guard();

-- business_shop_limit must exist before the insert trigger can call it.
create trigger vendors_branch_insert
  before insert on public.vendors
  for each row execute function public.vendor_branch_before_insert();

create trigger vendors_branch_guard
  before update on public.vendors
  for each row execute function public.vendor_branch_guard_update();

create trigger vendors_branch_payout_guard
  before insert or update of payout_msisdn on public.vendors
  for each row execute function public.vendor_branch_payout_guard();

create trigger vendors_branch_payout_flag
  after insert or update of payout_msisdn on public.vendors
  for each row execute function public.vendor_branch_payout_flag();

revoke all on function public.vendor_branch_before_insert() from public, anon, authenticated;
revoke all on function public.vendor_branch_guard_update() from public, anon, authenticated;
revoke all on function public.vendor_branch_payout_guard() from public, anon, authenticated;
revoke all on function public.vendor_branch_payout_flag() from public, anon, authenticated;
revoke all on function public.vendor_business_staff_seat_guard() from public, anon, authenticated;
revoke all on function public.vendor_location_branch_distance_guard() from public, anon, authenticated;
revoke all on function public.normalize_vendor_business() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Fuzzy duplicate scan -> vendor_branch_flags (admin review queue)
-- ---------------------------------------------------------------------------
create function public.vendor_branch_dedup_scan(p_vendor_id uuid) returns integer
language plpgsql security definer set search_path = pg_catalog, public, extensions
as $$
declare
  v_branch public.vendors%rowtype;
  v_min integer := public.branch_min_sibling_distance_m();
  v_phones text[];
  v_payout text;
  v_inserted integer := 0;
  v_n integer;
begin
  select * into v_branch from public.vendors where id = p_vendor_id;
  if not found then
    raise exception using errcode = 'P0002', message = 'vendor_not_found';
  end if;
  v_payout := public.normalize_zm_msisdn(v_branch.payout_msisdn);
  v_phones := array_remove(array[
    public.normalize_zm_msisdn(v_branch.contact_phone),
    public.normalize_zm_msisdn(v_branch.whatsapp_msisdn)
  ], null);

  -- Name: trigram similarity against OTHER owners' storefronts.
  insert into public.vendor_branch_flags (vendor_id, kind, matched_vendor_id, score, details)
  select p_vendor_id, 'name_similar', v.id,
         round(similarity(lower(v.display_name), lower(v_branch.display_name))::numeric, 3),
         jsonb_build_object('name', v_branch.display_name, 'matched_name', v.display_name)
    from public.vendors v
   where v.owner_user_id <> v_branch.owner_user_id
     and similarity(lower(v.display_name), lower(v_branch.display_name)) >= 0.6
   order by 4 desc
   limit 5
  on conflict do nothing;
  get diagnostics v_n = row_count; v_inserted := v_inserted + v_n;

  -- Phone: this branch's contact/WhatsApp number used by another owner.
  if cardinality(v_phones) > 0 then
    insert into public.vendor_branch_flags (vendor_id, kind, matched_vendor_id, score, details)
    select distinct on (v.id) p_vendor_id, 'phone_match', v.id, 1.0,
           jsonb_build_object('phone', p.phone)
      from public.vendors v
      cross join lateral unnest(array[
        public.normalize_zm_msisdn(v.contact_phone),
        public.normalize_zm_msisdn(v.whatsapp_msisdn),
        public.normalize_zm_msisdn(v.payout_msisdn)
      ]) as p(phone)
     where v.owner_user_id <> v_branch.owner_user_id
       and p.phone = any (v_phones)
    on conflict do nothing;
    get diagnostics v_n = row_count; v_inserted := v_inserted + v_n;
  end if;

  -- Payout: another owner's number (also hard-blocked by trigger) / same owner (review).
  if v_payout is not null then
    insert into public.vendor_branch_flags (vendor_id, kind, matched_vendor_id, score, details)
    select p_vendor_id,
           case when v.owner_user_id <> v_branch.owner_user_id
                then 'payout_other_owner' else 'payout_shared_same_owner' end,
           v.id, 1.0, jsonb_build_object('payout_msisdn', v_payout)
      from public.vendors v
     where v.id <> p_vendor_id
       and public.normalize_zm_msisdn(v.payout_msisdn) = v_payout
       and not exists (
         select 1 from public.vendor_branch_flags f
          where f.vendor_id = p_vendor_id and f.matched_vendor_id = v.id
            and f.kind = 'payout_shared_same_owner' and f.status = 'cleared'
            and f.details ->> 'payout_msisdn' = v_payout
       )
    on conflict do nothing;
    get diagnostics v_n = row_count; v_inserted := v_inserted + v_n;
  end if;

  -- GPS: another owner's storefront within the sibling distance (same plot/stall).
  insert into public.vendor_branch_flags (vendor_id, kind, matched_vendor_id, score, details)
  select distinct on (other.vendor_id) p_vendor_id, 'gps_near_other_owner', other.vendor_id,
         round(greatest(0, 1 - public.geo_distance_m(mine.lat, mine.lng, other.lat, other.lng) / v_min)::numeric, 3),
         jsonb_build_object('distance_m', round(public.geo_distance_m(mine.lat, mine.lng, other.lat, other.lng)))
    from public.vendor_locations mine
    join public.vendor_locations other on other.vendor_id <> mine.vendor_id
    join public.vendors ov on ov.id = other.vendor_id
   where mine.vendor_id = p_vendor_id
     and ov.owner_user_id <> v_branch.owner_user_id
     and other.lat between mine.lat - 0.01 and mine.lat + 0.01
     and other.lng between mine.lng - 0.01 and mine.lng + 0.01
     and public.geo_distance_m(mine.lat, mine.lng, other.lat, other.lng) < v_min
  on conflict do nothing;
  get diagnostics v_n = row_count; v_inserted := v_inserted + v_n;

  -- Storefront photo: identical bytes already used by any other branch.
  insert into public.vendor_branch_flags (vendor_id, kind, matched_vendor_id, score, details)
  select distinct on (other.vendor_id) p_vendor_id, 'image_duplicate', other.vendor_id, 1.0,
         jsonb_build_object('content_sha256', mine.content_sha256)
    from public.vendor_branch_evidence mine
    join public.vendor_branch_evidence other
      on other.content_sha256 = mine.content_sha256 and other.vendor_id <> mine.vendor_id
   where mine.vendor_id = p_vendor_id and mine.content_sha256 is not null
  on conflict do nothing;
  get diagnostics v_n = row_count; v_inserted := v_inserted + v_n;

  return v_inserted;
end;
$$;

revoke all on function public.vendor_branch_dedup_scan(uuid) from public, anon, authenticated;
grant execute on function public.vendor_branch_dedup_scan(uuid) to service_role;

-- ---------------------------------------------------------------------------
-- Guarded branch state machine (history row in the same transaction)
-- ---------------------------------------------------------------------------
--   draft          -> pending_review            (owner submits)
--   info_requested -> pending_review            (owner resubmits)
--   pending_review -> approved | info_requested | rejected   (admin)
-- Approval requires: no open duplicate flags, storefront photo + proof of
-- premises for physical branches, and an approved owner KYC on the business
-- (inherited: the branch gets its own approved kyc_records copy + ledger accounts).
create function public.transition_vendor_branch(
  p_vendor_id uuid, p_to text, p_actor uuid, p_note text default null
) returns jsonb
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_branch public.vendors%rowtype;
  v_kyc public.kyc_records%rowtype;
  v_kyc_id uuid;
  v_open integer;
  v_after jsonb;
begin
  select * into v_branch from public.vendors where id = p_vendor_id for update;
  if not found then
    raise exception using errcode = 'P0002', message = 'branch_not_found';
  end if;
  if v_branch.is_primary_branch then
    raise exception using errcode = '22023', message = 'branch_primary_not_reviewable';
  end if;
  if not (
    (v_branch.branch_status in ('draft', 'info_requested') and p_to = 'pending_review')
    or (v_branch.branch_status = 'pending_review' and p_to in ('approved', 'info_requested', 'rejected'))
  ) then
    raise exception using errcode = '22023', message = 'branch_invalid_transition',
      detail = json_build_object('from', v_branch.branch_status, 'to', p_to)::text;
  end if;
  if p_to in ('info_requested', 'rejected') and coalesce(btrim(p_note), '') = '' then
    raise exception using errcode = '22023', message = 'branch_note_required';
  end if;

  if p_to = 'pending_review' and v_branch.branch_kind = 'physical' and (
    select count(*) from public.vendor_branch_evidence e where e.vendor_id = p_vendor_id
  ) < 2 then
    raise exception using errcode = 'P0001', message = 'branch_evidence_required';
  end if;

  if p_to = 'approved' then
    select count(*) into v_open from public.vendor_branch_flags f
      where f.vendor_id = p_vendor_id and f.status = 'open';
    if v_open > 0 then
      raise exception using errcode = 'P0001', message = 'branch_open_flags';
    end if;
    if v_branch.branch_kind = 'physical' and (
      select count(*) from public.vendor_branch_evidence e where e.vendor_id = p_vendor_id
    ) < 2 then
      raise exception using errcode = 'P0001', message = 'branch_evidence_required';
    end if;
    v_kyc_id := public.business_owner_kyc(v_branch.business_id);
    if v_kyc_id is null then
      raise exception using errcode = 'P0001', message = 'branch_owner_kyc_required';
    end if;
    select * into v_kyc from public.kyc_records where id = v_kyc_id;
    if not exists (
      select 1 from public.kyc_records k where k.vendor_id = p_vendor_id and k.status = 'approved'
    ) then
      insert into public.kyc_records (
        vendor_id, tier, doc_storage_paths, momo_name_match, status, reviewer_notes,
        reviewed_by, reviewed_at, decision_reason
      ) values (
        p_vendor_id, v_kyc.tier, v_kyc.doc_storage_paths, v_kyc.momo_name_match, 'approved',
        'Inherited from business owner KYC ' || v_kyc.id::text,
        p_actor, now(), 'branch_inherited_owner_kyc'
      );
    end if;
  end if;

  perform set_config('convergeo.branch_transition', 'on', true);
  update public.vendors set
    branch_status = p_to,
    status = case when p_to = 'approved' and status in ('draft', 'pending_kyc') then 'active' else status end,
    kyc_tier = case when p_to = 'approved' then coalesce(v_kyc.tier, kyc_tier) else kyc_tier end
  where id = p_vendor_id;
  perform set_config('convergeo.branch_transition', 'off', true);

  if p_to = 'approved' then
    perform public.ensure_vendor_ledger_accounts(p_vendor_id);
  end if;

  insert into public.vendor_branch_events (vendor_id, from_status, to_status, actor, note)
  values (p_vendor_id, v_branch.branch_status, p_to, p_actor, nullif(btrim(p_note), ''));

  v_after := jsonb_build_object(
    'id', p_vendor_id, 'business_id', v_branch.business_id,
    'from', v_branch.branch_status, 'to', p_to,
    'inherited_kyc_record_id', case when p_to = 'approved' then v_kyc_id end
  );
  -- vendor_branch_events is the transition history (actor + note); admin
  -- decisions are additionally written to audit_log by the API's audited admin
  -- route (exactly one row per admin mutation).
  return v_after || jsonb_build_object(
    'status_before', v_branch.status, 'note', nullif(btrim(p_note), '')
  );
end;
$$;

revoke all on function public.transition_vendor_branch(uuid, text, uuid, text) from public, anon, authenticated;
grant execute on function public.transition_vendor_branch(uuid, text, uuid, text) to service_role;

-- ---------------------------------------------------------------------------
-- Atomic branch creation (draft): storefront + location + per-branch plan
-- assignment (included / paid add-on) + duplicate scan, in one transaction.
-- The insert/location/payout triggers above remain the authority for limits,
-- sibling distance and payout ownership; this function adds the preconditions.
-- ---------------------------------------------------------------------------
create function public.create_vendor_branch(
  p_business_id uuid, p_owner uuid, p_payload jsonb
) returns jsonb
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
  v_business public.vendor_businesses%rowtype;
  v_plan public.vendor_plans%rowtype;
  v_count integer;
  v_role text;
  v_price bigint;
  v_kind text := coalesce(p_payload ->> 'branch_kind', 'physical');
  v_base text := p_payload ->> 'slug';
  v_slug text;
  v_n integer := 1;
  v_id uuid := gen_random_uuid();
  v_flags integer;
begin
  if not public.multi_branch_enabled() then
    raise exception using errcode = 'P0001', message = 'multi_branch_disabled';
  end if;
  select * into v_business from public.vendor_businesses b where b.id = p_business_id for update;
  if not found or v_business.owner_user_id <> p_owner then
    raise exception using errcode = 'P0002', message = 'business_not_found';
  end if;
  if v_business.status <> 'active' then
    raise exception using errcode = 'P0001', message = 'business_suspended';
  end if;
  if public.business_owner_kyc(p_business_id) is null then
    raise exception using errcode = 'P0001', message = 'branch_owner_kyc_required';
  end if;
  if v_kind = 'physical' and (p_payload ->> 'lat' is null or p_payload ->> 'lng' is null
                              or coalesce(btrim(p_payload ->> 'landmark'), '') = '') then
    raise exception using errcode = '22023', message = 'branch_location_required';
  end if;
  if v_base is null or v_base !~ '^[a-z0-9][a-z0-9-]{1,70}$' then
    raise exception using errcode = '22023', message = 'branch_slug_invalid';
  end if;

  select * into v_plan from public.vendor_plans p where p.key = public.business_plan_key(p_business_id);
  select count(*) into v_count from public.vendors v
    where v.business_id = p_business_id and v.branch_status <> 'rejected';
  if v_plan.included_shops is null or v_count < v_plan.included_shops then
    v_role := 'included';
    v_price := null;
  else
    v_role := 'addon';
    v_price := v_plan.extra_shop_price_ngwee; -- NULL here => insert trigger raises branch_limit_plan
  end if;

  v_slug := v_base;
  while exists (select 1 from public.vendors v where v.slug = v_slug) loop
    v_n := v_n + 1;
    v_slug := left(v_base, 66) || '-' || v_n::text;
  end loop;

  insert into public.vendors (
    id, owner_user_id, business_id, is_primary_branch, branch_status, branch_kind, status,
    slug, display_name, description, contact_phone, contact_email, whatsapp_msisdn,
    payout_msisdn, payout_rail
  ) values (
    v_id, p_owner, p_business_id, false, 'draft', v_kind, 'draft',
    v_slug, btrim(p_payload ->> 'display_name'), nullif(btrim(p_payload ->> 'description'), ''),
    public.normalize_zm_msisdn(p_payload ->> 'contact_phone'),
    nullif(lower(btrim(p_payload ->> 'contact_email')), ''),
    public.normalize_zm_msisdn(p_payload ->> 'whatsapp_msisdn'),
    public.normalize_zm_msisdn(p_payload ->> 'payout_msisdn'),
    p_payload ->> 'payout_rail'
  );

  if p_payload ->> 'lat' is not null and p_payload ->> 'lng' is not null then
    insert into public.vendor_locations (vendor_id, lat, lng, landmark, hours, address, map_url)
    values (
      v_id, (p_payload ->> 'lat')::double precision, (p_payload ->> 'lng')::double precision,
      btrim(p_payload ->> 'landmark'), coalesce(p_payload -> 'hours', '{}'::jsonb),
      nullif(btrim(p_payload ->> 'address'), ''), nullif(btrim(p_payload ->> 'map_url'), '')
    );
  end if;

  insert into public.vendor_plan_assignments (
    vendor_id, plan_key, source, branch_billing_role, addon_price_ngwee, assigned_by, note
  ) values (
    v_id, v_plan.key, 'subscription', v_role, v_price, p_owner, 'branch of business ' || p_business_id::text
  );

  v_flags := public.vendor_branch_dedup_scan(v_id);

  insert into public.vendor_branch_events (vendor_id, from_status, to_status, actor, note)
  values (v_id, null, 'draft', p_owner, null);

  return jsonb_build_object(
    'id', v_id, 'slug', v_slug, 'business_id', p_business_id, 'plan_key', v_plan.key,
    'branch_billing_role', v_role, 'addon_price_ngwee', v_price, 'flags_opened', v_flags
  );
end;
$$;

revoke all on function public.create_vendor_branch(uuid, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.create_vendor_branch(uuid, uuid, jsonb) to service_role;

-- ---------------------------------------------------------------------------
-- Row level security. Every write is API-only (service role). Owners read their
-- own businesses, evidence, history and staff; duplicate flags are admin-only
-- (they name other owners' shops). Anon: no grant.
-- ---------------------------------------------------------------------------
alter table public.vendor_businesses enable row level security;
alter table public.vendor_branch_evidence enable row level security;
alter table public.vendor_branch_events enable row level security;
alter table public.vendor_branch_flags enable row level security;
alter table public.vendor_business_staff enable row level security;
alter table public.vendor_businesses force row level security;
alter table public.vendor_branch_evidence force row level security;
alter table public.vendor_branch_events force row level security;
alter table public.vendor_branch_flags force row level security;
alter table public.vendor_business_staff force row level security;

revoke all on public.vendor_businesses from public, anon, authenticated;
revoke all on public.vendor_branch_evidence from public, anon, authenticated;
revoke all on public.vendor_branch_events from public, anon, authenticated;
revoke all on public.vendor_branch_flags from public, anon, authenticated;
revoke all on public.vendor_business_staff from public, anon, authenticated;
grant select on public.vendor_businesses to authenticated;
grant select on public.vendor_branch_evidence to authenticated;
grant select on public.vendor_branch_events to authenticated;
grant select on public.vendor_branch_flags to authenticated;
grant select on public.vendor_business_staff to authenticated;
grant all on public.vendor_businesses to service_role;
grant all on public.vendor_branch_evidence to service_role;
grant all on public.vendor_branch_events to service_role;
grant all on public.vendor_branch_flags to service_role;
grant all on public.vendor_business_staff to service_role;

create policy vendor_businesses_select_own
  on public.vendor_businesses for select to authenticated
  using (owner_user_id = (select auth.uid()) or public.has_role('admin'));

create policy vendor_branch_evidence_select_own
  on public.vendor_branch_evidence for select to authenticated
  using (
    public.has_role('admin')
    or exists (select 1 from public.vendors v
               where v.id = vendor_branch_evidence.vendor_id and v.owner_user_id = (select auth.uid()))
  );

create policy vendor_branch_events_select_own
  on public.vendor_branch_events for select to authenticated
  using (
    public.has_role('admin')
    or exists (select 1 from public.vendors v
               where v.id = vendor_branch_events.vendor_id and v.owner_user_id = (select auth.uid()))
  );

create policy vendor_branch_flags_select_admin
  on public.vendor_branch_flags for select to authenticated
  using (public.has_role('admin'));

create policy vendor_business_staff_select_own
  on public.vendor_business_staff for select to authenticated
  using (
    public.has_role('admin')
    or exists (select 1 from public.vendor_businesses b
               where b.id = vendor_business_staff.business_id and b.owner_user_id = (select auth.uid()))
  );

commit;

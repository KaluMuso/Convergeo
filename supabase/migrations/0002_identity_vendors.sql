-- M03-P01: Identity, vendors & KYC schema (FK root for the domain model).

-- ---------------------------------------------------------------------------
-- Shared triggers
-- ---------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  phone text,
  display_name text,
  locale text not null default 'en',
  notif_prefs jsonb not null default '{}'::jsonb,
  dpa_consent_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row
  execute function public.set_updated_at();

create table public.user_roles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  role text not null check (role in ('customer', 'vendor', 'admin')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint user_roles_user_id_role_key unique (user_id, role)
);

create index user_roles_user_id_idx on public.user_roles (user_id);

create trigger user_roles_set_updated_at
  before update on public.user_roles
  for each row
  execute function public.set_updated_at();

-- Contract helper for later pebbles: role checks with pinned search_path.
create or replace function public.has_role(required_role text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$ select exists(select 1 from user_roles where user_id = auth.uid() and role = required_role) $$;

create table public.vendors (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.profiles (id) on delete restrict,
  slug text not null unique,
  display_name text not null,
  description text,
  logo_url text,
  status text not null default 'draft'
    check (status in ('draft', 'pending_kyc', 'active', 'suspended')),
  kyc_tier int check (kyc_tier in (1, 2, 3)),
  preferred_badge boolean not null default false,
  caps_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index vendors_slug_idx on public.vendors (slug);
create index vendors_status_idx on public.vendors (status);

create trigger vendors_set_updated_at
  before update on public.vendors
  for each row
  execute function public.set_updated_at();

create table public.vendor_locations (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  lat double precision not null,
  lng double precision not null,
  landmark text not null,
  hours jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger vendor_locations_set_updated_at
  before update on public.vendor_locations
  for each row
  execute function public.set_updated_at();

create table public.kyc_records (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  tier int not null check (tier in (1, 2, 3)),
  doc_storage_paths text[] not null default '{}',
  momo_name_match jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'rejected')),
  reviewer_notes text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index kyc_records_vendor_id_status_idx on public.kyc_records (vendor_id, status);

create trigger kyc_records_set_updated_at
  before update on public.kyc_records
  for each row
  execute function public.set_updated_at();

-- Owners must not mutate vendor lifecycle fields via PostgREST; admins/service bypass.
create or replace function public.guard_vendor_status_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.status is distinct from old.status
    or new.kyc_tier is distinct from old.kyc_tier then
    raise exception 'vendor status and kyc_tier are server-controlled';
  end if;

  return new;
end;
$$;

create trigger vendors_guard_status_update
  before update on public.vendors
  for each row
  execute function public.guard_vendor_status_update();

-- Owners cannot change immutable profile keys or self-soft-delete via PostgREST.
create or replace function public.guard_profile_owner_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  jwt_role text := coalesce(auth.jwt() ->> 'role', '');
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  if jwt_role = 'service_role' or public.has_role('admin') then
    return new;
  end if;

  if new.id is distinct from old.id
    or new.deleted_at is distinct from old.deleted_at then
    raise exception 'profile id and deleted_at are server-controlled';
  end if;

  return new;
end;
$$;

create trigger profiles_guard_owner_update
  before update on public.profiles
  for each row
  execute function public.guard_profile_owner_update();

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.profiles enable row level security;
alter table public.user_roles enable row level security;
alter table public.vendors enable row level security;
alter table public.vendor_locations enable row level security;
alter table public.kyc_records enable row level security;

alter table public.profiles force row level security;
alter table public.user_roles force row level security;
alter table public.vendors force row level security;
alter table public.vendor_locations force row level security;
alter table public.kyc_records force row level security;

-- profiles: owner read/update live row; admins full access.
create policy profiles_owner_select
  on public.profiles
  for select
  to authenticated
  using (
    id = (select auth.uid())
    and deleted_at is null
  );

comment on policy profiles_owner_select on public.profiles is
  'Authenticated users may read their own profile while it is not soft-deleted.';

create policy profiles_owner_update
  on public.profiles
  for update
  to authenticated
  using (
    id = (select auth.uid())
    and deleted_at is null
  )
  with check (
    id = (select auth.uid())
    and deleted_at is null
  );

comment on policy profiles_owner_update on public.profiles is
  'Owners may update their own live profile; id/deleted_at changes are blocked by trigger.';

create policy profiles_admin_all
  on public.profiles
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy profiles_admin_all on public.profiles is
  'Platform admins may read and mutate every profile row.';

-- user_roles: intentionally no client policies — service-role / migrations only.
comment on table public.user_roles is
  'Role assignments are server-writable only; RLS enabled with zero client policies.';

-- vendors: public read for active storefronts; owners manage their draft rows sans lifecycle fields.
create policy vendors_public_active_select
  on public.vendors
  for select
  using (status = 'active');

comment on policy vendors_public_active_select on public.vendors is
  'Anonymous and authenticated clients may read vendors that are publicly active.';

create policy vendors_owner_select
  on public.vendors
  for select
  to authenticated
  using (owner_user_id = (select auth.uid()));

comment on policy vendors_owner_select on public.vendors is
  'Owners may read their vendor rows in any lifecycle status.';

create policy vendors_owner_insert
  on public.vendors
  for insert
  to authenticated
  with check (owner_user_id = (select auth.uid()));

comment on policy vendors_owner_insert on public.vendors is
  'Authenticated users may create vendor rows they own (default status draft).';

create policy vendors_owner_update
  on public.vendors
  for update
  to authenticated
  using (owner_user_id = (select auth.uid()))
  with check (owner_user_id = (select auth.uid()));

comment on policy vendors_owner_update on public.vendors is
  'Owners may update display fields; status/kyc_tier guarded by trigger.';

create policy vendors_admin_all
  on public.vendors
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy vendors_admin_all on public.vendors is
  'Platform admins may manage every vendor row including lifecycle fields.';

-- vendor_locations: mirror vendor visibility (active public, owner always, admin all).
create policy vendor_locations_public_active_select
  on public.vendor_locations
  for select
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.status = 'active'
    )
  );

comment on policy vendor_locations_public_active_select on public.vendor_locations is
  'Locations are public only when the parent vendor is active.';

create policy vendor_locations_owner_select
  on public.vendor_locations
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy vendor_locations_owner_select on public.vendor_locations is
  'Owners may read locations for their vendors regardless of status.';

create policy vendor_locations_owner_insert
  on public.vendor_locations
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy vendor_locations_owner_update
  on public.vendor_locations
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy vendor_locations_owner_delete
  on public.vendor_locations
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy vendor_locations_owner_insert on public.vendor_locations is
  'Owners may create locations for vendors they own.';
comment on policy vendor_locations_owner_update on public.vendor_locations is
  'Owners may update locations for vendors they own.';
comment on policy vendor_locations_owner_delete on public.vendor_locations is
  'Owners may delete locations for vendors they own.';

create policy vendor_locations_admin_all
  on public.vendor_locations
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy vendor_locations_admin_all on public.vendor_locations is
  'Platform admins may manage every vendor location.';

-- kyc_records: vendor-owner read only; never public; admin full access.
create policy kyc_records_owner_select
  on public.kyc_records
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = kyc_records.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy kyc_records_owner_select on public.kyc_records is
  'Vendor owners may read their own KYC submissions; no public access.';

create policy kyc_records_admin_all
  on public.kyc_records
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy kyc_records_admin_all on public.kyc_records is
  'Platform admins may review and mutate KYC records.';

-- API roles need table privileges; RLS policies enforce authorization.
grant select, insert, update, delete on table public.profiles to authenticated, service_role;
grant select, insert, update, delete on table public.user_roles to authenticated, service_role;
grant select, insert, update, delete on table public.vendors to authenticated, service_role;
grant select, insert, update, delete on table public.vendor_locations to authenticated, service_role;
grant select, insert, update, delete on table public.kyc_records to authenticated, service_role;

grant select on table public.profiles to anon;
grant select on table public.vendors to anon;
grant select on table public.vendor_locations to anon;
grant select on table public.kyc_records to anon;

grant execute on function public.has_role(text) to authenticated, anon, service_role;

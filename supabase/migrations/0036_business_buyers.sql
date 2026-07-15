-- FIX (strategy alignment): verified business-buyer model that gates B2B wholesale.
--
-- The business-pipeline strategy requires wholesale pricing AND wholesale discovery
-- to stay hidden until a PACRA-verified business enables "business mode". The prior
-- build applied wholesale/MOQ pricing based SOLELY on the listing (see
-- services/api/app/services/cart/merge.py) and exposed a public wholesale feed,
-- leaking B2B mechanics to ordinary consumers.
--
-- This adds the buyer-side business identity + a verification lifecycle, plus a
-- helper the API uses to gate every wholesale entry point (discovery, cart,
-- checkout). It is deliberately separate from vendor KYC (kyc_records is the
-- SELLER's identity; this is the BUYER's).

-- ---------------------------------------------------------------------------
-- Table
-- ---------------------------------------------------------------------------
create table public.business_buyers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references public.profiles (id) on delete cascade,
  legal_name text not null,
  registration_no text not null,            -- PACRA business registration number
  tpin text,                                -- ZRA TPIN (optional at apply time)
  status text not null default 'pending'
    check (status in ('pending', 'verified', 'rejected', 'suspended')),
  reviewer_notes text,
  verified_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index business_buyers_user_id_idx on public.business_buyers (user_id);
create index business_buyers_status_idx on public.business_buyers (status);

create trigger business_buyers_set_updated_at
  before update on public.business_buyers
  for each row
  execute function public.set_updated_at();

comment on table public.business_buyers is
  'Buyer-side B2B identity. status=verified unlocks wholesale (see is_verified_business). Distinct from vendor kyc_records.';

-- ---------------------------------------------------------------------------
-- Guard: status/verified_at are server-controlled; owners never self-verify.
-- Mirrors public.guard_vendor_status_update (0002).
-- ---------------------------------------------------------------------------
create or replace function public.guard_business_buyer_status_update()
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
    or new.verified_at is distinct from old.verified_at
    or new.user_id is distinct from old.user_id then
    raise exception 'business_buyer status, verified_at and user_id are server-controlled';
  end if;

  return new;
end;
$$;

create trigger business_buyers_guard_status_update
  before update on public.business_buyers
  for each row
  execute function public.guard_business_buyer_status_update();

-- ---------------------------------------------------------------------------
-- Eligibility helper (mirrors public.has_role): verified business buyer?
-- ---------------------------------------------------------------------------
create or replace function public.is_verified_business(uid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists(
    select 1
    from public.business_buyers
    where user_id = uid
      and status = 'verified'
  );
$$;

comment on function public.is_verified_business(uuid) is
  'True when the given user has a verified business_buyers row — the B2B wholesale eligibility gate.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------
alter table public.business_buyers enable row level security;
alter table public.business_buyers force row level security;

create policy business_buyers_owner_select
  on public.business_buyers
  for select
  to authenticated
  using (user_id = (select auth.uid()));

comment on policy business_buyers_owner_select on public.business_buyers is
  'Authenticated users may read their own business-buyer application.';

create policy business_buyers_owner_insert
  on public.business_buyers
  for insert
  to authenticated
  with check (
    user_id = (select auth.uid())
    and status = 'pending'
  );

comment on policy business_buyers_owner_insert on public.business_buyers is
  'Users may create their own application; status is pinned to pending (no self-verify).';

create policy business_buyers_owner_update
  on public.business_buyers
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

comment on policy business_buyers_owner_update on public.business_buyers is
  'Owners may edit their application details; status/verified_at changes blocked by trigger.';

create policy business_buyers_admin_all
  on public.business_buyers
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy business_buyers_admin_all on public.business_buyers is
  'Platform admins may review, verify, reject and suspend business buyers.';

-- ---------------------------------------------------------------------------
-- API grants (RLS enforces authorization)
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on table public.business_buyers to authenticated, service_role;

grant execute on function public.is_verified_business(uuid) to authenticated, anon, service_role;

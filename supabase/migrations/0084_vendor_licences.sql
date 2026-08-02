-- R02-P12 — regulator licences and their expiry.
--
-- Some categories cannot be sold honestly without a licence: pharmacy,
-- agro-chemicals, alcohol, certain foods, financial services. The platform has
-- KYC tiers (kyc_records, 0056) but no notion of a category-specific regulator
-- licence that EXPIRES.
--
-- THE CENTRAL RULE: validity is DERIVED, never stored.
--
--   valid  ==  status = 'verified'  AND  expires_on >= current_date
--
-- There is deliberately no `is_valid` column and no "mark expired" job. A
-- stored boolean is only as true as the last time something remembered to
-- update it, and an expired licence still displaying a verified badge is the
-- platform vouching for something it has not checked — worse than showing no
-- badge at all. Deriving it means the badge disappears at midnight on its own,
-- with nothing scheduled and nothing to fail.
--
-- Mirrors the KYC posture: status is server-controlled by a guard trigger,
-- documents live in private storage, and every decision is auditable.

create table if not exists public.vendor_licences (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  regulated_class text not null,
  regulator text not null,
  licence_number text not null,
  issued_on date,
  expires_on date not null,
  document_path text,
  status text not null default 'pending'
    check (status in ('pending', 'verified', 'rejected', 'revoked')),
  reviewer_notes text,
  verified_by uuid references auth.users (id),
  verified_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint vendor_licences_dates_ordered
    check (issued_on is null or expires_on >= issued_on)
);

comment on table public.vendor_licences is
  'Regulator licences per regulated class. Validity is DERIVED (verified AND expires_on >= current_date) — never stored, so a lapsed licence stops vouching for itself with nothing scheduled.';
comment on column public.vendor_licences.licence_number is
  'Commercially sensitive: never log in full.';

-- One live licence per vendor per regulated class. Revoked and rejected rows
-- are excluded so a vendor can re-apply after a refusal without first deleting
-- the evidence that they were refused.
create unique index if not exists vendor_licences_one_live_per_class
  on public.vendor_licences (vendor_id, regulated_class)
  where status in ('pending', 'verified');

create index if not exists vendor_licences_expiry_idx
  on public.vendor_licences (expires_on)
  where status = 'verified';

drop trigger if exists vendor_licences_set_updated_at on public.vendor_licences;
create trigger vendor_licences_set_updated_at
  before update on public.vendor_licences
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Status is server-controlled. Mirrors guard_vendor_status_update (0002) and
-- guard_business_buyer_status_update (0038).
-- ---------------------------------------------------------------------------
create or replace function public.guard_vendor_licence_status_update()
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
    or new.verified_by is distinct from old.verified_by
    or new.verified_at is distinct from old.verified_at
    or new.vendor_id is distinct from old.vendor_id then
    raise exception
      'vendor_licence status, verified_by, verified_at and vendor_id are server-controlled';
  end if;

  return new;
end;
$$;

drop trigger if exists vendor_licences_guard_status_update on public.vendor_licences;
create trigger vendor_licences_guard_status_update
  before update on public.vendor_licences
  for each row
  execute function public.guard_vendor_licence_status_update();

-- ---------------------------------------------------------------------------
-- Derived validity — the only way anything should ask "is this licence good?"
-- ---------------------------------------------------------------------------
create or replace function public.vendor_licence_is_valid(p_vendor_id uuid, p_class text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.vendor_licences l
    where l.vendor_id = p_vendor_id
      and l.regulated_class = p_class
      and l.status = 'verified'
      and l.expires_on >= current_date
  );
$$;

comment on function public.vendor_licence_is_valid(uuid, text) is
  'Derived licence validity. Returns false the moment a licence expires, with no job to run and nothing to forget.';

revoke all on function public.vendor_licence_is_valid(uuid, text) from public;
grant execute on function public.vendor_licence_is_valid(uuid, text) to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.vendor_licences enable row level security;
alter table public.vendor_licences force row level security;

-- No public SELECT policy: a licence row carries the licence NUMBER and the
-- reviewer's notes, neither of which is public information. The customer-facing
-- surface is the derived badge via vendor_licence_is_valid(), which discloses a
-- boolean and nothing else.
drop policy if exists vendor_licences_owner_select on public.vendor_licences;
create policy vendor_licences_owner_select
  on public.vendor_licences
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = vendor_licences.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  );

drop policy if exists vendor_licences_owner_insert on public.vendor_licences;
create policy vendor_licences_owner_insert
  on public.vendor_licences
  for insert
  to authenticated
  with check (
    status = 'pending'
    and exists (
      select 1 from public.vendors v
      where v.id = vendor_licences.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

drop policy if exists vendor_licences_owner_update on public.vendor_licences;
create policy vendor_licences_owner_update
  on public.vendor_licences
  for update
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = vendor_licences.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
    or public.has_role('admin')
  );

comment on policy vendor_licences_owner_insert on public.vendor_licences is
  'A vendor may apply; status is pinned to pending, so no self-verification.';

revoke all on public.vendor_licences from anon, authenticated;
grant select, insert, update on public.vendor_licences to authenticated;

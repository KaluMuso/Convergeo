-- 0093: Regulator licence expiry enforcement — schema + vendor compliance suspension.
--
-- Adds explicit ``expiry_date`` / ``license_body`` columns on vendor_licences
-- (alongside legacy ``expires_on`` / ``regulator``), and a new vendor lifecycle
-- status ``suspended_compliance`` for automated sweeper enforcement.

-- ---------------------------------------------------------------------------
-- 1. license_body enum (Zambia regulators)
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'license_body') then
    create type public.license_body as enum (
      'PACRA',
      'ZAMRA',
      'HPCZ',
      'ZIEA',
      'RTSA',
      'ZEMA',
      'ERB',
      'WARMA',
      'TCZ',
      'OTHER'
    );
  end if;
end
$$;

comment on type public.license_body is
  'Zambia regulator bodies for vendor_licences.license_body (PACRA, ZAMRA, HPCZ, etc.).';

-- ---------------------------------------------------------------------------
-- 2. vendor_licences: expiry_date + license_body
-- ---------------------------------------------------------------------------
alter table public.vendor_licences
  add column if not exists expiry_date date generated always as (expires_on) stored;

alter table public.vendor_licences
  add column if not exists license_body public.license_body;

comment on column public.vendor_licences.expiry_date is
  'Canonical expiry date (mirrors expires_on). Used by compliance sweepers.';
comment on column public.vendor_licences.license_body is
  'Regulator enum (PACRA, ZAMRA, HPCZ, ZIEA, …). Preferred over free-text regulator.';

-- Best-effort backfill from legacy regulator text.
update public.vendor_licences
set license_body = case
  when upper(regulator) like '%PACRA%' then 'PACRA'::public.license_body
  when upper(regulator) like '%ZAMRA%' then 'ZAMRA'::public.license_body
  when upper(regulator) like '%HPCZ%' then 'HPCZ'::public.license_body
  when upper(regulator) like '%ZIEA%' then 'ZIEA'::public.license_body
  when upper(regulator) like '%RTSA%' then 'RTSA'::public.license_body
  when upper(regulator) like '%ZEMA%' then 'ZEMA'::public.license_body
  when upper(regulator) like '%ERB%' then 'ERB'::public.license_body
  when upper(regulator) like '%WARMA%' then 'WARMA'::public.license_body
  when upper(regulator) like '%TCZ%'
    or upper(regulator) like '%TOURISM%' then 'TCZ'::public.license_body
  else 'OTHER'::public.license_body
end
where license_body is null;

create index if not exists vendor_licences_expiry_date_idx
  on public.vendor_licences (expiry_date)
  where status = 'verified';

-- Keep derived validity aligned with expiry_date / expires_on.
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
      and l.expiry_date >= current_date
  );
$$;

-- ---------------------------------------------------------------------------
-- 3. vendors.status: add suspended_compliance
-- ---------------------------------------------------------------------------
alter table public.vendors
  drop constraint if exists vendors_status_check;

alter table public.vendors
  add constraint vendors_status_check
  check (status in (
    'draft',
    'pending_kyc',
    'active',
    'suspended',
    'suspended_compliance'
  ));

comment on constraint vendors_status_check on public.vendors is
  'Vendor lifecycle including suspended_compliance for expired regulator licences.';

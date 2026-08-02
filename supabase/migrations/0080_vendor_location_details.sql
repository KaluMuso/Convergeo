-- R02-P07 — vendor branches: label, structured address, phone, primary, status.
--
-- `vendor_locations` has existed since 0002 with lat/lng/landmark/hours, and is
-- already joined by seven routers (catalog, directory, products, vendor_profile,
-- comparison, checkout, events_public). This migration EXTENDS it. Replacing it
-- with a new "branches" table would have orphaned every one of those call sites
-- for no gain.
--
-- Zambia guardrail (CLAUDE.md): landmark + GPS is the primary addressing mode,
-- not street number. `landmark` therefore stays NOT NULL and the structured
-- fields are all nullable — they refine an address, they never replace it.
--
-- Additive only. Existing rows keep working untouched: every new column is
-- nullable or carries a default that reproduces today's behaviour.

-- ---------------------------------------------------------------------------
-- Columns
-- ---------------------------------------------------------------------------
alter table public.vendor_locations
  -- Human name for the branch: "Main shop", "Kabwata stall". Null for the
  -- single-location vendors that predate this migration.
  add column if not exists label text,
  add column if not exists area text,
  add column if not exists street text,
  add column if not exists city text,
  add column if not exists province text,
  -- Branch contact line. Deliberately NOT vendors.whatsapp_msisdn (0046),
  -- which is the storefront's public WhatsApp number: a vendor closing one
  -- branch must not blank the number customers use to reach the business.
  -- Same reasoning D35 applied when it refused to overload that column for
  -- intake identity.
  add column if not exists phone_e164 text,
  add column if not exists is_primary boolean not null default false,
  add column if not exists status text not null default 'active';

-- ---------------------------------------------------------------------------
-- Constraints
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'vendor_locations_status_check'
  ) then
    alter table public.vendor_locations
      add constraint vendor_locations_status_check
      check (status in ('active', 'closed'));
  end if;

  -- E.164, Zambia-shaped but not Zambia-locked: a vendor may legitimately list
  -- a foreign line. Validated here as well as in the API because a constraint
  -- cannot be bypassed by the next endpoint someone writes.
  if not exists (
    select 1 from pg_constraint where conname = 'vendor_locations_phone_e164_check'
  ) then
    alter table public.vendor_locations
      add constraint vendor_locations_phone_e164_check
      check (phone_e164 is null or phone_e164 ~ '^\+[1-9][0-9]{7,14}$');
  end if;

  -- A label, where present, is unique per vendor: two branches both called
  -- "Main shop" are a dispatch error waiting to happen.
  if not exists (
    select 1 from pg_constraint where conname = 'vendor_locations_label_len_check'
  ) then
    alter table public.vendor_locations
      add constraint vendor_locations_label_len_check
      check (label is null or char_length(btrim(label)) between 1 and 80);
  end if;
end
$$;

-- At most ONE primary branch per vendor. A partial unique index rather than a
-- trigger: the database refuses the second primary outright, so no application
-- path — present or future — can produce an ambiguous "where do I collect?".
create unique index if not exists vendor_locations_one_primary_per_vendor
  on public.vendor_locations (vendor_id)
  where is_primary;

create index if not exists vendor_locations_vendor_status_idx
  on public.vendor_locations (vendor_id, status);

comment on column public.vendor_locations.label is
  'Branch name shown to customers ("Main shop"). Null for legacy single-location vendors.';
comment on column public.vendor_locations.phone_e164 is
  'Branch contact number. NOT the storefront WhatsApp number (vendors.whatsapp_msisdn, 0046).';
comment on column public.vendor_locations.is_primary is
  'Exactly one branch per vendor may be primary (partial unique index).';
comment on column public.vendor_locations.status is
  'active | closed. Closing hides a branch from public reads without deleting its history.';

-- ---------------------------------------------------------------------------
-- Public visibility: a closed branch disappears from public reads.
-- ---------------------------------------------------------------------------
-- The existing public policy only checks that the parent vendor is active, so
-- without this a branch marked `closed` would keep showing on the storefront —
-- and sending customers to a shut door is worse than showing nothing.
-- Owners keep seeing their own closed branches via vendor_locations_owner_select,
-- which is untouched.
drop policy if exists vendor_locations_public_active_select on public.vendor_locations;

create policy vendor_locations_public_active_select
  on public.vendor_locations
  for select
  using (
    status = 'active'
    and exists (
      select 1
      from public.vendors v
      where v.id = vendor_locations.vendor_id
        and v.status = 'active'
    )
  );

comment on policy vendor_locations_public_active_select on public.vendor_locations is
  'Locations are public only when the branch is active AND the parent vendor is active.';

-- ---------------------------------------------------------------------------
-- Backfill: promote each vendor's existing (single) location to primary so the
-- "primary branch" concept is never empty for a vendor that already had one.
-- Deterministic — oldest row wins — so a replay produces the same result.
-- ---------------------------------------------------------------------------
with ranked as (
  select id, row_number() over (partition by vendor_id order by created_at, id) as rn
  from public.vendor_locations
)
update public.vendor_locations vl
set is_primary = true
from ranked
where ranked.id = vl.id
  and ranked.rn = 1
  and not exists (
    select 1
    from public.vendor_locations other
    where other.vendor_id = vl.vendor_id
      and other.is_primary
  );

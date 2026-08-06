-- Listing/service-anchored B2B RFQ threads with financial payload (quote in ngwee).
--
-- Distinct from:
--   * enquiry_threads (0082) — pre-transaction messaging, no money columns
--   * jobs/job_quotes (0004) — category broadcast RFQ for services marketplace
--
-- One customer ↔ one vendor negotiation on a specific listing or service listing.
-- Money is integer ngwee; quote validity is server-controlled.

create table if not exists public.rfq_threads (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references auth.users (id) on delete cascade,
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  listing_id uuid references public.vendor_listings (id) on delete restrict,
  service_id uuid references public.services (id) on delete restrict,
  requested_details text not null
    check (char_length(btrim(requested_details)) between 1 and 4000),
  status text not null default 'pending'
    check (status in ('pending', 'quoted', 'accepted', 'rejected')),
  quote_price_ngwee bigint check (quote_price_ngwee is null or quote_price_ngwee > 0),
  quote_valid_until timestamptz,
  quoted_at timestamptz,
  last_message_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint rfq_threads_subject_check check (
    (listing_id is not null and service_id is null)
    or (listing_id is null and service_id is not null)
  ),
  constraint rfq_threads_quote_when_quoted check (
    status not in ('quoted', 'accepted')
    or (
      quote_price_ngwee is not null
      and quote_valid_until is not null
      and quoted_at is not null
    )
  )
);

comment on table public.rfq_threads is
  '1:1 customer↔vendor RFQ on a listing or service. Carries formal quote payload (ngwee + valid_until).';

create unique index if not exists rfq_threads_one_open_per_listing
  on public.rfq_threads (customer_id, listing_id)
  where listing_id is not null and status not in ('rejected', 'accepted');

create unique index if not exists rfq_threads_one_open_per_service
  on public.rfq_threads (customer_id, service_id)
  where service_id is not null and status not in ('rejected', 'accepted');

create index if not exists rfq_threads_vendor_idx
  on public.rfq_threads (vendor_id, status, last_message_at desc nulls last);

create index if not exists rfq_threads_customer_idx
  on public.rfq_threads (customer_id, last_message_at desc nulls last);

drop trigger if exists rfq_threads_set_updated_at on public.rfq_threads;
create trigger rfq_threads_set_updated_at
  before update on public.rfq_threads
  for each row
  execute function public.set_updated_at();

create table if not exists public.rfq_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.rfq_threads (id) on delete cascade,
  sender_role text not null check (sender_role in ('customer', 'vendor', 'admin')),
  sender_id uuid not null references auth.users (id) on delete cascade,
  body text not null check (char_length(btrim(body)) between 1 and 2000),
  created_at timestamptz not null default timezone('utc', now())
);

comment on table public.rfq_messages is
  'Negotiation messages on an RFQ thread. No attachments — same posture as enquiry_messages.';

create index if not exists rfq_messages_thread_idx
  on public.rfq_messages (thread_id, created_at);

-- ---------------------------------------------------------------------------
-- Subject must belong to the thread vendor.
-- ---------------------------------------------------------------------------
create or replace function public.rfq_threads_guard()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  owner_vendor uuid;
  listing_class text;
begin
  if new.listing_id is not null then
    select vendor_id, product_class
      into owner_vendor, listing_class
    from public.vendor_listings
    where id = new.listing_id;
    if owner_vendor is null then
      raise exception 'rfq_threads: listing % does not exist', new.listing_id;
    end if;
    if listing_class is distinct from 'E' then
      raise exception 'rfq_threads: listing % is not Class E (made-to-order)', new.listing_id;
    end if;
  elsif new.service_id is not null then
    select vendor_id into owner_vendor
    from public.services
    where id = new.service_id;
    if owner_vendor is null then
      raise exception 'rfq_threads: service % does not exist', new.service_id;
    end if;
  end if;

  if owner_vendor <> new.vendor_id then
    raise exception
      'rfq_threads: vendor % does not own subject', new.vendor_id;
  end if;

  return new;
end;
$$;

drop trigger if exists rfq_threads_guard_trg on public.rfq_threads;
create trigger rfq_threads_guard_trg
  before insert or update on public.rfq_threads
  for each row
  execute function public.rfq_threads_guard();

-- ---------------------------------------------------------------------------
-- Cart lines sourced from an accepted RFQ keep the quoted price.
-- ---------------------------------------------------------------------------
alter table public.cart_items
  add column if not exists rfq_thread_id uuid references public.rfq_threads (id) on delete set null;

comment on column public.cart_items.rfq_thread_id is
  'When set, unit_price_ngwee was snapshotted from rfq_threads.quote_price_ngwee at accept time and must not be re-derived from listing tiers.';

create unique index if not exists cart_items_rfq_thread_unique
  on public.cart_items (cart_id, rfq_thread_id)
  where rfq_thread_id is not null;

-- ---------------------------------------------------------------------------
-- RLS — customer sees own threads; vendor sees threads for their shop.
-- ---------------------------------------------------------------------------
alter table public.rfq_threads enable row level security;
alter table public.rfq_threads force row level security;
alter table public.rfq_messages enable row level security;
alter table public.rfq_messages force row level security;

drop policy if exists rfq_threads_customer_select on public.rfq_threads;
create policy rfq_threads_customer_select
  on public.rfq_threads
  for select
  to authenticated
  using (customer_id = (select auth.uid()));

drop policy if exists rfq_threads_vendor_select on public.rfq_threads;
create policy rfq_threads_vendor_select
  on public.rfq_threads
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = rfq_threads.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

drop policy if exists rfq_messages_party_select on public.rfq_messages;
create policy rfq_messages_party_select
  on public.rfq_messages
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.rfq_threads t
      left join public.vendors v on v.id = t.vendor_id
      where t.id = rfq_messages.thread_id
        and (
          t.customer_id = (select auth.uid())
          or v.owner_user_id = (select auth.uid())
        )
    )
  );

revoke all on public.rfq_threads from anon, authenticated;
revoke all on public.rfq_messages from anon, authenticated;
grant select on public.rfq_threads to authenticated;
grant select on public.rfq_messages to authenticated;

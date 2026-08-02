-- R02-P13 — listing-anchored customer→business enquiries (D37).
--
-- The first customer-facing messaging surface in the product. There is no
-- message/thread/chat table anywhere today; the only message-shaped tables are
-- the WAHA intake ones (0073), which are a private vendor-intake lane and must
-- not be reused or joined to.
--
-- D37 fences this to social COMMERCE: enquiries anchored to something for sale,
-- with a business on one end. Customer-to-customer DMs, groups, public profiles
-- and image exchange are out.
--
-- THE BINDING REQUIREMENT IS STRUCTURAL. A customer↔customer thread must be
-- UNREPRESENTABLE, not merely unreachable from the UI, because a UI restriction
-- is one careless endpoint away from being gone and a foreign key is not. Three
-- things enforce it here:
--
--   1. the party columns are semantically distinct and both NOT NULL - there is
--      no generic participant_a/participant_b to point at two customers;
--   2. a CHECK forbids vendor_id = customer_id;
--   3. a trigger asserts vendor_id is the vendor that actually owns the
--      subject, so a thread cannot be aimed at an unrelated business either.
--
-- No attachment column exists. Absence is the enforcement: D37 defers image
-- exchange, and a column nobody added cannot be quietly populated later without
-- a migration that has to argue for itself.

create table if not exists public.enquiry_threads (
  id uuid primary key default gen_random_uuid(),
  subject_kind text not null check (subject_kind in ('listing', 'event', 'service')),
  subject_id uuid not null,
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  customer_id uuid not null references auth.users (id) on delete cascade,
  status text not null default 'open' check (status in ('open', 'answered', 'closed')),
  last_message_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint enquiry_threads_parties_distinct check (vendor_id <> customer_id)
);

comment on table public.enquiry_threads is
  'Listing/event/service-anchored customer->business enquiry (D37). A customer-to-customer thread is structurally unrepresentable: both party columns are distinct, NOT NULL, and the vendor is verified against the subject.';

-- One open thread per customer per subject: re-asking about the same item
-- continues the conversation rather than spawning a parallel one the vendor
-- has to notice separately.
create unique index if not exists enquiry_threads_one_open_per_subject
  on public.enquiry_threads (customer_id, subject_kind, subject_id)
  where status <> 'closed';

create index if not exists enquiry_threads_vendor_idx
  on public.enquiry_threads (vendor_id, status, last_message_at desc);
create index if not exists enquiry_threads_customer_idx
  on public.enquiry_threads (customer_id, last_message_at desc);

drop trigger if exists enquiry_threads_set_updated_at on public.enquiry_threads;
create trigger enquiry_threads_set_updated_at
  before update on public.enquiry_threads
  for each row
  execute function public.set_updated_at();

create table if not exists public.enquiry_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.enquiry_threads (id) on delete cascade,
  sender_role text not null check (sender_role in ('customer', 'vendor', 'admin')),
  sender_id uuid not null references auth.users (id) on delete cascade,
  body text not null check (char_length(btrim(body)) between 1 and 2000),
  created_at timestamptz not null default timezone('utc', now())
);

comment on table public.enquiry_messages is
  'Messages on an enquiry thread. Deliberately has NO attachment/media column - D37 defers image exchange, and absence is the enforcement.';

create index if not exists enquiry_messages_thread_idx
  on public.enquiry_messages (thread_id, created_at);

-- ---------------------------------------------------------------------------
-- The subject must belong to the thread's vendor.
-- ---------------------------------------------------------------------------
create or replace function public.enquiry_threads_guard()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  owner_vendor uuid;
begin
  -- NB: each subject table names its owner differently. `events` uses
  -- organiser_vendor_id (0004), not vendor_id — assuming otherwise would have
  -- made every event enquiry fail at runtime rather than at deploy.
  if new.subject_kind = 'listing' then
    select vendor_id into owner_vendor
    from public.vendor_listings where id = new.subject_id;
  elsif new.subject_kind = 'event' then
    select organiser_vendor_id into owner_vendor
    from public.events where id = new.subject_id;
  elsif new.subject_kind = 'service' then
    select vendor_id into owner_vendor
    from public.services where id = new.subject_id;
  end if;

  if owner_vendor is null then
    raise exception 'enquiry_threads: % % does not exist', new.subject_kind, new.subject_id;
  end if;

  if owner_vendor <> new.vendor_id then
    raise exception
      'enquiry_threads: vendor % does not own % %',
      new.vendor_id, new.subject_kind, new.subject_id;
  end if;

  return new;
end;
$$;

drop trigger if exists enquiry_threads_guard_trg on public.enquiry_threads;
create trigger enquiry_threads_guard_trg
  before insert or update on public.enquiry_threads
  for each row
  execute function public.enquiry_threads_guard();

-- ---------------------------------------------------------------------------
-- RLS — two-party isolation, both directions.
-- ---------------------------------------------------------------------------
alter table public.enquiry_threads enable row level security;
alter table public.enquiry_threads force row level security;
alter table public.enquiry_messages enable row level security;
alter table public.enquiry_messages force row level security;

drop policy if exists enquiry_threads_customer_select on public.enquiry_threads;
create policy enquiry_threads_customer_select
  on public.enquiry_threads
  for select
  to authenticated
  using (customer_id = (select auth.uid()));

drop policy if exists enquiry_threads_vendor_select on public.enquiry_threads;
create policy enquiry_threads_vendor_select
  on public.enquiry_threads
  for select
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = enquiry_threads.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

drop policy if exists enquiry_messages_party_select on public.enquiry_messages;
create policy enquiry_messages_party_select
  on public.enquiry_messages
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.enquiry_threads t
      left join public.vendors v on v.id = t.vendor_id
      where t.id = enquiry_messages.thread_id
        and (
          t.customer_id = (select auth.uid())
          or v.owner_user_id = (select auth.uid())
        )
    )
  );

comment on policy enquiry_messages_party_select on public.enquiry_messages is
  'Only the thread''s two parties may read it. There is no public read: an enquiry is private correspondence, not a review.';

-- Writes go through the service-role API only, which applies the rate limit,
-- the prohibited-content screen and the audit trail. No INSERT/UPDATE/DELETE
-- policy for `authenticated` exists on purpose.
revoke all on public.enquiry_threads from anon, authenticated;
revoke all on public.enquiry_messages from anon, authenticated;
grant select on public.enquiry_threads to authenticated;
grant select on public.enquiry_messages to authenticated;

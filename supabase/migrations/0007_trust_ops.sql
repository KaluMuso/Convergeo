-- M03-P06: Trust & ops schema — reviews, disputes, returns, notification outbox, audit log, flags.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.reviews (
  id uuid primary key default gen_random_uuid(),
  order_item_id uuid not null references public.order_items (id) on delete restrict,
  rating int not null check (rating between 1 and 5),
  body text,
  photos text[] not null default '{}'::text[],
  vendor_reply text,
  vendor_reply_at timestamptz,
  status text not null default 'published'
    check (status in ('published', 'flagged', 'removed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint reviews_order_item_id_key unique (order_item_id)
);

create index reviews_status_order_item_id_idx
  on public.reviews (status, order_item_id)
  where status = 'published';

create trigger reviews_set_updated_at
  before update on public.reviews
  for each row
  execute function public.set_updated_at();

comment on table public.reviews is
  'Verified-purchase reviews (one per order_item); public reads published rows only.';

create table public.disputes (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete restrict,
  opener_user_id uuid not null references auth.users (id) on delete restrict,
  evidence_paths text[] not null default '{}'::text[],
  vendor_response text,
  admin_decision text,
  status text not null default 'open'
    check (status in (
      'open', 'vendor_responded', 'resolved_refund', 'resolved_release', 'rejected'
    )),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index disputes_order_id_idx on public.disputes (order_id);
create index disputes_opener_user_id_idx on public.disputes (opener_user_id);

create trigger disputes_set_updated_at
  before update on public.disputes
  for each row
  execute function public.set_updated_at();

create table public.returns (
  id uuid primary key default gen_random_uuid(),
  order_item_id uuid not null references public.order_items (id) on delete restrict,
  lane int not null check (lane in (1, 2)),
  evidence_paths text[] not null default '{}'::text[],
  fee_breakdown jsonb not null default '{}'::jsonb,
  status text not null default 'requested'
    check (status in ('requested', 'approved', 'rejected', 'completed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index returns_order_item_id_idx on public.returns (order_item_id);

create trigger returns_set_updated_at
  before update on public.returns
  for each row
  execute function public.set_updated_at();

create table public.notification_outbox (
  id uuid primary key default gen_random_uuid(),
  dedupe_key text not null unique,
  channel text not null check (channel in ('whatsapp', 'sms', 'email')),
  template text,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'sent', 'failed')),
  attempts int not null default 0 check (attempts >= 0),
  next_retry_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index notification_outbox_status_next_retry_at_idx
  on public.notification_outbox (status, next_retry_at);

create trigger notification_outbox_set_updated_at
  before update on public.notification_outbox
  for each row
  execute function public.set_updated_at();

comment on table public.notification_outbox is
  'At-least-once notification dispatch queue (M14); dedupe_key unique for effectively-once delivery.';

create table public.audit_log (
  id uuid primary key default gen_random_uuid(),
  actor uuid,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  before jsonb,
  after jsonb,
  at timestamptz not null default timezone('utc', now())
);

create index audit_log_entity_type_entity_id_at_idx
  on public.audit_log (entity_type, entity_id, at desc);

comment on table public.audit_log is
  'Append-only admin mutation audit trail; service_role only — no client policies.';

create table public.flags (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  entity_id uuid not null,
  reason text not null,
  reporter_user_id uuid not null references auth.users (id) on delete restrict,
  status text not null default 'open'
    check (status in ('open', 'actioned', 'dismissed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index flags_entity_type_entity_id_idx on public.flags (entity_type, entity_id);
create index flags_reporter_user_id_idx on public.flags (reporter_user_id);

create trigger flags_set_updated_at
  before update on public.flags
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Verified-purchase gate (security definer — clients cannot bypass)
-- ---------------------------------------------------------------------------

create or replace function public.validate_review_verified_purchase()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  order_customer_id uuid;
  order_status text;
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  select o.customer_id, o.status
  into order_customer_id, order_status
  from public.order_items oi
  join public.orders o on o.id = oi.order_id
  where oi.id = new.order_item_id;

  if order_customer_id is null then
    raise exception 'order_item not found for review';
  end if;

  if order_status not in ('delivered', 'completed') then
    raise exception 'review requires delivered or completed order (status=%)', order_status;
  end if;

  if order_customer_id is distinct from auth.uid() then
    raise exception 'review author must be the order customer';
  end if;

  return new;
end;
$$;

create trigger reviews_validate_verified_purchase
  before insert on public.reviews
  for each row
  execute function public.validate_review_verified_purchase();

comment on function public.validate_review_verified_purchase() is
  'Enforces verified-purchase: order_item must belong to auth.uid() on a delivered/completed order.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.reviews enable row level security;
alter table public.disputes enable row level security;
alter table public.returns enable row level security;
alter table public.notification_outbox enable row level security;
alter table public.audit_log enable row level security;
alter table public.flags enable row level security;

alter table public.reviews force row level security;
alter table public.disputes force row level security;
alter table public.returns force row level security;
alter table public.notification_outbox force row level security;
alter table public.audit_log force row level security;
alter table public.flags force row level security;

-- reviews: public read published; author insert once; vendor reply; admin all.
create policy reviews_public_select
  on public.reviews
  for select
  to anon, authenticated
  using (status = 'published');

comment on policy reviews_public_select on public.reviews is
  'Anyone may read published reviews; flagged/removed rows are hidden from clients.';

create policy reviews_author_insert
  on public.reviews
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.order_items oi
      join public.orders o on o.id = oi.order_id
      where oi.id = order_item_id
        and o.customer_id = (select auth.uid())
    )
  );

comment on policy reviews_author_insert on public.reviews is
  'Customers may insert one review per owned order_item; delivered/completed gate enforced by validate_review_verified_purchase trigger.';

create policy reviews_vendor_reply_update
  on public.reviews
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.order_item_products oip
      join public.vendor_listings vl on vl.id = oip.listing_id
      join public.vendors v on v.id = vl.vendor_id
      where oip.order_item_id = reviews.order_item_id
        and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.order_item_products oip
      join public.vendor_listings vl on vl.id = oip.listing_id
      join public.vendors v on v.id = vl.vendor_id
      where oip.order_item_id = reviews.order_item_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy reviews_vendor_reply_update on public.reviews is
  'Vendor owners may reply to reviews on their own listings (vendor_reply fields; column guard in M15).';

create policy reviews_admin_all
  on public.reviews
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy reviews_admin_all on public.reviews is
  'Platform admins may moderate reviews (publish/flag/remove).';

-- disputes: parties select; opener insert; admin all.
create policy disputes_party_select
  on public.disputes
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.orders o
      where o.id = disputes.order_id
        and (
          o.customer_id = (select auth.uid())
          or exists (
            select 1
            from public.vendors v
            where v.id = o.vendor_id
              and v.owner_user_id = (select auth.uid())
          )
        )
    )
  );

comment on policy disputes_party_select on public.disputes is
  'Order customer and fulfilling vendor may read disputes on their orders.';

create policy disputes_opener_insert
  on public.disputes
  for insert
  to authenticated
  with check (opener_user_id = (select auth.uid()));

comment on policy disputes_opener_insert on public.disputes is
  'Authenticated users may open disputes as themselves (party membership enforced in M09).';

create policy disputes_admin_all
  on public.disputes
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy disputes_admin_all on public.disputes is
  'Platform admins may resolve disputes and record decisions.';

-- returns: customer select/insert own order_item; vendor read own listing; admin all.
create policy returns_customer_select
  on public.returns
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.order_items oi
      join public.orders o on o.id = oi.order_id
      where oi.id = returns.order_item_id
        and o.customer_id = (select auth.uid())
    )
  );

comment on policy returns_customer_select on public.returns is
  'Customers may read return requests for their own order items.';

create policy returns_customer_insert
  on public.returns
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.order_items oi
      join public.orders o on o.id = oi.order_id
      where oi.id = order_item_id
        and o.customer_id = (select auth.uid())
    )
  );

comment on policy returns_customer_insert on public.returns is
  'Customers may request returns on their own order items.';

create policy returns_vendor_select
  on public.returns
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.order_item_products oip
      join public.vendor_listings vl on vl.id = oip.listing_id
      join public.vendors v on v.id = vl.vendor_id
      where oip.order_item_id = returns.order_item_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy returns_vendor_select on public.returns is
  'Vendor owners may read return requests for items sold from their listings.';

create policy returns_admin_all
  on public.returns
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy returns_admin_all on public.returns is
  'Platform admins may approve/reject/complete returns.';

-- notification_outbox + audit_log: service_role only (zero client policies).
comment on table public.notification_outbox is
  'Notification dispatch queue; RLS enabled with zero client policies — service_role only.';

comment on table public.audit_log is
  'Admin mutation audit; RLS enabled with zero client policies — service_role only.';

-- flags: reporter insert; admin select/all; no public read.
create policy flags_reporter_insert
  on public.flags
  for insert
  to authenticated
  with check (reporter_user_id = (select auth.uid()));

comment on policy flags_reporter_insert on public.flags is
  'Authenticated users may report content; rows are not publicly readable.';

create policy flags_admin_all
  on public.flags
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy flags_admin_all on public.flags is
  'Platform admins may triage and action flags.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

grant select, insert, update, delete on table public.reviews to authenticated, service_role;
grant select, insert, update, delete on table public.disputes to authenticated, service_role;
grant select, insert, update, delete on table public.returns to authenticated, service_role;
grant select, insert, update, delete on table public.notification_outbox to service_role;
grant select, insert, update, delete on table public.audit_log to service_role;
grant select, insert, update, delete on table public.flags to authenticated, service_role;

grant execute on function public.validate_review_verified_purchase() to authenticated, service_role;

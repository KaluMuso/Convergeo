-- M03-P05: Money schema — double-entry escrow ledger, payments, webhooks, payouts, refunds, invoices.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.ledger_accounts (
  id uuid primary key default gen_random_uuid(),
  kind text not null
    check (kind in (
      'platform_cash', 'escrow', 'commission_revenue',
      'vendor_payable', 'cod_receivable', 'fees'
    )),
  vendor_id uuid references public.vendors (id) on delete restrict,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint ledger_accounts_vendor_kind_check check (
    (kind in ('vendor_payable', 'cod_receivable') and vendor_id is not null)
    or (kind not in ('vendor_payable', 'cod_receivable') and vendor_id is null)
  )
);

create unique index ledger_accounts_kind_platform_uidx
  on public.ledger_accounts (kind)
  where vendor_id is null;

create unique index ledger_accounts_kind_vendor_id_uidx
  on public.ledger_accounts (kind, vendor_id)
  where vendor_id is not null;

create index ledger_accounts_vendor_id_idx on public.ledger_accounts (vendor_id);

create trigger ledger_accounts_set_updated_at
  before update on public.ledger_accounts
  for each row
  execute function public.set_updated_at();

comment on table public.ledger_accounts is
  'Chart of accounts: platform-wide buckets (vendor_id null) and per-vendor payable/COD rows.';

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  checkout_group_id uuid not null references public.checkout_groups (id) on delete restrict,
  provider text not null check (provider in ('lenco')),
  rail text not null check (rail in ('mtn', 'airtel', 'zamtel', 'card', 'cod')),
  lenco_reference text not null
    check (lenco_reference ~ '^[-._A-Za-z0-9]+$'),
  amount_ngwee bigint not null check (amount_ngwee > 0),
  status text not null default 'initiated'
    check (status in ('initiated', 'pending', 'success', 'failed', 'expired')),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint payments_lenco_reference_key unique (lenco_reference)
);

create index payments_checkout_group_id_idx on public.payments (checkout_group_id);
create index payments_status_idx on public.payments (status);

create trigger payments_set_updated_at
  before update on public.payments
  for each row
  execute function public.set_updated_at();

create table public.payouts (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete restrict,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  rail text not null check (rail in ('mtn', 'airtel', 'zamtel', 'card')),
  lenco_reference text
    check (lenco_reference is null or lenco_reference ~ '^[-._A-Za-z0-9]+$'),
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'paid', 'failed')),
  resolve_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index payouts_vendor_id_idx on public.payouts (vendor_id);
create index payouts_status_idx on public.payouts (status);

create trigger payouts_set_updated_at
  before update on public.payouts
  for each row
  execute function public.set_updated_at();

create table public.refunds (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete restrict,
  lane int not null check (lane in (1, 2)),
  breakdown jsonb not null default '{}'::jsonb,
  amount_ngwee bigint not null check (amount_ngwee > 0),
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'processing', 'completed', 'failed', 'cancelled')),
  payout_ref uuid references public.payouts (id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index refunds_order_id_idx on public.refunds (order_id);

create trigger refunds_set_updated_at
  before update on public.refunds
  for each row
  execute function public.set_updated_at();

create table public.ledger_transactions (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  checkout_group_id uuid references public.checkout_groups (id) on delete restrict,
  order_id uuid references public.orders (id) on delete restrict,
  payment_id uuid references public.payments (id) on delete restrict,
  payout_id uuid references public.payouts (id) on delete restrict,
  refund_id uuid references public.refunds (id) on delete restrict,
  created_at timestamptz not null default timezone('utc', now())
);

create index ledger_transactions_checkout_group_id_idx
  on public.ledger_transactions (checkout_group_id);
create index ledger_transactions_order_id_idx on public.ledger_transactions (order_id);
create index ledger_transactions_payment_id_idx on public.ledger_transactions (payment_id);

comment on table public.ledger_transactions is
  'Immutable financial event header; kind examples: payment_captured, escrow_release, payout, refund, commission, cod_settle.';

create table public.ledger_postings (
  id uuid primary key default gen_random_uuid(),
  transaction_id uuid not null references public.ledger_transactions (id) on delete restrict,
  account_id uuid not null references public.ledger_accounts (id) on delete restrict,
  amount_ngwee bigint not null,
  created_at timestamptz not null default timezone('utc', now())
);

create index ledger_postings_transaction_id_idx on public.ledger_postings (transaction_id);
create index ledger_postings_account_id_idx on public.ledger_postings (account_id);

comment on table public.ledger_postings is
  'Double-entry lines per transaction. Sign convention: debit positive (+), credit negative (−); sum per transaction_id must be zero.';

create table public.webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_id text not null,
  signature_valid boolean not null default false,
  processed_at timestamptz,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint webhook_events_provider_event_id_key unique (provider, event_id)
);

create index webhook_events_processed_at_idx
  on public.webhook_events (processed_at)
  where processed_at is null;

comment on table public.webhook_events is
  'Inbound payment webhook idempotency log; (provider, event_id) unique prevents replay at DB level.';

create table public.invoice_counters (
  series text primary key,
  next_no bigint not null default 1 check (next_no >= 1)
);

comment on table public.invoice_counters is
  'Gapless sequential invoice allocation per series via public.next_invoice_no() (SELECT … FOR UPDATE).';

create table public.invoices (
  id uuid primary key default gen_random_uuid(),
  series text not null,
  no bigint not null check (no >= 1),
  order_id uuid not null references public.orders (id) on delete restrict,
  snapshot jsonb not null default '{}'::jsonb,
  vat_flag boolean not null default false,
  vat_ngwee bigint not null default 0 check (vat_ngwee >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  constraint invoices_series_no_key unique (series, no)
);

create index invoices_order_id_idx on public.invoices (order_id);

-- ---------------------------------------------------------------------------
-- Integrity functions & triggers
-- ---------------------------------------------------------------------------

-- Zero-sum guard: postings may be inserted in multiple statements within one DB txn;
-- DEFERRABLE INITIALLY DEFERRED fires at COMMIT so balanced multi-row inserts succeed.
create or replace function public.enforce_ledger_zero_sum()
returns trigger
language plpgsql
as $$
declare
  txn_id uuid;
  total bigint;
begin
  txn_id := coalesce(new.transaction_id, old.transaction_id);

  select coalesce(sum(amount_ngwee), 0)
  into total
  from public.ledger_postings
  where transaction_id = txn_id;

  if total <> 0 then
    raise exception 'ledger transaction % postings must sum to zero (got % ngwee)', txn_id, total
      using errcode = '23514';
  end if;

  return null;
end;
$$;

comment on function public.enforce_ledger_zero_sum() is
  'Constraint trigger: rejects COMMIT when any ledger_transaction postings do not net to zero.';

create constraint trigger ledger_postings_zero_sum
  after insert or update or delete on public.ledger_postings
  deferrable initially deferred
  for each row
  execute function public.enforce_ledger_zero_sum();

-- Gapless invoice number: locks counter row, returns current value, then increments.
create or replace function public.next_invoice_no(p_series text)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  allocated bigint;
begin
  select next_no
  into allocated
  from public.invoice_counters
  where series = p_series
  for update;

  if not found then
    raise exception 'unknown invoice series %', p_series;
  end if;

  update public.invoice_counters
  set next_no = next_no + 1
  where series = p_series;

  return allocated;
end;
$$;

comment on function public.next_invoice_no(text) is
  'Serialized gapless invoice allocation: SELECT … FOR UPDATE on invoice_counters, return+increment next_no.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.ledger_accounts enable row level security;
alter table public.ledger_transactions enable row level security;
alter table public.ledger_postings enable row level security;
alter table public.payments enable row level security;
alter table public.webhook_events enable row level security;
alter table public.payouts enable row level security;
alter table public.refunds enable row level security;
alter table public.invoice_counters enable row level security;
alter table public.invoices enable row level security;

alter table public.ledger_accounts force row level security;
alter table public.ledger_transactions force row level security;
alter table public.ledger_postings force row level security;
alter table public.payments force row level security;
alter table public.webhook_events force row level security;
alter table public.payouts force row level security;
alter table public.refunds force row level security;
alter table public.invoice_counters force row level security;
alter table public.invoices force row level security;

-- ledger_accounts: service-role only — zero client policies (money mechanics server-side).
comment on table public.ledger_accounts is
  'Chart of accounts; RLS enabled with zero client policies — service_role writes, admin reads via policy below.';

create policy ledger_accounts_admin_all
  on public.ledger_accounts
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy ledger_accounts_admin_all on public.ledger_accounts is
  'Platform admins may inspect ledger accounts; customers/vendors have no direct access.';

-- ledger_transactions: service-role only.
comment on table public.ledger_transactions is
  'Financial event headers; RLS enabled with zero client policies — service_role only.';

create policy ledger_transactions_admin_all
  on public.ledger_transactions
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy ledger_transactions_admin_all on public.ledger_transactions is
  'Platform admins may inspect ledger transactions; no client read/write.';

-- ledger_postings: service-role only.
comment on table public.ledger_postings is
  'Double-entry postings; RLS enabled with zero client policies — service_role only.';

create policy ledger_postings_admin_all
  on public.ledger_postings
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy ledger_postings_admin_all on public.ledger_postings is
  'Platform admins may inspect postings; zero-sum enforced by constraint trigger.';

-- webhook_events: service-role only.
comment on table public.webhook_events is
  'Webhook idempotency log; RLS enabled with zero client policies — service_role only.';

create policy webhook_events_admin_all
  on public.webhook_events
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy webhook_events_admin_all on public.webhook_events is
  'Platform admins may inspect webhook events; replay blocked by (provider, event_id) unique.';

-- invoice_counters: service-role only.
comment on table public.invoice_counters is
  'Invoice sequence counters; RLS enabled with zero client policies — next_invoice_no() is service_role only.';

create policy invoice_counters_admin_all
  on public.invoice_counters
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy invoice_counters_admin_all on public.invoice_counters is
  'Platform admins may inspect counters; allocation via security definer next_invoice_no().';

-- payments: customer reads own via checkout_groups; no client writes.
create policy payments_customer_select
  on public.payments
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.checkout_groups cg
      where cg.id = payments.checkout_group_id
        and cg.customer_id = (select auth.uid())
    )
  );

comment on policy payments_customer_select on public.payments is
  'Customers may read payments for their own checkout sessions; insert/update require service_role.';

create policy payments_admin_all
  on public.payments
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy payments_admin_all on public.payments is
  'Platform admins may manage all payment rows.';

-- payouts: vendor reads own via vendors.owner_user_id; no client writes.
create policy payouts_vendor_select
  on public.payouts
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = payouts.vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on policy payouts_vendor_select on public.payouts is
  'Vendor owners may read their own payout rows; insert/update require service_role.';

create policy payouts_admin_all
  on public.payouts
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy payouts_admin_all on public.payouts is
  'Platform admins may manage all payout rows.';

-- refunds: order customer reads own; no client writes.
create policy refunds_customer_select
  on public.refunds
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.orders o
      where o.id = refunds.order_id
        and o.customer_id = (select auth.uid())
    )
  );

comment on policy refunds_customer_select on public.refunds is
  'Customers may read refunds on their own orders; insert/update require service_role.';

create policy refunds_admin_all
  on public.refunds
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy refunds_admin_all on public.refunds is
  'Platform admins may manage all refund rows.';

-- invoices: order customer reads own; no client writes.
create policy invoices_customer_select
  on public.invoices
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.orders o
      where o.id = invoices.order_id
        and o.customer_id = (select auth.uid())
    )
  );

comment on policy invoices_customer_select on public.invoices is
  'Customers may read invoices for their own orders; insert requires service_role.';

create policy invoices_admin_all
  on public.invoices
  for all
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

comment on policy invoices_admin_all on public.invoices is
  'Platform admins may manage all invoice rows.';

-- API roles need table privileges; RLS policies enforce authorization.
grant select, insert, update, delete on table public.ledger_accounts to authenticated, service_role;
grant select, insert, update, delete on table public.ledger_transactions to authenticated, service_role;
grant select, insert, update, delete on table public.ledger_postings to authenticated, service_role;
grant select, insert, update, delete on table public.payments to authenticated, service_role;
grant select, insert, update, delete on table public.webhook_events to authenticated, service_role;
grant select, insert, update, delete on table public.payouts to authenticated, service_role;
grant select, insert, update, delete on table public.refunds to authenticated, service_role;
grant select, insert, update, delete on table public.invoice_counters to authenticated, service_role;
grant select, insert, update, delete on table public.invoices to authenticated, service_role;

grant execute on function public.enforce_ledger_zero_sum() to authenticated, service_role;
grant execute on function public.next_invoice_no(text) to authenticated, service_role;

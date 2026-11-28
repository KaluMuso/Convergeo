-- Pending: vendor bulk price edit audit tables (draft roadmap). RLS: vendor read own batches.

create table if not exists public.vendor_price_change_batches (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors (id) on delete cascade,
  operation_id uuid not null,
  adjustment_kind text not null check (adjustment_kind in ('delta_ngwee', 'percent_bps')),
  adjustment_value integer not null,
  listing_count integer not null default 0,
  applied_count integer not null default 0,
  skipped_count integer not null default 0,
  created_at timestamptz not null default now(),
  unique (vendor_id, operation_id)
);

create table if not exists public.vendor_price_change_batch_items (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.vendor_price_change_batches (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  old_price_ngwee bigint,
  new_price_ngwee bigint,
  applied boolean not null default false,
  skip_reason text,
  warnings text[] not null default '{}'::text[],
  created_at timestamptz not null default now()
);

create index if not exists vendor_price_change_batches_vendor_created_idx
  on public.vendor_price_change_batches (vendor_id, created_at desc);

create index if not exists vendor_price_change_batch_items_batch_idx
  on public.vendor_price_change_batch_items (batch_id);

alter table public.vendor_price_change_batches enable row level security;
alter table public.vendor_price_change_batch_items enable row level security;

create policy vendor_price_change_batches_owner_read
  on public.vendor_price_change_batches
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendors v
      where v.id = vendor_id
        and v.owner_user_id = (select auth.uid())
    )
  );

create policy vendor_price_change_batch_items_owner_read
  on public.vendor_price_change_batch_items
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.vendor_price_change_batches b
      join public.vendors v on v.id = b.vendor_id
      where b.id = batch_id
        and v.owner_user_id = (select auth.uid())
    )
  );

comment on table public.vendor_price_change_batches is
  'Audit header for vendor bulk price apply operations (idempotent on operation_id).';
comment on table public.vendor_price_change_batch_items is
  'Per-listing bulk price preview/apply outcomes for a batch.';
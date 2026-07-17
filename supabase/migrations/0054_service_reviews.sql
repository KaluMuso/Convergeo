-- 0054: Service reviews — verified-engagement reviews of a service provider.
--
-- Product reviews (0007) key off order_item_id and derive identity through
-- order_item_products; services never flow through that table. An accepted RFQ
-- quote instead creates an order with service_deposit/service_balance line items
-- linked via order_item_services(order_item_id, job_id, quote_id). RFQ jobs are
-- category-based, not tied to a specific `services` listing, so a service review
-- attributes to the PROVIDER VENDOR of the completed job (job_quotes.provider_
-- vendor_id), gated to the job's customer once the service order is completed.
--
-- Mirrors the product-review shape (0007): one review per completed job, a
-- SECURITY DEFINER verified-engagement trigger (defense-in-depth alongside the
-- API gate), public-read + author-insert + vendor-reply + admin RLS. Additive;
-- reversible (drop table + trigger fn).

create table if not exists public.service_reviews (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs (id) on delete cascade,
  provider_vendor_id uuid not null references public.vendors (id) on delete restrict,
  customer_id uuid not null references public.profiles (id) on delete cascade,
  rating int not null check (rating between 1 and 5),
  body text,
  vendor_reply text,
  vendor_reply_at timestamptz,
  status text not null default 'published'
    check (status in ('published', 'flagged', 'removed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint service_reviews_job_id_key unique (job_id)
);

create index if not exists service_reviews_provider_status_idx
  on public.service_reviews (provider_vendor_id, status);

create index if not exists service_reviews_customer_id_idx
  on public.service_reviews (customer_id);

create trigger service_reviews_set_updated_at
  before update on public.service_reviews
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Verified-engagement gate (mirrors validate_review_verified_purchase, 0007).
-- superuser/seeding bypasses; the service-role API is the primary gate.
-- ---------------------------------------------------------------------------

create or replace function public.validate_service_review_verified_engagement()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  job_customer_id uuid;
begin
  if session_user in ('postgres', 'supabase_admin') then
    return new;
  end if;

  select customer_id into job_customer_id
  from public.jobs
  where id = new.job_id;

  if job_customer_id is null then
    raise exception 'job not found for service review';
  end if;

  if job_customer_id is distinct from auth.uid() then
    raise exception 'service review author must be the job customer';
  end if;

  if new.customer_id is distinct from job_customer_id then
    raise exception 'service review customer_id must match the job customer';
  end if;

  -- The provider must be the one whose quote was accepted for this job.
  if not exists (
    select 1
    from public.job_quotes q
    where q.job_id = new.job_id
      and q.status = 'accepted'
      and q.provider_vendor_id = new.provider_vendor_id
  ) then
    raise exception 'service review provider must match the accepted quote';
  end if;

  -- The service order for this job must be completed (job done AND vendor paid).
  if not exists (
    select 1
    from public.order_item_services ois
    join public.order_items oi on oi.id = ois.order_item_id
    join public.orders o on o.id = oi.order_id
    where ois.job_id = new.job_id
      and o.status = 'completed'
  ) then
    raise exception 'service review requires a completed service order';
  end if;

  return new;
end;
$$;

create trigger service_reviews_validate_verified_engagement
  before insert on public.service_reviews
  for each row
  execute function public.validate_service_review_verified_engagement();

comment on function public.validate_service_review_verified_engagement() is
  'Enforces verified engagement: job must belong to auth.uid(), provider must match the accepted quote, and the service order must be completed.';

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------

alter table public.service_reviews enable row level security;
alter table public.service_reviews force row level security;

drop policy if exists service_reviews_public_select on public.service_reviews;
create policy service_reviews_public_select on public.service_reviews
  for select
  to anon, authenticated
  using (status = 'published');

drop policy if exists service_reviews_author_insert on public.service_reviews;
create policy service_reviews_author_insert on public.service_reviews
  for insert
  to authenticated
  with check (
    customer_id = (select auth.uid())
    and exists (
      select 1 from public.jobs j
      where j.id = job_id and j.customer_id = (select auth.uid())
    )
  );

drop policy if exists service_reviews_vendor_reply_update on public.service_reviews;
create policy service_reviews_vendor_reply_update on public.service_reviews
  for update
  to authenticated
  using (
    exists (
      select 1 from public.vendors v
      where v.id = provider_vendor_id and v.owner_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.vendors v
      where v.id = provider_vendor_id and v.owner_user_id = (select auth.uid())
    )
  );

drop policy if exists service_reviews_admin_all on public.service_reviews;
create policy service_reviews_admin_all on public.service_reviews
  for all
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

grant select, insert, update, delete on public.service_reviews to authenticated, service_role;

comment on table public.service_reviews is
  'Verified-engagement reviews of a service provider (one per completed RFQ job).';

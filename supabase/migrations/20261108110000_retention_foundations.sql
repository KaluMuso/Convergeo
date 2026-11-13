-- Retention foundations: saved searches with alert preferences, listing price-drop /
-- back-in-stock subscriptions, admin-scheduled flash deals, and product Q&A.
--
-- Reused (not duplicated): user_recently_viewed (0066), vendor_follows (0083),
-- reviews.photos (0007, verified-purchase by construction: one review per
-- order_item), notification_outbox (0007) for alert delivery.
--
-- Access model: customer-owned rows (saved_searches, listing_alert_subscriptions)
-- carry owner-scoped RLS so a direct PostgREST read with a user JWT sees only the
-- caller's rows; the API uses the service role after its own authz. Flash deals and
-- Q&A are service-role only (the API exposes published rows publicly).
--
-- Down (manual, reversible — additive only):
--   drop table if exists public.product_answers;
--   drop table if exists public.product_questions;
--   drop table if exists public.flash_deals;
--   drop table if exists public.listing_alert_subscriptions;
--   drop table if exists public.saved_searches;

-- ---------------------------------------------------------------------------
-- saved_searches
-- ---------------------------------------------------------------------------
create table public.saved_searches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  label text check (label is null or length(trim(label)) between 1 and 80),
  query text not null default '' check (length(query) <= 200),
  filters jsonb not null default '{}'::jsonb check (jsonb_typeof(filters) = 'object'),
  alert_enabled boolean not null default true,
  alert_frequency text not null default 'daily'
    check (alert_frequency in ('instant', 'daily', 'weekly')),
  last_alerted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index saved_searches_user_query_filters_uidx
  on public.saved_searches (user_id, query, filters);
create index saved_searches_alert_idx
  on public.saved_searches (alert_frequency, last_alerted_at) where alert_enabled;

create trigger saved_searches_set_updated_at
  before update on public.saved_searches
  for each row execute function public.set_updated_at();

alter table public.saved_searches enable row level security;
alter table public.saved_searches force row level security;
revoke all on public.saved_searches from public, anon;
grant select, insert, update, delete on public.saved_searches to authenticated, service_role;

create policy saved_searches_owner_all
  on public.saved_searches
  for all
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- listing_alert_subscriptions (price drop / back in stock)
-- ---------------------------------------------------------------------------
create table public.listing_alert_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  kind text not null check (kind in ('price_drop', 'back_in_stock')),
  -- Price observed at subscribe time / last notification (integer ngwee).
  baseline_price_ngwee bigint check (baseline_price_ngwee is null or baseline_price_ngwee > 0),
  target_price_ngwee bigint check (target_price_ngwee is null or target_price_ngwee > 0),
  active boolean not null default true,
  last_notified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint listing_alert_subscriptions_unique unique (user_id, listing_id, kind)
);

create index listing_alert_subscriptions_active_idx
  on public.listing_alert_subscriptions (kind, listing_id) where active;

create trigger listing_alert_subscriptions_set_updated_at
  before update on public.listing_alert_subscriptions
  for each row execute function public.set_updated_at();

alter table public.listing_alert_subscriptions enable row level security;
alter table public.listing_alert_subscriptions force row level security;
revoke all on public.listing_alert_subscriptions from public, anon;
grant select, insert, update, delete on public.listing_alert_subscriptions
  to authenticated, service_role;

create policy listing_alert_subscriptions_owner_all
  on public.listing_alert_subscriptions
  for all
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- flash_deals (admin-scheduled windows; price honesty enforced by the API:
-- a deal only shows while the listing's live price <= deal_price_ngwee)
-- ---------------------------------------------------------------------------
create table public.flash_deals (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.vendor_listings (id) on delete cascade,
  deal_price_ngwee bigint not null check (deal_price_ngwee > 0),
  reference_price_ngwee bigint not null check (reference_price_ngwee > 0),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  position integer not null default 0,
  enabled boolean not null default true,
  created_by uuid,
  updated_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint flash_deals_window_valid check (ends_at > starts_at),
  constraint flash_deals_is_discount check (deal_price_ngwee < reference_price_ngwee)
);

create index flash_deals_live_idx on public.flash_deals (starts_at, ends_at) where enabled;

create trigger flash_deals_set_updated_at
  before update on public.flash_deals
  for each row execute function public.set_updated_at();

alter table public.flash_deals enable row level security;
alter table public.flash_deals force row level security;
revoke all on public.flash_deals from public, anon, authenticated;
grant select, insert, update, delete on public.flash_deals to service_role;

-- ---------------------------------------------------------------------------
-- product Q&A
-- ---------------------------------------------------------------------------
create table public.product_questions (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products (id) on delete cascade,
  asker_user_id uuid references auth.users (id) on delete set null,
  body text not null check (length(trim(body)) between 5 and 500),
  status text not null default 'published' check (status in ('published', 'hidden')),
  flag_count integer not null default 0 check (flag_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index product_questions_product_idx
  on public.product_questions (product_id, created_at desc) where status = 'published';

create table public.product_answers (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references public.product_questions (id) on delete cascade,
  author_user_id uuid references auth.users (id) on delete set null,
  author_role text not null check (author_role in ('vendor', 'customer', 'admin')),
  vendor_id uuid references public.vendors (id) on delete set null,
  body text not null check (length(trim(body)) between 2 and 1000),
  status text not null default 'published' check (status in ('published', 'hidden')),
  flag_count integer not null default 0 check (flag_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint product_answers_vendor_role check (author_role <> 'vendor' or vendor_id is not null)
);

create index product_answers_question_idx
  on public.product_answers (question_id, created_at) where status = 'published';

create trigger product_questions_set_updated_at
  before update on public.product_questions
  for each row execute function public.set_updated_at();
create trigger product_answers_set_updated_at
  before update on public.product_answers
  for each row execute function public.set_updated_at();

alter table public.product_questions enable row level security;
alter table public.product_questions force row level security;
alter table public.product_answers enable row level security;
alter table public.product_answers force row level security;
revoke all on public.product_questions from public, anon, authenticated;
revoke all on public.product_answers from public, anon, authenticated;
grant select, insert, update on public.product_questions to service_role;
grant select, insert, update on public.product_answers to service_role;

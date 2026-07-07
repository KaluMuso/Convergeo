-- M03-P07: admin-tunable platform config tables + seeds (FK-free; uses has_role from 0002)

-- ---------------------------------------------------------------------------
-- Shared updated_at trigger
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- commission_rates (D4 category commissions in basis points)
-- ---------------------------------------------------------------------------
create table public.commission_rates (
  category_key text primary key,
  rate_bps integer not null check (rate_bps >= 0 and rate_bps <= 10000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger commission_rates_set_updated_at
  before update on public.commission_rates
  for each row execute function public.set_updated_at();

insert into public.commission_rates (category_key, rate_bps) values
  ('electronics', 500),
  ('home', 800),
  ('fashion_beauty', 1000),
  ('services', 1200),
  ('event_tickets', 500),
  ('supplies', 300),
  ('groceries', 500),
  ('default', 800),
  ('free_events', 0);

-- ---------------------------------------------------------------------------
-- delivery_zones (Lusaka bands; free-delivery threshold lives in platform_config)
-- ---------------------------------------------------------------------------
create table public.delivery_zones (
  zone_key text primary key,
  label text not null,
  fee_ngwee bigint not null check (fee_ngwee >= 0),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger delivery_zones_set_updated_at
  before update on public.delivery_zones
  for each row execute function public.set_updated_at();

insert into public.delivery_zones (zone_key, label, fee_ngwee, active) values
  ('lusaka_a', 'Lusaka Band A (central)', 3000, true),
  ('lusaka_b', 'Lusaka Band B (mid-ring)', 4500, true),
  ('lusaka_c', 'Lusaka Band C (outer)', 6500, true);

-- ---------------------------------------------------------------------------
-- platform_config (typed runtime knobs — values stored as jsonb scalars)
-- ---------------------------------------------------------------------------
create table public.platform_config (
  key text primary key,
  value jsonb not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger platform_config_set_updated_at
  before update on public.platform_config
  for each row execute function public.set_updated_at();

insert into public.platform_config (key, value, description) values
  (
    'cod_cap_ngwee',
    '50000'::jsonb,
  -- F8: founder to confirm D12 COD cap (≤K500 recommended)
    'Maximum order total (ngwee) eligible for cash-on-delivery — K500 = 50_000 ngwee'
  ),
  (
    'free_delivery_threshold_ngwee',
    '20000'::jsonb,
    'Lusaka free delivery threshold (ngwee) — K200 = 20_000 ngwee (D16)'
  ),
  ('reservation_ttl_min', '15'::jsonb, 'Cart/inventory reservation TTL in minutes'),
  ('ai_guest_quota', '3'::jsonb, 'Ask Vergeo guest question quota (D23)'),
  ('ai_free_monthly_quota', '25'::jsonb, 'Ask Vergeo free-account monthly quota (D23)'),
  ('ai_monthly_cap_usd', '15'::jsonb, 'Global Ask Vergeo monthly spend cap in USD (D23)'),
  ('release_after_delivered_hours', '48'::jsonb, 'Auto-release escrow hours after delivered status (D5)'),
  ('release_after_shipped_days', '7'::jsonb, 'Auto-release escrow days after shipped fallback (D5)');

-- ---------------------------------------------------------------------------
-- feature_flags (all off at launch)
-- ---------------------------------------------------------------------------
create table public.feature_flags (
  flag text primary key,
  enabled boolean not null default false,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger feature_flags_set_updated_at
  before update on public.feature_flags
  for each row execute function public.set_updated_at();

insert into public.feature_flags (flag, enabled, description) values
  ('paid_tiers', false, 'Vendor subscription tiers (D3) — off at launch'),
  ('abandoned_cart', false, 'Abandoned-cart recovery nudges'),
  ('wallet', false, 'Vergeo wallet / store credit'),
  ('zamtel_collections', false, 'Zamtel MoMo collections — pending F9a');

-- ---------------------------------------------------------------------------
-- merch_slots (home merchandising; hero placeholder for renderer)
-- ---------------------------------------------------------------------------
create table public.merch_slots (
  id uuid primary key default gen_random_uuid(),
  slot_key text not null,
  variant_key text not null,
  payload jsonb not null default '{}'::jsonb,
  schedule_from timestamptz,
  schedule_to timestamptz,
  position integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index merch_slots_slot_key_position_idx
  on public.merch_slots (slot_key, position);

create trigger merch_slots_set_updated_at
  before update on public.merch_slots
  for each row execute function public.set_updated_at();

insert into public.merch_slots (slot_key, variant_key, payload, schedule_from, position, active) values
  (
    'hero',
    'editorial-light',
    '{"title_key": "merch.hero.placeholder.title", "subtitle_key": "merch.hero.placeholder.subtitle"}'::jsonb,
    now(),
    0,
    true
  );

-- ---------------------------------------------------------------------------
-- prohibited_categories (D8 launch fence)
-- ---------------------------------------------------------------------------
create table public.prohibited_categories (
  key text primary key,
  reason text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger prohibited_categories_set_updated_at
  before update on public.prohibited_categories
  for each row execute function public.set_updated_at();

insert into public.prohibited_categories (key, reason) values
  ('salaula', 'Used clothing (salaula) excluded from launch catalog (D8)'),
  ('used_phones', 'Used phones excluded — selective new phones only (D8)'),
  ('fresh_produce', 'Fresh produce excluded at launch (D8)'),
  ('alcohol', 'Alcohol excluded at launch (D8)'),
  ('pharma', 'Pharmaceuticals excluded at launch (D8)'),
  ('live_animals', 'Live animals excluded at launch (D8)'),
  ('heavy_building_materials', 'Heavy building materials (cement/sand/aggregates) excluded (D8)');

-- ---------------------------------------------------------------------------
-- vendor_quotas (KYC tier caps — D9 T1 at launch)
-- ---------------------------------------------------------------------------
create table public.vendor_quotas (
  tier integer primary key check (tier in (1, 2, 3)),
  max_listings integer not null,
  first_orders_cap_ngwee bigint,
  first_orders_count integer,
  payout_velocity jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger vendor_quotas_set_updated_at
  before update on public.vendor_quotas
  for each row execute function public.set_updated_at();

insert into public.vendor_quotas (tier, max_listings, first_orders_cap_ngwee, first_orders_count, payout_velocity) values
  (1, 30, 50000, 5, '{"note": "T1 Seller caps — first 5 orders ≤K500 each (D9)"}'::jsonb),
  (2, 9999, null, null, '{"note": "T2 Verified Business — caps lifted"}'::jsonb),
  (3, 9999, null, null, '{"note": "T3 Premium — caps lifted"}'::jsonb);

-- ---------------------------------------------------------------------------
-- config_audit (append-only; written by trigger, not clients)
-- ---------------------------------------------------------------------------
create table public.config_audit (
  id uuid primary key default gen_random_uuid(),
  actor uuid,
  table_name text not null,
  row_key text not null,
  before jsonb,
  after jsonb,
  at timestamptz not null default now()
);

create index config_audit_table_name_at_idx
  on public.config_audit (table_name, at desc);

-- ---------------------------------------------------------------------------
-- Audit trigger (security definer — bypasses RLS for inserts)
-- ---------------------------------------------------------------------------
create or replace function public.audit_config_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  rec jsonb;
  row_key text;
begin
  if tg_op = 'DELETE' then
    rec := to_jsonb(old);
  else
    rec := to_jsonb(new);
  end if;

  row_key := coalesce(
    rec ->> 'category_key',
    rec ->> 'zone_key',
    rec ->> 'key',
    rec ->> 'flag',
    rec ->> 'id',
    rec ->> 'tier'
  );

  insert into public.config_audit (actor, table_name, row_key, before, after)
  values (
    auth.uid(),
    tg_table_name,
    row_key,
    case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) else null end,
    case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) else null end
  );

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create trigger commission_rates_audit
  after insert or update or delete on public.commission_rates
  for each row execute function public.audit_config_change();

create trigger delivery_zones_audit
  after insert or update or delete on public.delivery_zones
  for each row execute function public.audit_config_change();

create trigger platform_config_audit
  after insert or update or delete on public.platform_config
  for each row execute function public.audit_config_change();

create trigger feature_flags_audit
  after insert or update or delete on public.feature_flags
  for each row execute function public.audit_config_change();

create trigger merch_slots_audit
  after insert or update or delete on public.merch_slots
  for each row execute function public.audit_config_change();

create trigger prohibited_categories_audit
  after insert or update or delete on public.prohibited_categories
  for each row execute function public.audit_config_change();

create trigger vendor_quotas_audit
  after insert or update or delete on public.vendor_quotas
  for each row execute function public.audit_config_change();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.commission_rates enable row level security;
alter table public.delivery_zones enable row level security;
alter table public.platform_config enable row level security;
alter table public.feature_flags enable row level security;
alter table public.merch_slots enable row level security;
alter table public.prohibited_categories enable row level security;
alter table public.vendor_quotas enable row level security;
alter table public.config_audit enable row level security;

alter table public.commission_rates force row level security;
alter table public.delivery_zones force row level security;
alter table public.platform_config force row level security;
alter table public.feature_flags force row level security;
alter table public.merch_slots force row level security;
alter table public.prohibited_categories force row level security;
alter table public.vendor_quotas force row level security;
alter table public.config_audit force row level security;

-- commission_rates: public read (checkout/PLP commission display), admin write
create policy commission_rates_select_public
  on public.commission_rates
  for select
  to anon, authenticated
  using (true);

create policy commission_rates_insert_admin
  on public.commission_rates
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy commission_rates_update_admin
  on public.commission_rates
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy commission_rates_delete_admin
  on public.commission_rates
  for delete
  to authenticated
  using (public.has_role('admin'));

-- delivery_zones: public read (delivery fee display), admin write
create policy delivery_zones_select_public
  on public.delivery_zones
  for select
  to anon, authenticated
  using (true);

create policy delivery_zones_insert_admin
  on public.delivery_zones
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy delivery_zones_update_admin
  on public.delivery_zones
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy delivery_zones_delete_admin
  on public.delivery_zones
  for delete
  to authenticated
  using (public.has_role('admin'));

-- platform_config: authenticated read (server + vendor/admin apps); admin write
create policy platform_config_select_authenticated
  on public.platform_config
  for select
  to authenticated
  using (true);

create policy platform_config_insert_admin
  on public.platform_config
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy platform_config_update_admin
  on public.platform_config
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy platform_config_delete_admin
  on public.platform_config
  for delete
  to authenticated
  using (public.has_role('admin'));

-- feature_flags: public read (client gating), admin write
create policy feature_flags_select_public
  on public.feature_flags
  for select
  to anon, authenticated
  using (true);

create policy feature_flags_insert_admin
  on public.feature_flags
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy feature_flags_update_admin
  on public.feature_flags
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy feature_flags_delete_admin
  on public.feature_flags
  for delete
  to authenticated
  using (public.has_role('admin'));

-- merch_slots: public read (home renderer), admin write
create policy merch_slots_select_public
  on public.merch_slots
  for select
  to anon, authenticated
  using (true);

create policy merch_slots_insert_admin
  on public.merch_slots
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy merch_slots_update_admin
  on public.merch_slots
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy merch_slots_delete_admin
  on public.merch_slots
  for delete
  to authenticated
  using (public.has_role('admin'));

-- prohibited_categories: admin read/write (moderation + admin UI; API uses service role)
create policy prohibited_categories_select_admin
  on public.prohibited_categories
  for select
  to authenticated
  using (public.has_role('admin'));

create policy prohibited_categories_insert_admin
  on public.prohibited_categories
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy prohibited_categories_update_admin
  on public.prohibited_categories
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy prohibited_categories_delete_admin
  on public.prohibited_categories
  for delete
  to authenticated
  using (public.has_role('admin'));

-- vendor_quotas: admin read/write (onboarding enforcement via API service role)
create policy vendor_quotas_select_admin
  on public.vendor_quotas
  for select
  to authenticated
  using (public.has_role('admin'));

create policy vendor_quotas_insert_admin
  on public.vendor_quotas
  for insert
  to authenticated
  with check (public.has_role('admin'));

create policy vendor_quotas_update_admin
  on public.vendor_quotas
  for update
  to authenticated
  using (public.has_role('admin'))
  with check (public.has_role('admin'));

create policy vendor_quotas_delete_admin
  on public.vendor_quotas
  for delete
  to authenticated
  using (public.has_role('admin'));

-- config_audit: admin read only; no client writes (trigger is security definer)
create policy config_audit_select_admin
  on public.config_audit
  for select
  to authenticated
  using (public.has_role('admin'));

-- ---------------------------------------------------------------------------
-- Data API grants (auto_expose_new_tables is off in config.toml)
-- ---------------------------------------------------------------------------
grant select on public.commission_rates to anon, authenticated;
grant select on public.delivery_zones to anon, authenticated;
grant select on public.platform_config to authenticated;
grant select on public.feature_flags to anon, authenticated;
grant select on public.merch_slots to anon, authenticated;
grant select on public.prohibited_categories to authenticated;
grant select on public.vendor_quotas to authenticated;
grant select on public.config_audit to authenticated;

grant insert, update, delete on public.commission_rates to authenticated;
grant insert, update, delete on public.delivery_zones to authenticated;
grant insert, update, delete on public.platform_config to authenticated;
grant insert, update, delete on public.feature_flags to authenticated;
grant insert, update, delete on public.merch_slots to authenticated;
grant insert, update, delete on public.prohibited_categories to authenticated;
grant insert, update, delete on public.vendor_quotas to authenticated;

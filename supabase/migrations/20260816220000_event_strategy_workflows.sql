-- Events strategy remaining workflows (Codex audit close-out).
-- Additive. Operational tables stay service-role only.

-- ---------------------------------------------------------------------------
-- Ticket economics: perks, multi-day pass scope, organiser fee/ID/high-value flags
-- ---------------------------------------------------------------------------
alter table public.ticket_types
  add column if not exists perks text,
  add column if not exists pass_kind text not null default 'instance'
    check (pass_kind in ('instance', 'event_pass'));

comment on column public.ticket_types.perks is
  'Optional organiser-authored perk copy shown on the ticket type (VIP lounge, merch, etc.).';
comment on column public.ticket_types.pass_kind is
  'instance = valid only for the purchased instance; event_pass = valid on any scheduled date of the event.';

alter table public.events
  add column if not exists city text,
  add column if not exists id_check_enabled boolean not null default false,
  add column if not exists high_value_verified_at timestamptz,
  add column if not exists high_value_verified_by uuid references auth.users (id) on delete set null;

comment on column public.events.city is
  'Optional city label for Where-lens filtering (Lusaka, Ndola, Kitwe, Livingstone, Kabwe, …).';
comment on column public.events.id_check_enabled is
  'When true, door staff are instructed to ID-match holders of tickets priced over K500.';
comment on column public.events.high_value_verified_at is
  'Set by admin after the K100,000 pre-event verification call. Null = not verified.';

create index if not exists events_city_idx on public.events (city)
  where city is not null;

-- ---------------------------------------------------------------------------
-- Capacity tree: allocated tier sums must not exceed instance (venue) capacity
-- ---------------------------------------------------------------------------
create or replace function public.enforce_ticket_allocation_capacity_tree()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_instance_id uuid;
  v_capacity int;
  v_allocated bigint;
begin
  v_instance_id := coalesce(new.instance_id, old.instance_id);
  select ei.capacity into v_capacity
  from public.event_instances ei
  where ei.id = v_instance_id;
  if v_capacity is null then
    return coalesce(new, old);
  end if;

  select coalesce(sum(tti.allocation), 0) into v_allocated
  from public.ticket_type_instances tti
  where tti.instance_id = v_instance_id;

  if v_allocated > v_capacity then
    raise exception using
      errcode = '23514',
      message = 'ticket type allocations exceed instance capacity',
      hint = 'Reduce tier allocations so they sum to at most the venue capacity.';
  end if;
  return coalesce(new, old);
end;
$$;

drop trigger if exists ticket_type_instances_capacity_tree on public.ticket_type_instances;
create trigger ticket_type_instances_capacity_tree
  after insert or update or delete on public.ticket_type_instances
  for each row
  execute function public.enforce_ticket_allocation_capacity_tree();

revoke all on function public.enforce_ticket_allocation_capacity_tree() from public;
revoke execute on function public.enforce_ticket_allocation_capacity_tree()
  from public, anon, authenticated;
grant execute on function public.enforce_ticket_allocation_capacity_tree()
  to postgres, service_role;

create or replace function public.enforce_instance_capacity_vs_allocations()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_allocated bigint;
begin
  select coalesce(sum(tti.allocation), 0) into v_allocated
  from public.ticket_type_instances tti
  where tti.instance_id = new.id;
  if v_allocated > new.capacity then
    raise exception using
      errcode = '23514',
      message = 'instance capacity is below allocated ticket-type sums';
  end if;
  return new;
end;
$$;

drop trigger if exists event_instances_capacity_tree on public.event_instances;
create trigger event_instances_capacity_tree
  after update of capacity on public.event_instances
  for each row
  execute function public.enforce_instance_capacity_vs_allocations();

revoke all on function public.enforce_instance_capacity_vs_allocations() from public;
revoke execute on function public.enforce_instance_capacity_vs_allocations()
  from public, anon, authenticated;
grant execute on function public.enforce_instance_capacity_vs_allocations()
  to postgres, service_role;

-- ---------------------------------------------------------------------------
-- Checkout platform fee (buyer pass-through). Additive; default 0 preserves
-- absorb-fee totals (subtotal + delivery).
-- ---------------------------------------------------------------------------
alter table public.checkout_groups
  add column if not exists platform_fee_ngwee bigint not null default 0
    check (platform_fee_ngwee >= 0);
alter table public.orders
  add column if not exists platform_fee_ngwee bigint not null default 0
    check (platform_fee_ngwee >= 0);

comment on column public.checkout_groups.platform_fee_ngwee is
  'Buyer-paid platform fee in ngwee. Zero when the organiser absorbs the commission.';
comment on column public.orders.platform_fee_ngwee is
  'Buyer-paid platform fee snapshot for this vendor order. Not organiser settlement.';

-- ---------------------------------------------------------------------------
-- Event-specific disputes
-- ---------------------------------------------------------------------------
alter table public.disputes
  add column if not exists kind text not null default 'order'
    check (kind in ('order', 'event_misrepresentation')),
  add column if not exists event_id uuid references public.events (id) on delete set null,
  add column if not exists organiser_respond_by timestamptz;

create index if not exists disputes_event_id_idx on public.disputes (event_id)
  where event_id is not null;
create index if not exists disputes_kind_status_idx on public.disputes (kind, status);

comment on column public.disputes.kind is
  'order = generic order dispute; event_misrepresentation requires photo/video evidence and a 7-day post-event window.';

-- ---------------------------------------------------------------------------
-- Door manual override audit
-- ---------------------------------------------------------------------------
create table if not exists public.event_checkin_overrides (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events (id) on delete cascade,
  ticket_id uuid not null references public.tickets (id) on delete restrict,
  instance_id uuid not null references public.event_instances (id) on delete restrict,
  actor_user_id uuid not null references auth.users (id) on delete restrict,
  reason text not null check (btrim(reason) <> ''),
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists event_checkin_overrides_event_idx
  on public.event_checkin_overrides (event_id, created_at desc);
create index if not exists event_checkin_overrides_ticket_idx
  on public.event_checkin_overrides (ticket_id);

alter table public.event_checkin_overrides enable row level security;
alter table public.event_checkin_overrides force row level security;
revoke all on table public.event_checkin_overrides from anon, authenticated;
grant all on table public.event_checkin_overrides to service_role;

-- ---------------------------------------------------------------------------
-- Promo redemptions (codes/affiliates tables already exist)
-- ---------------------------------------------------------------------------
create table if not exists public.event_promo_redemptions (
  id uuid primary key default gen_random_uuid(),
  promo_id uuid not null references public.event_promo_codes (id) on delete restrict,
  event_id uuid not null references public.events (id) on delete cascade,
  order_id uuid not null references public.orders (id) on delete restrict,
  customer_id uuid not null references auth.users (id) on delete restrict,
  discount_ngwee bigint not null check (discount_ngwee >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  constraint event_promo_redemptions_order_key unique (order_id)
);
create index if not exists event_promo_redemptions_promo_idx
  on public.event_promo_redemptions (promo_id);

alter table public.event_promo_redemptions enable row level security;
alter table public.event_promo_redemptions force row level security;
revoke all on table public.event_promo_redemptions from anon, authenticated;
grant all on table public.event_promo_redemptions to service_role;

-- ---------------------------------------------------------------------------
-- Platform config: T1 three-event uncap + high-value verification threshold
-- ---------------------------------------------------------------------------
insert into public.platform_config (key, value, description) values
  (
    'organiser_t1_success_events_to_uncap',
    '3'::jsonb,
    'Paid completed events after which a Tier-1 organiser is uncapped (strategy §7.2).'
  ),
  (
    'event_high_value_gmv_ngwee',
    '10000000'::jsonb,
    'Projected paid GMV (ngwee) that requires a pre-event verification call (K100,000).'
  ),
  (
    'event_id_check_threshold_ngwee',
    '50000'::jsonb,
    'Ticket unit price (ngwee) at which optional organiser ID-check is suggested (K500).'
  )
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Hierarchical categories: 11 strategy parents; keep the six launch slugs as children
-- ---------------------------------------------------------------------------
insert into public.event_categories (slug, parent_slug, label_key, sort) values
  ('music', null, 'events.categories.music', 5),
  ('comedy-theatre-parent', null, 'events.categories.comedyTheatreParent', 15),
  ('sports', null, 'events.categories.sports', 25),
  ('conferences-workshops', null, 'events.categories.conferencesWorkshops', 35),
  ('family', null, 'events.categories.family', 45),
  ('religious', null, 'events.categories.religious', 55),
  ('markets', null, 'events.categories.markets', 65),
  ('exhibitions', null, 'events.categories.exhibitions', 75),
  ('nightlife', null, 'events.categories.nightlife', 85),
  ('community', null, 'events.categories.community', 95),
  ('private-events', null, 'events.categories.privateEvents', 105)
on conflict (slug) do nothing;

update public.event_categories set parent_slug = 'conferences-workshops', sort = 36
  where slug = 'workshops' and parent_slug is null;
update public.event_categories set parent_slug = 'comedy-theatre-parent', sort = 16
  where slug = 'comedy-theatre' and parent_slug is null;
update public.event_categories set parent_slug = 'nightlife', sort = 86
  where slug = 'pop-up-dinners' and parent_slug is null;
update public.event_categories set parent_slug = 'exhibitions', sort = 76
  where slug = 'cultural-arts' and parent_slug is null;
update public.event_categories set parent_slug = 'community', sort = 96
  where slug = 'lifestyle-community' and parent_slug is null;
update public.event_categories set parent_slug = 'community', sort = 97
  where slug = 'free-rsvp' and parent_slug is null;

insert into public.event_categories (slug, parent_slug, label_key, sort) values
  ('concerts', 'music', 'events.categories.concerts', 6),
  ('festivals', 'music', 'events.categories.festivals', 7),
  ('gospel', 'music', 'events.categories.gospel', 8),
  ('stand-up', 'comedy-theatre-parent', 'events.categories.standUp', 17),
  ('football', 'sports', 'events.categories.football', 26),
  ('church', 'religious', 'events.categories.church', 56)
on conflict (slug) do nothing;

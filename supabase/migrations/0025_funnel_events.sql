-- M07-P08: Server-side checkout funnel events (GA4-mirror-stable schema for M16-P05).
-- Down (manual): drop table public.funnel_events;

-- ---------------------------------------------------------------------------
-- funnel_events
-- ---------------------------------------------------------------------------
create table public.funnel_events (
  id uuid primary key default gen_random_uuid(),
  stage text not null
    check (stage in (
      'cart_add',
      'checkout_start',
      'step_complete',
      'payment_start',
      'order_placed',
      'abandoned'
    )),
  checkout_group_id uuid references public.checkout_groups (id) on delete cascade,
  customer_id uuid references auth.users (id) on delete set null,
  snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create unique index funnel_events_checkout_group_stage_uidx
  on public.funnel_events (checkout_group_id, stage)
  where checkout_group_id is not null;

create index funnel_events_stage_created_at_idx
  on public.funnel_events (stage, created_at desc);

create index funnel_events_customer_id_created_at_idx
  on public.funnel_events (customer_id, created_at desc)
  where customer_id is not null;

comment on table public.funnel_events is
  'Server-side checkout funnel stages; idempotent per (checkout_group_id, stage). Source of truth for M16 GA4 mirror.';

comment on column public.funnel_events.stage is
  'Funnel stage: cart_add → checkout_start → step_complete → payment_start → order_placed; abandoned on reservation expiry.';

comment on column public.funnel_events.snapshot is
  'Stage-specific JSON payload (cart lines, totals, step metadata) — stable shape for analytics unification.';

-- ---------------------------------------------------------------------------
-- Row level security — admin read; service_role writes
-- ---------------------------------------------------------------------------
alter table public.funnel_events enable row level security;
alter table public.funnel_events force row level security;

create policy funnel_events_admin_select
  on public.funnel_events
  for select
  to authenticated
  using (public.has_role('admin'));

create policy funnel_events_service_role_all
  on public.funnel_events
  for all
  to service_role
  using (true)
  with check (true);

comment on policy funnel_events_admin_select on public.funnel_events is
  'Platform admins may query funnel aggregates; writes are service_role only.';
comment on policy funnel_events_service_role_all on public.funnel_events is
  'API funnel recorder and abandonment sweeper use service_role.';

grant select on table public.funnel_events to authenticated;
grant select, insert, update, delete on table public.funnel_events to service_role;

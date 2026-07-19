-- 0059: Exclusive escrow-drain claim per order (D17 single-drain).
--
-- Refund PRE_RELEASE (escrow → cash) and RELEASE_TO_VENDOR both drain escrow.
-- Without a shared claim, concurrent refund execute + release sweeper can both
-- pass their one-shot checks and double-pay (customer refund + vendor release).
--
-- This table is a durable mutex: at most one of ('refund', 'release') may claim
-- an order. POST_RELEASE clawback does not need a claim (release already won).
-- Service-role / migrations only — no client policies.
--
-- Additive; reversible: DROP TABLE public.order_money_gates;

create table public.order_money_gates (
  order_id uuid primary key references public.orders (id) on delete restrict,
  gate text not null check (gate in ('refund', 'release')),
  created_at timestamptz not null default timezone('utc', now())
);

comment on table public.order_money_gates is
  'Exclusive escrow-drain claim (refund vs release). Service-role only; enforces D17 single-drain under concurrency.';

alter table public.order_money_gates enable row level security;
alter table public.order_money_gates force row level security;

-- Zero client policies — service_role / migrations only (same posture as user_roles).

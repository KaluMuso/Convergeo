-- M10-P02: Per-customer purchase cap on ticket types.
-- Reversible:
--   ALTER TABLE public.ticket_types DROP COLUMN IF EXISTS per_customer_cap;

alter table public.ticket_types
  add column if not exists per_customer_cap int
    check (per_customer_cap is null or per_customer_cap > 0);

comment on column public.ticket_types.per_customer_cap is
  'Maximum tickets of this type a single holder may hold for an instance; NULL = unlimited.';

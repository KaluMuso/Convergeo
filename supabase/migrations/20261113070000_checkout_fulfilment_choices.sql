-- POST /orders server-authoritative fulfilment (order-integrity follow-up #1).
--
-- The fulfilment step records each vendor group's delivery/pickup choice and the
-- delivery zone it priced, so order creation can recompute fulfilment and
-- delivery fees from server state instead of trusting the request body.
-- Shape: [{"vendor_id": uuid-text, "fulfilment": "delivery"|"pickup",
--          "delivery_zone": text|null}, ...]. NULL = fulfilment not confirmed yet;
-- POST /orders refuses such a session with orders.fulfilment_not_confirmed.
--
-- Additive only. checkout_groups has no client write policies (0005), so only the
-- service role can set this column.
--
-- Reversible rollback:
--   ALTER TABLE public.checkout_groups DROP COLUMN IF EXISTS fulfilment_choices;

alter table public.checkout_groups
  add column if not exists fulfilment_choices jsonb;

alter table public.checkout_groups
  drop constraint if exists checkout_groups_fulfilment_choices_array_check;
alter table public.checkout_groups
  add constraint checkout_groups_fulfilment_choices_array_check
  check (fulfilment_choices is null or jsonb_typeof(fulfilment_choices) = 'array');

comment on column public.checkout_groups.fulfilment_choices is
  'Server-recorded per-vendor fulfilment choices from POST /checkout/steps/fulfilment; POST /orders re-prices from these.';

-- One active/settled refund per *source* (return / dispute / admin key), not per
-- order. FIX-B's order-scoped unique (0032) blocked a second item return on a
-- multi-item order and caused execute_refund to short-circuit to the first
-- refund's wrong amount.
--
-- Additive + reversible.
-- Down (manual):
--   drop index public.refunds_source_key_active_uniq;
--   alter table public.refunds drop column source_key;
--   recreate refunds_order_id_active_uniq from 0032;

alter table public.refunds
  add column if not exists source_key text;

-- Backfill from caller idempotency key stored in breakdown, else order fallback
-- (matches app _stable_ledger_key_base / dispute-admin whole-order path).
update public.refunds
set source_key = coalesce(
  nullif(btrim(breakdown->>'idempotency_key'), ''),
  'refund-order-' || order_id::text
)
where source_key is null;

do $$
declare
  offending int;
begin
  select count(*)
  into offending
  from (
    select source_key
    from public.refunds
    where status in ('pending', 'processing', 'completed')
      and source_key is not null
    group by source_key
    having count(*) > 1
  ) dups;

  if offending > 0 then
    raise exception
      'cannot add refunds_source_key_active_uniq: % source_key(s) already have multiple active/settled refunds',
      offending;
  end if;
end $$;

alter table public.refunds
  alter column source_key set not null;

comment on column public.refunds.source_key is
  'Stable caller identity (return-/dispute-/refund-order-* key). Dedup + unique active refunds.';

drop index if exists public.refunds_order_id_active_uniq;

create unique index refunds_source_key_active_uniq
  on public.refunds (source_key)
  where status in ('pending', 'processing', 'completed');

comment on index public.refunds_source_key_active_uniq is
  'At-most-one active/settled refund per source_key; allows multi-item returns on one order.';

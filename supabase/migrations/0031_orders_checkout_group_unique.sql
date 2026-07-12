-- FIX-A: orders-create concurrency backstop — one order per (checkout_group, vendor).
--
-- Bug #2 (CRITICAL): two concurrent checkout submits for the same checkout_group
-- could each insert a full per-vendor order set, because the in-tx guard did not
-- serialize on checkout_groups.status and orders had no uniqueness on
-- (checkout_group_id, vendor_id). The real fix is the in-tx status recheck under
-- FOR UPDATE plus conditional hold consumption (services/api). This UNIQUE index
-- is the DB backstop: a duplicate order set becomes a hard error, never a silent
-- double. A checkout group fans out to at most ONE order per vendor by design, so
-- this index is a true invariant (no legitimate row violates it).
--
-- Additive-only. No column/function/type change (packages/types unaffected).
--
-- Down (manual):
--   drop index if exists public.orders_checkout_group_vendor_key;

create unique index if not exists orders_checkout_group_vendor_key
  on public.orders (checkout_group_id, vendor_id);

comment on index public.orders_checkout_group_vendor_key is
  'FIX-A backstop: at most one order per (checkout_group, vendor) — blocks duplicate order sets from concurrent checkout submits.';

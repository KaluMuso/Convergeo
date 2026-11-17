-- Unpaid prepaid order auto-cancel: admin-editable window (hours).
--
-- The internal sweeper POST /internal/order-jobs/cancel-unpaid cancels PLACED
-- prepaid (non-COD) orders still without money or a live payment attempt this
-- many hours after creation, through the guarded transition_order path (system
-- actor, audit note). The code default is also 12 when the row is missing.
--
-- No schema change: one row in the existing `platform_config` table.
-- Additive and idempotent.
--
-- Reversible: `delete from public.platform_config where key = 'unpaid_order_cancel_hours';`

insert into public.platform_config (key, value, description) values
  (
    'unpaid_order_cancel_hours',
    '12'::jsonb,
    'Hours after creation before an unpaid PREPAID order is auto-cancelled (COD never; in-flight payments are kept).'
  )
on conflict (key) do nothing;

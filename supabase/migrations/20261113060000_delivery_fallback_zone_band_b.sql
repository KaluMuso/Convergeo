-- Founder decision (13 Nov 2026): a typed Lusaka landmark the keyword matcher
-- cannot place is charged Band B (K45). Read by
-- services/api/app/routers/checkout.py::_load_fallback_delivery_zone, which
-- expects platform_config.value to be a JSON string naming an active zone key.
-- Additive and idempotent. Down: delete from public.platform_config
--   where key = 'delivery_fallback_zone';

insert into public.platform_config (key, value, description)
values (
  'delivery_fallback_zone',
  '"lusaka_b"'::jsonb,
  'Delivery zone for a typed Lusaka landmark the matcher cannot place (founder decision 2026-11-13: Band B)'
)
on conflict (key) do update
  set value = excluded.value,
      description = excluded.description;

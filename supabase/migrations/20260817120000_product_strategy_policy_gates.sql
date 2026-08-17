-- Product-strategy policy seed, extra taxonomy (Phase 2/3, hidden), and
-- fail-closed feature flags for Ask maturity + cancel-rate auto-suspend.
-- Additive and idempotent. Existing Phase-1 categories stay shoppable.

-- ---------------------------------------------------------------------------
-- Feature flags and platform knobs (default OFF — preserve live Ask / no
-- automatic vendor suspension until an operator enables them).
-- ---------------------------------------------------------------------------

insert into public.feature_flags (flag, enabled, description) values
  (
    'ask_maturity_gate',
    false,
    'When enabled, Ask Vergeo refuses until ask_min_completed_orders completed orders exist'
  ),
  (
    'cancel_rate_auto_suspend',
    false,
    'When enabled, vendors at ≥10% cancel-rate (min 10 orders) are auto-suspended'
  )
on conflict (flag) do nothing;

insert into public.platform_config (key, value, description) values
  (
    'ask_min_completed_orders',
    '10000'::jsonb,
    'Completed-order threshold for the Ask Vergeo data-maturity gate'
  )
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Phase-1 category policy: every existing category is A/B, enabled, phase 1.
-- Electronics is high-risk (counterfeit). Missing-policy rows stay shoppable
-- so this insert is additive even if a category is added later without a row.
-- ---------------------------------------------------------------------------

insert into public.category_product_policies (
  category_id,
  phase,
  enabled,
  allowed_product_classes,
  minimum_kyc_tier,
  required_licence_types,
  evidence_requirements,
  high_risk
)
select
  c.id,
  1,
  true,
  array['A', 'B']::char(1)[],
  1,
  '{}'::text[],
  '{}'::jsonb,
  c.path = 'electronics' or c.path like 'electronics/%'
from public.categories c
on conflict (category_id) do nothing;

-- ---------------------------------------------------------------------------
-- Five additional departments (13 total) for Phase 2/3. Public catalogue
-- hides categories whose policy.enabled is false.
-- ---------------------------------------------------------------------------

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values
  ('c00000009-0000-4000-8000-000000000001', null, 'Agriculture & Commodities', 'agriculture-commodities', 'agriculture-commodities', 'groceries', 8),
  ('c00000010-0000-4000-8000-000000000001', null, 'Auto Parts', 'auto-parts', 'auto-parts', 'home', 9),
  ('c00000011-0000-4000-8000-000000000001', null, 'Building Materials', 'building-materials', 'building-materials', 'home', 10),
  ('c00000012-0000-4000-8000-000000000001', null, 'Used Goods', 'used-goods', 'used-goods', 'electronics', 11),
  ('c00000013-0000-4000-8000-000000000001', null, 'Made to Order', 'made-to-order', 'made-to-order', 'fashion_beauty', 12)
on conflict (id) do nothing;

insert into public.categories (id, parent_id, name, slug, path, commission_key, position)
values
  ('d00000080-0000-4000-8000-000000000001', 'c00000009-0000-4000-8000-000000000001', 'Maize & Mealie', 'maize-mealie', 'agriculture-commodities/maize-mealie', 'groceries', 0),
  ('d00000081-0000-4000-8000-000000000001', 'c00000009-0000-4000-8000-000000000001', 'Beans & Pulses', 'beans-pulses', 'agriculture-commodities/beans-pulses', 'groceries', 1),
  ('d00000082-0000-4000-8000-000000000001', 'c00000009-0000-4000-8000-000000000001', 'Fresh Produce', 'fresh-produce', 'agriculture-commodities/fresh-produce', 'groceries', 2),
  ('d00000083-0000-4000-8000-000000000001', 'c00000009-0000-4000-8000-000000000001', 'Livestock Feed', 'livestock-feed', 'agriculture-commodities/livestock-feed', 'groceries', 3),
  ('d00000084-0000-4000-8000-000000000001', 'c00000009-0000-4000-8000-000000000001', 'Fertiliser', 'fertiliser', 'agriculture-commodities/fertiliser', 'groceries', 4),
  ('d00000085-0000-4000-8000-000000000001', 'c00000010-0000-4000-8000-000000000001', 'Engine Parts', 'engine-parts', 'auto-parts/engine-parts', 'home', 0),
  ('d00000086-0000-4000-8000-000000000001', 'c00000010-0000-4000-8000-000000000001', 'Tyres', 'tyres', 'auto-parts/tyres', 'home', 1),
  ('d00000087-0000-4000-8000-000000000001', 'c00000010-0000-4000-8000-000000000001', 'Batteries', 'batteries', 'auto-parts/batteries', 'home', 2),
  ('d00000088-0000-4000-8000-000000000001', 'c00000010-0000-4000-8000-000000000001', 'Body & Lights', 'body-lights', 'auto-parts/body-lights', 'home', 3),
  ('d00000089-0000-4000-8000-000000000001', 'c00000010-0000-4000-8000-000000000001', 'Oils & Fluids', 'oils-fluids', 'auto-parts/oils-fluids', 'home', 4),
  ('d00000090-0000-4000-8000-000000000001', 'c00000011-0000-4000-8000-000000000001', 'Cement & Aggregates', 'cement-aggregates', 'building-materials/cement-aggregates', 'home', 0),
  ('d00000091-0000-4000-8000-000000000001', 'c00000011-0000-4000-8000-000000000001', 'Timber', 'timber', 'building-materials/timber', 'home', 1),
  ('d00000092-0000-4000-8000-000000000001', 'c00000011-0000-4000-8000-000000000001', 'Roofing', 'roofing', 'building-materials/roofing', 'home', 2),
  ('d00000093-0000-4000-8000-000000000001', 'c00000011-0000-4000-8000-000000000001', 'Steel & Mesh', 'steel-mesh', 'building-materials/steel-mesh', 'home', 3),
  ('d00000094-0000-4000-8000-000000000001', 'c00000011-0000-4000-8000-000000000001', 'Tiles & Sanitary', 'tiles-sanitary', 'building-materials/tiles-sanitary', 'home', 4),
  ('d00000095-0000-4000-8000-000000000001', 'c00000012-0000-4000-8000-000000000001', 'Used Phones', 'used-phones', 'used-goods/used-phones', 'electronics', 0),
  ('d00000096-0000-4000-8000-000000000001', 'c00000012-0000-4000-8000-000000000001', 'Used Vehicles', 'used-vehicles', 'used-goods/used-vehicles', 'electronics', 1),
  ('d00000097-0000-4000-8000-000000000001', 'c00000012-0000-4000-8000-000000000001', 'Used Appliances', 'used-appliances', 'used-goods/used-appliances', 'electronics', 2),
  ('d00000098-0000-4000-8000-000000000001', 'c00000012-0000-4000-8000-000000000001', 'Used Furniture', 'used-furniture', 'used-goods/used-furniture', 'home', 3),
  ('d00000099-0000-4000-8000-000000000001', 'c00000012-0000-4000-8000-000000000001', 'Parts Not Working', 'parts-not-working', 'used-goods/parts-not-working', 'electronics', 4),
  ('d00000100-0000-4000-8000-000000000001', 'c00000013-0000-4000-8000-000000000001', 'Tailoring', 'tailoring', 'made-to-order/tailoring', 'fashion_beauty', 0),
  ('d00000101-0000-4000-8000-000000000001', 'c00000013-0000-4000-8000-000000000001', 'Custom Furniture', 'custom-furniture', 'made-to-order/custom-furniture', 'home', 1),
  ('d00000102-0000-4000-8000-000000000001', 'c00000013-0000-4000-8000-000000000001', 'Print & Signage', 'print-signage', 'made-to-order/print-signage', 'supplies', 2),
  ('d00000103-0000-4000-8000-000000000001', 'c00000013-0000-4000-8000-000000000001', 'Fabrication', 'fabrication', 'made-to-order/fabrication', 'home', 3),
  ('d00000104-0000-4000-8000-000000000001', 'c00000013-0000-4000-8000-000000000001', 'Bespoke Gifts', 'bespoke-gifts', 'made-to-order/bespoke-gifts', 'fashion_beauty', 4)
on conflict (id) do nothing;

insert into public.category_product_policies (
  category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier,
  required_licence_types, evidence_requirements, high_risk
)
select c.id, 2, false, array['A', 'B', 'C']::char(1)[], 1, '{}'::text[], '{}'::jsonb, false
from public.categories c
where c.path = 'agriculture-commodities' or c.path like 'agriculture-commodities/%'
on conflict (category_id) do nothing;

insert into public.category_product_policies (
  category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier,
  required_licence_types, evidence_requirements, high_risk
)
select c.id, 2, false, array['A', 'B']::char(1)[], 2, '{}'::text[], '{}'::jsonb, true
from public.categories c
where c.path = 'auto-parts' or c.path like 'auto-parts/%'
on conflict (category_id) do nothing;

insert into public.category_product_policies (
  category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier,
  required_licence_types, evidence_requirements, high_risk
)
select c.id, 3, false, array['A', 'B', 'C']::char(1)[], 2, '{}'::text[], '{}'::jsonb, false
from public.categories c
where c.path = 'building-materials' or c.path like 'building-materials/%'
on conflict (category_id) do nothing;

insert into public.category_product_policies (
  category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier,
  required_licence_types, evidence_requirements, high_risk
)
select
  c.id,
  2,
  false,
  array['D']::char(1)[],
  2,
  '{}'::text[],
  jsonb_build_object('photo', true, 'condition_report', true),
  true
from public.categories c
where c.path = 'used-goods' or c.path like 'used-goods/%'
on conflict (category_id) do nothing;

insert into public.category_product_policies (
  category_id, phase, enabled, allowed_product_classes, minimum_kyc_tier,
  required_licence_types, evidence_requirements, high_risk
)
select c.id, 3, false, array['E']::char(1)[], 1, '{}'::text[], '{}'::jsonb, false
from public.categories c
where c.path = 'made-to-order' or c.path like 'made-to-order/%'
on conflict (category_id) do nothing;

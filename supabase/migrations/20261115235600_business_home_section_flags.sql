-- Business Home — per-section switches for products, services and events.
--
-- Founder rule: a Business Home section (/v/[slug]) shows only when its
-- feature is ON *and* the shop has at least one live item in it. Clips use the
-- existing `clips` flag (0077) and offers use `business_offers`
-- (20261113233000). These three rows cover the live selling sections.
--
-- They are kill switches for surfaces that are already live, so they are
-- inserted ON, and the API treats a missing row as ON (clips/offers stay
-- fail-closed). Turning one off hides that section on every Business Home.
--
-- No schema change: rows in the existing `feature_flags` table. Additive and
-- idempotent (an operator's existing choice is never overwritten).
--
-- Reversible:
--   delete from public.feature_flags
--   where flag in ('business_home_products', 'business_home_services', 'business_home_events');

insert into public.feature_flags (flag, enabled, description) values
  (
    'business_home_products',
    true,
    'Business Home: show the Products section on /v/[slug] (only when the shop has live products).'
  ),
  (
    'business_home_services',
    true,
    'Business Home: show the Services section on /v/[slug] (only when the shop has active services).'
  ),
  (
    'business_home_events',
    true,
    'Business Home: show the Events section on /v/[slug] (only when the shop has an upcoming event).'
  )
on conflict (flag) do nothing;

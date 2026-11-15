-- Business Home — offers block flag (growth blueprint §8, phase B).
--
-- No coupons table exists on this base yet, so the customer storefront's
-- "Offers" block is a placeholder that stays hidden until this flag is turned
-- on (and, in practice, until shop-funded coupons ship). Same table and
-- fail-closed posture as the `clips` flags (0077): a missing row is OFF.
--
-- No schema change: one row in the existing `feature_flags` table, inserted
-- OFF. Additive and idempotent.
--
-- Reversible: `delete from public.feature_flags where flag = 'business_offers';`

insert into public.feature_flags (flag, enabled, description) values
  (
    'business_offers',
    false,
    'Business Home: show the shop''s own offers/coupons block on /v/[slug]. OFF until shop coupons ship.'
  )
on conflict (flag) do nothing;

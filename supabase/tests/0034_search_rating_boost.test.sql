-- 0034 test: Bayesian review rating feeds the search_apply_boost ranking multiplier.
-- Pure-function assertions (no seeding / RLS) — run: supabase test db (pgTAP).

begin;

set local search_path to public, extensions;

select extensions.plan(6);

-- No rating signal (absent key) is neutral — NOT a spurious boost. This is the
-- coalesce guard: least()/greatest() ignore NULLs, so an unguarded term would
-- have handed every unreviewed row the full +0.10.
select extensions.is(
  round(public.search_apply_boost(1.0, '{}'::jsonb)::numeric, 6),
  1.0::numeric,
  'no boost signals => score unchanged'
);

-- rating_bayes at the 4.0 prior mean (also where unreviewed items shrink to) => neutral.
select extensions.is(
  round(public.search_apply_boost(1.0, '{"rating_bayes": 4.0}'::jsonb)::numeric, 6),
  1.0::numeric,
  'rating at the prior mean => no rating boost'
);

-- A perfect 5.0 earns the capped +0.10.
select extensions.is(
  round(public.search_apply_boost(1.0, '{"rating_bayes": 5.0}'::jsonb)::numeric, 6),
  1.1::numeric,
  '5.0 rating => +0.10 boost'
);

-- Below the prior is floored to neutral — never a penalty.
select extensions.is(
  round(public.search_apply_boost(1.0, '{"rating_bayes": 1.5}'::jsonb)::numeric, 6),
  1.0::numeric,
  'below-prior rating => neutral, never a penalty'
);

-- Higher rating outranks lower at equal base score (the whole point of the fix).
select extensions.ok(
  public.search_apply_boost(1.0, '{"rating_bayes": 4.8}'::jsonb)
    > public.search_apply_boost(1.0, '{"rating_bayes": 4.2}'::jsonb),
  '4.8 outranks 4.2 at equal base score'
);

-- Rating stacks additively with the existing signals: in_stock 0.10 + verified 0.05 + rating 0.10.
select extensions.is(
  round(
    public.search_apply_boost(1.0, '{"in_stock": true, "verified": true, "rating_bayes": 5.0}'::jsonb)::numeric,
    6
  ),
  1.25::numeric,
  'in_stock + verified + 5.0 rating => 1.25'
);

select * from extensions.finish();

rollback;

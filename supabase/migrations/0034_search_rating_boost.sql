-- 0034: wire the Bayesian review rating into search ranking.
--
-- Migration 0028 computes rating_bayes (a Bayesian-shrunk mean star rating, prior
-- mean m = 4.0) and MERGES it into search_documents.boost_signals expressly so it
-- can influence the search boost. But search_apply_boost (defined in 0009) only
-- read in_stock / verified / below_median, so review quality never affected the
-- RRF score — the rating write was dead code with respect to ranking. Two listings
-- with identical lexical/vector rank and identical in_stock/verified/below_median
-- flags but a 4.9 vs 1.5 rating scored identically.
--
-- Add a bounded, non-negative rating term centred on the prior mean:
--   * rating_bayes is in [1,5]; unreviewed items sit at the 4.0 prior -> 0 boost.
--   * above the prior earns up to +0.10 at a perfect 5.0 (on par with in_stock).
--   * below the prior stays neutral (floored to 0) — never a penalty, so brand-new
--     or lightly-reviewed listings are not buried (the Bayesian shrinkage in 0028
--     already damps low review counts toward the prior, so no extra count gate).
--   * absent rating_bayes coalesces to the prior -> 0, so unreviewed == neutral
--     (NOT a spurious boost — least()/greatest() ignore NULLs, hence the coalesce).
--
-- Additive / reversible: only the body of search_apply_boost changes. Its signature,
-- search_rrf, and every caller are untouched. To revert, restore the 0009 body
-- (drop the rating_bayes term).

create or replace function public.search_apply_boost(
  p_base_score double precision,
  p_boost_signals jsonb
)
returns double precision
language sql
immutable
as $$
  select p_base_score
    * (
      1.0
      + case when coalesce((p_boost_signals ->> 'in_stock')::boolean, false) then 0.10 else 0.0 end
      + case when coalesce((p_boost_signals ->> 'verified')::boolean, false) then 0.05 else 0.0 end
      + case when coalesce((p_boost_signals ->> 'below_median')::boolean, false) then 0.05 else 0.0 end
      + greatest(
          0.0,
          least(
            0.10,
            (coalesce((p_boost_signals ->> 'rating_bayes')::double precision, 4.0) - 4.0) * 0.10
          )
        )
    );
$$;

comment on function public.search_apply_boost(double precision, jsonb) is
  'RRF ranking multiplier: in_stock (+0.10), verified (+0.05), below_median (+0.05), '
  'and Bayesian review rating (up to +0.10 for ratings above the 4.0 prior; absent/'
  'below-prior ratings are neutral). Rating signal wired in 0034 (0028 writes it).';

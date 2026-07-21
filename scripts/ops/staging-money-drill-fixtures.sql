-- Staging money-drill fixtures: surface a handful of COD-eligible retail
-- listings in public discovery by moving their Cloudinary public_ids off the
-- `demo/` prefix (FD-04 / VC-P06 excludes `demo/%` from catalog + search).
--
-- Reversible: rewrite `staging-drill/` back to `demo/`.
-- Images may 404 until Cloudinary assets are renamed/copied to match; checkout
-- and cart still work for the money drill.
--
-- Apply against the live Vergeo5 project only when preparing S1–S3 drills.
-- Do NOT run against a true isolated staging DB that already has non-demo stock.

begin;

with drill as (
  select vl.id
  from public.vendor_listings vl
  where vl.id in (
    'b904645c-ed91-1329-72e3-43d7868855fe', -- tea-coffee-standard (K28.97)
    '7cbffa47-c958-410b-ae32-e341d6b52fa3', -- flour-baking-standard
    '0b33171a-468c-ecec-71c1-61f96ca48076', -- cooking-oil-5l
    '388660b1-40c5-d004-7bde-f9c532686c67', -- footwear-premium
    'cef8e01d-4184-5e19-9fcf-732d7166a39b'  -- beverages-standard
  )
  and vl.status = 'active'
  and coalesce(vl.wholesale, false) = false
  and vl.price_ngwee > 0
  and vl.price_ngwee <= 50000 -- COD ≤ K500
)
update public.listing_images li
set
  cloudinary_public_id = regexp_replace(li.cloudinary_public_id, '^demo/', 'staging-drill/'),
  updated_at = now()
from drill
where li.listing_id = drill.id
  and li.cloudinary_public_id ilike 'demo/%';

commit;

-- Rollback:
-- update public.listing_images
-- set cloudinary_public_id = regexp_replace(cloudinary_public_id, '^staging-drill/', 'demo/'),
--     updated_at = now()
-- where cloudinary_public_id ilike 'staging-drill/%';

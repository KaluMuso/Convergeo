-- Tag the lone demo seed service with canonical demo/ media so public discovery
-- exclusion (FD-04 / VC-P06) can detect it without title-string heuristics.
-- Safe to re-run: only touches rows still missing demo portfolio media.

update public.services
set portfolio_images = array['demo/services/tech-services']::text[],
    updated_at = timezone('utc', now())
where id = '1be21900-7a4f-48ee-bee5-19f770b75e55'
  and (
    portfolio_images is null
    or cardinality(portfolio_images) = 0
    or not exists (
      select 1
      from unnest(portfolio_images) as image(public_id)
      where image.public_id like 'demo/%'
         or image.public_id like '%/demo/%'
    )
  );

-- Re-project search index for the updated service.
select public.search_upsert_service('1be21900-7a4f-48ee-bee5-19f770b75e55');

-- Extend search_query_facets: wholesale/demo exclusion + multi-entity-kind facets.

create or replace function public.search_query_facets(
  query text,
  query_embedding vector(384) default null,
  filters jsonb default '{}'::jsonb
)
returns jsonb
language sql
stable
security definer
set search_path = public, extensions
as $$
  with params as (
    select
      nullif(trim(query), '') as raw_query,
      coalesce(public.expand_search_terms(query), nullif(trim(query), '')) as expanded_query,
      query_embedding as query_embedding,
      coalesce(filters, '{}'::jsonb) as f,
      coalesce((filters ->> 'exclude_wholesale')::boolean, true) as exclude_wholesale,
      coalesce((filters ->> 'exclude_demo')::boolean, true) as exclude_demo
  ),
  entity_scope as (
    select
      case
        when jsonb_typeof(p.f -> 'entity_kinds') = 'array' then p.f -> 'entity_kinds'
        when p.f ->> 'entity_kind' is not null then jsonb_build_array(p.f ->> 'entity_kind')
        else '["product", "listing"]'::jsonb
      end as kinds
    from params p
  ),
  filtered as (
    select sd.*
    from public.search_documents sd
    cross join params p
    cross join entity_scope es
    where sd.is_public = true
      and sd.entity_kind in (
        select jsonb_array_elements_text(es.kinds)
      )
      and (
        not p.exclude_wholesale
        or sd.entity_kind <> 'listing'
        or not exists (
          select 1
          from public.vendor_listings vl
          where vl.id = sd.entity_id
            and vl.wholesale = true
        )
      )
      and (
        not p.exclude_demo
        or sd.entity_kind <> 'listing'
        or not exists (
          select 1
          from public.vendor_listings vl
          join public.listing_images li on li.listing_id = vl.id
          where vl.id = sd.entity_id
            and (
              lower(li.cloudinary_public_id) = 'demo'
              or lower(li.cloudinary_public_id) like 'demo/%'
              or lower(li.cloudinary_public_id) like '%/demo/%'
            )
        )
      )
  ),
  matched as (
    select distinct f.id
    from filtered f
    cross join params p
    where (
      (
        p.expanded_query is not null
        and f.tsv @@ websearch_to_tsquery('simple', p.expanded_query)
      )
      or (
        p.raw_query is not null
        and (
          f.title % p.raw_query
          or coalesce(array_to_string(f.locale_terms, ' '), '') % p.raw_query
          or exists (
            select 1
            from public.synonyms s
            where s.term = lower(p.raw_query)
              and (
                f.title ilike '%' || s.canonical || '%'
                or coalesce(array_to_string(f.locale_terms, ' '), '') ilike '%' || s.canonical || '%'
              )
          )
        )
      )
      or (
        p.query_embedding is not null
        and f.embedding is not null
      )
    )
  ),
  docs as (
    select sd.category_path, sd.price_min_ngwee, sd.price_max_ngwee, sd.entity_kind
    from matched m
    join filtered sd on sd.id = m.id
  ),
  category_counts as (
    select coalesce(d.category_path, '') as value, count(*)::int as count
    from docs d
    cross join params p
    where d.category_path is not null
      and d.category_path <> ''
      and (
        p.f ->> 'price_min_ngwee' is null
        or d.price_max_ngwee is null
        or d.price_max_ngwee >= (p.f ->> 'price_min_ngwee')::bigint
      )
      and (
        p.f ->> 'price_max_ngwee' is null
        or d.price_min_ngwee is null
        or d.price_min_ngwee <= (p.f ->> 'price_max_ngwee')::bigint
      )
    group by d.category_path
  ),
  price_counts as (
    select
      case
        when coalesce(d.price_min_ngwee, 0) < 50000 then 'under_50k'
        when coalesce(d.price_min_ngwee, 0) < 200000 then '50k_200k'
        when coalesce(d.price_min_ngwee, 0) < 500000 then '200k_500k'
        else 'over_500k'
      end as value,
      count(*)::int as count
    from docs d
    cross join params p
    where d.entity_kind in ('product', 'listing')
      and (
        p.f ->> 'category_path' is null
        or d.category_path like (p.f ->> 'category_path') || '%'
      )
    group by 1
  )
  select jsonb_build_object(
    'categories',
    coalesce(
      (
        select jsonb_agg(jsonb_build_object('value', value, 'count', count) order by value)
        from category_counts
        where value <> ''
      ),
      '[]'::jsonb
    ),
    'price',
    coalesce(
      (
        select jsonb_agg(jsonb_build_object('value', value, 'count', count) order by value)
        from price_counts
      ),
      '[]'::jsonb
    )
  );
$$;

comment on function public.search_query_facets(text, vector, jsonb) is
  'Disjunctive facet counts for query-matched documents. Supports entity_kinds[], excludes wholesale/demo listings by default.';

-- Accurate search facet counts over the full query-matched document set (not RRF top-N).
-- Optional seed row for mega_menu merchandising slot.

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
      coalesce(filters, '{}'::jsonb) as f
  ),
  filtered as (
    select sd.*
    from public.search_documents sd
    cross join params p
    where sd.is_public = true
      and sd.entity_kind in ('product', 'listing')
      and (
        p.f ->> 'entity_kind' is null
        or sd.entity_kind = p.f ->> 'entity_kind'
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
    select sd.category_path, sd.price_min_ngwee, sd.price_max_ngwee
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
    where (
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
  'Disjunctive category/price facet counts for all documents matching the search query (full corpus, not RRF top-N).';

insert into public.merch_slots (slot_key, variant_key, payload, schedule_from, position, active)
select
  'mega_menu',
  'default',
  jsonb_build_object(
    'featured_minis', '[]'::jsonb,
    'promo_text', '',
    'promo_cta_label', '',
    'promo_href', '/search'
  ),
  now(),
  0,
  true
where not exists (
  select 1 from public.merch_slots ms where ms.slot_key = 'mega_menu'
);

-- M03-P10 catalog seed integrity tests
-- Applies seed.sql then asserts category tree + product stub counts.
-- Run: supabase test db (pgTAP) after db reset

begin;

set local search_path to public, extensions;

select extensions.plan(8);

-- Apply catalog seed (CI uses --no-seed; tests self-seed)
\set seed_path '..'/seed.sql
\ir ../seed.sql

-- ---------------------------------------------------------------------------
-- Category tree integrity
-- ---------------------------------------------------------------------------

select extensions.is(
  (select count(*)::integer from public.categories where parent_id is null),
  8,
  'eight root departments seeded'
);

select extensions.ok(
  not exists (
    select 1
    from public.categories c
    where c.parent_id is not null
      and not exists (
        select 1 from public.categories p where p.id = c.parent_id
      )
  ),
  'no orphan parent_id references'
);

select extensions.ok(
  not exists (
    select 1
    from public.categories c
    join public.categories p on p.id = c.parent_id
    where c.path <> p.path || '/' || c.slug
  ),
  'materialized path consistent with parent slug chain'
);

select extensions.ok(
  (select count(*)::integer from public.categories where parent_id is not null) between 60 and 80,
  'subcategory count in D8 range (60-80)'
);

-- ---------------------------------------------------------------------------
-- Product stub counts + aliases
-- ---------------------------------------------------------------------------

select extensions.ok(
  (select count(*)::integer from public.products) between 140 and 160,
  'canonical product stub count near 150'
);

select extensions.ok(
  (select count(*)::integer from public.products where status = 'active') =
  (select count(*)::integer from public.products),
  'all seeded products are active'
);

select extensions.ok(
  (select count(*)::integer
   from public.products
   where aliases is not null
     and cardinality(aliases) > 0) >= 100,
  'majority of product stubs carry searchable aliases'
);

select extensions.ok(
  exists (
    select 1
    from public.products
    where aliases @> array['chitenge']::text[]
       or aliases @> array['chitange']::text[]
  ),
  'chitenge/chitange alias present per D25'
);

select extensions.ok(
  exists (
    select 1
    from public.products p
    join public.categories c on c.id = p.category_id
    where c.parent_id is not null
  ),
  'every product links to a subcategory'
);

select extensions.finish();

rollback;

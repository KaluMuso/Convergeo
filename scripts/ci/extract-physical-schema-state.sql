-- Read-only physical schema state extractor for staging convergence preflight.
-- Run with: psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -tA -f scripts/ci/extract-physical-schema-state.sql
select json_build_object(
  'extracted_at_utc', timezone('utc', now()),
  'tables', coalesce((
    select json_object_agg(format('%I.%I', schemaname, tablename), true)
    from pg_tables
    where (schemaname, tablename) in (
      ('private', 'rate_counter_scope_manifest')
    )
  ), '{}'::json),
  'metrics', json_build_object(
    'rate_counter_scope_count', (select count(*)::int from private.rate_counter_scope_manifest)
  ),
  'columns', coalesce((
    select json_object_agg(
      format('%I.%I.%I', table_schema, table_name, column_name),
      json_build_object(
        'nullable', is_nullable = 'YES',
        'default', column_default
      )
    )
    from information_schema.columns
    where (table_schema, table_name, column_name) = ('public', 'listing_view_dedup', 'surface')
  ), '{}'::json),
  'primary_keys', coalesce((
    select json_object_agg(
      format('%I.%I', n.nspname, c.relname),
      json_build_object(
        'columns', (
          select json_agg(a.attname order by array_position(con.conkey, a.attnum))
          from unnest(con.conkey) with ordinality as ck(attnum, ord)
          join pg_attribute a
            on a.attrelid = con.conrelid
           and a.attnum = ck.attnum
        )
      )
    )
    from pg_constraint con
    join pg_class c on c.oid = con.conrelid
    join pg_namespace n on n.oid = c.relnamespace
    where con.contype = 'p'
      and n.nspname = 'public'
      and c.relname = 'listing_view_dedup'
  ), '{}'::json),
  'functions', coalesce((
    select json_object_agg(
      format(
        '%I.%I(%s)',
        n.nspname,
        p.proname,
        pg_get_function_identity_arguments(p.oid)
      ),
      json_build_object(
        'security', case when p.prosecdef then 'definer' else 'invoker' end,
        'arguments', pg_get_function_arguments(p.oid),
        'search_path', coalesce((
          select string_to_array(replace(setting, 'search_path=', ''), ', ')
          from unnest(coalesce(p.proconfig, array[]::text[])) as setting
          where setting like 'search_path=%'
          limit 1
        ), array[]::text[]),
        'grants', coalesce((
          select json_agg(distinct grantee order by grantee)
          from information_schema.routine_privileges rp
          where rp.specific_schema = n.nspname
            and rp.routine_name = p.proname
            and rp.privilege_type = 'EXECUTE'
            and grantee not in ('PUBLIC')
        ), '[]'::json)
      )
    )
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where (n.nspname, p.proname) in (
      ('public', 'has_role'),
      ('private', 'has_role'),
      ('public', 'bump_rate_counter'),
      ('public', 'record_listing_view'),
      ('private', 'is_verified_business')
    )
  ), '{}'::json),
  'absent_functions', coalesce((
    select json_agg(signature order by signature)
    from (
      values
        ('public.is_verified_business(uid uuid)'),
        ('public.record_listing_view(p_session_id uuid, p_listing_id uuid, p_day date, p_view_kind text)')
    ) as expected(signature)
    where to_regprocedure(
      case
        when expected.signature like 'public.is_verified_business%'
          then 'public.is_verified_business(uuid)'
        else 'public.record_listing_view(uuid, uuid, date, text)'
      end
    ) is null
  ), '[]'::json),
  'extensions', coalesce((
    select json_object_agg(e.extname, n.nspname)
    from pg_extension e
    join pg_namespace n on n.oid = e.extnamespace
    where e.extname in ('pg_trgm', 'vector')
  ), '{}'::json)
)::text;

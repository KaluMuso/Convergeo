-- Staging / CI schema isolation checks (no secrets).
-- Expected: zero rows from each SELECT. Run with:
--   psql "$DB_URL" -v ON_ERROR_STOP=1 -f scripts/ci/check-staging-schema.sql
--
-- 1) Every public base table must have RLS enabled.
-- 2) Every public view exposed to anon/authenticated must use security_invoker
--    (Postgres 15+) so underlying table RLS applies. Unexposed views are OK.

\echo ==> Check: public base tables without RLS
SELECT format('FAIL table without RLS: %s', c.relname) AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND c.relrowsecurity = false;

\echo ==> Check: exposed public views without security_invoker
SELECT format('FAIL exposed view without security_invoker: %s', c.relname) AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'v'
  AND (
    has_table_privilege('anon', c.oid, 'SELECT')
    OR has_table_privilege('authenticated', c.oid, 'SELECT')
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_options_to_table(c.reloptions) AS opt
    WHERE opt.option_name = 'security_invoker'
      AND lower(opt.option_value) IN ('true', 'on', '1')
  );

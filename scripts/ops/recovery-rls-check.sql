-- recovery-rls-check.sql — post-restore RLS verification for STG-REC-04 drills.
--
-- Asserts that application-critical public tables have RLS enabled.
-- Run with ON_ERROR_STOP=1 after restore-smoke.sql succeeds.
--
-- No secrets; pure catalog queries.

\set ON_ERROR_STOP on

DO $rls$
DECLARE
  critical_tables text[] := ARRAY[
    'profiles', 'user_roles', 'vendors', 'vendor_listings', 'orders', 'order_items',
    'payments', 'payouts', 'refunds', 'ledger_accounts', 'ledger_transactions',
    'ledger_postings', 'disputes', 'returns', 'notification_outbox'
  ];
  t text;
  rls_on boolean;
  missing int := 0;
BEGIN
  FOREACH t IN ARRAY critical_tables LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE WARNING 'RLS CHECK: table public.% not present (skipped)', t;
      CONTINUE;
    END IF;
    SELECT c.relrowsecurity
      INTO rls_on
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = t;
    IF NOT COALESCE(rls_on, false) THEN
      missing := missing + 1;
      RAISE EXCEPTION 'RLS CHECK FAIL: public.% has row security disabled', t;
    END IF;
    RAISE NOTICE 'RLS OK: public.% row security enabled', t;
  END LOOP;

  IF missing > 0 THEN
    RAISE EXCEPTION 'RLS CHECK FAIL: % critical table(s) without RLS', missing;
  END IF;

  RAISE NOTICE 'RLS CHECK PASS: critical tables have row security enabled';
END
$rls$;

-- restore-smoke.sql — post-restore invariant assertions for M15-P09 DR drills.
--
-- Run against a FRESHLY RESTORED target DB with ON_ERROR_STOP=1:
--   psql -v ON_ERROR_STOP=1 "$TARGET_DB_URL" -f scripts/ops/restore-smoke.sql
--
-- Checks (RAISE EXCEPTION => psql exits non-zero => restore-staging.sh fails loudly):
--   1. Every core table is present (structural integrity of the restore).
--   2. Config seed tables are non-empty (0008_config.sql data survived the roundtrip).
--   3. The Supabase migration ledger exists and is non-empty (currency vs the repo
--      is asserted by restore-staging.sh, which knows the filesystem migration count).
--      If the ledger table is absent (raw pg_restore of a non-Supabase dump), fall
--      back to asserting the newest-migration marker object (0029 analytics_events).
--
-- This file takes NO external variables and embeds NO secrets — it is pure invariants.

\set ON_ERROR_STOP on

DO $smoke$
DECLARE
  required_tables text[] := ARRAY[
    'profiles', 'user_roles', 'vendors', 'vendor_listings', 'vendor_locations',
    'products', 'categories', 'services', 'events', 'event_instances', 'tickets',
    'orders', 'order_items', 'order_events', 'payments', 'payouts', 'refunds',
    'ledger_accounts', 'ledger_transactions', 'ledger_postings',
    'invoices', 'invoice_counters', 'disputes', 'returns',
    'notification_outbox', 'webhook_events', 'reconciliation_reports',
    'search_documents', 'analytics_events',
    'commission_rates', 'delivery_zones', 'platform_config',
    'feature_flags', 'vendor_quotas', 'prohibited_categories'
  ];
  seed_tables text[] := ARRAY[
    'commission_rates', 'delivery_zones', 'platform_config',
    'feature_flags', 'vendor_quotas', 'prohibited_categories'
  ];
  t          text;
  n          bigint;
  ledger_n   bigint;
  ledger_max text;
BEGIN
  -- 1. Structural: every core table must exist in public.
  FOREACH t IN ARRAY required_tables LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'SMOKE FAIL: required table public.% missing after restore', t;
    END IF;
  END LOOP;
  RAISE NOTICE 'SMOKE OK: % core tables present', array_length(required_tables, 1);

  -- 2. Data: config seed tables must be non-empty.
  FOREACH t IN ARRAY seed_tables LOOP
    EXECUTE format('SELECT count(*) FROM public.%I', t) INTO n;
    IF n = 0 THEN
      RAISE EXCEPTION 'SMOKE FAIL: seed table public.% is empty after restore', t;
    END IF;
    RAISE NOTICE 'SMOKE OK: public.% has % row(s)', t, n;
  END LOOP;

  -- 3. Migration ledger present + non-empty (currency vs repo asserted by caller).
  IF to_regclass('supabase_migrations.schema_migrations') IS NOT NULL THEN
    SELECT count(*), max(version)
      INTO ledger_n, ledger_max
      FROM supabase_migrations.schema_migrations;
    IF ledger_n = 0 THEN
      RAISE EXCEPTION 'SMOKE FAIL: supabase_migrations.schema_migrations is empty';
    END IF;
    RAISE NOTICE 'SMOKE OK: migration ledger has % rows, latest=%', ledger_n, ledger_max;
  ELSE
    -- Fallback: no Supabase ledger in this dump — assert the newest migration marker.
    IF to_regclass('public.analytics_events') IS NULL THEN
      RAISE EXCEPTION 'SMOKE FAIL: no migration ledger AND newest-migration marker missing';
    END IF;
    RAISE WARNING 'SMOKE: no supabase_migrations.schema_migrations; verified 0029 marker only';
  END IF;

  RAISE NOTICE 'SMOKE PASS: restore invariants hold';
END
$smoke$;

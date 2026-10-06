-- typegen_synthetic_catalog_contract
-- Reviewed source expectations for the 138-input disposable replay. Output
-- hashes and bounded direct ACL deltas; no definitions or fixture rows leave CI.
-- This is a synthetic fresh-install check, not a hosted staging comparison.
WITH
expected_schemas(name, owner, public_usage, public_create, anon_usage, anon_create,
                 authenticated_usage, authenticated_create, service_usage, service_create) AS (
  VALUES ('reconciliation_private', 'postgres', false, false, false, false,
          false, false, true, false)
),
actual_schemas AS (
  SELECT e.name, pg_get_userbyid(n.nspowner) AS owner,
    EXISTS (SELECT 1 FROM aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) acl
      WHERE acl.grantee = 0 AND acl.privilege_type = 'USAGE') AS public_usage,
    EXISTS (SELECT 1 FROM aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) acl
      WHERE acl.grantee = 0 AND acl.privilege_type = 'CREATE') AS public_create,
    has_schema_privilege('anon', n.oid, 'USAGE') AS anon_usage,
    has_schema_privilege('anon', n.oid, 'CREATE') AS anon_create,
    has_schema_privilege('authenticated', n.oid, 'USAGE') AS authenticated_usage,
    has_schema_privilege('authenticated', n.oid, 'CREATE') AS authenticated_create,
    has_schema_privilege('service_role', n.oid, 'USAGE') AS service_usage,
    has_schema_privilege('service_role', n.oid, 'CREATE') AS service_create
  FROM expected_schemas e LEFT JOIN pg_namespace n ON n.nspname = e.name
),
expected_relations(schema_name, relation_name, owner, rls, forced, anon_acl,
                   authenticated_acl, service_acl) AS (
  VALUES
    ('public', 'cart_merge_receipts', 'postgres', true, true, '', '', 'SI'),
    ('public', 'payment_collection_exceptions', 'postgres', true, true, '', '', 'SIU'),
    ('public', 'payment_collection_receipts', 'postgres', true, true, '', '', 'SIU'),
    ('public', 'service_payment_obligations', 'postgres', true, true, '', '', 'SIU'),
    ('public', 'reconciliation_report_versions', 'postgres', true, true, '', 'S', 'S'),
    ('public', 'vendor_stock_operations', 'postgres', true, true, '', '', ''),
    ('public', 'stock_claim_identities', 'postgres', true, true, '', '', ''),
    ('reconciliation_private', 'report_streams', 'postgres', true, true, '', '', '')
),
actual_relations AS (
  SELECT e.schema_name, e.relation_name, pg_get_userbyid(c.relowner) AS owner,
    c.relrowsecurity AS rls, c.relforcerowsecurity AS forced,
    concat(CASE WHEN has_table_privilege('anon', c.oid, 'SELECT') THEN 'S' END,
           CASE WHEN has_table_privilege('anon', c.oid, 'INSERT') THEN 'I' END,
           CASE WHEN has_table_privilege('anon', c.oid, 'UPDATE') THEN 'U' END,
           CASE WHEN has_table_privilege('anon', c.oid, 'DELETE') THEN 'D' END) AS anon_acl,
    concat(CASE WHEN has_table_privilege('authenticated', c.oid, 'SELECT') THEN 'S' END,
           CASE WHEN has_table_privilege('authenticated', c.oid, 'INSERT') THEN 'I' END,
           CASE WHEN has_table_privilege('authenticated', c.oid, 'UPDATE') THEN 'U' END,
           CASE WHEN has_table_privilege('authenticated', c.oid, 'DELETE') THEN 'D' END) AS authenticated_acl,
    concat(CASE WHEN has_table_privilege('service_role', c.oid, 'SELECT') THEN 'S' END,
           CASE WHEN has_table_privilege('service_role', c.oid, 'INSERT') THEN 'I' END,
           CASE WHEN has_table_privilege('service_role', c.oid, 'UPDATE') THEN 'U' END,
           CASE WHEN has_table_privilege('service_role', c.oid, 'DELETE') THEN 'D' END) AS service_acl
  FROM expected_relations e LEFT JOIN pg_class c
    ON c.oid = to_regclass(format('%I.%I', e.schema_name, e.relation_name))
),
-- Inspect direct grants as well as effective access. This catches inherited or
-- PUBLIC access masking a missing grant to one of the protected API roles.
expected_direct_acl(schema_name, relation_name, grantee, privilege, grantor, grantable) AS (
  VALUES
    ('public','cart_merge_receipts','service_role','SELECT','postgres',false),
    ('public','cart_merge_receipts','service_role','INSERT','postgres',false),
    ('public','payment_collection_exceptions','service_role','SELECT','postgres',false),
    ('public','payment_collection_exceptions','service_role','INSERT','postgres',false),
    ('public','payment_collection_exceptions','service_role','UPDATE','postgres',false),
    ('public','payment_collection_receipts','service_role','SELECT','postgres',false),
    ('public','payment_collection_receipts','service_role','INSERT','postgres',false),
    ('public','payment_collection_receipts','service_role','UPDATE','postgres',false),
    ('public','service_payment_obligations','service_role','SELECT','postgres',false),
    ('public','service_payment_obligations','service_role','INSERT','postgres',false),
    ('public','service_payment_obligations','service_role','UPDATE','postgres',false),
    ('public','reconciliation_report_versions','authenticated','SELECT','postgres',false),
    ('public','reconciliation_report_versions','service_role','SELECT','postgres',false)
),
actual_direct_acl AS (
  SELECT e.schema_name, e.relation_name,
    CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE grantee.rolname END AS grantee,
    a.privilege_type AS privilege, pg_get_userbyid(a.grantor) AS grantor,
    a.is_grantable AS grantable
  FROM expected_relations e
  JOIN pg_class c ON c.oid = to_regclass(format('%I.%I', e.schema_name, e.relation_name))
  CROSS JOIN LATERAL aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
  LEFT JOIN pg_roles grantee ON grantee.oid = a.grantee
  WHERE a.grantee = 0 OR grantee.rolname IN ('anon', 'authenticated', 'service_role')
),
expected_functions(signature, owner, definer, search_path, anon_execute,
                   authenticated_execute, service_execute) AS (
  VALUES
    ('public.confirm_funded_service(uuid,uuid,boolean)', 'postgres', true, '', false, false, true),
    ('public.adjust_vendor_stock(uuid,uuid,uuid,uuid,uuid,integer,text,text,integer)',
       'postgres', true, 'pg_catalog, public', false, false, true),
    ('public.claim_stock_reservation(uuid,uuid,integer,uuid,timestamptz)',
       'postgres', true, 'pg_catalog, public', false, false, true),
    ('public.append_reconciliation_report_version(jsonb)',
       'postgres', false, '', false, false, true),
    ('reconciliation_private.append_report(jsonb)',
       'postgres', true, '', false, false, true)
),
actual_functions AS (
  SELECT e.signature, pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef AS definer,
    (SELECT CASE substring(setting FROM 13) WHEN '""' THEN ''
             ELSE substring(setting FROM 13) END
      FROM unnest(p.proconfig) AS setting
      WHERE setting LIKE 'search_path=%' LIMIT 1) AS search_path,
    has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_execute,
    has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated_execute,
    has_function_privilege('service_role', p.oid, 'EXECUTE') AS service_execute
  FROM expected_functions e LEFT JOIN pg_proc p ON p.oid = to_regprocedure(e.signature)
),
expected_service_reads(relation_name, can_select) AS (
  VALUES ('platform_config', true), ('delivery_zones', true),
    ('commission_rates', true), ('vendor_quotas', true),
    ('product_relations', true), ('vendor_storefront_collections', true),
    ('vendor_storefront_collection_items', true)
),
actual_service_reads AS (
  SELECT e.relation_name,
    has_table_privilege('service_role', to_regclass(format('public.%I', e.relation_name)), 'SELECT')
      AS can_select
  FROM expected_service_reads e
),
expected_fixtures(kind, fixture_key, fixture_value) AS (
  VALUES
    ('platform_config', 'cod_cap_ngwee', '50000'::jsonb),
    ('platform_config', 'free_delivery_threshold_ngwee', '20000'::jsonb),
    ('platform_config', 'waha_intake_vendor_allowlist', '[]'::jsonb),
    ('feature_flags', 'paid_tiers', 'false'::jsonb),
    ('feature_flags', 'waha_vendor_intake', 'false'::jsonb),
    ('commission_rates', 'default', '800'::jsonb),
    ('commission_rates', 'free_events', '0'::jsonb),
    ('delivery_zones', 'lusaka_a', '[3000,true]'::jsonb),
    ('empty_table', 'auth.users', '0'::jsonb),
    ('empty_table', 'public.orders', '0'::jsonb),
    ('empty_table', 'public.vendor_listings', '0'::jsonb),
    ('empty_table', 'storage.objects', '0'::jsonb)
),
actual_fixtures AS (
  SELECT e.kind, e.fixture_key,
    CASE e.kind
      WHEN 'platform_config' THEN (SELECT value FROM public.platform_config WHERE key = e.fixture_key)
      WHEN 'feature_flags' THEN (SELECT to_jsonb(enabled) FROM public.feature_flags WHERE flag = e.fixture_key)
      WHEN 'commission_rates' THEN (SELECT to_jsonb(rate_bps) FROM public.commission_rates WHERE category_key = e.fixture_key)
      WHEN 'delivery_zones' THEN (SELECT jsonb_build_array(fee_ngwee, active) FROM public.delivery_zones WHERE zone_key = e.fixture_key)
      WHEN 'empty_table' THEN CASE e.fixture_key
        WHEN 'auth.users' THEN (SELECT to_jsonb(count(*)) FROM auth.users)
        WHEN 'public.orders' THEN (SELECT to_jsonb(count(*)) FROM public.orders)
        WHEN 'public.vendor_listings' THEN (SELECT to_jsonb(count(*)) FROM public.vendor_listings)
        WHEN 'storage.objects' THEN (SELECT to_jsonb(count(*)) FROM storage.objects)
      END
    END AS fixture_value
  FROM expected_fixtures e
),
direct_acl_differences AS (
  SELECT 'missing'::text AS direction, d.* FROM (
    SELECT * FROM expected_direct_acl EXCEPT ALL SELECT * FROM actual_direct_acl
  ) d
  UNION ALL
  SELECT 'unexpected'::text AS direction, d.* FROM (
    SELECT * FROM actual_direct_acl EXCEPT ALL SELECT * FROM expected_direct_acl
  ) d
),
comparisons AS (
  SELECT 'direct_role_acl' AS group_name,
    (SELECT jsonb_agg(to_jsonb(e) ORDER BY schema_name, relation_name, grantee, privilege) FROM expected_direct_acl e) AS expected,
    (SELECT jsonb_agg(to_jsonb(a) ORDER BY schema_name, relation_name, grantee, privilege) FROM actual_direct_acl a) AS actual
  UNION ALL SELECT 'schema_owner_acl',
    (SELECT jsonb_agg(to_jsonb(e) ORDER BY name) FROM expected_schemas e) AS expected,
    (SELECT jsonb_agg(to_jsonb(a) ORDER BY name) FROM actual_schemas a) AS actual
  UNION ALL SELECT 'relation_owner_acl_rls',
    (SELECT jsonb_agg(to_jsonb(e) ORDER BY schema_name, relation_name) FROM expected_relations e),
    (SELECT jsonb_agg(to_jsonb(a) ORDER BY schema_name, relation_name) FROM actual_relations a)
  UNION ALL SELECT 'function_owner_acl_config',
    (SELECT jsonb_agg(to_jsonb(e) ORDER BY signature) FROM expected_functions e),
    (SELECT jsonb_agg(to_jsonb(a) ORDER BY signature) FROM actual_functions a)
  UNION ALL SELECT 'source_fixture',
    (SELECT jsonb_agg(to_jsonb(e) ORDER BY kind, fixture_key) FROM expected_fixtures e),
    (SELECT jsonb_agg(to_jsonb(a) ORDER BY kind, fixture_key) FROM actual_fixtures a)
  UNION ALL SELECT 'service_read_grants',
    (SELECT jsonb_agg(to_jsonb(e) ORDER BY relation_name) FROM expected_service_reads e),
    (SELECT jsonb_agg(to_jsonb(a) ORDER BY relation_name) FROM actual_service_reads a)
)
SELECT line FROM (
  SELECT 0 AS phase, group_name AS sort_key,
    group_name || '|' || encode(extensions.digest(expected::text, 'sha256'), 'hex') || '|'
      || encode(extensions.digest(actual::text, 'sha256'), 'hex') AS line
  FROM comparisons
  UNION ALL
  SELECT 1, direction || '|' || schema_name || '|' || relation_name || '|' ||
    grantee || '|' || privilege || '|' || grantor || '|' || grantable::text,
    'direct_acl_delta|' || direction || '|' || schema_name || '|' || relation_name || '|' ||
    grantee || '|' || privilege || '|' ||
    CASE WHEN grantor IN ('postgres', 'supabase_admin') THEN grantor ELSE '<other>' END ||
    '|' || grantable::text
  FROM (SELECT * FROM direct_acl_differences
        ORDER BY direction, schema_name, relation_name, grantee, privilege, grantor, grantable
        LIMIT 64) d
  UNION ALL
  SELECT 2, 'truncated', 'direct_acl_delta|truncated'
  WHERE (SELECT count(*) FROM direct_acl_differences) > 64
) output ORDER BY phase, sort_key;

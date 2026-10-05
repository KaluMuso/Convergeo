-- Read-only evidence extractor for an authorized disposable rehearsal.
-- Run with: psql -X -Atq -v ON_ERROR_STOP=1 "$DB_URL" -f this-file > snapshot.json
-- Keep the output under restricted custody: migration statements and catalog
-- definitions may contain sensitive material. Never commit live snapshots.

SELECT jsonb_build_object(
  'snapshot_schema', 1,
  'database', current_database(),
  'database_marker', (SELECT shobj_description(oid, 'pg_database')
                        FROM pg_database WHERE datname = current_database()),
  'server_address', inet_server_addr()::text,
  'server_port', inet_server_port(),
  'ledger_columns', (
    SELECT jsonb_agg(jsonb_build_object(
      'name', attname, 'type', format_type(atttypid, atttypmod),
      'not_null', attnotnull) ORDER BY attnum)
    FROM pg_attribute
    WHERE attrelid = 'supabase_migrations.schema_migrations'::regclass
      AND attnum > 0 AND NOT attisdropped
  ),
  'version_primary_key', EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_attribute a
      ON a.attrelid = c.conrelid AND a.attname = 'version'
    WHERE c.conrelid = 'supabase_migrations.schema_migrations'::regclass
      AND c.contype = 'p' AND c.conkey = ARRAY[a.attnum]::smallint[]
  ),
  'idempotency_key_unique', EXISTS (
    SELECT 1 FROM pg_index i JOIN pg_attribute a
      ON a.attrelid = i.indrelid AND a.attname = 'idempotency_key'
    WHERE i.indrelid = 'supabase_migrations.schema_migrations'::regclass
      AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
      AND i.indnkeyatts = 1 AND i.indkey[0] = a.attnum
      AND i.indpred IS NULL AND i.indexprs IS NULL
  ),
  'history', (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'version', m.version, 'statements', m.statements,
      'statements_shape', array_dims(m.statements),
      'name', m.name, 'created_by', m.created_by,
      'idempotency_key', m.idempotency_key, 'rollback', m.rollback,
      'rollback_shape', array_dims(m.rollback)
    ) ORDER BY m.version), '[]'::jsonb)
    FROM supabase_migrations.schema_migrations m
  ),
  'catalog', jsonb_build_object(
    'database', (
      SELECT jsonb_build_object('owner', pg_get_userbyid(datdba), 'acl', datacl::text)
      FROM pg_database WHERE datname = current_database()
    ),
    'schemas', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'name', n.nspname, 'owner', pg_get_userbyid(n.nspowner),
        'acl', n.nspacl::text) ORDER BY n.nspname), '[]'::jsonb)
      FROM pg_namespace n
      WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
    ),
    'relations', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'schema', n.nspname, 'name', c.relname, 'kind', c.relkind,
        'owner', pg_get_userbyid(c.relowner), 'acl', c.relacl::text)
        ORDER BY n.nspname, c.relname, c.relkind), '[]'::jsonb)
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
        AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
    ),
    'column_privileges', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'schema', n.nspname, 'relation', c.relname,
        'column', a.attname, 'acl', a.attacl::text)
        ORDER BY n.nspname, c.relname, a.attname), '[]'::jsonb)
      FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
        AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL
    ),
    'functions', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'schema', n.nspname, 'name', p.proname,
        'arguments', pg_get_function_identity_arguments(p.oid),
        'owner', pg_get_userbyid(p.proowner), 'acl', p.proacl::text)
        ORDER BY n.nspname, p.proname, pg_get_function_identity_arguments(p.oid)),
        '[]'::jsonb)
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
    ),
    'types', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'schema', n.nspname, 'name', t.typname, 'kind', t.typtype,
        'owner', pg_get_userbyid(t.typowner), 'acl', t.typacl::text)
        ORDER BY n.nspname, t.typname, t.typtype), '[]'::jsonb)
      FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
    ),
    'default_privileges', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'owner', pg_get_userbyid(d.defaclrole), 'schema', n.nspname,
        'object_type', d.defaclobjtype, 'acl', d.defaclacl::text)
        ORDER BY pg_get_userbyid(d.defaclrole), n.nspname, d.defaclobjtype),
        '[]'::jsonb)
      FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
    )
  )
)::text;

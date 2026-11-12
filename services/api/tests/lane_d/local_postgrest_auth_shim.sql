-- Local PostgREST 14 + bare pgvector test database only.
-- The repository's migration-replay shim creates a minimal auth.uid() that reads
-- request.jwt.claim.sub. PostgREST 14 exposes the complete verified claims JSON;
-- this function permits exercising customer and service_role RLS in the drill.
-- Do not apply this to hosted Supabase (its Auth schema is authoritative).
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    nullif(
      nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub',
      ''
    )
  )::uuid;
$$;

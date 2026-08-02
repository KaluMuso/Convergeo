-- Provision the RLS test roles for the isolation matrix.
--
-- Run via psql with ON_ERROR_STOP as its own CI step, BEFORE pytest. This
-- exists for diagnosability as much as for provisioning: on 2026-08-02 the
-- same statements, executed from inside the pytest session fixture, took the
-- database down mid-bootstrap ("server closed the connection unexpectedly",
-- run 30736920217) and the one failure cascaded into 2,314 fixture errors.
-- Running the bootstrap here means a crash or refusal is seen in isolation,
-- attributable to a single statement, with the server logs adjacent.
--
-- Statements are existence-guarded, not exception-guarded, because on a
-- Supabase stack the connecting `postgres` role is NOT a superuser and
-- Postgres checks privileges before duplicate names: a blind
-- `CREATE ROLE service_role ... BYPASSRLS` fails on permission even though
-- the role exists (run 30736608352).

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END $$;

-- NOSUPERUSER NOBYPASSRLS is the point of the tester: it must be subject to
-- policy, or every deny assertion in the matrix passes without testing
-- anything.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vergeo_rls_tester') THEN
    CREATE ROLE vergeo_rls_tester LOGIN PASSWORD 'test' NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;

GRANT authenticated TO vergeo_rls_tester;
GRANT anon TO vergeo_rls_tester;
GRANT vergeo_rls_tester TO CURRENT_USER;

-- Verify, loudly: attributes and memberships, in one place.
DO $$
DECLARE
  attrs text;
  memberships int;
BEGIN
  SELECT rolsuper::text || ',' || rolbypassrls::text INTO attrs
  FROM pg_roles WHERE rolname = 'vergeo_rls_tester';
  IF attrs IS DISTINCT FROM 'false,false' THEN
    RAISE EXCEPTION 'vergeo_rls_tester has SUPERUSER or BYPASSRLS (%) — the matrix would pass without testing anything', attrs;
  END IF;

  SELECT count(*) INTO memberships
  FROM pg_auth_members m
  JOIN pg_roles granted ON granted.oid = m.roleid
  JOIN pg_roles member ON member.oid = m.member
  WHERE member.rolname = 'vergeo_rls_tester'
    AND granted.rolname IN ('anon', 'authenticated');
  IF memberships < 2 THEN
    RAISE EXCEPTION 'vergeo_rls_tester lacks membership in anon/authenticated (found %) — SET LOCAL ROLE impersonation cannot work', memberships;
  END IF;
END $$;

SELECT 'rls tester provisioned: ' || rolname FROM pg_roles WHERE rolname = 'vergeo_rls_tester';

# Replaying the Lane D D1 local drill

The checked-in drill is `services/api/tests/lane_d/test_collection_identity_postgrest.py`. It uses the production FastAPI webhook handler, a JWT-verified local PostgREST service role, the canonical migrations on disposable PostgreSQL 16/pgvector, and the production ledger adapter/constraint trigger. It simulates **only** the external Lenco callback/status boundary with local synthetic signing material. No provider call or real money is made.

From the repository root on PowerShell, provision three distinct disposable Docker names/network and a fresh database. Build `services/api/tests/lane_d/Dockerfile` with the repository root as context. The test image uses the S3 `services/api/uv.lock` without modifying it. Set these local-only environment variables to newly generated synthetic values: `LANE_D_DB_PASSWORD`, `LANE_D_JWT_SECRET`, `LANE_D_WEBHOOK_TOKEN`. Do not use a hosted key or a real Lenco token. Use a unique Docker project/name prefix per replay; do not reuse another lane's database.

1. Run a `pgvector/pgvector:pg16` container on a new private Docker network. Do not publish a host port; the test image and `public.ecr.aws/supabase/postgrest:v14.14` container join that network. Create a non-inheriting PostgREST login role and grant it `anon`, `authenticated`, and `service_role`. Configure PostgREST with `PGRST_DB_URI`, `PGRST_DB_SCHEMAS=public`, `PGRST_DB_ANON_ROLE=anon`, and `PGRST_JWT_SECRET=$env:LANE_D_JWT_SECRET`.
2. Replay `scripts/ci/migration-replay.sh` against the disposable database. On Windows, normalize its checkout CRLF to LF in a **lane-local temporary copy two directories below the repository root** before invoking Bash (the script derives the repository root from its own path). The replay must report all 114 S3 migrations successfully applied.
3. The bare-Postgres replay shim has a minimal `auth.users`; add the standard fixture columns `instance_id`, `aud`, `role`, `encrypted_password`, `email_confirmed_at`, `raw_app_meta_data`, `raw_user_meta_data`, `updated_at`. Apply `services/api/tests/lane_d/local_postgrest_auth_shim.sql` to the disposable database only. That shim reads PostgREST's verified JWT claims and is **not** a hosted migration.
4. Run the test image on the private network with the repository mounted at `/workspace`, working directory `/workspace/services/api`, and the environment names below. `LANE_D_POSTGREST_URL` is the private PostgREST root URL (not a Supabase gateway URL). `SUPABASE_DB_URL` is the disposable direct PostgreSQL DSN. Both point only at the lane-local containers.

```text
ENV=development
SUPABASE_DB_URL=<disposable local PostgreSQL DSN>
LANE_D_POSTGREST_URL=<private local PostgREST root URL>
LANE_D_JWT_SECRET=<new synthetic local JWT signing secret>
LANE_D_WEBHOOK_TOKEN=<new synthetic local callback signing token>
LENCO_API_TOKEN=<same synthetic callback signing token>
PYTHONPATH=/workspace/services/api
pytest tests/lane_d/test_collection_identity_postgrest.py -q --junitxml=<lane-specific JUnit path>
```

The test file itself signs the locally simulated callback using the application's Lenco HMAC contract, posts to `/webhooks/lenco`, drains the stored event over PostgREST and checks payment/ledger rows directly in PostgreSQL. It also proves owner/stranger RLS using synthetic JWTs **verified by PostgREST**, without claiming the tokens were issued by real Supabase Auth. The `xfail` cancellation test is intentional evidence of a separate remaining release blocker, not a waived passing invariant. Preserve the raw JUnit and output log; do not record synthetic or external token values.

Run the existing DB-backed tests in **fresh databases per fixture family**. Several historical tests reuse fixed checkout IDs or a fixed reconciliation report date and fail when unrelated files share a mutable database. The pre-repair combined run and the fresh-DB selected rerun are both retained in the separate lane handoff export's `evidence/` folder; their outcomes must be reported separately. The repository keeps the sanitized accounting query and aggregate result.

# API reliability and deployment-truth runbook

Use this runbook to investigate customer-facing `ETIMEDOUT`, `ECONNRESET`, or
`TypeError: fetch failed` reports without changing production configuration.
Run it for the staging API first. Production execution needs the normal approved
change window in [deploy-verify-runbook.md](deploy-verify-runbook.md).

## What the API proves

`/healthz` is liveness only. `/readyz` performs a bounded one-second check of
the Supabase REST dependency; it returns HTTP 200 with `status=degraded` when
that critical dependency cannot be proved. `search_rpc` is opt-in
(`?checks=search`) and informational because keyword search has a fallback.

`/fingerprint` is the deployment-truth endpoint. It exposes only:

- `env`
- `git_sha`, `image_tag`, and `build_id` — SHA/digest-shaped values only; any
  malformed or absent value is returned as `unknown`
- `supabase_project_ref`

It never exposes a host URL, connection string, secret, or configuration value.
The candidate SHA and image tag must match the expected immutable deployment
values. `unknown`, an unexpected environment, or a project-ref mismatch is a
failed proof, not a warning to waive.

## Read-only staging smoke

Set `BASE` to the documented staging API URL; do not paste credentials into the
terminal or an evidence artifact.

```bash
curl --fail --show-error --max-time 10 "$BASE/healthz"
curl --fail --show-error --max-time 10 "$BASE/readyz"
curl --fail --show-error --max-time 10 "$BASE/readyz?checks=search"
curl --fail --show-error --max-time 10 "$BASE/fingerprint"

curl --silent --show-error --output /dev/null --dump-header - \
  --request OPTIONS "$BASE/cart" \
  --header 'Origin: https://<approved-customer-preview-origin>' \
  --header 'Access-Control-Request-Method: POST' \
  --header 'Access-Control-Request-Headers: Authorization, Content-Type'
```

Record response bodies with only the public fields above, the HTTP status, and
the returned `X-Request-ID`. The CORS preflight must reflect the exact approved
origin and permit credentials. A missing header is a configuration gate: do not
work around it with `*`.

## Timeout and reset triage

1. Take a request ID from the affected browser/API response. API request logs
   emit `api_request_completed` or `api_request_failed` with that ID, method,
   route, status, and duration in milliseconds.
2. For dependency probes, inspect `upstream_dependency_failed`. Its bounded
   `failure_kind` is one of `timeout`, `connection_reset`,
   `connection_refused`, `network_unreachable`, `network_error`,
   `unexpected_status`, or `unknown`. The log deliberately omits URL, response
   body, and exception text.
3. On the API host, compare the local API with the public proxy, without
   printing environment files:

   ```bash
   curl --fail --max-time 5 http://127.0.0.1:8000/healthz
   curl --fail --max-time 5 https://api.staging.vergeo5.com/healthz
   docker ps --filter name=vergeo5-api-staging
   docker stats --no-stream vergeo5-api-staging
   docker logs --tail 100 vergeo5-api-staging
   ```

   Local success with public failure points to Caddy/DNS/TLS; both failing points
   to the API container or its dependencies. A sustained high latency or restart
   count is an operational incident; capture redacted metrics before changing
   limits or restarting containers.

## Rollback evidence

If a SHA-tagged staging deployment regresses, use the recorded previous image
through `infra/staging/redeploy-api-staging.sh --rollback`, then repeat the
four probes and retain the before/after fingerprints. Production rollback uses
the approved flow in `deploy-verify-runbook.md`; do not run it merely to test a
suspected issue. A rollback is complete only when the public probe, local probe,
CORS preflight, and matching restored fingerprint all pass.

# Rollback drill — NOT_RUN

Controlled harmless deploy + immutable rollback of customer, vendor, admin, and API was **not** executed.

Blockers:

1. `DEPLOYED_API_DIGEST=UNKNOWN` — cannot prove API rollback to an immutable version.
2. API `GET /healthz` / `/readyz` / `/fingerprint` → **HTTP 502**.
3. Live migration tip drift vs repo — elevates risk of frontend/API/DB skew after a promote/rollback cycle.
4. Prompt constraint: do not widen production outage for a drill when preconditions fail.

Elapsed time: n/a  
Failed steps: drill aborted before mutate  
Health/critical routes after rollback: n/a

**Verdict: FAIL** for G9 / LIVE-10.

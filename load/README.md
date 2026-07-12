# Vergeo5 load tests (k6)

Load scripts + the post-run money-safety invariant check for the money-critical checkout
path. **Lenco is always stubbed** — load tests never touch a real payment provider.

> **⚠ The 100-concurrent-checkout run and the p95 numbers are FOUNDER / STAGING-GATED.**
> They require a deployed staging API + seeded data + a Lenco stub, none of which are
> reachable from the build/CI environment. The scripts, thresholds and invariant check in
> this directory are the deliverable; the live numbers are captured by the founder against
> staging and recorded in [`docs/ops/load-test-results.md`](../docs/ops/load-test-results.md).
> No p95 numbers are fabricated.

## Contents

| File | Purpose |
| --- | --- |
| `k6/checkout-load.js` | 100cc checkout: session→reserve→fulfilment→payment→orders→Lenco-stub. Encoded thresholds `p95<500`; money-safety counters `oversell_errors==0`, `orders_created>0`. |
| `k6/browse-load.js` | Read-heavy discovery mix (≈60% search / 30% PLP / 10% suggest). Encoded read thresholds `p95<400`. |
| `invariant-check.py` | Post-run proof: zero oversells, ledger balanced, invoices gapless. **Exits non-zero on any violation.** |

## Prerequisites (staging — founder-gated)

1. **k6** installed (`k6 version`). Not required to review/lint the scripts.
2. **A deployed staging API** reachable at `BASE_URL` (no trailing slash), e.g.
   `https://api.staging.vergeo5.com`.
3. **Seeded fixtures** on staging:
   - N tracked `vendor_listings` with known `stock_qty` (include at least one deliberately
     scarce listing to stress the oversell guard under contention).
   - N test customers, each with an **active cart** already holding those listings
     (`/checkout/session` reads the caller's active cart).
   - A valid Supabase JWT per test customer.
4. **A Lenco stub** — a local/mock HTTP service that accepts the collection push and returns
   2xx without contacting Lenco. Point `LENCO_STUB_URL` at it. The script refuses any URL
   that looks like a real Lenco host.
5. **`SUPABASE_DB_URL`** for the invariant check — the connection string of the SAME
   database the load run hit (service-role/DB creds via env only; never committed).

## Environment variables

| Var | Script | Default | Notes |
| --- | --- | --- | --- |
| `BASE_URL` | both | `http://localhost:8000` | Staging API origin, no trailing slash. |
| `AUTH_TOKENS` | checkout | — | Comma-separated Supabase JWTs (one per seeded customer). Required. `AUTH_TOKEN` (single) also accepted. |
| `LENCO_STUB_URL` | checkout | `http://localhost:9099/lenco-stub` | Mock push endpoint. Must NOT be a real Lenco host. |
| `PAYMENT_METHOD` | checkout | `momo` | `momo` \| `card` \| `cod`. |
| `PAYMENT_RAIL` | checkout | `mtn` | `mtn` \| `airtel` (momo only). |
| `PAYER_NUMBER` | checkout | `+260970000000` | Test MoMo number. |
| `BROWSE_VUS` | browse | `100` | Peak VUs for the browse mix. |
| `SUPABASE_DB_URL` | invariant-check | local-dev default | DB the run hit. |

## Run procedure (staging)

```bash
# 1. Checkout load — 100 concurrent, ~4 min including ramp.
BASE_URL=https://api.staging.vergeo5.com \
AUTH_TOKENS="$STAGING_JWT_1,$STAGING_JWT_2,...,$STAGING_JWT_100" \
LENCO_STUB_URL=http://127.0.0.1:9099/lenco-stub \
k6 run load/k6/checkout-load.js

# 2. Browse load — read mix.
BASE_URL=https://api.staging.vergeo5.com \
k6 run load/k6/browse-load.js

# 3. Money-safety proof — MUST pass (non-zero exit on any violation).
SUPABASE_DB_URL="$STAGING_DB_URL" python3 load/invariant-check.py

# Offline structure/parse validation (no staging, no k6):
node --check load/k6/checkout-load.js   # after copying to .mjs (see below)
python3 -m py_compile load/invariant-check.py
```

A run **passes** only when: k6 thresholds are green (`p95<500` checkout, `p95<400` reads,
`oversell_errors==0`, `orders_created>0`) **and** `invariant-check.py` exits `0`. k6
thresholds alone are not sufficient — the invariant check is the authoritative money gate.

### Offline validation note

`node --check` cannot resolve k6's `k6/http` imports directly, but it *parses* ES-module
syntax. Copy a script to a `.mjs` temp file and `node --check` it to confirm structure, or
use `k6 run --vus 1 --iterations 1 <script>` against a local API when k6 is available. The
build env used to author this pebble had **no k6 and no reachable DB**, so validation here
was: (a) `node --check` structure pass on both k6 scripts, (b) `py_compile` + query review
for the invariant check. See `docs/ops/load-test-results.md`.

## Thresholds (encoded in the scripts — single source of truth)

- **checkout-load.js:** `http_req_duration{scenario:checkout_100cc}: p95<500`,
  `order_create_ms: p95<500`, `checkout_session_ms: p95<500`, `http_req_failed: rate<0.01`,
  `checks: rate>0.99`, `oversell_errors: count==0`, `orders_created: count>0`.
- **browse-load.js:** `http_req_duration{route:search}: p95<400`,
  `{route:plp}: p95<400`, `{route:suggest}: p95<250`, `http_req_failed: rate<0.01`,
  `checks: rate>0.99`.

## What each invariant catches

| Invariant | Query shape | Failure it catches |
| --- | --- | --- |
| Zero oversells | tracked `vendor_listings` with `stock_qty < 0`, and active holds on out-of-stock listings | A concurrency race that let two checkouts claim the last unit — stock driven below zero. |
| Ledger balanced | per-`transaction_id` `sum(amount_ngwee) <> 0`, plus system-wide `sum <> 0` | A half-posted transaction (one leg written, sibling lost) — money created/destroyed. |
| Invoice gapless | per `series`, `min(no) <> 1 OR max(no) <> count(*)` | A hole from a number allocated by `next_invoice_no()` whose invoice row rolled back. |

## Tuning log

Record each staging run: date, commit, VU profile, p95/p99 per hop, error rate, invariant
result, and any config change made in response (DB pool size, PgBouncer mode, API worker
count, reservation TTL). Append newest-first.

| Date | Commit | Profile | p95 checkout | p95 reads | err rate | invariants | change made |
| --- | --- | --- | --- | --- | --- | --- | --- |
| _pending_ | _staging-gated_ | 100 VUs / 4 min | _founder-gated_ | _founder-gated_ | _founder-gated_ | _founder-gated_ | initial baseline TBD |

## Guardrails

- **No committed credentials** — every secret (JWTs, DB URL, stub URL) is env-only.
- **Lenco always stubbed** — the checkout script hard-refuses a real Lenco host.
- **No app / migration / CI changes** — this pebble adds only `load/` + the findings doc.
- Money stays **integer ngwee** end-to-end; the invariant check compares integers only.

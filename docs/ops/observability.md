# Observability — Vergeo5 (M16-P06)

How Vergeo5 sees itself in production: structured logs, error tracking (Sentry), uptime
monitoring (UptimeRobot), and a single availability error budget that decides when the
founder gets paged. Incident response itself lives in the disaster-recovery runbook:
[`docs/ops/runbook-disaster-recovery.md`](./runbook-disaster-recovery.md).

Live capture and alert-firing are **founder-gated**: they need a real Sentry DSN and a
configured UptimeRobot account (see "Founder actions" below). No DSN is ever committed —
everything ships as a strict no-op until the env is populated.

---

## 1. Sentry (error tracking)

Four init targets, one PII-scrubbing invariant.

| Target        | Init site                                                                       | Notes                                              |
| ------------- | ------------------------------------------------------------------------------- | -------------------------------------------------- |
| API (FastAPI) | `services/api/app/core/sentry.py`                                               | `init_sentry()` called from settings load          |
| customer web  | `apps/customer/sentry.client.config.ts` (lazy-loaded via `app/sentry-init.tsx`) | errors-only browser SDK; serwist/CSP preserved     |
| vendor web    | `apps/vendor/sentry.client.config.ts` (lazy-loaded via `app/sentry-init.tsx`)   | errors-only browser SDK                            |
| admin web     | `apps/admin/sentry.client.config.ts` (lazy-loaded via `app/sentry-init.tsx`)    | strictest: no tracing, console/http crumbs dropped |

**No-op without a DSN.** Every target checks its DSN env var first
(`SENTRY_DSN` on the API, `NEXT_PUBLIC_SENTRY_DSN` in the browser) and does nothing when
it is unset. Dev and CI therefore never emit events and never need a secret.

**Bundle discipline — the browser SDK is lazy-loaded off first-load.** `@sentry/nextjs`
is ~63 KB gz; wiring it the default way (`withSentryConfig`) injects it into every route's
**first-load JS**, blowing the ≤150 KB gz budget (CLAUDE.md #7). Instead, each app mounts a
tiny `"use client"` loader (`app/sentry-init.tsx`) that, after hydration and only when a
DSN is present, does `import('@sentry/nextjs')` — landing the SDK in an **async chunk**,
never in a route's first-load manifest. `sentry.client.config.ts` uses `import type` only
(zero runtime SDK), so importing it into the loader costs ~nothing. Net first-load delta:
~flat (within the bundle-guard regression tolerance). Server-side Next errors are captured
via `instrumentation.ts` (Node runtime only) using `SENTRY_DSN` or
`NEXT_PUBLIC_SENTRY_DSN` — still without `withSentryConfig`.

**PII scrubbing (the core invariant).** Both the API and every client run the same
scrubber on `before_send` (event body) AND `before_breadcrumb` (every breadcrumb):

- **Key-based redaction** — any key whose name contains `phone`, `msisdn`, `mobile`,
  `tel`, `email`, `address`, `street`, `landmark`, `gps`, `latitude`, `longitude`,
  `coordinate`, `token`, `authorization`, `password`, `secret`, `api_key`, `otp`,
  `pin`, `cookie`, `refresh`, `access_token`, `service_role`, `signature`,
  `payment_payload`, `card_number`, `pan`, `cvv`, or `lenco` has its whole value
  replaced with `[redacted]`. The list here is **non-exhaustive** — see `packages/observability/src/scrub.ts` and `services/api/app/core/sentry.py` for the full set (also `passwd`, `set-cookie`, `refresh_token`, `service-role`, `x-lenco-signature`, `cvc`, `encrypted_payload`).
- **Pattern-based masking** inside free text — emails → `[redacted-email]`, Zambian /
  E.164 phone numbers → `[redacted-phone]`, bearer tokens & JWTs → `[redacted-token]`.
- `send_default_pii` / `sendDefaultPii` is left **off** so the SDK never attaches request
  bodies, headers, cookies, or user PII on its own.

The API scrubber is unit-proven in `services/api/tests/test_sentry_scrubber.py`; the
shared TS scrubber in `@vergeo/observability` has matching vitest coverage.

**Tags.** API middleware attaches `application=api`, `request_id`, `route`, and
`release_sha`. Browser/server inits set `application` + `release_sha`. Opaque
`ord-*` / `pay-*` IDs may be tagged when policy-compliant — never phones/emails.

**Release & source maps.** `release` = immutable git SHA (`SENTRY_RELEASE` /
`NEXT_PUBLIC_SENTRY_RELEASE` / `GIT_SHA` / `VERCEL_GIT_COMMIT_SHA`).
Because `withSentryConfig` is intentionally NOT used (it forces the SDK into first-load),
client source-map upload runs as a **separate, gated deploy step** rather than at build
time. On the deploy host, when `SENTRY_AUTH_TOKEN` (+ `SENTRY_ORG`, `SENTRY_PROJECT`) are
set, run after the build:

```bash
# gated: no token -> skip, never fails the build
[ -n "$SENTRY_AUTH_TOKEN" ] && npx @sentry/cli sourcemaps inject apps/<app>/.next \
  && npx @sentry/cli sourcemaps upload --release "$SENTRY_RELEASE" apps/<app>/.next
```

A missing token is a no-op, so dev/CI/DSN-less deploys never fail for lack of a secret.
The API uploads no browser maps; its `release` is the same git SHA for cross-linking.

**CSP.** The browser SDK POSTs to `*.ingest.sentry.io` (and region variants
`*.ingest.us.sentry.io`, `*.ingest.de.sentry.io`). Those hosts — and only those — were
added to each app's `connect-src`. No other CSP directive changed.

---

## 2. Structured logs

The API already emits one JSON object per line (`services/api/app/logging.py`,
`JsonFormatter`). Field conventions:

| Field        | Always?  | Meaning                                                     |
| ------------ | -------- | ----------------------------------------------------------- |
| `timestamp`  | yes      | ISO-8601 UTC                                                |
| `level`      | yes      | `INFO` / `WARNING` / `ERROR` / ...                          |
| `message`    | yes      | human-readable line — **never** interpolate raw PII into it |
| `logger`     | yes      | dotted logger name                                          |
| `request_id` | when set | correlation id (echoes `X-Request-ID`; joins log ↔ Sentry)  |
| `path`       | when set | request path (no query string / no PII)                     |
| `exc_info`   | on error | formatted traceback                                         |

Rules: log **identifiers, not PII** — use `ord-*` / `pay-*` references and `user_id`, never
phone/email/address. `request_id` is the join key across logs, Sentry events, and support
tickets. Money is integer ngwee in logs (never a float).

---

## 3. Error budget — 99.5% API availability

**Target: 99.5% monthly availability** of the API (`/health` returning 200). That budget:

| Window  | Allowed downtime (0.5%) |
| ------- | ----------------------- |
| 30 days | **216 min (3.6 h)**     |
| 7 days  | 50.4 min                |
| 24 h    | 7.2 min                 |

"Down" = `/health` failing (non-200 or timeout) on **2 consecutive** UptimeRobot checks at
a 1-minute interval (≈2 min to page — absorbs a single flaky probe).

### Alert thresholds → founder WhatsApp (via n8n)

| Signal                                                    | Action                                      |
| --------------------------------------------------------- | ------------------------------------------- |
| API `/health` down ≥2 checks (~2 min)                     | **Page** founder on WhatsApp (n8n)          |
| Any of the 3 web origins down ≥2 checks                   | **Page** founder on WhatsApp (n8n)          |
| Payment webhook endpoint down ≥2 checks                   | **Page** founder on WhatsApp (n8n)          |
| Fast burn: >20% of monthly budget in 1 h (>43 min down/h) | **Page** — likely full outage               |
| Slow burn: >50% of monthly budget consumed (>108 min/mo)  | **Warn** — review before budget exhausts    |
| Sentry: new unresolved `error`-level issue spike          | **Warn** (Sentry alert rule, founder-gated) |

Paging path (below) is deliberately **independent of the API**: if the API is the thing
that is down, the alert must still get out.

---

## 4. Uptime monitoring & paging path

Monitors and the exact setup transcript live in
[`infra/uptimerobot.md`](../../infra/uptimerobot.md). The paging workflow is
[`infra/n8n/uptime-alert.json`](../../infra/n8n/uptime-alert.json):

```
UptimeRobot (monitor trips)
  → POST /webhook/uptime-alert + header X-Uptime-Secret
  → n8n constant-time verify against $env.UPTIME_WEBHOOK_SECRET
  → (auth fail → 401, no WhatsApp)
  → (alertType == down) → WhatsApp Cloud API (template: ops_uptime_alert) → founder
```

**Webhook authentication (VD-P05 / Prompt 9 / RC-08).** The n8n workflow requires header
`X-Uptime-Secret` (or `x-uptime-secret`) to equal `$env.UPTIME_WEBHOOK_SECRET`. Verification
uses `crypto.timingSafeEqual` in the workflow Code node and fails closed when the env secret
is missing, the header is absent, or the value is wrong. The secret is env-only — never
committed — and unauthenticated POSTs short-circuit with HTTP 401 before any WhatsApp call
(CI: `scripts/ci/validate-n8n-no-plaintext-secrets.sh`). Rotation and test-event steps are
in [`infra/uptimerobot.md`](../../infra/uptimerobot.md).

The n8n workflow calls the **WhatsApp Cloud API directly** (not the notification outbox /
our own API), on purpose: an outage of the API or its database must not swallow its own
downtime alert. The recovery ("up" again) event is `alertType == 2` and is ignored by the
paging branch — recovery is confirmed from the UptimeRobot dashboard.

### Money-workflow failure paging (VD-P06)

The money/ops ticks (`release-job`, `reconciliation`, `payment-sweeper`,
`payout-failure-alert`) retry transient HTTP failures (3× / 5s) and, on workflow error,
page the founder with a **metadata-only** WhatsApp body (workflow name, status, last
node, timestamp — no payment refs, tokens, or PII). Shared template:
[`infra/n8n/money-workflow-error-alert.json`](../../infra/n8n/money-workflow-error-alert.json).
Each money workflow also embeds the same Error Trigger path so paging works without a
cross-workflow `errorWorkflow` id at import time.

---

## 5. Protected test-event paths

Use these only after DSNs are set. Never leave them open on production without both a
secret **and** an explicit enable flag.

| Surface  | Path                                  | Auth                                            | Production gate                               |
| -------- | ------------------------------------- | ----------------------------------------------- | --------------------------------------------- |
| API      | `POST /internal/sentry-test`          | `X-Internal-Token: $INTERNAL_SENTRY_TEST_TOKEN` | 404 unless `ENABLE_SENTRY_TEST_ENDPOINT=true` |
| customer | `POST /api/observability/sentry-test` | `X-Sentry-Test-Secret: $SENTRY_TEST_SECRET`     | same (`ENABLE_SENTRY_TEST_ENDPOINT=true`)     |
| vendor   | `POST /api/observability/sentry-test` | same                                            | same                                          |
| admin    | `POST /api/observability/sentry-test` | same                                            | same                                          |

Each response returns `{ok, application, event_id, environment, release}` (no DSN). Events
are tagged `test_event=true`, `application=<surface>`, `release_sha=<git sha>`.

Shared browser/server scrubbing lives in `@vergeo/observability` (mirrors the API scrubber).
Server Next.js init uses `instrumentation.ts` + optional server-only `SENTRY_DSN` (never
expose `SENTRY_AUTH_TOKEN` to the browser).

---

## Founder actions (gate live capture / alerts)

1. **Sentry** — under org `convergeo-w2`, create projects `vergeo5-customer`,
   `vergeo5-vendor`, `vergeo5-admin`, `vergeo5-api` (agent create may be org-permission
   blocked). Set `SENTRY_DSN` (API host) and per-app `NEXT_PUBLIC_SENTRY_DSN` on Vercel;
   set `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT` and release SHAs
   (`SENTRY_RELEASE` / `NEXT_PUBLIC_SENTRY_RELEASE` / `GIT_SHA`). Optional:
   `SENTRY_AUTH_TOKEN` + `SENTRY_ORG` + `SENTRY_PROJECT` for gated source-map upload.
2. **UptimeRobot** — create the monitors in `infra/uptimerobot.md`; point their webhook
   alert contact at the n8n `uptime-alert` webhook URL **with** header `X-Uptime-Secret`
   matching n8n `UPTIME_WEBHOOK_SECRET`.
3. **n8n** — set `UPTIME_WEBHOOK_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`,
   `WHATSAPP_CLOUD_API_TOKEN`, and `FOUNDER_WHATSAPP_TO`; import/activate
   `uptime-alert.json` only after the secret is set.
4. **WhatsApp** — register the `ops_uptime_alert` utility template (founder action F5).
5. **Verify** — fire one test event per surface; force one controlled uptime alert; confirm
   wrong/missing uptime secrets return 401 with no WhatsApp; record evidence (never commit
   DSNs or secrets). G6 stays FAIL until both are demonstrated.

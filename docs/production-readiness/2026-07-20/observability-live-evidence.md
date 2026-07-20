# Prompt 9 — Observability live evidence (sanitised)

**Date:** 2026-07-20  
**Branch:** `cursor/observability-sentry-uptime-da3e`  
**Org probed:** Sentry `convergeo-w2` (region `https://de.sentry.io`)  
**Companion code PR:** this branch (repo wiring)

---

## Final gate stance

| Gate   | Verdict  | Why                                                                                                                              |
| ------ | -------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **G6** | **FAIL** | Vergeo5 Sentry projects not creatable by agent (403); no test-event ingestion proved; no controlled uptime alert delivery proved |

Do **not** treat code completeness as G6 PASS.

---

## Repository work completed (CODE)

| Item                                                                                | Status                       |
| ----------------------------------------------------------------------------------- | ---------------------------- |
| Shared scrubber `@vergeo/observability`                                             | Done + vitest                |
| API scrubber expanded (cookies, tokens, payment, signatures, service-role)          | Done + pytest                |
| API `request_id` / `route` / `application` / `release_sha` tags                     | Done                         |
| Protected API test path `POST /internal/sentry-test`                                | Done (prod fail-closed)      |
| Next client lazy Sentry + tags                                                      | Done (customer/vendor/admin) |
| Next `instrumentation.ts` server init                                               | Done                         |
| Next protected `POST /api/observability/sentry-test`                                | Done                         |
| `uptime-alert.json` secret gate (`X-Uptime-Secret` vs `$env.UPTIME_WEBHOOK_SECRET`) | Done (`active: false`)       |
| UptimeRobot monitor table → locale health + healthz/readyz                          | Docs updated                 |
| Env name documentation (`infra/.env.example`, `docs/ops/observability.md`)          | Done                         |

**Automated tests (this session):**

- `pnpm --filter @vergeo/observability test` → 5 passed
- `uv run pytest tests/test_sentry_scrubber.py tests/test_sentry_test_endpoint.py tests/test_uptime_alert_workflow.py tests/test_health.py -q` → 17 passed
- typecheck: `@vergeo/observability`, customer, vendor, admin → OK

No DSNs, webhook secrets, or WhatsApp tokens were committed.

---

## Live configuration probes

### Sentry projects

| Probe                                           | Result                                                              |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| `find_organizations`                            | `convergeo-w2` present                                              |
| `find_projects`                                 | Only unrelated `zed*` projects — **no** `vergeo5-*`                 |
| `create_project` ×4 (customer/vendor/admin/api) | **HTTP 403** — “organization has disabled this feature for members” |

**BLOCKED_EXTERNAL (founder):** create team-accessible Vergeo5 projects + set DSNs in Vercel/API host env.

### Test events (all four surfaces)

| Surface  | Attempted | Result                                                                       |
| -------- | --------- | ---------------------------------------------------------------------------- |
| customer | No        | DSN unset / project absent                                                   |
| vendor   | No        | same                                                                         |
| admin    | No        | same                                                                         |
| API      | No        | `SENTRY_DSN` unset in agent env; live API `healthz` was 502 earlier same day |

### Uptime monitors + alert

| Check                                                     | Result                                                               |
| --------------------------------------------------------- | -------------------------------------------------------------------- |
| UptimeRobot monitors for locale health / healthz / readyz | **NOT_AUDITABLE** (no UptimeRobot API access in agent env)           |
| n8n `uptime-alert` live import + activate                 | Not activated (requires `UPTIME_WEBHOOK_SECRET` + WhatsApp template) |
| Controlled down-alert delivery + latency                  | **NOT RUN**                                                          |

---

## Founder checklist to close G6

1. In Sentry org `convergeo-w2`, create projects: `vergeo5-customer`, `vergeo5-vendor`, `vergeo5-admin`, `vergeo5-api` (or grant agent create-project permission and re-run).
2. Set per-surface DSNs (env only):
   - API: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`/`GIT_SHA`
   - Apps: `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT`, `NEXT_PUBLIC_SENTRY_RELEASE`
3. Fire protected test endpoints; confirm four events with tags `application`, `release_sha`, `test_event=true` (paste redacted issue URLs here).
4. Set n8n `UPTIME_WEBHOOK_SECRET`; import/activate `uptime-alert.json`.
5. Create five UptimeRobot monitors per `infra/uptimerobot.md` with header `X-Uptime-Secret`.
6. Force one down notification; record WhatsApp delivery timestamp and latency (no secrets).
7. Only then flip G6 → PASS with this evidence file updated.

---

## Explicit non-claims

- Not G6 PASS
- Not production-money approval
- Source-map upload not demonstrated (needs `SENTRY_AUTH_TOKEN` on deploy host)

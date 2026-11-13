# n8n on Vergeo5 OCI

n8n runs as a container in `infra/docker-compose.yml` and is exposed **only** behind Caddy at `n8n.vergeo5.com` (TLS terminated at Caddy).

## Purpose (launch)

- Notification outbox digests and retries (M14)
- Payment reconciliation alerts (M08)
- Nightly Postgres backups to OCI Object Storage (M01-P07)

## Workflows

Importable workflow JSON lives in `infra/n8n/*.json` (registry: `docs/ops/n8n-workflows.md`).
Database backup: `backup.json` + schedule notes in `backup-schedule.md` — see
`docs/ops/backup-runbook.md` (CODE_COMPLETE; G7 still needs live dump + restore proof).

### Disabled response-check drafts

`kyc-nudge.json`, `low-stock-alert.json`, `review-request.json`, and
`abandoned-cart.json` are separate, inactive schedules. Each now checks the API's
`items`/`count`/`enqueued`/`skipped` envelope after its POST and fails on a missing or
inconsistent body, even if HTTP returned 200. A valid `skipped` count is not treated
as an error: the API uses it for preference exclusions and outbox dedupe collisions.
The four POST nodes have no automatic retry; a failed batch may already have queued
earlier items, and the next scheduled tick uses the API's stable outbox dedupe key.
This isolates **workflow branches**. The API still enqueues items inside one tick,
so a failure on one item aborts that tick; these workflow drafts cannot provide
per-item recovery or explain the live low-stock 500 without an API-side diagnosis.

`payment-sweeper.json` is also inactive and now checks its four documented result
counters. Its existing 3-attempt/5-second transport retry and error branch are
unchanged. This source file is separate from the live combined reconciliation
workflow; review the exact live export before transplanting the check.

The shared error handler is still inactive. After its import, credential check, and
approved activation, bind each target workflow's **instance-local**
`settings.errorWorkflow` to the verified handler in n8n Workflow Settings. Keep the
ID out of these portable JSON files. An Error Trigger node inside a workflow is not
a substitute for that setting. See `docs/ops/n8n-backup-and-alerts.md` for the
founder-owned activation gates. Likewise, `admin-digest.json` already contains a
WhatsApp send node; the reported live fetch-only digest needs an exact live export
comparison before any source patch or import. No recipient or delivery action is
added by this draft.

Mocked checks: `node --test scripts/ci/n8n-workflow-outcome.test.mjs`.

`scripts/n8n/prepare-combined-repair-drafts.mjs` prepares **inactive** copies of
the installed combined nudges and payment/reconciliation workflows from the
scrubbed, read-only reference `convergeo-n8n-installed-scrubbed-2026-10-05.json`.
It requires the reviewed 18,173-byte SHA-256
`c47a4b0006a0b9f3bde53a76a24287cf335fd0c1174fb3d1087414d6cfae25ca` and
exact active version IDs. Usage: `node scripts/n8n/prepare-combined-repair-drafts.mjs
<scrubbed-reference.json> <local-output-directory>`. It preserves the other
money branches and their existing no-retry policy; only the payment sweeper
branch gets a counter check. It never imports or activates a workflow. Its
synthetic, source-only test is
`node --test scripts/n8n/prepare-combined-repair-drafts.test.mjs`.

## Security notes

- Enable `N8N_BASIC_AUTH_*` in `infra/.env` (names in `.env.example` only).
- Do not expose port `5678` publicly — Caddy is the sole entrypoint.
- Rotate `N8N_ENCRYPTION_KEY` only with a documented credential migration (breaks stored credentials).

## Operations

```bash
cd infra
docker compose logs -f n8n
docker compose restart n8n
```

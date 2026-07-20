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

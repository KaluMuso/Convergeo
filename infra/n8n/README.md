# n8n on Vergeo5 OCI

n8n runs as a container in `infra/docker-compose.yml` and is exposed **only** behind Caddy at `n8n.vergeo5.com` (TLS terminated at Caddy).

## Purpose (launch)

- Notification outbox digests and retries (M14)
- Payment reconciliation alerts (M08)
- Nightly Postgres backups to OCI Object Storage (M01-P07)

## Workflows

Workflow JSON exports will live under `infra/n8n/workflows/` in later pebbles (M14+). At M01-P06 we only commit the container + routing.

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

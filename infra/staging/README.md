# Staging plane templates (STG-01)

Isolated staging infrastructure **code** for Vergeo5. Does not provision cloud
resources by itself.

| Path                                   | Purpose                                  |
| -------------------------------------- | ---------------------------------------- |
| `forbidden-production-identifiers.env` | Public prod IDs staging must never equal |
| `.env.staging.example`                 | OCI/API/n8n env **names** for staging    |
| `docker-compose.staging.yml`           | Distinct containers/ports/volumes        |
| `redeploy-api-staging.sh`              | SHA-tagged deploy + rollback             |
| `vercel-preview.env.example`           | Branch `staging` Preview env names       |
| `n8n/README.md`                        | Import / activate / rollback             |

Docs:

- `docs/production-readiness/2026-07-18/staging/staging-plane-runbook.md`
- `docs/production-readiness/2026-07-18/staging/staging-secret-register.md`
- `docs/production-readiness/2026-07-18/staging/staging-provisioning-checklist.md`

CI: `.github/workflows/deploy-staging.yml` + `scripts/ci/check-staging-separation.sh`.

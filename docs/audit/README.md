# Convergeo / Vergeo5 Platform Audit (2026-07-24)

Evidence-based audit of the full platform. **No code fixes** — documentation only.

## Start here

1. [Platform Architecture Overview](./platform-architecture-overview.md) — executive summary
2. [Platform Risk Register](./platform-risk-register.md) — prioritized findings
3. [Prioritised Remediation Roadmap](./prioritised-remediation-roadmap.md) — what to fix first

## Reports

| #   | Report                                                                                 |
| --- | -------------------------------------------------------------------------------------- |
| 1   | [platform-architecture-overview.md](./platform-architecture-overview.md)               |
| 2   | [customer-pages-and-components.md](./customer-pages-and-components.md)                 |
| 3   | [vendor-pages-and-components.md](./vendor-pages-and-components.md)                     |
| 4   | [admin-pages-and-components.md](./admin-pages-and-components.md)                       |
| 5   | [frontend-backend-integration-map.md](./frontend-backend-integration-map.md)           |
| 6   | [api-inventory.md](./api-inventory.md)                                                 |
| 7   | [database-schema-and-rls-audit.md](./database-schema-and-rls-audit.md)                 |
| 8   | [authentication-and-permissions-matrix.md](./authentication-and-permissions-matrix.md) |
| 9   | [automation-workflow-inventory.md](./automation-workflow-inventory.md)                 |
| 10  | [ui-ux-browser-audit.md](./ui-ux-browser-audit.md)                                     |
| 11  | [deployment-and-environment-audit.md](./deployment-and-environment-audit.md)           |
| 12  | [testing-and-observability-audit.md](./testing-and-observability-audit.md)             |
| 13  | [dead-code-unused-routes-and-mocks.md](./dead-code-unused-routes-and-mocks.md)         |
| 14  | [platform-risk-register.md](./platform-risk-register.md)                               |
| 15  | [prioritised-remediation-roadmap.md](./prioritised-remediation-roadmap.md)             |

## Machine-readable inventory

- [inventory.json](./inventory.json) — applications, pages, components, API endpoints, workflows, known issues

## Evidence artifacts (internal)

- `_prod_api_paths.json` — parsed from production OpenAPI (not committed if large)

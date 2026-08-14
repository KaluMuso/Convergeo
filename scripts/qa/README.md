# Release certification framework

Independent, mode-aware release certification for Vergeo5. Produces per-gate JSON
fragments under `scripts/qa/evidence/<sha>/<environment>/<runId>/` and aggregates
them into machine-readable certificates.

## Modes

| Mode                   | Certificate title                      | Strict exit 0 when         |
| ---------------------- | -------------------------------------- | -------------------------- |
| `local-development`    | Local Development Report (report-only) | `LOCAL_DEVELOPMENT_REPORT` |
| `ci`                   | CI Release Certificate                 | `PASS` only                |
| `integrated-staging`   | Staging Release Certificate            | `PASS` only                |
| `production-readiness` | Production-Readiness Certificate       | `PASS` only                |

Terminal successful certification verdict is **`PASS`** (all required gates PASS).
Any `FAIL`, `BLOCKED_EXTERNAL`, `NOT_RUN`, `UNKNOWN`, `MEASUREMENT_UNSTABLE`, or
missing required gate yields a non-`PASS` verdict and strict modes exit non-zero.

## Commands

```bash
# Local report (never a promotion certificate)
pnpm release-certify:local

# CI static/integration subset
bash scripts/qa/release-certify.sh --mode ci --layer static --skip-e2e --skip-rls

# Strict staging (requires seed reset, deploy identity proof, etc.)
bash scripts/qa/release-certify.sh --mode integrated-staging --environment staging
```

Integrated-staging certification on GitHub Actions must run via
`.github/workflows/release-certify.yml` with explicit `candidate_sha` input matching
the exact staging candidate commit. On success it uploads immutable artifact
`staging-certification-evidence` consumed by the merge gate (RELCTRL-03).

## Self-tests

```bash
pnpm release-certify:self-test
```

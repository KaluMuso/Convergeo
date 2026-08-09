# Release certification (`scripts/qa`)

Independent certification framework for promotion decisions. Failures are
undeniable — certificates cannot go green from stale evidence, missing gates,
or misclassified external blocks.

## Modes

| Mode                   | Title                                                | Exit 0 when                          |
| ---------------------- | ---------------------------------------------------- | ------------------------------------ |
| `local-development`    | Local Development Report (not a release certificate) | report generated                     |
| `ci`                   | CI Release Certificate                               | `CERTIFIABLE_AFTER_INTEGRATION` only |
| `integrated-staging`   | Staging Release Certificate                          | `CERTIFIABLE_AFTER_INTEGRATION` only |
| `production-readiness` | Production-Readiness Certificate                     | `CERTIFIABLE_AFTER_INTEGRATION` only |

Required gates per mode: [`required-gates.json`](./required-gates.json).

## Evidence isolation

Every run writes to:

```text
scripts/qa/evidence/<git-sha>/<environment>/<run-id>/gate-*.json
```

Collectors load **only** that namespace. Fragments whose embedded `sha` /
`environment` / `run_id` disagree are rejected. Sibling namespaces cannot
contaminate a certificate.

## Status vocabulary

`PASS` · `FAIL` · `BLOCKED_EXTERNAL` · `NOT_RUN` · `UNKNOWN` · `MEASUREMENT_UNSTABLE`

Missing required gates are injected as `NOT_RUN` and never equal PASS.

## Usage

```bash
# Local report (non-blocking)
pnpm release-certify:local

# CI-mode static + self-tests (skips E2E/RLS when unavailable)
bash scripts/qa/release-certify.sh --mode ci --layer static --skip-e2e --skip-rls

# Strict staging (requires seed reset, deploy identity proof, etc.)
bash scripts/qa/release-certify.sh --mode integrated-staging --environment staging
```

## Self-tests

```bash
node --test scripts/qa/self-test/*.test.mjs
```

Includes: evidence isolation (stale SHA rejection), required-gate enforcement,
RLS classification, command-log sanitization, planted critical FAIL → red exit.

## Recovery semantics

- `backup-script-dry-run` — `backup_drill.sh --dry-run` only
- `restore-drill-proof` — real restore (`CERT_RUN_RESTORE_DRILL=1`); dry-run
  cannot satisfy this gate

## Deterministic browser deps

E2E installs once via `npm ci` against committed `e2e/package-lock.json`.
Never `npm install --no-package-lock`.

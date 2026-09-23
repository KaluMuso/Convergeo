# Lane C workflow patch request

Owner: Lane C (`.github/workflows/ci.yml`)

Lane B did not edit the shared workflow. Please replace the dependency job's inline Node audit parser with the B-owned fail-closed command after integrating this branch:

```yaml
- name: pnpm audit (fail on high)
  run: pnpm audit:dependencies -- --output audit.json
```

Before wiring, make an explicit decision about the two remaining high advisories `GHSA-jmr9-qjv8-65gv` and `GHSA-7pqw-9j4j-h8q3`. `scripts/ci/pnpm-audit-gate.mjs` intentionally has no allowlist, so it remains red until either the chain is removed/patched or an independently approved, bounded exception mechanism is supplied by the security owner. Do not copy the current broad inline allowlist automatically.

Keep Node and Python audits independent so a failed Node step cannot skip Python evidence. Suggested structure:

1. frozen pnpm install;
2. Node audit command, uploading raw `audit.json` even on a blocking result;
3. frozen API `uv sync --dev --frozen` in a separate step/job;
4. `uv export --frozen --all-groups --no-hashes` followed by pinned `pip-audit@2.10.1`, uploading raw JSON;
5. a final fail-closed aggregation step/job that consumes explicit exit codes and fails for missing, empty, malformed, or command-error evidence.

Required parser proof already exists:

```text
pnpm test:audit-gate
```

It covers empty output, malformed JSON, audit command failure, audit error payload, a planted high finding, and a valid non-blocking report.

Do not change the severity threshold. Preserve the `Dependency audit` required check name unless branch protection is deliberately coordinated. Add the standalone E2E lockfile audit (`npm ci --ignore-scripts && npm audit --json`) as a separate evidence-producing step if it is not already covered elsewhere.

After authorized publication, required hosted jobs at the exact Lane B head are: `Dependency audit`, `Secret scan (gitleaks)`, JS/TS lint/typecheck/build/tests, API lint/typecheck/tests, security gates, bundle wrong-plane checks, and Lane C's Playwright containment compatibility test.

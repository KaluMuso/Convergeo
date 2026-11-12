# Converged candidate: source handoff

This branch is a source candidate for hosted acceptance, not approval to merge,
deploy, migrate a shared database, activate money, or start workers. Its preserved
implementation parent is `5f81957e75eef439c9ca1789717a01824b07a1f3`
with tree `6338c5e6b77301f5c0a80a65a9608dd931b0182a`. The publication commit
adds only this record, the 108-test identity list, and Vercel branch guards.
Resolve its exact HEAD and tree with `git rev-parse HEAD` and
`git rev-parse 'HEAD^{tree}'`; these values cannot be embedded in their own commit.

## Reproduce from source

- Use Node 22, pnpm 9.15.4, Python 3.12, the committed locks, and disposable
  PostgreSQL 17.6 with the repository's extensions. `pnpm install --frozen-lockfile`
  and `pnpm turbo run lint typecheck test build` run the JS checks from the root.
- In `services/api`, `uv sync --dev`, then `uv run ruff check .`,
  `uv run mypy app tests scripts`, and `uv run pytest` run the API checks. DB
  cases require an isolated, fixture-compatible database and local roles/Auth;
  never point reset or migration commands at staging or production.
- `docs/acceptance/remaining-108-nodeids.json` contains the exact 108 original
  pytest node IDs, in input order, without private connection strings or results.
  Run each selected module against its own clone of a pristine PG17.6 template;
  preserve process exit codes and test reports. The private local orchestration
  depended on local Docker volumes and credentials and was not published.
- `e2e` is a separate pnpm package. Its Playwright tests need private same-site
  HTTPS origins, real local GoTrue OTP sessions and server roles, configured
  Access verification, and synthetic external provider responses. Do not use
  application auth bypasses. Credentials, TLS keys, browser state, and raw
  artifacts remain in the private handoff.

## Source-bound local evidence

The original 108 database identities passed 108/108 in 241 retained attempts at
`19c7fcbbdfb5c107eed9090161e96014029731b3` on the then 124-migration
template. This was not a final-HEAD 108-case rerun. At
`458f9aa88a01d981264fd814a81fcda84bafffa5`, a disposable PG17.6 fresh
127-migration replay and S3 114 + 13 upgrade had parity, and the sensitive
transaction/role subset passed 228/228. Later commits changed E2E fixtures only;
the exact `5f81957e` API image passed a local PG17.6 COD smoke.

The 65 browser identities yielded **40 authentic passes**, **12 payment-honesty
passes using real local Auth and deterministic provider status**, 8 disabled
clips cases, one inapplicable desktop mobile-nav assertion, 3 unstable INP
measurements, and one externally blocked MoMo case. This is not 65 passes or a
real provider-payment claim. The non-pass identities are:

| Result | Playwright IDs |
| --- | --- |
| Feature disabled | `46faaf85ec7d84c92492-e58ddad7ecfbd316fedd`, `46faaf85ec7d84c92492-a5d7098d34e2606dccac`, `46faaf85ec7d84c92492-6e05856594e37c1c82b0`, `46faaf85ec7d84c92492-04d6b05ea93a4ae484a9`, `b1cb44e606117cba3afa-37462ed2f7380b73f4eb`, `b1cb44e606117cba3afa-2bd3f5187d610c3cbeff`, `b1cb44e606117cba3afa-c0cb99d13d49775fc8fa`, `b1cb44e606117cba3afa-f5505e2feee19b418ea9` |
| Inapplicable desktop mobile-nav assertion | `2463d90220c817a01905-459848869e1d3fa6c64a` |
| INP measurement unstable | `3696a392312a87c68768-707cc217b62c4cdf543a`, `3696a392312a87c68768-c97f82e6d78e57e7db1e`, `3696a392312a87c68768-26298abc64678e4a3385` |
| External provider blocked | `d4d824e7ba51444f8f43-7e6bc9de9c242f383e5b` |

The fixed local responsiveness lab recorded a 352 ms checkout interaction
candidate, above the 200 ms target, with missing LCP; home and PDP lost their
execution context. No stable three-route INP verdict or field claim exists.

Hosted acceptance still needs a stable responsiveness result, authorized
provider-only testing, target Auth/Access checks, migration-ledger and worker
inventory reconciliation, accounting-policy signoff, and independent final
acceptance. Preserve accepted receipts and unresolved financial obligations.
The source guards only suppress automatic Vercel deployment of this exact branch;
manual staging and production operations require separate authorization.

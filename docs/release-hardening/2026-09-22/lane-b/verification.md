# Lane B verification register

All reported local passes use isolated Linux containers and the repository-pinned runtimes. Raw logs and exit-code sidecars are in `lane-b-security-deps-export-20260922T110458Z`.

## Dependency and install gates

| Gate                                                 | Result                  | Evidence                                                                 |
| ---------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------ |
| Exact Node frozen install (`22.23.2`, pnpm `9.15.4`) | PASS                    | `tests/candidate-pnpm-install.log`                                       |
| Root Node audit JSON                                 | FAIL (expected blocker) | `audit/candidate-pnpm-audit.json`: 0 critical, 2 high, 7 moderate, 0 low |
| Fail-closed audit gate                               | FAIL (correctly blocks) | `tests/candidate-pnpm-audit-gate.log`; only the two `extract-zip` highs  |
| Audit-gate self-tests                                | PASS, 6/6               | `tests/audit-gate-self-test.tap`                                         |
| Standalone E2E clean install                         | PASS                    | `tests/candidate-e2e-npm-ci.*`                                           |
| Standalone E2E npm audit                             | PASS, 0 vulnerabilities | `audit/e2e-npm-audit.json`                                               |
| Exact Python frozen export/audit                     | PASS, 0 vulnerabilities | `audit/candidate-pip-audit-final.json`                                   |

## JS/TS regression

| Gate                                     | Result                                                                                  |
| ---------------------------------------- | --------------------------------------------------------------------------------------- |
| `pnpm lint`                              | PASS                                                                                    |
| `pnpm typecheck`                         | PASS                                                                                    |
| `pnpm build` (all three apps/workspaces) | PASS                                                                                    |
| `pnpm test`                              | PASS; 16/16 Turbo tasks, customer 140 files / 732 tests plus the other workspace suites |
| `pnpm release-certify:self-test`         | PASS; 268/268                                                                           |
| Wrong-plane unit gate                    | PASS                                                                                    |
| Wrong-plane scan                         | PASS                                                                                    |
| Bundle guard                             | PASS                                                                                    |
| Bundle-guard self-test                   | PASS                                                                                    |
| Standalone E2E typecheck                 | PASS                                                                                    |
| Standalone E2E test discovery/list       | PASS                                                                                    |

The first generic Node container lacked Python and caused the i18n/release harness to fail. The retained reruns installed Python and passed. The six subsequent release-self-test failures were Windows-checkout CRLF artifacts in copied shell files; the final isolated Linux-equivalent run normalized only the throwaway copy and passed 268/268. These harness attempts are retained rather than hidden.

## API regression

| Gate                                   | Result                             |
| -------------------------------------- | ---------------------------------- |
| `uv sync --dev --frozen` at final lock | PASS                               |
| `uv run ruff check .`                  | PASS                               |
| `uv run mypy app tests scripts`        | PASS; 641 source files             |
| Focused auth/health regression         | PASS; 80/80                        |
| Full `uv run pytest`                   | INCOMPLETE / not claimed as a pass |

The broad API invocation collected 8,674 tests but encountered database-backed RLS and analytics setup errors because this lane had no distinct local database/project. It was stopped after preserving the raw partial log; sharing Lane A's running mutable database would violate the packet's isolation requirement. The affected dependency paths were still exercised by frozen installation, import/type analysis, FastAPI/TestClient health tests, and authentication tests. Full database-backed API CI remains required after authorized publication.

## Secret and security gates

| Gate                                                 | Result                                  |
| ---------------------------------------------------- | --------------------------------------- |
| Gitleaks 8.28.0 planted-secret self-test             | PASS                                    |
| Gitleaks 8.28.0 redacted candidate working-tree scan | PASS; no leaks                          |
| n8n plaintext-secret guard                           | PASS; 28 workflows                      |
| Supabase production advisor/catalog inspection       | PASS as read-only evidence; no mutation |

The working-tree scan initially classified `scripts/ci/fixtures/merge-evidence-incident-640.json`'s three identical 40-character commit SHAs as a generic API key. The exact fixture path is now documented in the existing RELCTRL SHA allowlist. This is a narrow false-positive classification, not an advisory or secret exception; the planted-secret self-test continues to prove scanner enforcement.

## Verification level

- Source-only: Lane C workflow integration request and any future Supabase migration.
- Locally verified: dependency locks, parser behavior, frontend build/tests, focused API regression, audits, secret and bundle gates.
- CI-verified: NOT_RUN at this unpublished head.
- Staged/live: NOT_RUN.
- Production-verified: read-only advisor/catalog state only; no code/config/database mutation.
- Independent review: NOT_RUN.

The current requirement-level status is `REPAIR_REQUIRED` because the two high `extract-zip` advisories have no patch and no independently approved risk disposition, the full database-backed API/hosted CI gates remain outstanding, and leaked-password protection needs an authorized production configuration change.

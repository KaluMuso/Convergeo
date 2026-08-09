# Vergeo5 Staging Release Certificate

_Promotion certificate: only `CERTIFIABLE_AFTER_INTEGRATION` is green._

| Field       | Value                                      |
| ----------- | ------------------------------------------ |
| SHA         | `c13d6692a66c4664efe9de31ba88d7e7b9066fe6` |
| Branch      | `unknown`                                  |
| Environment | staging                                    |
| Mode        | integrated-staging                         |
| Run ID      | `stg-qa-03-20260809`                       |
| Generated   | 2026-08-09T15:11:48.591Z                   |
| **Overall** | **BASELINE_FAILING**                       |

## Summary

| Status               | Count |
| -------------------- | ----: |
| pass                 |     4 |
| fail                 |     2 |
| blocked external     |     1 |
| not run              |    20 |
| unknown              |     2 |
| measurement unstable |     0 |
| rejected             |     0 |

## Required gates

| Gate                  | Status           | Detail                                                                                                                   |
| --------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| lint                  | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| typecheck             | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| unit-js               | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| unit-api              | PASS             | test_seed_staging.py 13 passed                                                                                           |
| i18n-parity           | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| deps-audit            | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| migration-replay      | PASS             | staging iyasmrmbcrvlfxpzescb at migration tip 20260802153539 (96 migrations)                                             |
| rls-isolation         | UNKNOWN          | RLS enabled on carts/orders/vendors/listings/checkout_groups; cross-persona pytest not run against live staging (identit |
| int-cart              | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-checkout          | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-rfq               | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-returns           | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-orders            | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-reviews           | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-authz             | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| deploy-identity       | FAIL             | BLOCKED_DEPLOYMENT_IDENTITY: api=161b58a3 customer/vendor/admin=c13d6692 master=c13d6692; deploy-staging run 31315246673 |
| e2e-browse-journey    | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY — stale API at 161b58a3 (237 commits behind)                                                 |
| e2e-mobile-layout     | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| e2e-data-quality      | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| e2e-ux-surfaces       | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| a11y-axe-smoke        | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| perf-web-vitals-smoke | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| perf-bundle-budgets   | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| payment-sandbox       | BLOCKED_EXTERNAL | Lenco sandbox not exercised; 0 orders/0 payments on staging; identity gate                                               |
| backup-script-dry-run | PASS             | backup_drill.sh --dry-run verdict SKIP (plan only)                                                                       |
| restore-drill-proof   | UNKNOWN          | No actual staging restore verified; backup_drill.sh --dry-run only (verdict SKIP)                                        |

## Full gate matrix

| Gate                  | Layer       | Status           | Detail                                                                                                                   |
| --------------------- | ----------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| a11y-axe-smoke        | ux          | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| backup-script-dry-run | recovery    | PASS             | backup_drill.sh --dry-run verdict SKIP (plan only)                                                                       |
| deploy-identity       | deploy      | FAIL             | BLOCKED_DEPLOYMENT_IDENTITY: api=161b58a3 customer/vendor/admin=c13d6692 master=c13d6692; deploy-staging run 31315246673 |
| deps-audit            | static      | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| discovery-privacy     | discovery   | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY — deployed discovery proofs require aligned API                                              |
| e2e-browse-journey    | ux          | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY — stale API at 161b58a3 (237 commits behind)                                                 |
| e2e-data-quality      | ux          | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| e2e-mobile-layout     | ux          | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| e2e-ux-surfaces       | ux          | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| i18n-parity           | static      | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| int-authz             | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-cart              | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-checkout          | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-orders            | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-returns           | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-reviews           | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| int-rfq               | integration | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| lint                  | static      | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| migration-replay      | database    | PASS             | staging iyasmrmbcrvlfxpzescb at migration tip 20260802153539 (96 migrations)                                             |
| payment-sandbox       | payments    | BLOCKED_EXTERNAL | Lenco sandbox not exercised; 0 orders/0 payments on staging; identity gate                                               |
| perf-bundle-budgets   | performance | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| perf-web-vitals-smoke | performance | NOT_RUN          | BLOCKED_DEPLOYMENT_IDENTITY                                                                                              |
| restore-drill-proof   | recovery    | UNKNOWN          | No actual staging restore verified; backup_drill.sh --dry-run only (verdict SKIP)                                        |
| rls-isolation         | security    | UNKNOWN          | RLS enabled on carts/orders/vendors/listings/checkout_groups; cross-persona pytest not run against live staging (identit |
| seed-safety           | database    | PASS             | seed_staging.py guards + test_seed_staging.py 13/13 + test-staging-guards.sh 21 pass                                     |
| synthetic-marketplace | data        | FAIL             | Seed contract incomplete: 1 listing, 0 location stock, 0 orders, no multi-seller Product A                               |
| typecheck             | static      | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |
| unit-api              | static      | PASS             | test_seed_staging.py 13 passed                                                                                           |
| unit-js               | static      | NOT_RUN          | Not in STG-QA-03 scope this run                                                                                          |

---

_No false green: BLOCKED_EXTERNAL, NOT_RUN, UNKNOWN, MEASUREMENT_UNSTABLE, and missing required gates are never translated to PASS._

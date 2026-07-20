# Defects / blockers discovered — Prompt 10 (2026-07-20)

| ID       | Severity | Defect                                                                             | Blocks                                        |
| -------- | -------- | ---------------------------------------------------------------------------------- | --------------------------------------------- |
| D-OPS-01 | P0       | `infra/n8n/backup.json` absent; n8n has zero backup workflows                      | G7, LIVE-09, approved restore                 |
| D-OPS-02 | P0       | No OCI/approved production backup artifact available to this agent                 | G7 restore of real data                       |
| D-OPS-03 | P0       | API `api.vergeo5.com` returns **502** on healthz/readyz/fingerprint                | G9, load, API readiness after restore         |
| D-OPS-04 | P0       | `DEPLOYED_API_DIGEST=UNKNOWN`                                                      | Immutable API rollback drill                  |
| D-OPS-05 | P0       | Live migration tip `0063_revoke_execute_review_reply_guards` vs repo tip semantics | Safe rollback / money drills                  |
| D-OPS-06 | P1       | `k6` binary absent in cloud agent environment                                      | Live 100cc run                                |
| D-OPS-07 | P1       | No approved staging target with Lenco stub + seeded JWTs                           | Load + invariant post-check                   |
| D-OPS-08 | P2       | Drill backup contains only `pad` + `platform_config` (+ test migration)            | Meaningful RLS/catalogue/money restore checks |

No threshold or pass-criteria changes were made to mask these defects.

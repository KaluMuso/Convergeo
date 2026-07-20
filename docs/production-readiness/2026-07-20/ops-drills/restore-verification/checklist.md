# Restore verification checklist — 2026-07-20

Artifact: `vergeo5-20260720T150434Z.sql.gz` (`backup_mode=drill`, `env_id=local-ci`)

| #   | Check                         | Result             | Notes                                    |
| --- | ----------------------------- | ------------------ | ---------------------------------------- |
| 1   | Checksum before restore       | **PASS**           | SHA-256 matches manifest                 |
| 2   | Isolated non-prod target      | **PASS**           | Local Postgres DB only; dropped after    |
| 3   | Start/finish timestamps       | **PASS**           | Both `2026-07-20T15:23:11Z`              |
| 4   | Migration ledger              | **CONDITIONAL**    | Only `0099_test` — not live tip          |
| 5   | Key table counts              | **FAIL**           | Catalogue/money tables missing from dump |
| 6   | Constraints / indexes         | **CONDITIONAL**    | Present on drill tables only             |
| 7   | RLS / FORCE RLS               | **FAIL**           | No RLS-bearing app tables in restore     |
| 8   | Representative catalogue      | **FAIL**           | Missing                                  |
| 9   | Order/payment/ledger fixtures | **FAIL**           | Missing                                  |
| 10  | API readiness vs restored DB  | **NOT_RUN**        | API not re-pointed                       |
| 11  | RTO ≤ 30 min                  | **PASS (numeric)** | 0s elapsed; not a prod-artifact RTO      |
| 12  | Production overwrite          | **PASS (none)**    | `production_overwrite=false`             |

**Verdict: CONDITIONAL** — proves dump→restore plumbing on a drill artifact; does **not** clear G7.

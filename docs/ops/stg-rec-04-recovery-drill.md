# STG-REC-04 — Real Non-Production Recovery Drill Capability

Executable, fail-closed procedure for a **genuine** staging backup → restore →
verification drill into a safe disposable non-production target.

**Certification distinction (never conflate):**

| Verdict                                 | Meaning                                                  |
| --------------------------------------- | -------------------------------------------------------- |
| `BACKUP_CONFIGURATION_VALID`            | Backup scripts/workflows configured; no restore proven   |
| `RESTORE_TARGET_AUTHORIZATION_REQUIRED` | Tooling ready; disposable restore target not provisioned |
| `RESTORE_FAILED`                        | Restore operation failed before verification             |
| `RESTORE_VERIFICATION_FAILED`           | Restore completed but smoke/RLS/schema checks failed     |
| `RESTORE_DRILL_PROVEN`                  | Full drill succeeded with evidence                       |

Dry-run (`--dry-run`, `backup_drill.sh --dry-run`) **cannot** satisfy
`RESTORE_DRILL_PROVEN`.

## Project identity (public refs only)

| Role                                  | Project ref            | Name           | Region     |
| ------------------------------------- | ---------------------- | -------------- | ---------- |
| **Staging source**                    | `iyasmrmbcrvlfxpzescb` | vergeo-sandbox | eu-west-1  |
| **Production (never restore target)** | `dpadrlxukcjbewpqympu` | Vergeo5        | eu-north-1 |

Production database host `db.dpadrlxukcjbewpqympu.supabase.co` is **hard-rejected**
by `scripts/ops/lib/recovery-guards.sh` and `services/api/app/core/recovery_guards.py`.
There is no `--force-production` escape hatch.

## Safe restore target options (preferred order)

1. **Dedicated recovery/drill Supabase project** (recommended) — isolated project
   ref ≠ staging ≠ production; migrations applied; disposable after drill.
2. **Supabase branching** — preview branch database if founder authorizes plan cost.
3. **Local ephemeral Postgres** — proves dump/restore plumbing only; does **not**
   prove Supabase RLS/extensions/auth integration. Use `infra/scripts/restore-drill.sh`
   for CI plumbing proof.

> **Supabase hosted Postgres** does not support multiple databases per project.
> A restore into staging's `postgres` database would destroy the active staging
> plane. The drill **must** target a separate project or authorized branch.

## Founder authorization required

**Action:** Provision a disposable non-production Supabase project (or authorize
a Supabase preview branch) for recovery drills.

| Item        | Detail                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| Scope       | One dedicated drill project OR branch, eu-west-1 preferred (near staging)                              |
| Cost        | Supabase project/branch may incur monthly compute; **do not create without explicit founder approval** |
| Credentials | Store `RESTORE_TARGET_DB_URL` in founder secret manager only                                           |
| Lifecycle   | Reset or delete drill project after each drill                                                         |

Once provisioned:

```bash
export SOURCE_DB_URL="$STAGING_DB_URL"              # iyasmrmbcrvlfxpzescb (read)
export RESTORE_TARGET_DB_URL="$RECOVERY_DRILL_DB_URL" # dedicated drill project
export RESTORE_TARGET_KIND=dedicated-drill-project
bash scripts/ops/recovery-drill.sh
```

Evidence JSON is written to `RECOVERY_EVIDENCE_PATH`
(default `/tmp/vergeo5-recovery-evidence.json`).

## Drill contract (12 points)

The orchestrator `scripts/ops/recovery-drill.sh` proves:

1. Source identity captured (`source_project_ref`)
2. Backup generated (`pg_dump --format=custom`)
3. Backup integrity recorded (`backup_sha256`, `backup_size_bytes`)
4. Drill marker recorded in source (`vergeo5_recovery_drill_marker`)
5. Restoration into isolated target (`restore-staging.sh`)
6. Schema parity (`restore-smoke.sql` — 35 core tables)
7. Representative rows (`restore-smoke.sql` — seed tables non-empty)
8. Critical constraints/functions (smoke + migration ledger currency)
9. RLS enabled (`recovery-rls-check.sql`)
10. Application-critical tables available (smoke required tables)
11. Recovery duration recorded (`duration_seconds`)
12. Target disposed safely (founder resets drill project post-evidence)

## Evidence schema

Machine-readable evidence: `scripts/ops/recovery-evidence.schema.json`

Compatible with QA-02 gate collectors under `scripts/qa/evidence/<sha>/…`.

**Never includes** connection strings, passwords, or service-role keys.

## Tooling map

| Component                        | Role                               | Real vs dry-run             |
| -------------------------------- | ---------------------------------- | --------------------------- |
| `infra/scripts/db-dump.sh`       | Nightly plain-gzip backup → OCI    | Real when creds set         |
| `infra/scripts/db-restore.sh`    | Restore nightly `.sql.gz`          | Real; prod hard-reject      |
| `scripts/ops/restore-staging.sh` | Custom-format SOURCE→TARGET drill  | `--dry-run` = plan only     |
| `scripts/ops/recovery-drill.sh`  | STG-REC-04 orchestrator + evidence | `--plan` = plan only        |
| `infra/scripts/restore-drill.sh` | CI ephemeral marker drill          | Real isolated Postgres      |
| `scripts/ops/backup_drill.sh`    | G7 orchestrator                    | `--dry-run` ≠ restore proof |
| `infra/n8n/backup.json`          | Scheduled backup workflow          | `active: false` in repo     |

## Nightly vs drill dump formats

- **Nightly** (`db-dump.sh`): plain SQL + gzip → `db-restore.sh`
- **Drill** (`recovery-drill.sh` / `restore-staging.sh`): custom format → `pg_restore`

Do not mix formats.

## Related

- `docs/ops/backup-restore-drill.md` — G7 founder checklist
- `docs/ops/runbook-disaster-recovery.md` — incident restore
- `docs/ops/drill-log.md` — append-only drill transcript
- `infra/staging/forbidden-production-identifiers.env` — production identifiers

# n8n backup & shared failure-alert reconciliation

**Owner:** VD-P04 (backup) · VD-P06 (shared failure alert) · **Status:** committed & importable,
`active: false` (founder-gated). **Reconciles:** OPS-N8N-01 audit §3.5 (database backup **DORMANT**)
and §5 (no live shared Error Workflow) —
`docs/production-readiness/2026-07-19/ops/ops-n8n-01-automation-readiness-audit.md`.

This is the single review surface for the two workflows the audit flagged as *inactive or
unpublished*: an operator can import and review both from here without guessing, and the
**founder-owned activation tasks are explicit and left unchecked** in §8. Nothing in this
change activates anything — both JSON exports ship `active: false`.

> **Automation must never self-activate these.** A model may draft config or fill structured
> fields, but importing, publishing, or activating an n8n workflow — and every task in §8 —
> is a **founder** action. No AI/automation step may check a box in §8 or flip `active: true`.

---

## 1. Inventory (committed ↔ live)

| Workflow file (importable)               | JSON `name`                                             | Live ID (inactive)  | Trigger(s)                                                            | Money? | Owner  |
| ---------------------------------------- | ------------------------------------------------------- | ------------------- | -------------------------------------------------------------------- | ------ | ------ |
| `infra/n8n/backup.json`                  | Vergeo5 — Database Backup                               | `OAdOD4kmIbSNehkJ`  | Cron `0 2 * * *` + watchdog `0 4 * * *` (Africa/Lusaka) + manual webhook | No (ops) | VD-P04 |
| `infra/n8n/money-workflow-error-alert.json` | Vergeo5 — Shared Workflow Failure Alert (deduplicated) | `LVuHqWgT1tqjYOtc`* | Error Trigger (fires on a linked workflow's failed run)              | No (alert) | VD-P06 |

\* The live `LVuHqWgT1tqjYOtc` scaffold was created WhatsApp-less (audit / fleet-import doc). The
committed JSON is the authoritative version — it **includes** the WhatsApp delivery node and the
dedupe route, so re-import it rather than publishing the WA-less scaffold.

Both are already registered in `docs/ops/n8n-workflows.md` (drift-tested by
`services/api/tests/test_n8n_registry.py`). Backup schedule contract:
`infra/n8n/backup-schedule.md`. Backup restore proof: `docs/ops/backup-restore-drill.md`.

---

## 2. Review card — `backup.json` (database backup)

| Control                 | Detail                                                                                                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Schedule**            | Nightly dump cron `0 2 * * *`; missed-schedule watchdog `0 4 * * *`; both `settings.timezone = Africa/Lusaka`. Manual break-glass drill via `POST /webhook/backup-manual`.                 |
| **Ownership**           | VD-P04. Activation is founder-only (§8). Alerts page `$env.FOUNDER_WHATSAPP_TO`.                                                                                                          |
| **Credential names**    | `Vergeo5 OCI Host SSH` (SSH Private Key → 3 SSH nodes); `Vergeo5 WhatsApp Cloud API` (Header Auth → 3 WhatsApp nodes). IDs ship as `REPLACE_WITH_CREDENTIAL_ID` — **names only, no values**. |
| **Idempotency**         | Dump artifact key is timestamped (`db/vergeo5-<ts>.sql.gz`) — re-runs never overwrite. SSH nodes `retryOnFail` 2×/5s; a re-run just writes a new dated object. Alerting is deduped (below). |
| **Retention**           | 14 days (`BACKUP_RETENTION_DAYS`, D21) — OCI prune + local prune in `db-dump.sh`. n8n execution history kept ≥ 7 days for post-mortem.                                                    |
| **Encryption**          | At rest: OCI Object Storage bucket (server-side encryption, no public access, deploy-user + founder only). In transit: HTTPS upload + Postgres `sslmode=require`. Credentials at rest: n8n `N8N_ENCRYPTION_KEY`. |
| **Restore verification**| `infra/scripts/db-restore.sh` + `infra/scripts/restore-drill.sh`; runbook `docs/ops/backup-restore-drill.md`; evidence logged in `docs/ops/drill-log.md`. **G7 PASS requires a real dated dump + timed restore (RTO ≤ 30m)** — importing the workflow does not satisfy G7. |
| **Failure routing**     | Soft failure (non-zero exit; SSH nodes use `continueOnFail`) → `IF … OK` false branch → `Build Alert Payload` (redact) → **`Dedupe Ops Alert` → `IF Ops Alert Fresh`** → `WhatsApp Ops Alert`. Hard crash → internal `Error Trigger` → `Build Workflow Error Alert` → WhatsApp. May **also** be linked to the shared handler (§8). |
| **Dedupe**              | `Dedupe Ops Alert` keys on `status\|reasons` in workflow-scoped static data; repeats within `$env.BACKUP_ALERT_DEDUPE_MINUTES` (default **360** = 6 h) are suppressed, so the 02:00 dump + 04:00 watchdog + consecutive-night failures collapse to **one** page per signature. Manual-drill path is intentionally **not** deduped (a human ran it and wants the result). |
| **Rollback**            | Unpublish (MCP `unpublish_workflow` / UI → inactive); re-import last-good `backup.json` at its git SHA (scrub credential IDs); rotate the SSH / WhatsApp credentials if compromised (never log values). DB data rollback is out-of-band via `infra/ROLLBACK.md` + restore drill. |
| **Operator alerts**     | Founder WhatsApp, metadata only: status, reasons, `env_id`, dump name, size, sha256 **prefix**, migration tip, redacted stderr tail. Never connection strings, Bearer tokens, or service-role keys. |

**n8n `$env` (instance):** `WHATSAPP_CLOUD_API_URL`, `WHATSAPP_CLOUD_API_TOKEN`,
`FOUNDER_WHATSAPP_TO`, `BACKUP_WEBHOOK_SECRET`, optional `BACKUP_MIN_BYTES` (default 10240),
optional `BACKUP_ALERT_DEDUPE_MINUTES` (default 360).
**VM `infra/.env`:** `SUPABASE_DB_URL`, `OCI_NAMESPACE`, `OCI_BUCKET_NAME`, `OCI_CLI_PROFILE`
(or instance principal), `BACKUP_RETENTION_DAYS`. `db-dump.sh` reads these at runtime —
**never** embed a value in the workflow JSON or a message.

---

## 3. Review card — `money-workflow-error-alert.json` (shared failure alert)

| Control                 | Detail                                                                                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Schedule**            | None — event-driven. An `Error Trigger` fires when a **linked** workflow's run ends in error (linked via each workflow's `settings.errorWorkflow`).                        |
| **Ownership**           | VD-P06. Shared handler for money ticks (`release-job`, `reconciliation`, `payment-sweeper`, `payout-failure-alert`) and `backup.json`. Pages `$env.FOUNDER_WHATSAPP_TO`.  |
| **Credential names**    | WhatsApp Cloud API via `$env` Bearer (no bound credential needed). No SSH, no internal token — it never calls our API.                                                    |
| **Idempotency**         | Alert delivery only; no state mutation. `Page Founder On Failure` uses `retryOnFail` 2×/60s + `continueOnFail` so a transient WhatsApp 5xx retries without erroring the handler itself. |
| **Retention**           | n8n execution history ≥ 7 days. Dedupe state is pruned each run (see below).                                                                                              |
| **Encryption**          | Outbound HTTPS to Graph API. Credentials at rest via `N8N_ENCRYPTION_KEY`. No dump/PII involved.                                                                          |
| **Restore verification**| N/A (no data path).                                                                                                                                                       |
| **Failure routing**     | `Error Trigger` → `Sanitize Error Payload` (metadata only) → **`Deduplicate Alert` → `IF Alert Fresh`** → `Page Founder On Failure`.                                       |
| **Dedupe**              | `Deduplicate Alert` keys on `workflow\|status\|lastNode` in workflow-scoped static data; repeats within `$env.ALERT_DEDUPE_WINDOW_MINUTES` (default **15**) are suppressed. A workflow that errors every tick (e.g. the audit's "dispatch erroring every ~1m" or the 3-day daily-report failures) pages the founder **once per window**, not per run. |
| **Rollback**            | Unpublish; unlink from `settings.errorWorkflow` on downstream workflows; re-import last-good JSON at its git SHA.                                                          |
| **Operator alerts**     | Founder WhatsApp, metadata only: workflow name, status, last node, timestamp. **Never** payment references, tokens, PII, or DB/service-role keys.                          |

**n8n `$env` (instance):** `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_CLOUD_API_TOKEN`,
`FOUNDER_WHATSAPP_TO`, optional `ALERT_DEDUPE_WINDOW_MINUTES` (default 15).

---

## 4. Deduplicated alert route (how it works)

Both workflows send failure pages through the same shape:

```
… failure detected → build/sanitize payload → Dedupe (static data + cooldown) → IF fresh → WhatsApp founder page
```

- **State store:** n8n `$getWorkflowStaticData('global')` — a per-workflow map of
  `signature → last-sent-epoch-ms`. No external database, no secrets.
- **Suppression:** if the same signature paged within the cooldown window, the run is marked
  `suppress: true` and the `IF … Fresh` node drops it (no WhatsApp send). Otherwise it pages and
  records `now`.
- **Self-pruning:** expired keys are deleted each run, so the map cannot grow unbounded.
- **Windows:** `ALERT_DEDUPE_WINDOW_MINUTES` (shared handler, default 15) and
  `BACKUP_ALERT_DEDUPE_MINUTES` (backup, default 360). Tune per environment; both fail safe to
  the defaults if unset.
- **Signatures:** shared = `workflow|status|lastNode`; backup = `status|reasons`. Distinct
  *failure modes* still page independently — dedupe only collapses **repeats of the same failure**.

Net effect (the audit's acceptance point): **failed runs have a deduplicated alert route** — an
error storm becomes one actionable page, not hundreds.

---

## 5. Security invariants (must hold on every import/edit)

- **Scoped internal API access.** Workflows that call our API use a **per-concern**
  `X-Internal-Token` (e.g. `INTERNAL_DISPATCH_TOKEN`, `INTERNAL_RECONCILIATION_TOKEN`), never a
  broad key. The two workflows here call **no** internal endpoint — backup runs `db-dump.sh` over
  SSH; the alert handler calls only the WhatsApp Graph API.
- **Never a Supabase service-role key in a message.** The service-role key exists only in
  server-side env; it is **never** placed in a WhatsApp/SMS/email body or n8n payload. Backup
  alert Code nodes actively redact `service_role_key`, `postgres://…` DSNs, `password=…`, and
  `Bearer …`. `SUPABASE_DB_URL` lives in the VM `infra/.env` and is consumed by `db-dump.sh` only.
- **Secrets by reference only.** All tokens/recipients are `$env.*`; credential IDs ship as
  `REPLACE_WITH_CREDENTIAL_ID`. Enforced by `scripts/ci/validate-n8n-no-plaintext-secrets.sh`
  and `scripts/ci/validate-backup-workflow.sh`.

---

## 6. Import & review (staging first, then production — founder)

1. n8n → **Workflows → Import from file** → `infra/n8n/backup.json` and
   `infra/n8n/money-workflow-error-alert.json`. Leave both **inactive**.
2. Create the Header Auth / SSH credentials (names in §2/§3), replace each
   `REPLACE_WITH_CREDENTIAL_ID`.
3. Set the instance `$env` vars listed in §2/§3 (values never committed).
4. Review each node against the cards above — no guessing required.
5. Do **not** activate here. Activation is §8 (founder).

---

## 7. Rollback / disable (fast path)

1. **Unpublish** the workflow (MCP `unpublish_workflow` or UI → inactive). Confirm
   `search_workflows` shows `active: false`.
2. Re-import the last-known-good JSON from `infra/n8n/*.json` at a known git SHA; scrub
   credential IDs back to the placeholder.
3. If a credential/token is suspected compromised, rotate it in n8n + the API/VM env — **never**
   log or message the value. Do **not** rotate `N8N_ENCRYPTION_KEY` without a credential-migration
   plan (it invalidates all stored credentials).
4. Database rollback is separate: `infra/ROLLBACK.md` + `docs/ops/backup-restore-drill.md`.

---

## 8. Founder-owned activation tasks — explicit & UNCHECKED

> These require founder credentials and judgment. **Do not activate** until each box below is
> genuinely satisfied. Leaving them unchecked is intentional — this reconciliation ships the
> importable definitions only. AI/automation must not check these or set `active: true`.

**Shared failure alert (`money-workflow-error-alert.json`)**

- [ ] Create/confirm the `Vergeo5 WhatsApp Cloud API` credential (or `$env` WhatsApp vars) so the page node can deliver.
- [ ] Set instance `$env`: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_CLOUD_API_TOKEN`, `FOUNDER_WHATSAPP_TO`, (optional) `ALERT_DEDUPE_WINDOW_MINUTES`.
- [ ] Import the committed JSON (supersede the WA-less live scaffold `LVuHqWgT1tqjYOtc`); leave inactive.
- [ ] Force one error on a throwaway test workflow → confirm exactly **one** founder page, and a repeat within the window is suppressed.
- [ ] Activate the shared handler, then link it as `settings.errorWorkflow` on the money ticks and on `backup.json`.

**Database backup (`backup.json`)**

- [ ] Create the `Vergeo5 OCI Host SSH` (SSH Private Key) and `Vergeo5 WhatsApp Cloud API` (Header Auth) credentials; replace each `REPLACE_WITH_CREDENTIAL_ID`.
- [ ] Set instance `$env`: `WHATSAPP_CLOUD_API_URL`, `WHATSAPP_CLOUD_API_TOKEN`, `FOUNDER_WHATSAPP_TO`, `BACKUP_WEBHOOK_SECRET`, (optional) `BACKUP_MIN_BYTES`, `BACKUP_ALERT_DEDUPE_MINUTES`.
- [ ] Set VM `infra/.env`: `SUPABASE_DB_URL` (session pooler), `OCI_NAMESPACE`, `OCI_BUCKET_NAME`, `OCI_CLI_PROFILE` (or instance principal), `BACKUP_RETENTION_DAYS`.
- [ ] In the workflow Settings panel set **Timezone → Africa/Lusaka** and **Error Workflow → shared failure alert** (SDK import cannot set these).
- [ ] Confirm the OCI bucket has server-side encryption on and **no** public access.
- [ ] Activate → fire the manual drill (`X-Backup-Secret: $BACKUP_WEBHOOK_SECRET`) → confirm a dated `db/vergeo5-<ts>.sql.gz` object exists (name + size only, no secrets).
- [ ] Run a **timed restore** per `docs/ops/backup-restore-drill.md` (RTO ≤ 30 m) and log it in `docs/ops/drill-log.md` — **this**, not the import, flips **G7 → PASS**.

---

## 9. Related

- `infra/n8n/backup.json` · `infra/n8n/money-workflow-error-alert.json`
- `infra/n8n/backup-schedule.md` · `docs/ops/n8n-workflows.md` · `docs/ops/n8n-activation-runbook.md`
- `docs/ops/backup-runbook.md` · `docs/ops/backup-restore-drill.md` · `docs/ops/drill-log.md` · `infra/ROLLBACK.md`
- `docs/production-readiness/2026-07-19/ops/ops-n8n-01-automation-readiness-audit.md`
- `infra/scripts/db-dump.sh` · `db-backup-watchdog.sh` · `db-restore.sh` · `restore-drill.sh`
- Tests/guards: `scripts/ci/validate-backup-workflow.sh` · `scripts/ci/validate-n8n-no-plaintext-secrets.sh` · `services/api/tests/test_backup_workflow_artifact.py` · `services/api/tests/test_n8n_registry.py` · `services/api/tests/test_n8n_backup_alerts_reconcile.py`

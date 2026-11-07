# n8n activation runbook

**Status: inventory and approval checklist.** The owner confirms n8n runs on **Hetzner and stays there** ([issue #716](https://github.com/KaluMuso/Convergeo/issues/716) §8). Its current process, workflow IDs, versions, schedules, credentials, queues, and executions have not been verified for this runbook. Import, activation, message delivery, shared database changes, and money operations need separate exact-target owner approval. API and database rules remain in the API/database; n8n coordinates recoverable jobs and delivery.

## 1. Read-only inventory before any action

With authorized Hetzner/n8n read access, record environment and instance ID, workflow ID/name/version/active state, schedule and timezone, credential **names only**, API endpoint and target plane, queue ownership, linked error workflow, last successful/failed execution, and every outbound message or DB write. Compare each live definition with `infra/n8n/*.json` at the approved source SHA. Preserve secrets and customer data outside the evidence pack. Classify payment, reconciliation, expiry, cancellation, refund, payout, backup, notification and alert writers for the [cutover pause/drain](deploy-verify-runbook.md#1-database-change-boundary).

An authorized read-only workflow query can help inventory active state; a count alone cannot establish the expected definitions, credential bindings, healthy executions or launch readiness:

```bash
curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "https://n8n.vergeo5.com/api/v1/workflows?active=true" | jq '.data[] | {id, name, active}'
```

Confirm the actual URL and permissions before using this example. No live query or status verification was performed for this documentation update.

## 2. Activation decision per workflow

For **each** proposed activation, the owner records the exact workflow JSON hash and live ID/version, Hetzner instance, environment, API and database target, schedule, token/credential bindings, intended side effects, operator, approval record, and a disable/recovery path. Check deployment fingerprints and target migration state against the same candidate. `/readyz` being `ok` is only one observation; it never triggers automatic Wave A activation.

Before unpausing a writer after a shared cutover, prove the [writer pause/drain, exact migration application, recovery and compatibility gates](deploy-verify-runbook.md#1-database-change-boundary). Preserve incoming receipt IDs and queue state for replay; avoid two active schedulers for one job. Exercise a wrong token (401 when configured, rather than 503 for a missing token), a bounded safe execution, failure/alert routing, retries and deduplication in an approved isolated environment. A 401 does not prove the job's data behavior. Activate only the individually approved workflow, record the actual first execution result, and verify downstream effects and logs. Stop and disable the specific workflow on an unexpected write, send or failure; keep evidence for reconciliation. Do not assume an OCI Compose command controls the Hetzner instance or stop all n8n schedules as a routine rollback.

Money-moving, refund, payout, release, ticket and reconciliation workflows need their applicable provider-backed sandbox tests, approved financial policy, operator permissions, exact migration/ledger compatibility and separate activation approval. Notification and nudge workflows can send outward messages; require approved recipients, consent and message authorization. Neither group WhatsApp support nor delivery/acknowledgment is verified for this account. The [backup and shared-alert checklist](n8n-backup-and-alerts.md) is historical configuration guidance; an import or scheduled run does not prove a real backup/restore or an alert delivered to an operator.

For incident alerts, prove a durable incident record, deduplication, redaction and severity before delivery; keep messages to safe metadata and an authenticated Admin link. Prove authenticated operator acknowledgment, backup escalation and recovery/closure evidence. Use an independently operated uptime check to detect a complete Hetzner/n8n outage. Before any WhatsApp **group** delivery, verify this account/provider/group's API eligibility, group creation and join model, consent, message rules, delivery callbacks and costs; obtain the owner's approval for the actual route. A delivery receipt or group reply is not an acknowledgment or authority for a privileged action.

## 3. Historical inventory, not current status

The **2026-07-23** observation in the previous revision listed these IDs as active: notification dispatch `sevKtX1AmimQCWsG`, reconciliation `C1MpTNjrfLACMG3f`, reservation sweeper `F25zEWiPoIveARys`, embeddings `oqjfSdMXClfsf3qd`, admin digest `rb5d4LHlXAOqkfPX`, analytics retention `8drZTFO79pwMPfZy`, and operational nudges `zkIe2zW72qp5fcli` (despite a hold noted in that July record). It listed shared failure alert `LVuHqWgT1tqjYOtc` and backup `OAdOD4kmIbSNehkJ` as held. Treat all of these as **historical IDs and claims** until live read-only inventory confirms the current instance. Wave A and Wave B labels in the old plan are not activation authority. No current workflow health, backup receipt, restore result, alert route or launch readiness is established here.

Record dated operator decisions and evidence in the restricted operations record. Update release gates only from actual executions and an independent restore/compatibility review, not from checked-in JSON or this runbook.

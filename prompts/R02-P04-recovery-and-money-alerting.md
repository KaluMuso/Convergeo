> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P04 — Recovery evidence + money-workflow alerting `[CODE+OPS]`

## 1. Context
**Wave W1.** Closes RG-5 and VD-P06.

Verified 2026-08-01:
- The **restore drill is green** — 3 consecutive passes after 7 failures. But it is **CI-self-contained**: it proves the mechanism, not a restore of a real dump. RG-5 is not closed by it.
- `infra/n8n/backup.json` is imported on the instance but **inactive** (needs SSH + WhatsApp credentials).
- The **shared error alert** workflow is **inactive**.
- **None of the four money workflow JSONs declares an `errorWorkflow`** — `release-job.json`, `reconciliation.json`, `payment-sweeper.json`, `payout-failure-alert.json`. A failing money tick is therefore **silent**.

The last point is the dangerous one: reconciliation is how ledger drift is noticed, and an unmonitored reconciliation is indistinguishable from a healthy one right up until money is missing.

**Type:** `[CODE+OPS]`.

## 2. Objective & scope
A real dump restored and timed; backup + error-alert workflows active; every money workflow wired to the error handler.
**Non-goals:** new backup tooling (`infra/n8n/backup.json` and `docs/ops/backup-runbook.md` exist); moving money.

## 3. Files (edit ONLY these)
- `infra/n8n/release-job.json`, `reconciliation.json`, `payment-sweeper.json`, `payout-failure-alert.json` — add the error-workflow binding
- `docs/ops/n8n-workflows.md` — registry rows
- `docs/production-readiness/<YYYY-MM-DD>/recovery-evidence.md` (new)

**Guardrail:** `services/api/tests/test_n8n_registry.py` and `test_ops_n8n_01_audit.py` both enumerate `infra/n8n/*.json`. Any workflow you touch or add must satisfy **both**, and `scripts/ci/validate-n8n-no-plaintext-secrets.sh` must stay green.

## 4. Implementation spec
1. Bind each money workflow to the shared Error Trigger handler (`errorWorkflow` setting) so a non-2xx tick raises an actionable alert naming the workflow, the endpoint and the status.
2. Activate the shared error alert once its WhatsApp credential is bound.
3. Activate `backup.json` once SSH + storage credentials exist; observe **one successful dump** (size, checksum, destination).
4. **Restore that dump** into a scratch database. Record wall-clock **RTO** and the **RPO** implied by the schedule. Verify row counts on a few anchor tables.
5. Prove the alert fires: force one money tick to fail (point it at a deliberately bad path on **staging**) and capture the alert.

## 5. Security / conventions
Credential **names** only in the repo. The drill runs against staging/scratch — never restore over production. No real customer data in any pasted output.

## 10. Tests (RUN before reporting)
- `uv run pytest services/api/tests/test_n8n_registry.py services/api/tests/test_ops_n8n_01_audit.py services/api/tests/test_n8n_backup_alerts_reconcile.py -q`
- `bash scripts/ci/validate-n8n-no-plaintext-secrets.sh`
- The forced-failure alert, captured.
- The restore, with timings.

## 11. Acceptance criteria / DoD
- [ ] All four money workflows declare an `errorWorkflow`; a forced failure produces an alert.
- [ ] Shared error alert **active**.
- [ ] Backup workflow **active**; one successful dump recorded.
- [ ] A real dump restored to scratch; RTO/RPO documented.
- [ ] RG-5 evidence updated — and if any leg is still missing, RG-5 stays `FAIL` and says why.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P04 — Recovery + money alerting
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the alert and the restore timings · **EXCERPTS:** the errorWorkflow binding · **QUESTIONS:** …

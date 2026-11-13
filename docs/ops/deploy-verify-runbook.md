# Deploy, verify, and recovery runbook

**Status: planning and verification only.** This runbook does not authorize a shared database change, deployment, workflow activation, or production cutover. Obtain separate owner approval for each exact source, target, and action. The release acceptance contract is [issue #716](https://github.com/KaluMuso/Convergeo/issues/716) §§6–8. Use the [production release control](production-release-control.md), [disposable migration cutover contract](disposable-migration-cutover-runbook.md), and [guarded adoption boundary](lenco/service-adoption-upgrade-guard.md) for the current implementation. Older OCI/Compose and July launch plans are historical.

## 0. Bind the candidate and target

Record the reviewed Git commit and tree, PR head, exact migration filename/version/SHA-256 inventory, API and three Vercel artifact identities, frontend deployment plane, target Supabase project ref and host, non-secret configuration digest, and current migration ledger. Confirm that the target is the approved environment; staging evidence cannot approve production. Capture the deployed state separately from the proposed state. Never infer a live state from a checked-in file.

At PR #718 head `89ca38a5fa09e0e8bfa6c1ce6ea949ef04a6279b`, the checkout has **138 SQL migration files**. Recount and rehash at the actual candidate SHA. The previously captured **114-row sandbox history** and proposed 24-input gap are historical planning inputs, not proof of current target history or a safe direct upgrade. Read the actual six-column `schema_migrations` rows, including stored SQL and array shape, under authorized read-only access; compare exact rows and physical state, not just version numbers or counts. Keep row-bearing snapshots and database credentials in restricted custody outside Git.

```bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git ls-files 'supabase/migrations/*.sql' | wc -l
bash scripts/ops/verify_live.sh --dry-run # inspect verifier behavior; not release proof
```

## 1. Database change boundary

Before proposing a shared migration, the owner and independent reviewer need one target-bound plan with the complete ordered SQL and file hashes, actual ledger/owner/ACL/function body and grant state, dependency review, explicit application path through `20260929120003_adopt_existing_service_obligations.sql`, and subsequent migrations. Bind it to the source/target identities above. The [disposable rehearsal](disposable-migration-cutover-runbook.md) specifies source snapshot and dump custody, a fresh marked target, original owner/ACL restore, transaction and ledger checkpoint receipts, compatibility checks, and an independent recovery trial. Its example manifest and offline verifier do not prove source custody, live data correctness, writer drain, or release readiness.

Inventory and pause **every** API replica, payment and webhook receiver, reconciliation/expiry/cancellation job, n8n workflow, and other database writer. Record how incoming receipt IDs are buffered for durable retry, queue and in-flight counts reaching zero, and a maintenance/installer mutex covering the whole migration graph. Keep writers paused through apply and compatibility verification. Stop if any writer or committed ledger prefix is unaccounted for.

The repository's guarded adoption helper and the exact historical migration bytes must be reviewed together. `supabase db push` does **not** invoke that helper; **do not run a raw hosted push across pending `120003`** or run the helper and replay that SQL a second time. The staging pre-push guard is read-only and rejects pending adoption or missing target-bound application/review evidence; it does not repair history or authorize the push. A fresh empty replay cannot prove an upgrade of legacy orders. Keep shared application blocked until the approved plan, disposable upgrade and recovery evidence, actual target history, and applicable owner approval all agree. Never fabricate ledger rows or waive an unexplained mismatch.

After an authorized application, archive per-transaction SQL/history receipts, the final exact ledger and schema comparison, Auth/RLS and financial invariants, API/frontend compatibility, and source-to-artifact fingerprints. Resume each writer once only after the operator accepts these checks and reconciles buffered receipts. Passing `/readyz` alone does not approve migration or activation.

## 2. Recovery and rollback decision

Before any shared cutover, obtain a real immutable backup with source identity, timestamp, format, size, SHA-256, access/retention record, and a successful independent restore to an authorized fresh disposable target. Verify full history, ownership/ACLs, representative data, critical constraints/RLS, and application compatibility; time writer drain, restore, verification, and recovery point to calculate actual RTO/RPO. A backup schedule, object name, CI-only plumbing drill, or `--dry-run` is insufficient. See the [disposable cutover contract](disposable-migration-cutover-runbook.md) and [STG-REC-04 recovery drill](stg-rec-04-recovery-drill.md). The old ≤30-minute restore and 24-hour data-loss values are objectives until measured on the bound target; do not report them as achieved.

If apply fails, stop the installer, keep writers paused, preserve logs and the last committed checkpoint, and review the exact prefix before retry. For a post-cutover fault, an old API image is usable only if tested against the new schema and new financial records. Prefer an approved forward correction when old code would lose receipt, payment, order, or audit obligations. A database restore is a separate, explicitly approved decision with a verified dump, measured loss window, receipt preservation/replay and payment/Auth reconciliation. Never use `db-restore.sh --force` as a routine fallback or point a drill at staging/production `postgres`.

## 3. Runtime and frontend deployment

The owner confirms **n8n is hosted on Hetzner and stays there**. Verify the current API host, service topology, image digest, deploy control, and running replicas with the runtime operator before writing host-specific commands. Do not assume the old OCI VM or `infra/docker-compose.yml` contains the live API/Caddy/n8n stack. Do not check out `master` on a VM as a substitute for deploying the approved, target-built image. Production deployment and shared database application each require their own explicit approval.

The three Vercel projects are Customer, Vendor, and Admin. Follow [production release control](production-release-control.md) for exact-SHA staging certification and protected `master` release, and [deployment plane](deployment-plane.md) for build-time API origin binding. Record each actual deployment ID/SHA and probe its `/en/health` route. Confirm DNS and protection settings against current provider records; historical DNS tables are not live proof. Production and Preview bundles must point to their respective approved API planes. An API response or frontend health check does not demonstrate buyer, business, or operator acceptance.

For an approved deploy, compare `/healthz`, `/readyz`, `/fingerprint`, and the three portal fingerprints with the bound source, environment, artifacts and DB tip. Record failures and degraded fields. The non-destructive verifier helps collect observations:

```bash
# Replace every placeholder with identities from the same approved target.
export EXPECTED_ENV="<approved-environment>"
export MASTER_GIT_SHA="<approved-candidate-sha>"
export API_BASE_URL="<approved-api-origin>"
export CUSTOMER_URL="<approved-customer-origin>"
export VENDOR_URL="<approved-vendor-origin>"
export ADMIN_URL="<approved-admin-origin>"
export N8N_BASE_URL="<approved-n8n-origin>"
export EXPECTED_SUPABASE_PROJECT_REF="<approved-project-ref>"
export EXPECTED_IMAGE_TAG="<approved-api-image-sha>"
bash scripts/ops/verify_live.sh
```

Review the script's actual outputs and skipped gates. In `--dry-run`, it can report `OVERALL: PASS` while live gates are `SKIP`; that is not release proof. G0's historical `0064` check, G5 active-workflow count, and G9 fingerprint comparison are partial checks; none certifies the full 138-file ledger, paid-domain behavior, backup restore, or current operator approval. A new integrated SHA needs its own CI, staging and release evidence.

## 4. n8n and launch gate

Use the [n8n activation runbook](n8n-activation-runbook.md) for a **read-only** inventory of the Hetzner instance: workflow IDs/versions, active state, schedules, credentials by name, queue ownership, error routes, and recent executions. Classify every workflow that can write or send a message. `/readyz` does not authorize Wave A or Wave B activation. Require a separately approved workflow-by-workflow action, target binding, API token and negative-auth check, safe first execution, alert/retry proof, and operator receipt. Money and outbound-message workflows retain their policy and provider gates.

Before any launch claim, reconcile the full [issue #716](https://github.com/KaluMuso/Convergeo/issues/716) §6 acceptance contract, exact-source hosted checks, approved policy and provider-backed product/service/event evidence, recovery and rollback drills, operator coverage, and actual runtime facts. Mark an unobserved item **UNKNOWN** or **NOT_RUN**. The July 2026 observations elsewhere in `docs/production-readiness/` are dated evidence, not a live release certificate.

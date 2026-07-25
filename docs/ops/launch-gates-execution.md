# Launch gates execution runbook

Unified founder + agent path for **F9b** (Lenco sandbox + S1–S6), **G6** (Sentry),
**G7** (backup/restore), **F5** (WhatsApp Meta templates), and **Vercel prod promote**.

Scripts live under `scripts/ops/`; this doc is the single checklist. Never commit secrets.

---

## Quick matrix

| Gate       | What                                  | Automatable here?                  | Script / doc                                  |
| ---------- | ------------------------------------- | ---------------------------------- | --------------------------------------------- |
| **F9b**    | Lenco sandbox creds on isolated stack | Creds = founder only               | §1 below                                      |
| **S1–S6**  | Money drill harness + ledger proof    | Dry-run yes; live needs F9b        | `scripts/drills/lenco_sandbox_money_drill.py` |
| **G3**     | Payment ledger correctness            | PASS when live drill report        | `scripts/db/ledger-invariants.sql`            |
| **G6**     | Sentry DSN + test event ingest        | Smoke script when DSNs set         | `scripts/ops/sentry_smoke.sh`                 |
| **G7**     | Dated OCI backup + ≤30min restore     | Local drill yes; staging = founder | `scripts/ops/backup_drill.sh`                 |
| **F5**     | WhatsApp template Meta approval       | Submission pack in repo            | `docs/ops/whatsapp-templates.md`              |
| **Vercel** | customer/vendor/admin prod promote    | `VERCEL_TOKEN` + green builds      | `scripts/ops/vercel_promote.sh`               |

**Orchestrator:** `bash scripts/ops/launch_gates.sh` (or `--dry-run`).

**Post-deploy verifier:** `bash scripts/ops/verify_live.sh` reads optional report env vars.

---

## 0. Preconditions

- [ ] `master` tip identified (`git rev-parse HEAD`)
- [ ] API redeployed with fingerprint SHA — run **Actions → Deploy production** (`deploy-production.yml`) with `api_image_tag=d591ef5…` or current master SHA; requires `production` environment secrets `PRODUCTION_API_SSH_*`. Manual fallback: `infra/redeploy-api.sh <sha>` on Hetzner `91.107.236.37`
- [x] Migrations at repo tip on target Supabase — **70/70 applied on Vergeo5 (`dpadrlxukcjbewpqympu`) as of 2026-07-23** (`0069_orders_commission_snapshot_immutable` + `0070_vendor_commercial_tier`); API redeploy still required for fingerprint SHA + `commercial_tier` API fields
- [ ] Vendor/admin Vercel production at master — `VERCEL_TOKEN` + `bash scripts/ops/vercel_promote.sh --project vendor|admin` or **Deploy production** workflow; customer already auto-deployed from git
- [ ] `public_launch=false`; production money flags unchanged
- [ ] Isolated **staging** stack for money drills (never `api.vergeo5.com`)

---

## 1. F9b — Lenco sandbox credentials (founder)

1. Obtain from Lenco support (see `docs/ops/lenco/lenco-api-distilled.md`):
   - `LENCO_API_TOKEN`, `LENCO_ACCOUNT_ID`, `NEXT_PUBLIC_LENCO_PUBLIC_KEY`
2. On **isolated staging API only**:
   ```bash
   LENCO_ENV=sandbox
   PAYMENTS_ENABLED=true
   # never PAYMENTS_ALLOW_PRODUCTION on sandbox drills
   ```
3. Register webhook: `https://<staging-api>/webhooks/lenco`
4. Run fixtures: `psql "$SUPABASE_DB_URL" -f scripts/ops/staging-money-drill-fixtures.sql`

---

## 2. S1–S6 / G3 — Money drill

### CI / agent (no creds)

```bash
uv run python scripts/drills/lenco_sandbox_money_drill.py --mode dry-run
bash scripts/ops/launch_gates.sh --only f9b --dry-run
```

### Live sandbox (founder, isolated stack)

```bash
export LENCO_ENV=sandbox LENCO_API_TOKEN=... SUPABASE_DB_URL=... PAYMENTS_ENABLED=true
export API_BASE_URL=https://<staging-api>
uv run python scripts/drills/lenco_sandbox_money_drill.py --mode live \
  --report scripts/drills/reports/lenco-sandbox-drill-live.json
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f scripts/db/ledger-invariants.sql
```

**PASS:** `verdict=PASS`, `ledger_imbalance_ngwee=0`, gates S1/S2/S3/S6 green. Attach redacted JSON to launch checklist §3.

Runbook detail: `docs/ops/lenco/sandbox-money-drill.md`

---

## 3. G6 — Sentry DSN + test events

### Founder setup

1. Create Sentry projects under org `convergeo-w2`: `vergeo5-api`, `vergeo5-customer`, `vergeo5-vendor`, `vergeo5-admin`
2. Set DSNs:
   - API host: `SENTRY_DSN`, `SENTRY_RELEASE`, `SENTRY_ENVIRONMENT`
   - Vercel apps: `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_RELEASE`, `NEXT_PUBLIC_SENTRY_ENVIRONMENT`
3. Enable protected test paths **temporarily**:
   ```bash
   ENABLE_SENTRY_TEST_ENDPOINT=true
   INTERNAL_SENTRY_TEST_TOKEN=<random>
   SENTRY_TEST_SECRET=<random>
   ```
4. Redeploy API + promote frontends after env vars are set

### Verify

```bash
export ENABLE_SENTRY_TEST_ENDPOINT=true
export INTERNAL_SENTRY_TEST_TOKEN=...
export SENTRY_TEST_SECRET=...
bash scripts/ops/sentry_smoke.sh
```

Confirm four events in Sentry UI tagged `test_event=true`. Disable test endpoints or rotate tokens after verification.

Detail: `docs/ops/observability.md` §5

---

## 4. G7 — Dated backup + restore drill

### A. Nightly / manual OCI dump (founder on OCI host)

```bash
ssh opc@<oci-vm>
cd ~/vergeo5 && set -a && source infra/.env && set +a
export BACKUP_MODE=manual BACKUP_ENV_ID=production
bash infra/scripts/db-dump.sh
```

Or n8n webhook:

```bash
curl -fsS -X POST "https://n8n.vergeo5.com/webhook/backup-manual" \
  -H "X-Backup-Secret: ${BACKUP_WEBHOOK_SECRET}" \
  -d '{"mode":"drill"}'
```

Verify object exists:

```bash
bash scripts/ops/backup_drill.sh --verify-oci
```

### B. Staging restore (≤30 min RTO)

```bash
date -u +'DRILL START %Y-%m-%dT%H:%M:%SZ'
export SOURCE_DB_URL="$STAGING_DB_URL"
export SUPABASE_DB_URL="$STAGING_RESTORE_SCRATCH_URL"
bash scripts/ops/backup_drill.sh --staging-restore
date -u +'DRILL END %Y-%m-%dT%H:%M:%SZ'
```

Log wall-clock in `docs/ops/drill-log.md`. Local harness only (not RTO proof):

```bash
bash scripts/ops/backup_drill.sh --local
```

Detail: `docs/ops/backup-runbook.md`

---

## 5. F5 — WhatsApp Meta template approval (founder)

1. Open `docs/ops/whatsapp-templates.md` — submit templates **1–11** in WhatsApp Manager
2. Priority for launch blockers:
   - `rfq_job_broadcast` (RFQ fan-out)
   - `event_cancelled`, `event_schedule_changed` (events code paths ready)
   - `ops_uptime_alert` (uptime paging)
3. Add Bemba/Nyanja variants per D27 before broad rollout
4. Post-approval: add test number, enqueue fixture outbox row, confirm `message_status=sent`

Setup: `docs/ops/whatsapp-cloud-api-setup.md`

---

## 6. Vercel prod promote (founder)

When rate limits clear and preview builds are **READY**:

```bash
export VERCEL_TOKEN=...
export MASTER_GIT_SHA=$(git rev-parse HEAD)
bash scripts/ops/vercel_promote.sh
bash scripts/ops/probe-frontends.sh
```

Projects (team `vergeo-projects`):

| App      | Project id                         |
| -------- | ---------------------------------- |
| customer | `prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP` |
| vendor   | `prj_QiX9rpStSpNeEXd3UZDFFp7H2dXf` |
| admin    | `prj_Bpf852KXDuG1NZUomri0OsMBt1YS` |

If promote fails (build ERROR / rate limit), fix the failing preview deployment in Vercel UI first, then re-run.

Record `dpl_…` ids + `githubCommitSha` in `docs/production-readiness/.../evidence/deploy-promote.md`.

---

## 7. Full gate sweep

```bash
# Read-only live surfaces
bash scripts/ops/verify_live.sh

# Founder-gated pack (best effort)
bash scripts/ops/launch_gates.sh

# With reports for verify_live G3/G6/G7:
export MONEY_DRILL_REPORT=scripts/drills/reports/lenco-sandbox-drill-live.json
export SENTRY_SMOKE_REPORT=/tmp/vergeo5-sentry-smoke.json
export BACKUP_DRILL_REPORT=/tmp/vergeo5-backup-drill.json
bash scripts/ops/verify_live.sh
```

---

## Evidence slots

| Item                     | Where to paste proof                                           |
| ------------------------ | -------------------------------------------------------------- |
| Money drill JSON         | Launch checklist §3 staging money drill                        |
| Sentry event ids         | `docs/production-readiness/.../observability-live-evidence.md` |
| Backup/restore timings   | `docs/ops/drill-log.md`                                        |
| WhatsApp template status | `docs/ops/whatsapp-cloud-api-setup.md` checklist               |
| Vercel deploy ids        | `evidence/deploy-promote.md`                                   |

---

## Related

- `docs/ops/deploy-verify-runbook.md` — G0–G9 deploy path
- `docs/ops/lenco/sandbox-money-drill.md` — S1–S6 gate mapping
- `prompts/VB-P01-06-money-staging-verification.md` — evidence pack spec

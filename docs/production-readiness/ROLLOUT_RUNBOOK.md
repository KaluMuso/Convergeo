# Production rollout runbook — migration drift reconciliation (0072→0088)

**Written:** 2026-08-05 · **Mode:** GATED · **Owner:** Founder (solo ops)

This runbook is the ordered, copy-paste CLI path to bring **production** from ledger tip
`0071_vendor_listing_compare_at` to **`0088_user_saves`**, then deploy application code.
It pairs with the read-only drift checker `scripts/check_prod_drift.sh`.

| Field                        | Value                                                                                            |
| ---------------------------- | ------------------------------------------------------------------------------------------------ |
| Supabase project ref         | `dpadrlxukcjbewpqympu`                                                                           |
| Known live tip (pre-rollout) | `0071`                                                                                           |
| Target tip (this slice)      | `0088`                                                                                           |
| Pending count                | **17** migrations (`0072`–`0088`)                                                                |
| Repo tip (master)            | May include `0089_vendor_locations_geo_index` — **not** in this slice unless explicitly extended |

**Constraints**

- Run migrations **before** promoting code that depends on new schema.
- **Never** print or commit secrets. Export credentials into the shell only.
- **Do not** run destructive SQL by hand. Use `supabase db push` or Supabase Dashboard SQL editor for one-off repairs only when the CLI is blocked.
- Migrations are **forward-only** in prod. Roll back application first; restore DB only if schema apply failed or data was corrupted.

**Related docs:** `scripts/check_prod_drift.sh` · `docs/ops/supabase-workflow.md` ·
`docs/ops/deploy-verify-runbook.md` · `docs/ops/backup-runbook.md` · `infra/ROLLBACK.md` ·
`infra/redeploy-api.sh`

---

## 0. Preconditions

| #   | Check                                       | Command / action                                                                                                           |
| --- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 0.1 | On `master` at the intended release SHA     | `git fetch origin && git checkout master && git pull --ff-only && git rev-parse HEAD`                                      |
| 0.2 | CI green on that SHA                        | GitHub Actions → required checks                                                                                           |
| 0.3 | Maintenance note written                    | Timestamp + SHA in founder ops log                                                                                         |
| 0.4 | Credentials available (names only)          | `SUPABASE_DB_URL`, `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD`, `SUPABASE_PROJECT_ID`, `VERCEL_TOKEN`, SSH to API host |
| 0.5 | Money tables still at zero (launch posture) | Optional sanity: `psql "$SUPABASE_DB_URL" -tA -c "SELECT count(*) FROM payments;"` → expect `0`                            |

Record the release SHA as `RELEASE_SHA` for the rest of this runbook:

```bash
export RELEASE_SHA="$(git rev-parse HEAD)"
echo "RELEASE_SHA=${RELEASE_SHA}"
```

---

## 1. Drift check (read-only)

Prove which migrations are pending **before** any writes.

```bash
cd ~/vergeo5   # or your local clone path

# Requires psql + SUPABASE_DB_URL (session pooler, port 5432, sslmode=require)
export SUPABASE_DB_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require'

bash scripts/check_prod_drift.sh
```

**Expected pre-rollout output (illustrative):**

```text
LIVE_TIP=0071_vendor_listing_compare_at
LIVE_PREFIX=0071
REPO_TIP=0088_user_saves          # or newer if master advanced
PENDING_COUNT=17
PENDING:
  0072_waha_intake_flag
  0073_waha_intake_model
  ...
  0088_user_saves
```

Exit code `1` means drift exists (pending migrations). Exit code `0` means parity.
Exit code `2` means misconfiguration or connection failure — **stop**.

Machine-readable JSON:

```bash
bash scripts/check_prod_drift.sh --json | tee /tmp/prod-drift-$(date -u +%Y%m%dT%H%M%SZ).json
```

**Do not proceed** if `EXTRA_REMOTE_NOT_IN_REPO` lists unexpected rows — reconcile with
`docs/production-readiness/2026-07-20/deploy-migration-truth.md` before applying.

---

## 2. Pre-deployment database backup (G7)

Take an independent logical dump **before** `supabase db push`. Supabase dashboard PITR is additive, not a substitute.

### Option A — OCI host (preferred)

SSH to the API VM and run the nightly dump script in manual mode:

```bash
ssh root@<PRODUCTION_API_SSH_HOST>
cd ~/vergeo5/infra

export ENV=production
export BACKUP_MODE=manual
export BACKUP_ENV_ID=production-pre-0072-0088
# SUPABASE_DB_URL, OCI_NAMESPACE, OCI_BUCKET_NAME already in infra/.env

bash scripts/db-dump.sh | tee /tmp/pre-rollout-backup.log
```

Record from stdout:

- `dump_name` (e.g. `vergeo5-20260805T140000Z.sql.gz`)
- `migration_tip` (should read `0071` or the `0071_*` name)
- `sha256`

### Option B — Supabase Dashboard

Project → **Database** → **Backups** → confirm a recent snapshot or trigger backup.
Record backup id + timestamp.

### Option C — Local pg_dump (founder laptop)

```bash
export SUPABASE_DB_URL='...'   # same pooler URL as §1
pg_dump --no-owner --no-privileges --format=plain "$SUPABASE_DB_URL" \
  | gzip -c > "vergeo5-pre-0072-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
gzip -t "vergeo5-pre-0072-"*.sql.gz
```

**Gate:** do not continue until you have a restorable artifact name + timestamp written down.

---

## 3. Apply migrations 0072→0088

### 3.1 Link Supabase CLI (once per machine)

```bash
cd ~/vergeo5
export SUPABASE_ACCESS_TOKEN='...'    # personal access token
export SUPABASE_DB_PASSWORD='...'     # database password

supabase link --project-ref dpadrlxukcjbewpqympu
```

### 3.2 Optional — local replay sanity (no prod touch)

```bash
supabase db reset --no-seed
bash scripts/ci/migration-replay.sh
```

### 3.3 Apply to production

`supabase db push` applies **only** migrations not yet in `schema_migrations`, in numeric order.

```bash
cd ~/vergeo5
export SUPABASE_ACCESS_TOKEN='...'
export SUPABASE_DB_PASSWORD='...'

# Dry-run: shows pending SQL without applying (Supabase CLI ≥ 1.200)
supabase db push --dry-run

# Apply
supabase db push
```

### 3.4 Migration slice reference

| #    | File                      | Summary                                                 |
| ---- | ------------------------- | ------------------------------------------------------- |
| 0072 | `waha_intake_flag`        | `waha_vendor_intake` flag row (**default false**)       |
| 0073 | `waha_intake_model`       | WAHA intake tables + FORCE RLS                          |
| 0074 | `intake_media_bucket`     | `vendor-intake-media` storage policies                  |
| 0075 | `intake_handoff`          | Vendor handoff columns + `intake_deep_links`            |
| 0076 | `video_clips`             | Clips schema                                            |
| 0077 | `clip_feature_flags`      | `clips` / `clips_comments` flags (**default false**)    |
| 0078 | `clip_weekly_caps`        | Weekly cap config                                       |
| 0079 | `clip_cost_guard`         | `clip_spend_monthly` + cost guard RPCs                  |
| 0080 | `vendor_location_details` | Branch label/address/phone/status on `vendor_locations` |
| 0081 | `listing_location_stock`  | Per-branch stock on listings                            |
| 0082 | `enquiry_threads`         | Social-commerce enquiry threads                         |
| 0083 | `vendor_follows`          | Vendor follow graph                                     |
| 0084 | `vendor_licences`         | Licence evidence metadata                               |
| 0085 | `product_classes`         | Per-measure / made-to-order / condition columns         |
| 0086 | `cart_line_price_guard`   | Cart line price integrity trigger                       |
| 0087 | `product_class_enum`      | Product class enum hardening                            |
| 0088 | `user_saves`              | User saves / bookmarks                                  |

All feature flags introduced in this slice ship **disabled** (`false`). Old API binaries remain safe until redeployed.

### 3.5 Post-apply verification (read-only)

```bash
# Drift checker must exit 0
bash scripts/check_prod_drift.sh

# Ledger tip by name (not max(version) — avoids timestamp-key skew)
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT name FROM supabase_migrations.schema_migrations
   WHERE name ~ '^[0-9]+_' ORDER BY substring(name from '^[0-9]+')::int DESC LIMIT 5;"

# Dark-ship flags exist and are false
psql "$SUPABASE_DB_URL" -c \
  "SELECT key, value FROM public.feature_flags
   WHERE key IN ('clips','clips_comments','waha_vendor_intake');"

# Social-commerce / branch-stock objects exist
psql "$SUPABASE_DB_URL" -tA -c \
  "SELECT to_regclass('public.enquiry_threads'),
          to_regclass('public.vendor_follows'),
          to_regclass('public.user_saves');"
```

Run Supabase **Database → Advisors** (security + performance). Resolve any new ERROR-level findings before app deploy.

---

## 4. Deploy FastAPI backend (OCI / Hetzner)

Deploy **after** migrations succeed. Pin an immutable GHCR tag = `RELEASE_SHA`.

```bash
ssh root@<PRODUCTION_API_SSH_HOST>

# Record rollback target
docker inspect vergeo5-api --format '{{.Config.Image}}' | tee /tmp/pre-rollout-api-image.txt

# Deploy (script pulls first, recreates container, waits for /healthz)
bash /root/redeploy-api.sh "${RELEASE_SHA}"
# or from repo:
# cd ~/vergeo5/infra && bash redeploy-api.sh "${RELEASE_SHA}"
```

Verify:

```bash
curl -fsS https://api.vergeo5.com/healthz
curl -fsS https://api.vergeo5.com/readyz
curl -fsS https://api.vergeo5.com/fingerprint
# fingerprint.git_sha should match RELEASE_SHA (not "unknown")
```

**GitHub Actions alternative** (requires `production` environment secrets):

```text
Actions → Deploy production → Run workflow
  api_image_tag: <RELEASE_SHA>
  skip_vercel: true          # frontends in §5
  verify_live: false          # run manually after §5
```

---

## 5. Deploy Next.js frontends (Vercel CLI)

Three apps: **customer**, **vendor**, **admin**. Customer usually auto-deploys from `master` git integration; vendor/admin may need promote.

### 5.1 Confirm builds exist for RELEASE_SHA

```bash
export VERCEL_TOKEN='...'
export RELEASE_SHA='...'

vercel ls vergeo5-customer --prod
vercel ls convergeo-vendor --prod
vercel ls convergeo-admin --prod
```

### 5.2 Promote (if production is not already on RELEASE_SHA)

**REST helper (no Vercel CLI auth quirks):**

```bash
export VERCEL_TOKEN='...'
export MASTER_GIT_SHA="${RELEASE_SHA}"
bash scripts/ops/vercel_promote.sh
```

**Or Vercel CLI per project:**

```bash
# Customer — git-connected; trigger or promote latest master deployment
vercel deploy --prod --cwd apps/customer

# Vendor
vercel deploy --prod --cwd apps/vendor

# Admin
vercel deploy --prod --cwd apps/admin
```

Rollback to a prior deployment without redeploying:

```bash
vercel ls vergeo5-customer --prod
vercel rollback <deployment-url> --yes
```

### 5.3 Frontend smoke probes

```bash
bash scripts/ops/probe-frontends.sh
curl -fsS https://www.vergeo5.com/en/health
curl -fsS https://vendor.vergeo5.com/en/health
curl -fsS https://admin.vergeo5.com/en/health
```

---

## 6. Post-deploy verification

```bash
cd ~/vergeo5
export MASTER_GIT_SHA="${RELEASE_SHA}"
export SUPABASE_DB_URL='...'
export EXPECTED_ENV=production

bash scripts/ops/verify_live.sh
```

Record evidence under `docs/production-readiness/<date>/rollout-evidence.md`:

- `RELEASE_SHA`
- Pre-backup object name + `migration_tip`
- `check_prod_drift.sh` output (exit 0)
- API `/fingerprint` JSON
- `vercel_promote.sh` report path
- `verify_live.sh` gate matrix

---

## 7. Rollback — backend fails to boot

Use this path when the **API container does not pass `/healthz`** after §4. Database migrations from §3 are already applied — do **not** restore the DB unless schema apply itself was wrong.

### 7.1 Immediate — roll back API image only

On the API host:

```bash
# Read the image recorded in §4
PREV_IMAGE="$(cat /tmp/pre-rollout-api-image.txt)"
echo "Rolling back to ${PREV_IMAGE}"

docker rm -f vergeo5-api
docker run -d --name vergeo5-api \
  --env-file "$HOME/vergeo5-api.env" \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  "${PREV_IMAGE}"

# Or use redeploy-api.sh with the previous SHA:
# bash /root/redeploy-api.sh <KNOWN_GOOD_SHA>
```

Wait and verify:

```bash
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/healthz && break
  sleep 1
done
curl -fsS https://api.vergeo5.com/healthz
curl -fsS https://api.vergeo5.com/fingerprint
```

`redeploy-api.sh` prints a one-line rollback command automatically if the new container fails its health wait.

### 7.2 If frontends were promoted — roll back Vercel

```bash
vercel ls vergeo5-customer --prod
vercel rollback <last-known-good-deployment-url> --yes
# repeat for vendor + admin
```

### 7.3 When to restore the database

Restore **only if**:

- `supabase db push` failed mid-apply and the ledger is inconsistent, or
- A migration caused data corruption.

```bash
ssh root@<PRODUCTION_API_SSH_HOST>
cd ~/vergeo5/infra
export ENV=production
# Stop API traffic first (stop vergeo5-api or return 503 from Caddy)
bash scripts/db-restore.sh --file /var/backups/vergeo5/<pre-rollout-dump>.sql.gz --force
```

Then roll back API + Vercel to the pre-rollout SHA. Full playbook: `infra/ROLLBACK.md` Path B.

### 7.4 Resume forward

After fixing the defect on `master`:

1. Re-run §1 drift check (ledger should still be at `0088` if only API rolled back).
2. Redeploy API §4 with the fixed `RELEASE_SHA`.
3. Re-promote frontends §5.
4. Re-run §6.

---

## 8. Quick command checklist (copy block)

```bash
# --- vars ---
export RELEASE_SHA="$(git rev-parse HEAD)"
export SUPABASE_DB_URL='...'
export SUPABASE_ACCESS_TOKEN='...'
export SUPABASE_DB_PASSWORD='...'
export VERCEL_TOKEN='...'

# 1 drift
bash scripts/check_prod_drift.sh

# 2 backup (on OCI host)
ssh root@<host> 'cd ~/vergeo5/infra && ENV=production BACKUP_MODE=manual bash scripts/db-dump.sh'

# 3 migrate
supabase link --project-ref dpadrlxukcjbewpqympu
supabase db push --dry-run
supabase db push
bash scripts/check_prod_drift.sh   # expect exit 0

# 4 api
ssh root@<host> "bash /root/redeploy-api.sh ${RELEASE_SHA}"

# 5 vercel
MASTER_GIT_SHA="${RELEASE_SHA}" bash scripts/ops/vercel_promote.sh

# 6 verify
MASTER_GIT_SHA="${RELEASE_SHA}" EXPECTED_ENV=production bash scripts/ops/verify_live.sh
```

---

## 9. Rollback decision matrix

| Symptom                                     | Action                                          | DB restore? |
| ------------------------------------------- | ----------------------------------------------- | ----------- |
| API `/healthz` fails after redeploy         | §7.1 pin previous image                         | No          |
| Frontends broken, API healthy               | §7.2 Vercel rollback                            | No          |
| `db push` failed / partial apply            | Stop; inspect `schema_migrations`; restore §7.3 | **Yes**     |
| Migration applied but wrong data            | §7.3 restore pre-apply dump                     | **Yes**     |
| New schema + old API (intentional rollback) | §7.1 only — additive columns safe               | No          |

**RTO target:** ≤ 30 minutes for application rollback (`infra/ROLLBACK.md`).

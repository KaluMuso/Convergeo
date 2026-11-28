#!/usr/bin/env bash
# Weekly automatic restore drill for the R2 backups. NOT yet run anywhere: first run is a manual,
# supervised run (see docs/ops/backup-runbook-r2.md). Touches no production or staging database.
#
# Downloads the newest db/daily/ backup, verifies its checksum, decrypts it with the on-host DRILL
# key, restores it into a throwaway Postgres container, runs scripts/ops/restore-smoke.sql, writes a
# result marker to R2 (db/drill/), and removes every temporary file and container.
#
# Inputs: BACKUP_ENV_FILE (R2 access, same file as the backup), DRILL_GNUPGHOME (keyring holding the
# drill private key), REPO_DIR (checkout containing scripts/ops/restore-smoke.sql).
set -euo pipefail
umask 077

BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-/root/vergeo5-backup.env}"
DRILL_GNUPGHOME="${DRILL_GNUPGHOME:-/root/.gnupg-vergeo5-drill}"
REPO_DIR="${REPO_DIR:-/root/vergeo5}"
PG_IMAGE="${DRILL_PG_IMAGE:-pgvector/pgvector:pg17}"
KIND="${DRILL_KIND:-daily}"

envget() { grep -m1 -E "^$2=" "$1" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"; }
for v in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT R2_BUCKET; do
  val="$(envget "$BACKUP_ENV_FILE" "$v")"
  [ -n "$val" ] || { echo "$v is missing in $BACKUP_ENV_FILE" >&2; exit 2; }
  printf -v "$v" '%s' "$val"
done
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" AWS_DEFAULT_REGION=auto
SMOKE="$REPO_DIR/scripts/ops/restore-smoke.sql"
[ -f "$SMOKE" ] || { echo "smoke file not found: $SMOKE" >&2; exit 2; }

WORK="$(mktemp -d /var/tmp/vergeo5-drill.XXXXXX)"
CNAME="vergeo5-restore-drill-$$"
STATUS="fail"; DETAIL="unknown"
START="$(date -u +%s)"
cleanup() {
  docker rm -f "$CNAME" > /dev/null 2>&1 || true
  rm -rf "$WORK"
  local secs=$(( $(date -u +%s) - START ))
  printf '{"status":"%s","detail":"%s","seconds":%s,"finished_utc":"%s"}\n' \
    "$STATUS" "$DETAIL" "$secs" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "/var/tmp/vergeo5-drill-result.json"
  aws --endpoint-url "$R2_ENDPOINT" s3 cp /var/tmp/vergeo5-drill-result.json \
    "s3://$R2_BUCKET/db/drill/result-$(date -u +%Y%m%d-%H%M%SZ)-$STATUS.json" --only-show-errors || true
  echo "DRILL $STATUS ($DETAIL) in ${secs}s"
}
trap cleanup EXIT

KEY="$(aws --endpoint-url "$R2_ENDPOINT" s3api list-objects-v2 --bucket "$R2_BUCKET" --prefix "db/$KIND/" \
  --query 'sort_by(Contents[?ends_with(Key, `.dump.gpg`)], &LastModified)[-1].Key' --output text)"
[ -n "$KEY" ] && [ "$KEY" != "None" ] || { DETAIL="no backup found"; exit 1; }
aws --endpoint-url "$R2_ENDPOINT" s3 cp "s3://$R2_BUCKET/$KEY" "$WORK/in.gpg" --only-show-errors
aws --endpoint-url "$R2_ENDPOINT" s3 cp "s3://$R2_BUCKET/$KEY.sha256" "$WORK/in.sha256" --only-show-errors
EXPECT="$(cut -d' ' -f1 "$WORK/in.sha256")"
[ "$(sha256sum "$WORK/in.gpg" | cut -d' ' -f1)" = "$EXPECT" ] || { DETAIL="checksum mismatch"; exit 1; }

GNUPGHOME="$DRILL_GNUPGHOME" gpg --batch --quiet --decrypt -o "$WORK/in.dump" "$WORK/in.gpg" || { DETAIL="decrypt failed"; exit 1; }

docker run -d --name "$CNAME" -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=drill "$PG_IMAGE" > /dev/null
for _ in $(seq 1 60); do docker exec "$CNAME" pg_isready -U postgres -d drill > /dev/null 2>&1 && break; sleep 1; done
docker exec "$CNAME" pg_isready -U postgres -d drill > /dev/null || { DETAIL="throwaway postgres did not start"; exit 1; }
docker cp "$WORK/in.dump" "$CNAME:/tmp/in.dump"
# Errors for Supabase-only extensions/roles are expected; the smoke file decides pass or fail.
docker exec "$CNAME" pg_restore -U postgres -d drill --no-owner --no-privileges /tmp/in.dump > "$WORK/restore.log" 2>&1 || true
ERRS="$(grep -c 'error:' "$WORK/restore.log" || true)"
docker exec -i "$CNAME" psql -U postgres -d drill -v ON_ERROR_STOP=1 < "$SMOKE" > "$WORK/smoke.log" 2>&1 \
  || { DETAIL="smoke failed after $ERRS restore errors"; exit 1; }
STATUS="pass"; DETAIL="smoke ok; restore errors tolerated: $ERRS"

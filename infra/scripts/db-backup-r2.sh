#!/usr/bin/env bash
# Vergeo5 encrypted production database backup -> Cloudflare R2.
#
# Streams pg_dump (custom format) straight into gpg, so no plaintext dump ever touches disk,
# then uploads the encrypted file plus a sha256 file to R2 and checks the uploaded size.
# This is the LIVE backup path (cron: infra/cron/vergeo5-backup.cron). The older OCI script
# infra/scripts/db-dump.sh is kept only because the nightly CI restore drill still uses it.
#
# Usage: db-backup-r2.sh manual|daily|weekly
#
# Inputs (names only, values live on the host, never in the repo):
#   API_ENV_FILE          env file holding the production DB URL (default /root/vergeo5-api.env)
#   DB_URL_VAR            variable name inside that file (default SUPABASE_DB_URL)
#   BACKUP_ENV_FILE       R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET
#                         (default /root/vergeo5-backup.env)
#   BACKUP_PUBLIC_KEY     public GPG key file (default /root/vergeo5-backup-public.asc)
#   BACKUP_GPG_FPR        full fingerprint of the recipient key (public information)
#   BACKUP_EXTRA_FPR      optional second recipient, e.g. the on-host drill key (see runbook)
#
# Exit codes: 0 ok, 1 failure, 2 usage / configuration error.
set -euo pipefail
umask 077

KIND="${1:-daily}"
case "$KIND" in manual | daily | weekly) ;; *) echo "usage: $0 manual|daily|weekly" >&2; exit 2 ;; esac

API_ENV_FILE="${API_ENV_FILE:-/root/vergeo5-api.env}"
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-/root/vergeo5-backup.env}"
BACKUP_PUBLIC_KEY="${BACKUP_PUBLIC_KEY:-/root/vergeo5-backup-public.asc}"
DB_URL_VAR="${DB_URL_VAR:-SUPABASE_DB_URL}"
FPR="${BACKUP_GPG_FPR:?BACKUP_GPG_FPR must be set (public key fingerprint)}"
LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/vergeo5}"
KEEP_LOCAL_DAYS="${KEEP_LOCAL_DAYS:-7}"
MIN_BYTES="${BACKUP_MIN_BYTES:-51200}"
GNUPGHOME="${BACKUP_GNUPGHOME:-/root/.gnupg-vergeo5-backup}"
export GNUPGHOME

envget() { grep -m1 -E "^$2=" "$1" | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"; }

PGURL="$(envget "$API_ENV_FILE" "$DB_URL_VAR")"
[ -n "$PGURL" ] || { echo "DB URL variable $DB_URL_VAR is not set in $API_ENV_FILE" >&2; exit 2; }
for v in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT R2_BUCKET; do
  val="$(envget "$BACKUP_ENV_FILE" "$v")"
  [ -n "$val" ] || { echo "$v is missing in $BACKUP_ENV_FILE" >&2; exit 2; }
  printf -v "$v" '%s' "$val"
done
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" AWS_DEFAULT_REGION=auto

mkdir -p "$LOCAL_DIR" "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
gpg --batch --quiet --import "$BACKUP_PUBLIC_KEY"
gpg --batch --list-keys "$FPR" > /dev/null

RECIPIENTS=(-r "$FPR")
if [ -n "${BACKUP_EXTRA_FPR:-}" ]; then
  gpg --batch --list-keys "$BACKUP_EXTRA_FPR" > /dev/null
  RECIPIENTS+=(-r "$BACKUP_EXTRA_FPR")
fi

STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
NAME="vergeo5-prod-$STAMP.dump"
OUT="$LOCAL_DIR/$NAME.gpg"
trap 'rm -f "$OUT.part"' EXIT

# pipefail makes a failed pg_dump fail the whole job (no half-written file is promoted).
pg_dump "$PGURL" -Fc --no-owner --no-privileges |
  gpg --batch --yes --trust-model always "${RECIPIENTS[@]}" -o "$OUT.part" --encrypt
mv "$OUT.part" "$OUT"

SIZE="$(stat -c %s "$OUT")"
if [ "$SIZE" -lt "$MIN_BYTES" ]; then
  echo "encrypted dump too small ($SIZE bytes < $MIN_BYTES)" >&2
  rm -f "$OUT"
  exit 1
fi
(cd "$LOCAL_DIR" && sha256sum "$NAME.gpg" > "$NAME.gpg.sha256")

for f in "$NAME.gpg" "$NAME.gpg.sha256"; do
  aws --endpoint-url "$R2_ENDPOINT" s3 cp "$LOCAL_DIR/$f" "s3://$R2_BUCKET/db/$KIND/$f" --only-show-errors
done
REMOTE="$(aws --endpoint-url "$R2_ENDPOINT" s3api head-object --bucket "$R2_BUCKET" --key "db/$KIND/$NAME.gpg" --query ContentLength --output text)"
[ "$REMOTE" = "$SIZE" ] || { echo "upload size mismatch local=$SIZE remote=$REMOTE" >&2; exit 1; }

find "$LOCAL_DIR" -name 'vergeo5-prod-*' -mtime +"$KEEP_LOCAL_DAYS" -delete
echo "OK $KIND s3://$R2_BUCKET/db/$KIND/$NAME.gpg encrypted_size=$SIZE"

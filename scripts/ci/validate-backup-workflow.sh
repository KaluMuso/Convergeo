#!/usr/bin/env bash
# Static validation for the database backup workflow + host scripts.
# No live n8n / OCI / Postgres required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WF="${ROOT}/infra/n8n/backup.json"
DUMP="${ROOT}/infra/scripts/db-dump.sh"
WATCH="${ROOT}/infra/scripts/db-backup-watchdog.sh"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ok() { printf 'OK: %s\n' "$*"; }

[[ -f "${WF}" ]] || die "missing ${WF}"
[[ -f "${DUMP}" ]] || die "missing ${DUMP}"
[[ -f "${WATCH}" ]] || die "missing ${WATCH}"

# --- JSON parse + structural checks ---
python3 - "${WF}" <<'PY'
import json, re, sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8")
wf = json.loads(raw)

if wf.get("active") is not False:
    raise SystemExit("backup.json must ship with active: false")

settings = wf.get("settings") or {}
if settings.get("timezone") != "Africa/Lusaka":
    raise SystemExit("settings.timezone must be Africa/Lusaka")

nodes = {n["name"]: n for n in wf.get("nodes") or []}
required = [
    "Cron Nightly Dump",
    "Cron Missed-Schedule Watchdog",
    "Webhook Manual Backup",
    "SSH Nightly Dump",
    "SSH Watchdog",
    "SSH Manual Dump",
    "Build Alert Payload",
    "WhatsApp Ops Alert",
    "Error Trigger",
]
for name in required:
    if name not in nodes:
        raise SystemExit(f"missing node: {name}")

cron = nodes["Cron Nightly Dump"]["parameters"]["rule"]["interval"][0]["expression"]
if cron != "0 2 * * *":
    raise SystemExit(f"nightly cron must be '0 2 * * *', got {cron!r}")

watch = nodes["Cron Missed-Schedule Watchdog"]["parameters"]["rule"]["interval"][0]["expression"]
if watch != "0 4 * * *":
    raise SystemExit(f"watchdog cron must be '0 4 * * *', got {watch!r}")

# Credential placeholders only
for node in wf["nodes"]:
    creds = node.get("credentials") or {}
    for cred in creds.values():
        if cred.get("id") not in (None, "REPLACE_WITH_CREDENTIAL_ID"):
            raise SystemExit(
                f"node {node['name']!r} has non-placeholder credential id: {cred.get('id')!r}"
            )

# Must reference dump + watchdog scripts
blob = json.dumps(wf)
if "infra/scripts/db-dump.sh" not in blob:
    raise SystemExit("workflow must invoke infra/scripts/db-dump.sh")
if "infra/scripts/db-backup-watchdog.sh" not in blob:
    raise SystemExit("workflow must invoke infra/scripts/db-backup-watchdog.sh")
if "BACKUP_WEBHOOK_SECRET" not in blob:
    raise SystemExit("manual path must reference $env.BACKUP_WEBHOOK_SECRET")

# --- no-secrets validation (workflow JSON) ---
secret_patterns = [
    re.compile(r"(?i)postgres(?:ql)?://[^\s\"']+:[^\s\"']+@"),
    re.compile(r"(?i)(service_role|SUPABASE_SERVICE_ROLE_KEY)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
]
for pat in secret_patterns:
    m = pat.search(raw)
    if m:
        raise SystemExit(f"possible secret-shaped value in backup.json: {m.group(0)[:48]}…")

# Disallow hardcoded credential-looking assignments outside $env / placeholders
if re.search(r"sk_live_[A-Za-z0-9]+", raw):
    raise SystemExit("stripe-like secret pattern found")

print("json_structure_ok")
PY
ok "backup.json structure + no-secrets"

# --- shell syntax ---
bash -n "${DUMP}"
bash -n "${WATCH}"
ok "bash -n dump + watchdog"

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x "${DUMP}" "${WATCH}" || die "shellcheck failed"
  ok "shellcheck dump + watchdog"
else
  printf 'SKIP: shellcheck not installed\n'
fi

# Scripts must not echo raw DSN variables unredacted in obvious ways
if grep -nE 'echo .*\$\{?(SUPABASE_DB_URL|DATABASE_URL)' "${DUMP}" >/dev/null 2>&1; then
  die "db-dump.sh appears to echo DB URL directly"
fi
ok "dump script avoids raw DSN echo"

# Registry + runbook presence
grep -q 'backup\.json' "${ROOT}/docs/ops/n8n-workflows.md" \
  || die "docs/ops/n8n-workflows.md missing backup.json row"
[[ -f "${ROOT}/docs/ops/backup-runbook.md" ]] || die "missing backup-runbook.md"
[[ -f "${ROOT}/docs/ops/backup-restore-drill.md" ]] || die "missing backup-restore-drill.md"
ok "docs present"

printf '\nvalidate-backup-workflow: PASS\n'

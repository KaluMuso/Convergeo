#!/usr/bin/env bash
# Static guard: committed n8n workflow JSON must not embed plaintext ops secrets.
# Secrets belong in n8n credentials / host env ($env.*) only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
N8N_DIR="${ROOT}/infra/n8n"
FAIL=0

shopt -s nullglob
files=("${N8N_DIR}"/*.json)
if [[ "${#files[@]}" -eq 0 ]]; then
  echo "validate-n8n-no-plaintext-secrets: no workflow JSON under infra/n8n" >&2
  exit 1
fi

# Reject literal secret assignments / high-entropy tokens committed into workflow JSON.
# Allow $env.* and REPLACE_WITH_* credential placeholders.
pattern='(UPTIME_WEBHOOK_SECRET[[:space:]]*[:=][[:space:]]*["'"'"'][^$]|WHATSAPP_CLOUD_API_TOKEN[[:space:]]*[:=][[:space:]]*["'"'"'][^$]|Bearer[[:space:]]+[A-Za-z0-9_-]{20,}|sk_live_[A-Za-z0-9]+|whsec_[A-Za-z0-9+/=]{16,})'

for f in "${files[@]}"; do
  if grep -nE "${pattern}" "${f}"; then
    echo "FAIL: possible plaintext secret in ${f}" >&2
    FAIL=1
  fi
done

# Uptime workflow must reference env secret, never a literal header value.
UPTIME="${N8N_DIR}/uptime-alert.json"
if [[ -f "${UPTIME}" ]]; then
  if ! grep -q 'UPTIME_WEBHOOK_SECRET' "${UPTIME}"; then
    echo "FAIL: ${UPTIME} must reference \$env.UPTIME_WEBHOOK_SECRET" >&2
    FAIL=1
  fi
  if grep -qE 'X-Uptime-Secret[[:space:]]*[:=][[:space:]]*["'"'"'][^$"'"'"']{8,}' "${UPTIME}"; then
    echo "FAIL: ${UPTIME} appears to hardcode X-Uptime-Secret" >&2
    FAIL=1
  fi
fi

if [[ "${FAIL}" -ne 0 ]]; then
  exit 1
fi

echo "validate-n8n-no-plaintext-secrets OK (${#files[@]} workflows)"

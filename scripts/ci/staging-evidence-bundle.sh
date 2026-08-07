#!/usr/bin/env bash
# Merge per-portal Preview evidence + API fingerprint into one staging proof artifact.
#
# Usage:
#   bash scripts/ci/staging-evidence-bundle.sh \
#     --candidate-sha "$GITHUB_SHA" \
#     --preview-dir /tmp/preview-evidence \
#     --fingerprint /tmp/fingerprint.json \
#     --migrate-result success \
#     --output /tmp/staging-sha-proof.json
#
set -euo pipefail

CANDIDATE_SHA=""
PREVIEW_DIR=""
FINGERPRINT_FILE=""
MIGRATE_RESULT="skipped"
API_DEPLOY_FILE=""
OUTPUT="/tmp/staging-sha-proof.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate-sha) CANDIDATE_SHA="${2:-}"; shift 2 ;;
    --preview-dir) PREVIEW_DIR="${2:-}"; shift 2 ;;
    --fingerprint) FINGERPRINT_FILE="${2:-}"; shift 2 ;;
    --migrate-result) MIGRATE_RESULT="${2:-}"; shift 2 ;;
    --api-deploy) API_DEPLOY_FILE="${2:-}"; shift 2 ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "::error::unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [ -z "${CANDIDATE_SHA}" ] || [ -z "${PREVIEW_DIR}" ]; then
  echo "::error::--candidate-sha and --preview-dir are required" >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT}")"

CANDIDATE_SHA="${CANDIDATE_SHA}" \
PREVIEW_DIR="${PREVIEW_DIR}" \
FINGERPRINT_FILE="${FINGERPRINT_FILE}" \
MIGRATE_RESULT="${MIGRATE_RESULT}" \
API_DEPLOY_FILE="${API_DEPLOY_FILE}" \
OUTPUT="${OUTPUT}" \
python3 - <<'PY'
import json
import os
from datetime import UTC, datetime
from pathlib import Path

candidate_sha = os.environ["CANDIDATE_SHA"]
preview_dir = Path(os.environ["PREVIEW_DIR"])
fingerprint_file = os.environ.get("FINGERPRINT_FILE", "")
migrate_result = os.environ.get("MIGRATE_RESULT", "skipped")
api_deploy_file = os.environ.get("API_DEPLOY_FILE", "")
output = os.environ["OUTPUT"]

portals = {}
missing = []
for portal in ("customer", "vendor", "admin"):
    path = preview_dir / portal / "evidence.json"
    if not path.is_file():
        missing.append(portal)
        continue
    with path.open(encoding="utf-8") as fh:
        portals[portal] = json.load(fh)

if missing:
    raise SystemExit(f"::error::missing preview evidence for: {', '.join(missing)}")

fingerprint = None
if fingerprint_file and Path(fingerprint_file).is_file():
    with open(fingerprint_file, encoding="utf-8") as fh:
        fingerprint = json.load(fh)

api_deploy = None
if api_deploy_file and Path(api_deploy_file).is_file():
    api_deploy = Path(api_deploy_file).read_text(encoding="utf-8").strip()

bundle = {
    "candidate_sha": candidate_sha,
    "proved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "previews": portals,
    "api_fingerprint": fingerprint,
    "api_deploy_record": api_deploy,
    "migrate_supabase_result": migrate_result,
}

with open(output, "w", encoding="utf-8") as fh:
    json.dump(bundle, fh, indent=2)
    fh.write("\n")

# Human-readable summary (no secrets).
print(f"candidate_sha={candidate_sha}")
for portal, row in portals.items():
    print(
        f"{portal}: url={row.get('deployment_url')} "
        f"dpl={row.get('deployment_id')} "
        f"sha={row.get('github_commit_sha')} "
        f"api_env={row.get('api_env_verdict')} "
        f"health={row.get('health_verdict')}"
    )
if fingerprint:
    print(
        "api_fingerprint:",
        {k: fingerprint.get(k) for k in ("env", "git_sha", "image_tag", "supabase_project_ref")},
    )
print(f"migrate_supabase={migrate_result}")
PY

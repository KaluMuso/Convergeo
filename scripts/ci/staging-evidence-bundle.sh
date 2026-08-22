#!/usr/bin/env bash
# Merge per-portal Preview evidence + API fingerprint into one staging proof artifact.
# Fails before writing the artifact when identity proofs are inconsistent.
#
# Usage:
#   bash scripts/ci/staging-evidence-bundle.sh \
#     --candidate-sha "$GITHUB_SHA" \
#     --preview-dir /tmp/preview-evidence \
#     --fingerprint /tmp/fingerprint.json \
#     --staging-supabase-project-id "$STAGING_SUPABASE_PROJECT_ID" \
#     --migrate-result success \
#     --output /tmp/staging-sha-proof.json
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

CANDIDATE_SHA=""
PREVIEW_DIR=""
FINGERPRINT_FILE=""
STAGING_SUPABASE_PROJECT_ID=""
MIGRATE_RESULT="skipped"
API_DEPLOY_FILE=""
EXPECTED_IMAGE_TAG=""
ALLOW_MIGRATE_SKIPPED=0
OUTPUT="/tmp/staging-sha-proof.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate-sha) CANDIDATE_SHA="${2:-}"; shift 2 ;;
    --preview-dir) PREVIEW_DIR="${2:-}"; shift 2 ;;
    --fingerprint) FINGERPRINT_FILE="${2:-}"; shift 2 ;;
    --staging-supabase-project-id) STAGING_SUPABASE_PROJECT_ID="${2:-}"; shift 2 ;;
    --migrate-result) MIGRATE_RESULT="${2:-}"; shift 2 ;;
    --api-deploy) API_DEPLOY_FILE="${2:-}"; shift 2 ;;
    --expected-image-tag) EXPECTED_IMAGE_TAG="${2:-}"; shift 2 ;;
    --allow-migrate-skipped) ALLOW_MIGRATE_SKIPPED=1; shift ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "::error::unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [ -z "${CANDIDATE_SHA}" ] || [ -z "${PREVIEW_DIR}" ]; then
  echo "::error::--candidate-sha and --preview-dir are required" >&2
  exit 1
fi
if [ -z "${STAGING_SUPABASE_PROJECT_ID}" ]; then
  echo "::error::--staging-supabase-project-id is required" >&2
  exit 1
fi

VALIDATE_ARGS=(
  --candidate-sha "${CANDIDATE_SHA}"
  --staging-supabase-project-id "${STAGING_SUPABASE_PROJECT_ID}"
  --preview-dir "${PREVIEW_DIR}"
  --migrate-result "${MIGRATE_RESULT}"
)
if [ -n "${FINGERPRINT_FILE}" ]; then
  VALIDATE_ARGS+=(--fingerprint "${FINGERPRINT_FILE}")
fi
if [ -n "${EXPECTED_IMAGE_TAG}" ]; then
  VALIDATE_ARGS+=(--expected-image-tag "${EXPECTED_IMAGE_TAG}")
fi
if [ "${ALLOW_MIGRATE_SKIPPED}" -eq 1 ]; then
  VALIDATE_ARGS+=(--allow-migrate-skipped)
fi

python3 "${REPO_ROOT}/scripts/ci/validate_staging_proof.py" "${VALIDATE_ARGS[@]}"

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
for portal in ("customer", "vendor", "admin"):
    path = preview_dir / portal / "evidence.json"
    with path.open(encoding="utf-8") as fh:
        portals[portal] = json.load(fh)

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
        f"{portal}: url={row.get('preview_url')} "
        f"dpl={row.get('deployment_id')} "
        f"sha={row.get('deployment_sha')} "
        f"health={row.get('health_status')} "
        f"api_host={row.get('health_api_host')} "
        f"env_metadata={row.get('env_metadata_status')} (informational)"
    )
if fingerprint:
    print(
        "api_fingerprint:",
        {k: fingerprint.get(k) for k in ("env", "git_sha", "image_tag", "supabase_project_ref")},
    )
print(f"migrate_supabase={migrate_result}")
PY

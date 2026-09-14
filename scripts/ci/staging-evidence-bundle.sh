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
# Add --release-envelope plus the source/configuration arguments below only
# for the stronger v2 manifest-to-E2E handoff. Legacy diagnostic callers keep
# schema_version=1 and cannot be consumed as release inputs.
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
RELEASE_ENVELOPE=0
SOURCE_REPOSITORY=""
SOURCE_REPOSITORY_ID=""
SOURCE_WORKFLOW=""
SOURCE_REF=""
SOURCE_RUN_ID=""
SOURCE_RUN_ATTEMPT=""
CONFIGURATION_REVISION=""

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
    --release-envelope) RELEASE_ENVELOPE=1; shift ;;
    --source-repository) SOURCE_REPOSITORY="${2:-}"; shift 2 ;;
    --source-repository-id) SOURCE_REPOSITORY_ID="${2:-}"; shift 2 ;;
    --source-workflow) SOURCE_WORKFLOW="${2:-}"; shift 2 ;;
    --source-ref) SOURCE_REF="${2:-}"; shift 2 ;;
    --source-run-id) SOURCE_RUN_ID="${2:-}"; shift 2 ;;
    --source-run-attempt) SOURCE_RUN_ATTEMPT="${2:-}"; shift 2 ;;
    --configuration-revision) CONFIGURATION_REVISION="${2:-}"; shift 2 ;;
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
if [ "${RELEASE_ENVELOPE}" -eq 1 ]; then
  for value in \
    "${SOURCE_REPOSITORY}" \
    "${SOURCE_REPOSITORY_ID}" \
    "${SOURCE_WORKFLOW}" \
    "${SOURCE_REF}" \
    "${SOURCE_RUN_ID}" \
    "${SOURCE_RUN_ATTEMPT}" \
    "${CONFIGURATION_REVISION}"; do
    if [ -z "${value}" ]; then
      echo "::error::release envelope source/configuration arguments are required" >&2
      exit 1
    fi
  done
  if [ "${MIGRATE_RESULT}" != "success" ] || [ "${ALLOW_MIGRATE_SKIPPED}" -eq 1 ]; then
    echo "::error::release envelope requires executed successful migrations" >&2
    exit 1
  fi
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
RELEASE_ENVELOPE="${RELEASE_ENVELOPE}" \
SOURCE_REPOSITORY="${SOURCE_REPOSITORY}" \
SOURCE_REPOSITORY_ID="${SOURCE_REPOSITORY_ID}" \
SOURCE_WORKFLOW="${SOURCE_WORKFLOW}" \
SOURCE_REF="${SOURCE_REF}" \
SOURCE_RUN_ID="${SOURCE_RUN_ID}" \
SOURCE_RUN_ATTEMPT="${SOURCE_RUN_ATTEMPT}" \
CONFIGURATION_REVISION="${CONFIGURATION_REVISION}" \
python3 - <<'PY'
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

candidate_sha = os.environ["CANDIDATE_SHA"]
preview_dir = Path(os.environ["PREVIEW_DIR"])
fingerprint_file = os.environ.get("FINGERPRINT_FILE", "")
migrate_result = os.environ.get("MIGRATE_RESULT", "skipped")
api_deploy_file = os.environ.get("API_DEPLOY_FILE", "")
output = os.environ["OUTPUT"]
release_envelope = os.environ.get("RELEASE_ENVELOPE") == "1"

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
    "schema_version": 2 if release_envelope else 1,
    "candidate_sha": candidate_sha,
    "proved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "previews": portals,
    "api_fingerprint": fingerprint,
    "api_deploy_record": api_deploy,
    "migrate_supabase_result": migrate_result,
}

if release_envelope:
    bundle["source"] = {
        "repository": os.environ["SOURCE_REPOSITORY"],
        "repository_id": int(os.environ["SOURCE_REPOSITORY_ID"]),
        "workflow": os.environ["SOURCE_WORKFLOW"],
        "ref": os.environ["SOURCE_REF"],
        "candidate_sha": candidate_sha,
        "run_id": int(os.environ["SOURCE_RUN_ID"]),
        "run_attempt": int(os.environ["SOURCE_RUN_ATTEMPT"]),
    }
    bundle["configuration"] = {
        "identity_scheme": "operator-managed-non-secret-v1",
        "revision": os.environ["CONFIGURATION_REVISION"],
    }
    bundle["deployment_efficiency"] = {
        "create_calls": sum(row["deployment_create_calls"] for row in portals.values()),
        "reused_deployments": sum(row["reused_deployments"] for row in portals.values()),
        "portals": {
            portal: {
                "action": row["deployment_action"],
                "origin_attempt": row["deployment_origin_attempt"],
            }
            for portal, row in portals.items()
        },
    }
    bundle["proof_outcomes"] = {
        "deployment_checkpoint_reprobe": "PASS",
        "portal_identity_customer": "PASS",
        "portal_identity_vendor": "PASS",
        "portal_identity_admin": "PASS",
        "cors": "PASS",
        "database_service_role": "PASS",
        "customer_same_site_cart": "PASS",
        "api_fingerprint": "PASS",
        "migrations": "PASS",
    }
    sys.path.insert(0, str(Path.cwd() / "scripts" / "ci"))
    from validate_staging_proof import validate_release_envelope

    validate_release_envelope(
        bundle,
        candidate_sha=candidate_sha,
        source_run_id=int(os.environ["SOURCE_RUN_ID"]),
        source_run_attempt=int(os.environ["SOURCE_RUN_ATTEMPT"]),
        source_workflow=os.environ["SOURCE_WORKFLOW"],
        configuration_revision=os.environ["CONFIGURATION_REVISION"],
    )

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

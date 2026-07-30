#!/usr/bin/env bash
# Redeploy the Vergeo5 *staging* API from a SHA-tagged GHCR image.
#
# Distinct from production infra/redeploy-api.sh:
#   - container name: vergeo5-api-staging
#   - bind:           127.0.0.1:8001:8000
#   - env file:       ~/vergeo5-api-staging.env
#   - tag:            required git SHA (never "latest")
#   - ENV:            must be staging (enforced by API startup guards)
#   - shared-host:     fixed resource limits and one worker protect production
#
# Usage:
#   ./redeploy-api-staging.sh <git-sha>
#   ./redeploy-api-staging.sh --rollback   # restore previous known-good image
#
# Overridable via env:
#   API_ENV_FILE (default: $HOME/vergeo5-api-staging.env)
#   DEPLOY_RECORD_DIR (default: $HOME/.vergeo5-staging)
set -euo pipefail

IMAGE="ghcr.io/kalumuso/convergeo-api"
NAME="vergeo5-api-staging"
ENV_FILE="${API_ENV_FILE:-$HOME/vergeo5-api-staging.env}"
BIND="127.0.0.1:8001:8000"
RECORD_DIR="${DEPLOY_RECORD_DIR:-$HOME/.vergeo5-staging}"
RECORD_FILE="${RECORD_DIR}/api-deploy-record"
PREV_FILE="${RECORD_DIR}/api-previous-image"

# This deployment runs on the same host as production. These are deliberately
# constants rather than operator-overridable environment variables: a staging
# deploy must not be able to claim the host's remaining capacity by accident.
STAGING_MEMORY_LIMIT="768m"
STAGING_MEMORY_RESERVATION="384m"
STAGING_CPU_LIMIT="0.75"
STAGING_PIDS_LIMIT="256"
STAGING_WORKERS="1"
MIN_AVAILABLE_MEMORY_KIB=$((1536 * 1024))
MIN_AVAILABLE_DISK_KIB=$((5 * 1024 * 1024))

die() { printf '✗ %s\n' "$*" >&2; exit 1; }

mkdir -p "$RECORD_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  die "env file not found: $ENV_FILE (set API_ENV_FILE to override)"
fi

# Soft guard: refuse obvious production identifiers in the env file text
# (values are not printed).
if grep -Eq 'dpadrlxukcjbewpqympu|api\.vergeo5\.com' "$ENV_FILE"; then
  die "staging env file appears to contain production identifiers — aborting"
fi
if ! grep -Eq '^ENV=staging[[:space:]]*$' "$ENV_FILE"; then
  die "staging env file must contain ENV=staging"
fi

available_memory_kib="$(awk '/MemAvailable:/ { print $2; exit }' /proc/meminfo)"
if [[ ! "$available_memory_kib" =~ ^[0-9]+$ ]]; then
  die "could not determine host MemAvailable"
fi
if (( available_memory_kib < MIN_AVAILABLE_MEMORY_KIB )); then
  die "host has insufficient available memory for a staging deploy; need at least 1536 MiB available"
fi

available_disk_kib="$(df -Pk "$RECORD_DIR" | awk 'NR == 2 { print $4 }')"
if [[ ! "$available_disk_kib" =~ ^[0-9]+$ ]]; then
  die "could not determine available disk space"
fi
if (( available_disk_kib < MIN_AVAILABLE_DISK_KIB )); then
  die "host has insufficient free disk for a staging deploy; need at least 5 GiB free"
fi

TAG=""
ROLLBACK=0
if [[ "${1:-}" == "--rollback" ]]; then
  ROLLBACK=1
  [[ -f "$PREV_FILE" ]] || die "no previous staging image recorded at ${PREV_FILE}"
  PREV_IMAGE="$(cat "$PREV_FILE")"
  [[ "$PREV_IMAGE" != "none" && -n "$PREV_IMAGE" ]] || die "previous image record is empty"
  TAG="${PREV_IMAGE##*:}"
  echo "→ Rollback to previous known-good: ${PREV_IMAGE}"
elif [[ -n "${1:-}" ]]; then
  TAG="$1"
else
  die "usage: $0 <git-sha> | $0 --rollback"
fi

if [[ "$TAG" == "latest" ]]; then
  die "refusing tag 'latest' — staging requires an immutable git SHA tag"
fi
if [[ ! "$TAG" =~ ^[0-9a-f]{7,40}$ ]]; then
  die "tag must look like a git SHA (got: ${TAG})"
fi

echo "→ Pulling ${IMAGE}:${TAG} ..."
docker pull "${IMAGE}:${TAG}"

PREV_IMAGE="$(docker inspect --format '{{.Config.Image}}' "${NAME}" 2>/dev/null || echo none)"
echo "→ Current staging image: ${PREV_IMAGE}"
printf '%s\n' "$PREV_IMAGE" >"$PREV_FILE"

echo "→ Recreating ${NAME} (bind ${BIND}) ..."
docker rm -f "${NAME}" >/dev/null 2>&1 || true
docker run -d --name "${NAME}" \
  --init \
  --env-file "${ENV_FILE}" \
  -e "ENV=staging" \
  -e "GIT_SHA=${TAG}" \
  -e "API_IMAGE_TAG=${TAG}" \
  -e "SENTRY_RELEASE=${TAG}" \
  --memory "${STAGING_MEMORY_LIMIT}" \
  --memory-reservation "${STAGING_MEMORY_RESERVATION}" \
  --cpus "${STAGING_CPU_LIMIT}" \
  --pids-limit "${STAGING_PIDS_LIMIT}" \
  --security-opt no-new-privileges:true \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  --stop-timeout 20 \
  --restart unless-stopped \
  -p "${BIND}" \
  "${IMAGE}:${TAG}" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${STAGING_WORKERS}" >/dev/null

HEALTH_URL="http://127.0.0.1:8001/healthz"
FINGERPRINT_URL="http://127.0.0.1:8001/fingerprint"

echo "→ Waiting for /healthz ..."
for _ in $(seq 1 40); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "✓ Staging API healthy — ${IMAGE}:${TAG}"
    curl -fsS "$FINGERPRINT_URL" || true
    echo
    {
      echo "image=${IMAGE}:${TAG}"
      echo "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "rollback=${ROLLBACK}"
      echo "previous=${PREV_IMAGE}"
    } >"$RECORD_FILE"
    docker ps --filter "name=${NAME}" --format '  {{.Names}} {{.Status}} {{.Ports}}'
    exit 0
  fi
  sleep 1
done

echo "✗ ${NAME} did not become healthy within 40s." >&2
echo "  logs:     docker logs --tail 50 ${NAME}" >&2
if [[ "${PREV_IMAGE}" != "none" ]]; then
  echo "  rollback: $0 --rollback" >&2
  echo "  or: docker rm -f ${NAME} && docker run -d --name ${NAME} --env-file ${ENV_FILE} --restart unless-stopped -p ${BIND} ${PREV_IMAGE}" >&2
fi
exit 1

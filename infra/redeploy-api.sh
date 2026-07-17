#!/usr/bin/env bash
# Redeploy the Vergeo5 API from the prebuilt GHCR image.
#
# Production runs the API as a standalone container (name: vergeo5-api) bound to
# 127.0.0.1:8000, with Caddy running on the host (systemd) reverse-proxying
# api.vergeo5.com -> 127.0.0.1:8000. The image is built + pushed by
# .github/workflows/api-image.yml on every master push touching services/api.
#
# Safe & idempotent: pulls FIRST (so a failed pull never touches the running
# container), records the current image for rollback, recreates the container,
# then waits for /healthz and prints a rollback command if it doesn't come up.
#
# Usage:
#   ./redeploy-api.sh              # deploy :latest
#   ./redeploy-api.sh <git-sha>    # pin/rollback to a specific build tag
#
# Overridable via env:
#   API_ENV_FILE (default: $HOME/vergeo5-api.env)
#   API_BIND     (default: 127.0.0.1:8000:8000)  # host-Caddy reaches localhost:8000
set -euo pipefail

IMAGE="ghcr.io/kalumuso/convergeo-api"
TAG="${1:-latest}"
NAME="vergeo5-api"
ENV_FILE="${API_ENV_FILE:-$HOME/vergeo5-api.env}"
BIND="${API_BIND:-127.0.0.1:8000:8000}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "✗ env file not found: $ENV_FILE (set API_ENV_FILE to override)" >&2
  exit 1
fi

echo "→ Pulling ${IMAGE}:${TAG} ..."
docker pull "${IMAGE}:${TAG}"

PREV_IMAGE="$(docker inspect --format '{{.Config.Image}}' "${NAME}" 2>/dev/null || echo none)"
echo "→ Current image: ${PREV_IMAGE}"

echo "→ Recreating ${NAME} (bind ${BIND}) ..."
docker rm -f "${NAME}" >/dev/null 2>&1 || true
docker run -d --name "${NAME}" \
  --env-file "${ENV_FILE}" \
  --restart unless-stopped \
  -p "${BIND}" \
  "${IMAGE}:${TAG}" >/dev/null

echo "→ Waiting for /healthz ..."
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "✓ API healthy — ${IMAGE}:${TAG}"
    docker ps --filter "name=${NAME}" --format '  {{.Names}} {{.Status}} {{.Ports}}'
    exit 0
  fi
  sleep 1
done

echo "✗ ${NAME} did not become healthy within 30s." >&2
echo "  logs:     docker logs --tail 50 ${NAME}" >&2
if [[ "${PREV_IMAGE}" != "none" ]]; then
  echo "  rollback: docker rm -f ${NAME} && docker run -d --name ${NAME} --env-file ${ENV_FILE} --restart unless-stopped -p ${BIND} ${PREV_IMAGE}" >&2
fi
exit 1

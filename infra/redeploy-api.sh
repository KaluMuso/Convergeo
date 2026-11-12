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
#   ./redeploy-api.sh              # deploy :latest (prefer pinning a SHA for G9)
#   ./redeploy-api.sh <git-sha>    # pin/rollback to a specific GHCR build tag
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

_resolve_fingerprint_tag() {
  local tag="$1"
  if [[ "$tag" =~ ^[0-9a-f]{7,40}$ ]]; then
    printf '%s' "$tag"
    return
  fi
  local digest
  digest="$(docker image inspect "${IMAGE}:${tag}" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' 2>/dev/null || true)"
  if [[ -n "$digest" ]]; then
    printf '%s' "${digest##*:}"
    return
  fi
  printf '%s' "$tag"
}

echo "→ Pulling ${IMAGE}:${TAG} ..."
docker pull "${IMAGE}:${TAG}"

CANDIDATE_SOURCE_SHA="$(docker image inspect "${IMAGE}:${TAG}" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' 2>/dev/null || true)"
if [[ ! "${CANDIDATE_SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "✗ candidate image source SHA is missing or invalid" >&2
  exit 1
fi
if [[ "${TAG}" =~ ^[0-9a-f]{40}$ && "${CANDIDATE_SOURCE_SHA}" != "${TAG}" ]]; then
  echo "✗ candidate image source SHA differs from requested tag" >&2
  exit 1
fi
FINGERPRINT_TAG="$(_resolve_fingerprint_tag "$TAG")"
PREV_IMAGE="$(docker inspect --format '{{.Image}}' "${NAME}" 2>/dev/null || echo none)"
PREV_SOURCE_SHA=""
if [[ "${PREV_IMAGE}" != "none" ]]; then
  PREV_SOURCE_SHA="$(docker image inspect "${PREV_IMAGE}" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' 2>/dev/null || true)"
fi
echo "→ Current image: ${PREV_IMAGE}"
echo "→ Fingerprint tag: ${FINGERPRINT_TAG}"

echo "→ Recreating ${NAME} (bind ${BIND}) ..."
docker rm -f "${NAME}" >/dev/null 2>&1 || true
docker run -d --name "${NAME}" \
  --env-file "${ENV_FILE}" \
  -e "GIT_SHA=${CANDIDATE_SOURCE_SHA}" \
  -e "API_IMAGE_TAG=${FINGERPRINT_TAG}" \
  -e "SENTRY_RELEASE=${FINGERPRINT_TAG}" \
  --restart unless-stopped \
  -p "${BIND}" \
  "${IMAGE}:${TAG}" >/dev/null

echo "→ Waiting for /healthz ..."
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "✓ API healthy — ${IMAGE}:${TAG}"
    docker ps --filter "name=${NAME}" --format '  {{.Names}} {{.Status}} {{.Ports}}'
    if curl -fsS http://127.0.0.1:8000/fingerprint 2>/dev/null; then
      echo
    fi
    if [[ "$TAG" == "latest" ]]; then
      echo "  tip: pin immutable deploys with ./redeploy-api.sh <full-git-sha>" >&2
    fi
    exit 0
  fi
  sleep 1
done

echo "✗ ${NAME} did not become healthy within 30s." >&2
echo "  logs:     docker logs --tail 50 ${NAME}" >&2
if [[ "${PREV_SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  printf -v rollback_command 'docker rm -f %q && docker run -d --name %q --env-file %q -e GIT_SHA=%q -e API_IMAGE_TAG=%q -e SENTRY_RELEASE=%q --restart unless-stopped -p %q %q' \
    "${NAME}" "${NAME}" "${ENV_FILE}" "${PREV_SOURCE_SHA}" "${PREV_SOURCE_SHA}" "${PREV_SOURCE_SHA}" "${BIND}" "${PREV_IMAGE}"
  echo "  rollback: ${rollback_command}" >&2
elif [[ "${PREV_IMAGE}" != "none" ]]; then
  echo "  rollback: previous image source SHA unavailable; verify its identity before redeploying it" >&2
fi
exit 1

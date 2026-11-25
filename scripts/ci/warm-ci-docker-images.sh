#!/usr/bin/env bash
# CI-SPEED (T40): prefetch pinned Postgres / Supabase images so service containers
# and typegen stacks reuse warmed layers on the hosted runner.
set -euo pipefail

IMAGES=(
  "pgvector/pgvector:0.8.0-pg17-trixie"
)

for image in "${IMAGES[@]}"; do
  echo "warming ${image}"
  if ! docker pull "${image}"; then
    echo "::warning::docker pull ${image} failed; service container may cold-pull"
  fi
done
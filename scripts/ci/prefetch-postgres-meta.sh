#!/usr/bin/env bash
set -u

image="${POSTGRES_META_IMAGE:-public.ecr.aws/supabase/postgres-meta:v0.96.6}"
attempts="${POSTGRES_META_PULL_ATTEMPTS:-4}"
delay="${POSTGRES_META_PULL_BACKOFF_SECONDS:-2}"
[[ "${attempts}" =~ ^[1-9][0-9]?$ && "${attempts}" -le 10 &&
   "${delay}" =~ ^[0-9]+$ && "${#delay}" -le 2 && "${delay}" -le 30 ]] || {
  echo 'error: invalid postgres-meta retry budget' >&2
  exit 2
}

pull_image() {
  local candidate="$1" attempt status=1
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    echo "postgres-meta pull ${attempt}/${attempts}: ${candidate}" >&2
    if docker pull "${candidate}"; then
      return 0
    else
      status=$?
    fi
    if ((attempt < attempts)); then
      sleep "$delay" || return $?
    fi
  done
  echo "error: unable to pull ${candidate} after ${attempts} attempts" >&2
  return "$status"
}

if pull_image "${image}"; then
  docker image inspect --format='postgres-meta image={{index .RepoDigests 0}} id={{.Id}}' \
    "${image}" || exit $?
  exit 0
else
  status=$?
fi

# Supabase CLI v2.109.1's legacy-docker-registry.ts uses this official mirror.
# Only the pinned default can fall back. Do not redirect arbitrary overrides.
[[ "${image}" == 'public.ecr.aws/supabase/postgres-meta:v0.96.6' ]] || exit "$status"
mirror='ghcr.io/supabase/postgres-meta:v0.96.6'
echo "postgres-meta fallback: ${mirror}" >&2
if pull_image "${mirror}"; then
  :
else
  exit $?
fi

# gen types still requests the original name. A local alias changes no image
# bytes; provenance records the actual GHCR RepoDigests, not a fabricated ECR
# digest. Bind the alias to the inspected image ID and verify it after tagging.
if mirror_id="$(docker image inspect --format='{{.Id}}' "${mirror}")"; then
  :
else
  exit $?
fi
[[ "${mirror_id}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo 'error: invalid postgres-meta mirror image ID' >&2
  exit 1
}
docker tag "${mirror_id}" "${image}" || exit $?
if alias_id="$(docker image inspect --format='{{.Id}}' "${image}")"; then
  :
else
  exit $?
fi
[[ "${alias_id}" == "${mirror_id}" ]] || {
  echo 'error: postgres-meta mirror alias image mismatch' >&2
  exit 1
}
printf 'postgres-meta pull_source=%s local_alias=%s image_id=%s\n' \
  "${mirror}" "${image}" "${mirror_id}"
docker image inspect --format='postgres-meta image={{index .RepoDigests 0}} id={{.Id}}' \
  "${image}" || exit $?

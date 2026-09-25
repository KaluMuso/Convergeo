#!/usr/bin/env bash
set -u

image="${POSTGRES_META_IMAGE:-public.ecr.aws/supabase/postgres-meta:v0.96.6}"
attempts="${POSTGRES_META_PULL_ATTEMPTS:-4}"
delay="${POSTGRES_META_PULL_BACKOFF_SECONDS:-2}"

for ((attempt = 1; attempt <= attempts; attempt++)); do
  echo "postgres-meta pull ${attempt}/${attempts}: ${image}" >&2
  if docker pull "${image}"; then
    docker image inspect --format='postgres-meta image={{index .RepoDigests 0}} id={{.Id}}' \
      "${image}" || exit $?
    exit 0
  else
    status=$?
  fi
  if ((attempt < attempts)); then
    sleep "$delay"
  fi
done

echo "error: unable to pull ${image} after ${attempts} attempts" >&2
exit "$status"

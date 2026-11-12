#!/usr/bin/env bash
# Same OCI index used by qualified ECR typegen run 38140318887, job 114472861622.
# Official GHCR index bytes were verified against that digest (2026-10-12).
# CLI 2.109.1 / postgres-meta v0.96.6 and the existing ECR reference stay unchanged.
set -euo pipefail

readonly image='ghcr.io/supabase/postgres-meta@sha256:a84cc713585eea7b401e4a2561ec4a1e48c87083d1c7ecb4502f204bb4391300'
readonly expected_tag='public.ecr.aws/supabase/postgres-meta:v0.96.6'
readonly platform='linux/amd64' # The existing ubuntu-latest typegen runner is x64.

die() { printf '::error::%s\n' "$1" >&2; exit 1; }

runner_platform="$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')"
[[ "$runner_platform" == "$platform" ]] || die 'Typegen runner platform differs from qualification.'

# No login, registry override, tag substitution, retries or alternate-image fallback.
docker pull --platform "$platform" "$image"
digests="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image")"
printf '%s\n' "$digests" | grep -Fxq "$image" || die 'Qualified postgres-meta digest is absent.'
image_platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")"
[[ "$image_platform" == "$platform" ]] || die 'Pulled postgres-meta platform differs from qualification.'
image_id="$(docker image inspect --format '{{.Id}}' "$image")"
[[ "$image_id" =~ ^sha256:[a-f0-9]{64}$ ]] || die 'Pulled postgres-meta image identity is invalid.'

# Local alias only: Docker's default missing-image policy can reuse these exact bytes.
docker tag "$image" "$expected_tag"
cached_id="$(docker image inspect --format '{{.Id}}' "$expected_tag")"
[[ "$cached_id" == "$image_id" ]] || die 'Cached ECR alias does not match the qualified image.'
printf 'Qualified postgres-meta image cached for type generation.\n'

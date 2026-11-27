#!/usr/bin/env bash
# Pull the Supabase local-stack images from the ghcr.io/supabase mirror instead of the
# anonymous public.ecr.aws cap ("toomanyrequests: Data limit exceeded") and FAIL unless
# every image resolves to the reviewed digest. Pair with SUPABASE_INTERNAL_IMAGE_REGISTRY=ghcr.io
# so `supabase start` finds the images locally under the same name.
# Digests captured 2026-11-27; postgres-meta equals the pin in preload-typegen-meta.sh.
set -euo pipefail

registry='ghcr.io/supabase'
IMAGES=(
  "postgres:15.8.1.085=sha256:af083ef64d0408c8f098ee6f5c364a59b26f36fbc0f3a334a62c5c1d57362e9b"
  "postgrest:v14.14=sha256:d2009b5c9deffc210c8a5592698472fede14fd9f6ca89823c8474ca54d58c012"
  "studio:2026.07.06-sha-66cf431=sha256:4a5163e33578b346e6eab1352034d29140cf84b6d9989aab6fcf4b39edb3b13c"
  "kong:2.8.1=sha256:1b53405d8680a09d6f44494b7990bf7da2ea43f84a258c59717d4539abf09f6d"
  "gotrue:v2.192.0=sha256:b252efb680be37d4a8bf77c210cf0439c19b63a4b51929233a65dd101d25bdab"
  "imgproxy:v3.8.0=sha256:0facd355d50f3be665ebe674486f2b2e9cdaebd3f74404acd9b7fece2f661435"
  "logflare:1.46.0=sha256:f3c7a387ab7bb94af001b907c08df14258bd255f29d4cdb8bf6b393707558bf2"
  "mailpit:v1.30.2=sha256:37a38e48e9338cd7e89dfeb487f37b02ebfcd9cb23111bed2d345e79d37d6dd6"
  "postgres-meta:v0.96.6=sha256:a84cc713585eea7b401e4a2561ec4a1e48c87083d1c7ecb4502f204bb4391300"
  "realtime:v2.112.6=sha256:7b56da34216fd568042be043900d15cdd33c2c48c2116c9a333f9465255da80d"
  "storage-api:v1.62.5=sha256:1dbe962d9862ef12e20357f9d7ba5431989c1daf4a556d6cb20ee4efd1c57320"
  "vector:0.53.0-alpine=sha256:ca92d617e905953c3f852e7e88061f7039460e733522e3f0c21bc6ae946b2558"
)

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  printf '%s' "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin >/dev/null
fi

for entry in "${IMAGES[@]}"; do
  ref="${entry%%=*}"
  want="${entry#*=}"
  image="${registry}/${ref}"
  ok=0
  for attempt in 1 2 3; do
    if docker pull --quiet "$image" >/dev/null; then ok=1; break; fi
    echo "pull ${image} failed (attempt ${attempt}/3)" >&2
    sleep $((attempt * 5))
  done
  (( ok == 1 )) || { echo "::error::could not pull ${image}" >&2; exit 1; }
  got="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image")"
  if ! grep -Fq "@${want}" <<<"$got"; then
    echo "::error::digest mismatch for ${image}: expected ${want}, got: ${got:-none}" >&2
    exit 1
  fi
  echo "verified ${image} ${want}"
done

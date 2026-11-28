#!/usr/bin/env bash
# Pull the pinned critical-job image without hiding a registry throttle.
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo 'usage: pull-critical-postgrest-image.sh IMAGE LOG_DIR' >&2
  exit 2
fi

image="$1"
log_dir="$2"
if [[ ! -d "$log_dir" ]]; then
  echo "PostgREST pull evidence directory does not exist: $log_dir" >&2
  exit 2
fi
summary="$log_dir/postgrest-pull.log"
: > "$summary"

# public.ecr.aws serves anonymous pulls under a shared data cap ("toomanyrequests: Data limit
# exceeded"). When CI_POSTGREST_MIRROR=1, for the one pinned PostgREST image, prefer the ghcr.io/supabase mirror, accept it
# only when its digest equals the reviewed one, and tag it with the requested name. Any mirror
# failure or digest mismatch falls through to the original pull below; nothing is loosened.
ecr_postgrest='public.ecr.aws/supabase/postgrest:v14.14'
mirror_postgrest='ghcr.io/supabase/postgrest:v14.14'
mirror_digest='sha256:d2009b5c9deffc210c8a5592698472fede14fd9f6ca89823c8474ca54d58c012'
if [[ "${CI_POSTGREST_MIRROR:-}" == 1 && "$image" == "$ecr_postgrest" ]]; then
  if timeout --kill-after=5s 90s docker pull "$mirror_postgrest" > "$log_dir/postgrest-mirror-pull.log" 2>&1 \
      && docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$mirror_postgrest" \
        | grep -Fq "@${mirror_digest}" \
      && docker tag "$mirror_postgrest" "$image"; then
    printf 'mirror=%s digest=%s result=success\n' "$mirror_postgrest" "$mirror_digest" >> "$summary"
    exit 0
  fi
  printf 'mirror=%s result=unavailable-or-digest-mismatch; falling back to %s\n' \
    "$mirror_postgrest" "$image" >> "$summary"
fi

# At most three 60-second pulls, two short backoffs, and timeout cleanup.
max_attempts=3
for attempt in 1 2 3; do
  attempt_log="$log_dir/postgrest-pull-attempt-$attempt.log"
  if timeout --kill-after=5s 60s docker pull "$image" > "$attempt_log" 2>&1; then
    printf 'attempt=%d/%d result=success\n' "$attempt" "$max_attempts" >> "$summary"
    cat "$attempt_log" >> "$summary"
    exit 0
  else
    pull_status=$?
  fi

  printf 'attempt=%d/%d result=failed exit=%d\n' "$attempt" "$max_attempts" "$pull_status" >> "$summary"
  cat "$attempt_log" >> "$summary"
  # Only the registry's observed rate-limit response qualifies for retry.
  last_error="$(awk 'NF { line = $0 } END { print line }' "$attempt_log")"
  if (( pull_status == 124 || pull_status == 137 )) || \
      ! printf '%s\n' "$last_error" | grep -Eiq 'toomanyrequests:[[:space:]]*rate exceeded'; then
    echo "PostgREST pull failed (exit $pull_status); see $attempt_log" >&2
    tail -n 20 "$attempt_log" >&2 || true
    exit "$pull_status"
  fi
  if (( attempt == max_attempts )); then
    echo "PostgREST pull rate limit persisted after $max_attempts attempts; see $summary" >&2
    exit "$pull_status"
  fi
  delay=$((5 * (1 << (attempt - 1))))
  echo "PostgREST registry rate-limited pull $attempt/$max_attempts; retrying in ${delay}s" >&2
  sleep "$delay"
done

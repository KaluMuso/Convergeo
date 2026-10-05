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

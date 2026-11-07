#!/usr/bin/env bash
# Supplemental F2 test runner on an already provisioned disposable stack.
# Does not provision/reset databases, dispatch workflows, or replace the 88 gate.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
phase="${1:?expected pristine or upgrade}"
case "$phase" in
  pristine) group=collection ;;
  upgrade) group=prepaid ;;
  *) echo 'Expected pristine or upgrade' >&2; exit 1 ;;
esac
: "${F2_POSTGREST_CONTAINER:?dedicated running PostgREST container required}"
: "${RUNNER_TEMP:?isolated hosted runner evidence directory required}"
for name in SUPABASE_DB_URL SUPABASE_URL SUPABASE_REST_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_ANON_KEY LANE_D_POSTGREST_URL LANE_D_JWT_SECRET LANE_D_WEBHOOK_TOKEN; do
  [[ -n "${!name:-}" ]] || { echo "Missing $name" >&2; exit 1; }
done
evidence="$RUNNER_TEMP/f2-$phase"
mkdir -p "$evidence"
git rev-parse HEAD HEAD^{tree} > "$evidence/source.txt"
git diff --exit-code --quiet
git diff --cached --exit-code --quiet
manifest="$root/docs/ops/lenco/f2-required-nodes.txt"
cp "$manifest" "$evidence/expected-nodes.txt"
cd services/api
uv run --no-sync python ../../scripts/ci/critical_real_stack_http.py preflight \
  --group "$group" --database "ci_critical_$group" \
  --container "$F2_POSTGREST_CONTAINER" > "$evidence/preflight.log" 2>&1
tests=(tests/lane_d/test_f2_service_funding_postgrest.py tests/lane_d/test_f2_cancellation_postgrest.py)
uv run --no-sync pytest --collect-only -q --disable-warnings "${tests[@]}" > "$evidence/collection.log" 2>&1
python ../../scripts/ci/critical-real-stack-report.py collection --manifest "$manifest" \
  --input "$evidence/collection.log" --output "$evidence/collected-nodes.txt"
set +e
uv run --no-sync pytest -q -rA -o xfail_strict=true \
  --junitxml="$evidence/f2.xml" "${tests[@]}" > "$evidence/pytest.log" 2>&1
test_status=$?
# Collect the SAME complete related selection independently before execution.
# Remove stale manifests first; a failed collection cannot reuse previous evidence.
related_tests=(tests/test_order_state.py tests/test_job_completion.py tests/test_service_escrow.py tests/test_service_booking.py)
rm -f "$evidence/related-collected.json"
F2_COLLECTION_OUTPUT="$evidence/related-collected.json" \
  PYTHONPATH="$root/scripts/drills${PYTHONPATH:+:$PYTHONPATH}" \
  uv run --no-sync pytest -p f2_collection_manifest --collect-only -q \
  --disable-warnings "${related_tests[@]}" > "$evidence/related-collection.log" 2>&1
related_collection_status=$?
# Still execute other evidence paths after failure; the final gate rejects partial results.
uv run --no-sync pytest -q -rA -o xfail_strict=true \
  --junitxml="$evidence/related.xml" "${related_tests[@]}" \
  > "$evidence/related.log" 2>&1
related_status=$?
set -e
python ../../scripts/drills/f2_real_stack_report.py --manifest "$manifest" \
  --junit "$evidence/f2.xml" --pytest-exit "$test_status" \
  --related-manifest "$evidence/related-collected.json" \
  --related-collection-exit "$related_collection_status" \
  --related-junit "$evidence/related.xml" --related-pytest-exit "$related_status" \
  --output "$evidence/results.json"

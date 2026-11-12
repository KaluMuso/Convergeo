#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is required}"
[[ "${SUPABASE_DB_URL}" == 'postgresql://postgres:postgres@127.0.0.1:54322/postgres' ]] || {
  echo "error: service ACL probe requires the disposable typegen loopback database" >&2
  exit 1
}
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
contract="${root}/scripts/ci/typegen-synthetic-contract.sql"
psql_bin="${PSQL_BIN:-psql}"

# Consume only sanitized hashes and ACL metadata from the existing contract.
# Never print the captured catalog evidence or any database values.
if ! clean="$("${psql_bin}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -Atq \
  <"${contract}" 2>/dev/null)"; then
  echo "error: service ACL baseline query failed" >&2
  exit 1
fi
direct_hash_matches() {
  awk -F '|' '$1 == "direct_role_acl" && NF == 3 { count++; if ($2 != $3) bad = 1 }
    END { exit !(count == 1 && !bad) }' <<<"$1"
}
direct_hash_differs() {
  awk -F '|' '$1 == "direct_role_acl" && NF == 3 { count++; if ($2 == $3) bad = 1 }
    END { exit !(count == 1 && !bad) }' <<<"$1"
}
direct_hash_matches "${clean}" || { echo "error: service ACL baseline drift" >&2; exit 1; }
[[ "${clean}" != *direct_acl_delta\|* ]] || { echo "error: unexpected baseline ACL delta" >&2; exit 1; }

# A transactional negative control must be detected, then disappear on rollback.
# The transaction runs only against the disposable typegen database.
if ! polluted="$({
  printf 'BEGIN;\nGRANT MAINTAIN ON TABLE public.cart_merge_receipts TO service_role;\n'
  cat "${contract}"
  printf '\nROLLBACK;\n'
} | "${psql_bin}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -Atq 2>/dev/null)"; then
  echo "error: service ACL negative control query failed" >&2
  exit 1
fi
direct_hash_differs "${polluted}" || { echo "error: service ACL negative control was missed" >&2; exit 1; }
expected_delta='direct_acl_delta|unexpected|public|cart_merge_receipts|service_role|MAINTAIN|postgres|false'
[[ "$(grep -Fxc "${expected_delta}" <<<"${polluted}" || true)" == 1 &&
   "$(grep -c '^direct_acl_delta|' <<<"${polluted}" || true)" == 1 ]] || {
  echo "error: unexpected service ACL negative control evidence" >&2
  exit 1
}
if ! restored="$("${psql_bin}" "${SUPABASE_DB_URL}" -X -v ON_ERROR_STOP=1 -Atq \
  <"${contract}" 2>/dev/null)"; then
  echo "error: service ACL rollback query failed" >&2
  exit 1
fi
direct_hash_matches "${restored}" || { echo "error: service ACL rollback drift" >&2; exit 1; }
[[ "${restored}" == "${clean}" ]] || { echo "error: service ACL rollback changed catalog evidence" >&2; exit 1; }
echo 'service_table_acl_hardening=PASS'

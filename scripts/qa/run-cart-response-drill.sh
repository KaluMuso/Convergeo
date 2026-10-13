#!/usr/bin/env bash
# Test-only runner: reuse the already seeded/built disposable perf resources.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" = true && "${RUNNER_ENVIRONMENT:-}" = github-hosted ]]
[[ "${GITHUB_REPOSITORY:-}" = KaluMuso/Convergeo ]]
[[ "${CART_DRILL_LOCAL:-}" = 1 ]]
[[ "${SUPABASE_URL:-}" = http://127.0.0.1:54321 ]]
[[ "${SUPABASE_DB_URL:-}" = postgresql://postgres:postgres@127.0.0.1:54322/postgres ]]
[[ "${CART_DRILL_SOURCE_SHA:-}" = "$(git rev-parse HEAD)" ]]
drill_root=$(pwd)
drill_source_root="$drill_root"
drill_output="$drill_root/e2e/results/cart-response-drill"
drill_artifact_output="$drill_output"
drill_package_root=
drill_package_verified=false
drill_manifest_sha=
drill_node=$(command -v node)
drill_python_library="${pythonLocation:?}/lib"
[[ "$drill_python_library" = /opt/hostedtoolcache/Python/*/lib && -d "$drill_python_library" ]]
drill_python_real=$(readlink -f "$drill_root/services/api/.venv/bin/python")
[[ "$drill_python_real" = "${pythonLocation}/bin/python"* ]]
if [ ! -s "$drill_root/apps/customer/.next/BUILD_ID" ]; then
  echo "Cart drill preflight failed: completed head build missing" >&2
  exit 1
fi
drill_next="$drill_root/apps/customer/node_modules/next/dist/bin/next"
if [ ! -x "$drill_node" ] || [ ! -x "$drill_python_real" ] || [ ! -r "$drill_next" ]; then
  echo "Cart drill preflight failed: Node/Python/Next executable path unavailable" >&2
  exit 1
fi
drill_browser_executable=$(cd e2e && node --input-type=module -e 'import {createRequire} from "node:module"; const req=createRequire(import.meta.url); const testReq=createRequire(req.resolve("@playwright/test/package.json")); const pwReq=createRequire(testReq.resolve("playwright/package.json")); const {registry}=pwReq("playwright-core/lib/server/registry/index"); console.log(registry.findExecutable("chromium-headless-shell").executablePath())')
if [ ! -x "$drill_browser_executable" ]; then
  echo "Cart drill preflight failed: installed Chromium executable unavailable" >&2
  exit 1
fi
for drill_tool in sudo iptables ip6tables ss fuser useradd userdel pgrep pkill; do
  if ! command -v "$drill_tool" >/dev/null; then
    echo "Cart drill preflight failed: required tool $drill_tool unavailable" >&2
    exit 1
  fi
done
drill_browser_path=$(cd e2e && node --input-type=module -e 'import {chromium} from "@playwright/test"; import {dirname} from "node:path"; console.log(dirname(dirname(dirname(chromium.executablePath()))))')
drill_created=false
drill_v4=false
drill_v6=false
drill_uid=
drill_phase=guard_setup
drill_api_launcher=
drill_customer_launcher=
drill_launcher_status() {
  drill_last_launcher_status=not_started
  if [ -n "$1" ]; then
    if kill -0 "$1" 2>/dev/null; then drill_last_launcher_status=running
    elif wait "$1"; then drill_last_launcher_status=0
    else drill_last_launcher_status=$?; fi
  fi
}
drill_cleanup() {
  drill_status=$?
  trap - EXIT
  drill_launcher_status "$drill_api_launcher"
  drill_api_exit="$drill_last_launcher_status"
  drill_launcher_status "$drill_customer_launcher"
  drill_customer_exit="$drill_last_launcher_status"
  drill_cleanup_ok=true
  if [ "$drill_created" = true ]; then
    if sudo test -f "$drill_output/private-state.json"; then
      if ! drill_as_user "$drill_root/services/api/.venv/bin/python" "$drill_root/scripts/qa/cart-response-drill-db.py" cleanup <<< '{}'; then drill_cleanup_ok=false; fi
    fi
    sudo pkill -KILL -u "$drill_uid" 2>/dev/null || [ "$?" -eq 1 ] || drill_cleanup_ok=false
    for drill_cleanup_attempt in $(seq 1 20); do
      if ! sudo pgrep -u "$drill_uid" >/dev/null; then break; fi
      sleep 0.1
    done
    if sudo pgrep -u "$drill_uid" >/dev/null; then drill_cleanup_ok=false; fi
  fi
  if [ "$drill_v4" = true ]; then
    if sudo iptables -w -C OUTPUT -m owner --uid-owner "$drill_uid" -j CARTDRILL4 2>/dev/null; then
      sudo iptables -w -D OUTPUT -m owner --uid-owner "$drill_uid" -j CARTDRILL4 || drill_cleanup_ok=false
    fi
    sudo iptables -w -F CARTDRILL4 || drill_cleanup_ok=false
    sudo iptables -w -X CARTDRILL4 || drill_cleanup_ok=false
  fi
  if [ "$drill_v6" = true ]; then
    if sudo ip6tables -w -C OUTPUT -m owner --uid-owner "$drill_uid" -j CARTDRILL6 2>/dev/null; then
      sudo ip6tables -w -D OUTPUT -m owner --uid-owner "$drill_uid" -j CARTDRILL6 || drill_cleanup_ok=false
    fi
    sudo ip6tables -w -F CARTDRILL6 || drill_cleanup_ok=false
    sudo ip6tables -w -X CARTDRILL6 || drill_cleanup_ok=false
  fi
  if sudo test -d "$drill_output"; then
    sudo chown -R "$(id -u):$(id -g)" "$drill_output" || drill_cleanup_ok=false
    sudo chmod 700 "$drill_output" || drill_cleanup_ok=false
    if ! python3 - "$drill_output" "$drill_phase" "$drill_status" "$drill_api_exit" "$drill_customer_exit" <<'PY'
import json, re, sys
from pathlib import Path
p = Path(sys.argv[1])
def log_text(name):
    return (p / name).read_text(errors='replace') if (p / name).exists() else ''
def categories(name):
    text = log_text(name)
    markers = ['Permission denied', 'libpython', 'ModuleNotFoundError', 'EACCES', 'Address already in use', 'ERR_MODULE_NOT_FOUND', 'Pydantic', 'ValidationError']
    markers += ['MODULE_NOT_FOUND', 'Cannot find module', 'Cannot find package',
                'ERR_PACKAGE_PATH_NOT_EXPORTED', 'ERR_REQUIRE_ESM', 'ERR_UNKNOWN_FILE_EXTENSION',
                'ERR_DLOPEN_FAILED', 'EPERM', 'ENOENT', 'EADDRINUSE',
                'Failed to load next.config', 'Failed to load SWC binary']
    return [marker for marker in markers if marker in text]
def missing_customer_module():
    match = re.search(r"Cannot find (?:module|package) ['\"]([^'\"]+)['\"]", log_text('private-customer.log'))
    if match is None:
        return None
    name = match.group(1)
    public_modules = {'next', 'react', 'react-dom', 'styled-jsx', 'styled-jsx/style',
                      'typescript', '@next/env', '@swc/helpers', '@serwist/next',
                      'next-intl/plugin', '@vergeo/config', '@vergeo/config/security-headers'}
    if name in public_modules:
        return name
    if name.startswith('next/dist/'):
        return 'next_internal'
    return 'unclassified'
d = {'phase': sys.argv[2], 'exit': int(sys.argv[3]), 'api_log_categories': categories('private-api.log'),
     'api_launcher_status': sys.argv[4], 'customer_launcher_status': sys.argv[5],
     'python_probe_categories': categories('private-python-probe.log'),
     'customer_log_categories': categories('private-customer.log'),
     'customer_missing_module': missing_customer_module(), 'raw_logs_retained_privately_only': True}
try:
    health = json.loads((p / 'private-health-probe.json').read_text())
    assert isinstance(health, list) and len(health) == 2
    assert {row['name'] for row in health} == {'api', 'customer'}
    assert all(type(row['ok']) is bool for row in health)
    d['latest_health'] = [{'name': row['name'], 'ok': row['ok']} for row in health]
except (OSError, ValueError, TypeError, KeyError, AssertionError):
    d['health_evidence'] = 'unavailable_or_malformed'
(p / 'diagnostics.json').write_text(json.dumps(d, indent=2) + '\n')
PY
    then drill_cleanup_ok=false; fi
  fi
  if [ "$drill_created" = true ] && [ "$drill_cleanup_ok" = true ]; then sudo userdel cartdrill || drill_cleanup_ok=false; fi
  if [ -f "$drill_output/guard.json" ]; then
    if ! python3 - "$drill_output/guard.json" "$drill_cleanup_ok" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); d = json.loads(p.read_text()); d['process_and_firewall_cleanup'] = sys.argv[2] == 'true'
p.write_text(json.dumps(d, indent=2) + '\n')
PY
    then drill_cleanup_ok=false; fi
  fi
  if [ -n "$drill_package_root" ]; then
    mkdir -p "$drill_artifact_output" || drill_cleanup_ok=false
    chmod 700 "$drill_artifact_output" || drill_cleanup_ok=false
    for drill_evidence in outcome.json guard.json diagnostics.json python-path-diagnostics.json; do
      if [ "$drill_output" = "$drill_artifact_output" ]; then break; fi
      if [ -f "$drill_output/$drill_evidence" ] && [ ! -L "$drill_output/$drill_evidence" ]; then
        cp -- "$drill_output/$drill_evidence" "$drill_artifact_output/$drill_evidence" || drill_cleanup_ok=false
      fi
    done
    if [ -f "$drill_package_root/input-manifest.json" ] && [ ! -L "$drill_package_root/input-manifest.json" ]; then
      cp -- "$drill_package_root/input-manifest.json" "$drill_artifact_output/input-manifest.json" || drill_cleanup_ok=false
    fi
    [[ "$drill_package_root" = /tmp/cartdrill.* && "${drill_package_root#/tmp/}" != */* ]] || drill_cleanup_ok=false
    if [ "$drill_cleanup_ok" = true ]; then
      sudo rm -rf -- "$drill_package_root" || drill_cleanup_ok=false
    fi
  fi
  if [ "$drill_cleanup_ok" != true ] && [ "$drill_status" -eq 0 ]; then drill_status=1; fi
  exit "$drill_status"
}
trap drill_cleanup EXIT
drill_as_user() {
  (
  cd "$drill_root"
  sudo -u cartdrill env -i PATH=/usr/bin:/bin CART_DRILL_LOCAL=1 CART_DRILL_UID="$drill_uid" \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$drill_package_root/tmp" XDG_CACHE_HOME="$drill_package_root/cache" XDG_CONFIG_HOME="$drill_package_root/config" \
    LD_LIBRARY_PATH="$drill_python_library" \
    PLAYWRIGHT_BROWSERS_PATH="$drill_browser_path" \
    SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
    SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
    NEXT_PUBLIC_DEPLOYMENT_PLANE=development NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 \
    NEXT_PUBLIC_SITE_URL=http://127.0.0.1:3000 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
    NEXT_PUBLIC_SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" \
    ENV=development CORS_ORIGINS=http://127.0.0.1:3000 NEXT_TELEMETRY_DISABLED=1 CI=1 "$@"
  )
}
# No new package, image, database or provider is provisioned.
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin cartdrill
drill_created=true
drill_uid=$(id -u cartdrill)
[[ "$drill_uid" -gt 0 ]]
[[ "$(id -Gn cartdrill)" = cartdrill ]]
sudo iptables -w -N CARTDRILL4
drill_v4=true
sudo iptables -w -A CARTDRILL4 -p tcp -d 127.0.0.1 -m multiport --dports 3000,8000,54321,54322 -j RETURN
for drill_port in 54321 54322; do
  sudo iptables -w -A CARTDRILL4 -p tcp -m conntrack --ctorigdst 127.0.0.1 --ctorigdstport "$drill_port" -j RETURN
done
for drill_port in 3000 8000; do
  # Guarded servers must be able to reply to loopback clients' ephemeral ports.
  sudo iptables -w -A CARTDRILL4 -p tcp -m conntrack --ctdir REPLY --ctorigdst 127.0.0.1 --ctorigdstport "$drill_port" -j RETURN
done
sudo iptables -w -A CARTDRILL4 -j REJECT
sudo iptables -w -I OUTPUT 1 -m owner --uid-owner "$drill_uid" -j CARTDRILL4
sudo ip6tables -w -N CARTDRILL6
drill_v6=true
sudo ip6tables -w -A CARTDRILL6 -j REJECT
sudo ip6tables -w -I OUTPUT 1 -m owner --uid-owner "$drill_uid" -j CARTDRILL6
# Verify installed owner hooks before any guarded process starts.
sudo iptables -w -C OUTPUT -m owner --uid-owner "$drill_uid" -j CARTDRILL4
sudo ip6tables -w -C OUTPUT -m owner --uid-owner "$drill_uid" -j CARTDRILL6
drill_phase=runtime_packaging
mkdir -p "$drill_artifact_output"
chmod 700 "$drill_artifact_output"
drill_package_root=$(mktemp -d /tmp/cartdrill.XXXXXXXXXX)
drill_manifest_sha=$("$drill_source_root/services/api/.venv/bin/python" \
  "$drill_source_root/scripts/qa/cart-response-drill-package.py" package \
  "$drill_source_root" "$pythonLocation" "$drill_node" "$drill_browser_executable" \
  "$drill_package_root" "$CART_DRILL_SOURCE_SHA")
[[ "$drill_manifest_sha" =~ ^[a-f0-9]{64}$ ]]
# Only independent copies in this new directory receive the existing test group.
# Its relative links were checked against the manifest before this ownership step.
sudo chown -hR "$(id -u):cartdrill" "$drill_package_root"
drill_root="$drill_package_root"
drill_output="$drill_root/e2e/results/cart-response-drill"
drill_node="$drill_root/.runtime/bin/node"
drill_browser_path="$drill_root/.runtime/browsers"
for drill_sdk_dir in "$pythonLocation" "${pythonLocation}/bin" "${pythonLocation}/lib" "${pythonLocation}/lib/python3.12"; do
  sudo -u cartdrill test -r "$drill_sdk_dir"
  sudo -u cartdrill test -x "$drill_sdk_dir"
done
drill_as_user "$drill_root/services/api/.venv/bin/python" \
  "$drill_root/scripts/qa/cart-response-drill-package.py" verify \
  "$drill_root" "$drill_manifest_sha" "$pythonLocation" > "$drill_artifact_output/runtime-package.json"
drill_package_verified=true
mkdir -p "$drill_output"
sudo chown "$(id -u):cartdrill" "$drill_output"
sudo chmod 770 "$drill_output"
for drill_writable in tmp cache config; do
  sudo install -d -o "$drill_uid" -g cartdrill -m 700 "$drill_package_root/$drill_writable"
done
drill_phase=python_preflight
if drill_as_user "$drill_root/services/api/.venv/bin/python" -c 'import ssl, psycopg, uvicorn; print("isolated Python imports ready")' > "$drill_output/private-python-probe.log" 2>&1; then
  :
else
  drill_python_probe_exit=$?
  # Read metadata only after failure; preserve its exit and every isolation rule.
  python3 "$drill_root/scripts/qa/cart-response-drill-path-diagnostics.py" \
    "$drill_root" "$pythonLocation" "$drill_uid" "$(id -g cartdrill)" \
    > "$drill_output/python-path-diagnostics.json" 2>/dev/null || true
  exit "$drill_python_probe_exit"
fi
drill_phase=server_startup
# Production clients intentionally reject loopback. Preserve that guard and all
# preceding production checks; exercise the same source in local development mode.
sudo fuser -k 3000/tcp 8000/tcp || true
sudo chown -R cartdrill:cartdrill "$drill_root/apps/customer/.next"
sudo chmod -R u+rwX "$drill_root/apps/customer/.next"
drill_as_user "$drill_root/services/api/.venv/bin/python" -m uvicorn app.main:app --app-dir "$drill_root/services/api" --host 127.0.0.1 --port 8000 > "$drill_output/private-api.log" 2>&1 &
drill_api_launcher=$!
drill_as_user "$drill_node" "$drill_root/apps/customer/node_modules/next/dist/bin/next" dev "$drill_root/apps/customer" --hostname 127.0.0.1 --port 3000 > "$drill_output/private-customer.log" 2>&1 &
drill_customer_launcher=$!
for drill_attempt in $(seq 1 10); do
  if drill_as_user "$drill_node" --input-type=module -e 'const results=await Promise.all([["api","http://127.0.0.1:8000/healthz"],["customer","http://127.0.0.1:3000/en/health"]].map(async ([name,url])=>{try{return {name,ok:(await fetch(url,{signal:AbortSignal.timeout(5000)})).ok}}catch{return {name,ok:false}}}));console.log(JSON.stringify(results));process.exit(results.every(r=>r.ok)?0:1)' > "$drill_output/private-health-probe.json"; then break; fi
  if [ "$drill_attempt" -eq 10 ]; then exit 1; fi
  sleep 1
done
sudo ss -H -ltnp '( sport = :3000 or sport = :8000 )' > "$drill_output/private-listeners.txt"
python3 - "$drill_output/private-listeners.txt" "$drill_uid" <<'PY'
import re, sys
from pathlib import Path
rows = Path(sys.argv[1]).read_text().splitlines()
assert len(rows) == 2
assert {r.split()[3] for r in rows} == {'127.0.0.1:3000', '127.0.0.1:8000'}
for row in rows:
    pids = re.findall(r'pid=(\d+)', row); assert pids
    for pid in pids:
        status = Path('/proc/' + pid + '/status').read_text()
        uid = re.search(r'^Uid:\s+(\d+)', status, re.M); assert uid and uid[1] == sys.argv[2]
PY
drill_phase=browser_contract
set +e
drill_as_user "$drill_node" "$drill_root/e2e/scripts/cart-response-drill.mjs"
drill_result=$?
set -e
drill_phase=evidence_and_cleanup
sudo iptables -w -nvx -L CARTDRILL4 > "$drill_output/private-ipv4.txt"
sudo ip6tables -w -nvx -L CARTDRILL6 > "$drill_output/private-ipv6.txt"
sudo iptables -w -S CARTDRILL4 > "$drill_output/private-ipv4-rules.txt"
sudo ip6tables -w -S CARTDRILL6 > "$drill_output/private-ipv6-rules.txt"
sudo chown -R "$(id -u):cartdrill" "$drill_output"
sudo chmod 770 "$drill_output"
python3 - "$drill_output" "$drill_uid" "$CART_DRILL_SOURCE_SHA" "$drill_manifest_sha" "$drill_package_verified" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
def rejected(name):
    return sum(int(row.split()[0]) for row in (p / name).read_text().splitlines() if ' REJECT ' in row)
d = {'version': 1, 'uid': int(sys.argv[2]), 'source_sha': sys.argv[3], 'ipv4_owner_hook_verified': True,
     'runtime_package_verified': sys.argv[5] == 'true', 'runtime_manifest_sha256': sys.argv[4],
     'runtime_package_no_private_links': True,
     'customer_execution_mode': 'development; production loopback guard preserved',
     'ipv6_owner_hook_verified': True, 'allowed_loopback_tcp_ports': [3000, 8000, 54321, 54322],
     'dnat_original_destination': '127.0.0.1', 'dnat_original_tcp_ports': [54321, 54322],
     'loopback_server_reply_original_tcp_ports': [3000, 8000],
     'all_other_ipv4_and_ipv6_rejected': True, 'rejected_packets': rejected('private-ipv4.txt') + rejected('private-ipv6.txt'),
     'api_and_customer_listener_uid_verified': True,
     'ipv4_rules': (p / 'private-ipv4-rules.txt').read_text().splitlines(),
     'ipv6_rules': (p / 'private-ipv6-rules.txt').read_text().splitlines(),
     'process_and_firewall_cleanup': False,
     'coverage': 'dedicated UID application, browser and native SQL traffic; Supabase container daemons excluded'}
(p / 'guard.json').write_text(json.dumps(d, indent=2) + '\n')
PY
exit "$drill_result"

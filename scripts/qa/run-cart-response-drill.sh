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
drill_output="$drill_root/e2e/results/cart-response-drill"
drill_node=$(command -v node)
drill_browser_path=$(cd e2e && node --input-type=module -e 'import {chromium} from "@playwright/test"; import {dirname} from "node:path"; console.log(dirname(dirname(dirname(chromium.executablePath()))))')
drill_created=false
drill_v4=false
drill_v6=false
drill_uid=
drill_cleanup() {
  drill_status=$?
  trap - EXIT
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
  fi
  if [ "$drill_created" = true ] && [ "$drill_cleanup_ok" = true ]; then sudo userdel cartdrill || drill_cleanup_ok=false; fi
  if [ -f "$drill_output/guard.json" ]; then
    python3 - "$drill_output/guard.json" "$drill_cleanup_ok" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); d = json.loads(p.read_text()); d['process_and_firewall_cleanup'] = sys.argv[2] == 'true'
p.write_text(json.dumps(d, indent=2) + '\n')
PY
  fi
  if [ "$drill_cleanup_ok" != true ] && [ "$drill_status" -eq 0 ]; then drill_status=1; fi
  exit "$drill_status"
}
trap drill_cleanup EXIT
drill_as_user() {
  sudo -u cartdrill env -i PATH=/usr/bin:/bin CART_DRILL_LOCAL=1 CART_DRILL_UID="$drill_uid" \
    PLAYWRIGHT_BROWSERS_PATH="$drill_browser_path" \
    SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
    SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
    NEXT_PUBLIC_DEPLOYMENT_PLANE=development NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 \
    NEXT_PUBLIC_SITE_URL=http://127.0.0.1:3000 NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
    NEXT_PUBLIC_SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" \
    ENV=development CORS_ORIGINS=http://127.0.0.1:3000 NEXT_TELEMETRY_DISABLED=1 CI=1 "$@"
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
mkdir -p "$drill_output"
sudo chown "$(id -u):cartdrill" "$drill_output"
sudo chmod 770 "$drill_output"
# Production clients intentionally reject loopback. Preserve that guard and all
# preceding production checks; exercise the same source in local development mode.
sudo fuser -k 3000/tcp 8000/tcp || true
sudo chown -R cartdrill:cartdrill "$drill_root/apps/customer/.next"
drill_as_user "$drill_root/services/api/.venv/bin/python" -m uvicorn app.main:app --app-dir "$drill_root/services/api" --host 127.0.0.1 --port 8000 > "$drill_output/private-api.log" 2>&1 &
drill_as_user "$drill_node" "$drill_root/apps/customer/node_modules/next/dist/bin/next" dev "$drill_root/apps/customer" --hostname 127.0.0.1 --port 3000 > "$drill_output/private-customer.log" 2>&1 &
for drill_attempt in $(seq 1 10); do
  if drill_as_user "$drill_node" --input-type=module -e 'for (const u of ["http://127.0.0.1:8000/healthz","http://127.0.0.1:3000/en/health"]) {if (!(await fetch(u, {signal: AbortSignal.timeout(5000)})).ok) process.exit(1)}' >/dev/null 2>&1; then break; fi
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
set +e
drill_as_user "$drill_node" "$drill_root/e2e/scripts/cart-response-drill.mjs"
drill_result=$?
set -e
sudo iptables -w -nvx -L CARTDRILL4 > "$drill_output/private-ipv4.txt"
sudo ip6tables -w -nvx -L CARTDRILL6 > "$drill_output/private-ipv6.txt"
sudo iptables -w -S CARTDRILL4 > "$drill_output/private-ipv4-rules.txt"
sudo ip6tables -w -S CARTDRILL6 > "$drill_output/private-ipv6-rules.txt"
sudo chown -R "$(id -u):cartdrill" "$drill_output"
sudo chmod 770 "$drill_output"
python3 - "$drill_output" "$drill_uid" "$CART_DRILL_SOURCE_SHA" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
def rejected(name):
    return sum(int(row.split()[0]) for row in (p / name).read_text().splitlines() if ' REJECT ' in row)
d = {'version': 1, 'uid': int(sys.argv[2]), 'source_sha': sys.argv[3], 'ipv4_owner_hook_verified': True,
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

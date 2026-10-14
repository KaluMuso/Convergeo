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
drill_gid=
drill_swc_cache_record=
drill_swc_cache_root=
drill_swc_cache_requested=false
drill_phase=guard_setup
drill_api_launcher=
drill_customer_launcher=
drill_native_cache() {
  local -a cache_python=(python3)
  if [ "$1" = allocate ] || [ "$1" = verify ]; then
    cache_python=(sudo -u cartdrill env -i PATH=/usr/bin:/bin python3)
  elif [ "$1" = remove ]; then
    cache_python=(sudo env -i PATH=/usr/bin:/bin python3)
  fi
  # Native cache guard (stdlib only). Never import or execute an addon here.
  "${cache_python[@]}" - "$1" "$drill_uid" "$drill_gid" "$drill_swc_cache_record" <<'PY'
import json, os, re, shutil, stat, sys, tempfile
from contextlib import contextmanager

def require(condition):
    if not condition:
        raise ValueError('private native cache guard failed')

def trusted_parent():
    for path in ('/', '/tmp'):
        metadata = os.lstat(path)
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == 0)
        require(stat.S_IMODE(metadata.st_mode) == 0o1777 if path == '/tmp'
                else metadata.st_mode & 0o022 == 0)

def parse_record(value):
    require(len(value) <= 512)
    record = json.loads(value)
    require(type(record) is dict and set(record) == {'path', 'device', 'inode'})
    require(type(record['path']) is str and
            re.fullmatch(r'/tmp/cartdrill-swc\.[a-z0-9_]{8}', record['path']) is not None)
    require(all(type(record[k]) is int and record[k] >= 0 for k in ('device', 'inode')))
    require(record['inode'] > 0)
    return record

def validate_metadata(metadata, record, uid, gid):
    require(stat.S_ISDIR(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o700)
    require(metadata.st_uid == uid and metadata.st_gid == gid)
    require((metadata.st_dev, metadata.st_ino) == (record['device'], record['inode']))

@contextmanager
def checked_cache(record, uid, gid):
    trusted_parent()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open('/tmp', flags)
    cache = None
    try:
        parent_metadata = os.fstat(parent)
        require(parent_metadata.st_uid == 0 and
                stat.S_IMODE(parent_metadata.st_mode) == 0o1777)
        name = record['path'].rsplit('/', 1)[1]
        validate_metadata(os.stat(name, dir_fd=parent, follow_symlinks=False), record, uid, gid)
        cache = os.open(name, flags, dir_fd=parent)
        validate_metadata(os.fstat(cache), record, uid, gid)
        yield parent, cache, name
    finally:
        if cache is not None:
            os.close(cache)
        os.close(parent)

def allocate(uid, gid):
    require(uid > 0 and os.geteuid() == uid and os.getegid() == gid)
    trusted_parent()
    path = tempfile.mkdtemp(prefix='cartdrill-swc.', dir='/tmp')
    metadata = os.lstat(path)
    record = {'path': path, 'device': metadata.st_dev, 'inode': metadata.st_ino}
    # Capture allocation even if later validation fails, so EXIT cleanup can
    # refuse a substituted path instead of forgetting a partially set-up root.
    print(json.dumps(record, separators=(',', ':')), flush=True)
    with checked_cache(parse_record(json.dumps(record)), uid, gid):
        pass

def verify(record, uid, gid):
    with checked_cache(record, uid, gid):
        pass
    return record['path']

def mount_paths():
    with open('/proc/self/mountinfo') as mounts:
        for line in mounts:
            fields = line.split(' - ', 1)[0].split()
            require(len(fields) >= 6 and ' - ' in line)
            yield fields[4].replace('\\040', ' ').replace('\\011', '\t').replace('\\012', '\n').replace('\\134', '\\')

def remove(record, uid, gid):
    require(shutil.rmtree.avoids_symlink_attacks)
    require(all(path != record['path'] and not path.startswith(record['path'] + '/')
                for path in mount_paths()))
    with checked_cache(record, uid, gid) as (parent, cache, name):
        # Delete only inside the opened, identity-checked allocation. Symlinks
        # are unlinked, never followed. Recheck top-level identity before rmdir.
        for child in os.listdir(cache):
            metadata = os.stat(child, dir_fd=cache, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                shutil.rmtree(child, dir_fd=cache)
            else:
                os.unlink(child, dir_fd=cache)
        validate_metadata(os.stat(name, dir_fd=parent, follow_symlinks=False), record, uid, gid)
        os.rmdir(name, dir_fd=parent)

def main():
    try:
        action, uid, gid, value = sys.argv[1:]
        uid, gid = int(uid), int(gid)
        require(uid > 0 and gid >= 0)
        if action == 'allocate':
            require(value == '')
            allocate(uid, gid)
        elif action == 'verify':
            print(verify(parse_record(value), uid, gid))
        elif action == 'remove':
            remove(parse_record(value), uid, gid)
        else:
            require(False)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('Private native cache guard failed', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
PY
}
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
    if ! python3 - "$drill_output" "$drill_phase" "$drill_status" "$drill_api_exit" "$drill_customer_exit" "$drill_root" <<'PY'
import json, os, re, stat, sys
from pathlib import Path, PurePosixPath
p = Path(sys.argv[1])
log_cache = {}
log_truncated = {}
def log_text(name):
    if name not in log_cache:
        log_cache[name] = ''
        log_truncated[name] = False
        path = p / name
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as handle:
                size = handle.seek(0, 2)
                handle.seek(max(0, size - 65536))
                log_cache[name] = handle.read(65536).decode(errors='replace')
                log_truncated[name] = size > 65536
    return log_cache[name]
def categories(name):
    text = log_text(name)
    markers = ['Permission denied', 'libpython', 'ModuleNotFoundError', 'EACCES', 'Address already in use', 'ERR_MODULE_NOT_FOUND', 'Pydantic', 'ValidationError']
    markers += ['MODULE_NOT_FOUND', 'Cannot find module', 'Cannot find package',
                'ERR_PACKAGE_PATH_NOT_EXPORTED', 'ERR_REQUIRE_ESM', 'ERR_UNKNOWN_FILE_EXTENSION',
                'ERR_DLOPEN_FAILED', 'EPERM', 'ENOENT', 'EADDRINUSE',
                'Failed to load next.config', 'Failed to load SWC binary']
    return [marker for marker in markers if marker in text]
public_modules = {'next', 'react', 'react-dom', 'styled-jsx', 'styled-jsx/style',
                  'typescript', '@next/env', '@swc/helpers', '@serwist/next',
                  'next-intl/plugin', '@vergeo/config', '@vergeo/config/security-headers',
                  '@swc/core', '@swc/core-linux-x64-gnu', '@swc/core-linux-x64-musl',
                  '@vergeo/config/api-base-url', 'next-intl', 'webpack'}
# Output values are literals, never arbitrary source/package filenames or prefixes.
public_chain_paths = {
    'apps/customer/next.config.ts', 'apps/customer/next.config.compiled.js',
    'apps/customer/lib/api-base-url.ts', 'packages/config/src/index.ts',
    'packages/config/src/env.ts', 'packages/config/src/api-base-url.ts',
    'packages/config/src/security-headers.ts',
    'node_modules/next/dist/build/next-config-ts/transpile-config.js',
    'node_modules/next/dist/build/next-config-ts/require-hook.js',
    'node_modules/next/dist/build/swc/index.js', 'node_modules/next/dist/server/config.js',
    'node_modules/next/dist/server/require-hook.js', 'node_modules/next/dist/bin/next',
    'node_modules/@swc/core/index.js', 'node_modules/@swc/core/binding.js',
    'node_modules/next-intl/dist/esm/development/plugin.js',
    'node_modules/next-intl/dist/esm/development/plugin/getNextConfig.js',
    'node_modules/next-intl/dist/esm/production/plugin.js',
    'node_modules/next-intl/dist/esm/production/plugin/getNextConfig.js',
}
def public_relative_path(value):
    if len(sys.argv) <= 6:
        return None
    root = sys.argv[6].rstrip('/')
    if not root.startswith('/') or not value.startswith(root + '/'):
        return None
    alias = value[len(root) + 1:]
    if '\\' in alias or '..' in alias.split('/') or PurePosixPath(alias).as_posix() != alias:
        return None
    if alias in public_chain_paths:
        return alias
    if alias.startswith('node_modules/.pnpm/'):
        for public in sorted(public_chain_paths):
            if public.startswith('node_modules/') and alias.endswith('/' + public):
                return public
    return None
def customer_module_diagnostic():
    match = re.search(r"Cannot find (?:module|package) ['\"]([^'\"]+)['\"]", log_text('private-customer.log'))
    if match is None:
        return None, None, None
    name = match.group(1)
    if name in public_modules:
        return name, 'public_module', None
    if name.startswith('next/dist/'):
        return 'next_internal', 'next_internal', None
    path = public_relative_path(name)
    if path:
        return 'unclassified', 'public_runtime_file', path
    category = 'absolute_request' if name.startswith('/') else 'relative_request' if name.startswith(('./', '../')) else 'unclassified'
    return 'unclassified', category, None
def customer_require_chain():
    paths = []
    stack = False
    for line in log_text('private-customer.log').splitlines():
        line = line.strip()
        if line == 'Require stack:' or line == 'requireStack: [':
            stack = True
            continue
        if not stack:
            continue
        if line.startswith('- '):
            value = line[2:]
        else:
            match = re.fullmatch(r"['\"]([^'\"]+)['\"],?", line)
            if match is None:
                stack = False
                continue
            value = match.group(1)
        path = public_relative_path(value)
        if path and path not in paths:
            paths.append(path)
        if len(paths) == 8:
            break
    return paths
def customer_native_error_summary():
    text = log_text('private-customer.log')
    # Node's inspected Error.cause arrays can contain both a caught relative
    # addon miss and the fatal platform-loader error. Flatten exact code fields;
    # never treat the first MODULE_NOT_FOUND as the final cause or export text.
    native_codes = ('ERR_SWC_NATIVE_FORMAT', 'ERR_SWC_NATIVE_INTEGRITY',
                    'ERR_SWC_NATIVE_COMPRESSION', 'ERR_SWC_NATIVE_CACHE',
                    'ERR_SWC_NATIVE_CONFIGURATION', 'ERR_SWC_NATIVE_LOAD')
    allowed_codes = ('MODULE_NOT_FOUND', 'ERR_MODULE_NOT_FOUND', 'ERR_DLOPEN_FAILED',
                     'EACCES', 'EPERM', 'ENOENT') + native_codes
    observed = set()
    for match in re.finditer(r'''(?<![\w])(?:code|"code"|'code')\s*:\s*(['"])([A-Z][A-Z0-9_]{0,63})\1''', text):
        if match.group(2) in allowed_codes:
            observed.add(match.group(2))
    requests = []
    native_requests = (('./swc.linux-x64-gnu.node', 'swc_linux_x64_gnu_relative'),
                       ('./swc.linux-x64-musl.node', 'swc_linux_x64_musl_relative'))
    for request, category in native_requests:
        pattern = r'''Cannot find (?:module|package) (['"])''' + re.escape(request) + r'''\1'''
        if re.search(pattern, text):
            requests.append(category)
    # Recognize the Node header separately from launcher exit. An Error.cause
    # may be caught by a successful fallback; neither codes nor header alone
    # prove terminal failure or associate a specific code with the final cause.
    binding_error_header = re.search(r'(?m)^[ \t]*(?:[⨯×][ \t]*)?(?:\[cause\]:[ \t]*)?Error: Failed to load native binding(?:[ \t]*\{)?[ \t]*$', text) is not None
    state = ('native_binding_error_header' if binding_error_header else
             'relative_native_missing_attempt' if requests else
             'native_code_without_binding_error_header' if observed.intersection(native_codes) else
             'no_classified_native_evidence')
    return {'format': 'allowlisted_native_error_v1', 'scope': 'bounded_launcher_tail',
            'state': state, 'native_binding_error_header_observed': binding_error_header,
            'customer_launcher_failed': sys.argv[5] in {str(code) for code in range(1, 256)},
            'relative_native_missing_attempts': requests,
            'observed_error_codes': [code for code in allowed_codes if code in observed],
            'observed_native_carrier_codes': [code for code in native_codes if code in observed],
            'tail_truncated': log_truncated.get('private-customer.log', False)}
module, module_category, module_path = customer_module_diagnostic()
native_summary = customer_native_error_summary()
def request_lifecycle():
    # Consume only fixed metadata records after the original owned processes stop.
    # Raw clocks/PIDs/filenames never enter the exported initial-navigation vector.
    roles = {'sdk', 'customer'}
    operations = {'observer', 'pdp', 'compiler', 'product', 'comparison', 'related', 'reviews', 'enquiries'}
    events = {'ready', 'begin', 'settle', 'created', 'sent', 'received', 'headers', 'end', 'finish',
              'error', 'compile_ready', 'compile_begin', 'compile_settled', 'compile_error',
              'observer_error', 'limit'}
    errors = {'none', 'timeout', 'refused', 'reset', 'name_unresolved', 'aborted', 'other'}
    records = []
    invalid = False
    read_failed = False
    sink_failed = False
    files = []
    try:
        with os.scandir(p) as entries:
            for ordinal, entry in enumerate(entries):
                if ordinal >= 64:
                    invalid = True
                    break
                if not entry.name.startswith('private-lifecycle-'):
                    continue
                if entry.name.endswith('.failed'):
                    sink_failed = True
                elif entry.name.endswith('.jsonl'):
                    files.append(Path(entry.path))
    except OSError:
        read_failed = True
    # Discovery remains capped at64 entries and reading at8 files. Inherited
    # customer workers must not crowd out the sole SDK navigation window.
    if len(files) > 8:
        invalid = True
    files.sort(key=lambda filename: (not re.fullmatch(r'private-lifecycle-sdk-[0-9]{1,10}-[0-9]{1,10}\.jsonl', filename.name), filename.name))
    for filename in files[:8]:
        descriptor = None
        try:
            match = re.fullmatch(r'private-lifecycle-(sdk|customer)-[0-9]{1,10}-[0-9]{1,10}\.jsonl', filename.name)
            if match is None:
                invalid = True
                continue
            before = filename.lstat()
            if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600 or
                    before.st_uid != os.getuid() or before.st_nlink != 1 or before.st_size > 8192):
                invalid = True
                continue
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            current = os.fstat(descriptor)
            if (not stat.S_ISREG(current.st_mode) or stat.S_IMODE(current.st_mode) != 0o600 or
                    current.st_uid != os.getuid() or current.st_nlink != 1 or
                    (current.st_dev, current.st_ino, current.st_size) != (before.st_dev, before.st_ino, before.st_size)):
                invalid = True
                continue
            content = os.read(descriptor, 8193)
            if len(content) > 8192:
                invalid = True
                continue
            rows = content.decode('utf-8').splitlines()
            if len(rows) > 32:
                invalid = True
            previous = -1
            for line in rows[:32]:
                item = json.loads(line)
                if (type(item) is not dict or set(item) != {'version', 'role', 'operation', 'event', 'error', 'time'} or
                        type(item['version']) is not int or item['version'] != 1 or
                        type(item['role']) is not str or item['role'] not in roles or item['role'] != match[1] or
                        type(item['operation']) is not str or item['operation'] not in operations or
                        type(item['event']) is not str or item['event'] not in events or
                        type(item['error']) is not str or item['error'] not in errors or
                        type(item['time']) is not int or not 0 <= item['time'] <= 9007199254740991 or
                        item['time'] < previous):
                    invalid = True
                    continue
                previous = item['time']
                records.append(item)
        except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
            read_failed = True
        finally:
            if descriptor is not None:
                os.close(descriptor)
    starts = [r['time'] for r in records if (r['role'], r['operation'], r['event']) == ('sdk', 'pdp', 'begin')]
    ends = [r['time'] for r in records if (r['role'], r['operation'], r['event']) == ('sdk', 'pdp', 'settle')]
    window = len(starts) == len(ends) == 1 and 0 <= ends[0] - starts[0] <= 180000000
    selected = [r for r in records if window and starts[0] <= r['time'] <= ends[0]]
    def count(role, operation, event):
        return sum((r['role'], r['operation'], r['event']) == (role, operation, event) for r in selected)
    def first(role, operation, event):
        values = [r['time'] for r in selected if (r['role'], r['operation'], r['event']) == (role, operation, event)]
        return (min(values) - starts[0]) // 1000 if values else None
    ready = {role: any(r['role'] == role and r['operation'] == 'observer' and r['event'] == 'ready' for r in records) for role in roles}
    compiler_ready = any(r['role'] == 'customer' and r['operation'] == 'compiler' and r['event'] == 'compile_ready' for r in records)
    limited = any(r['event'] == 'limit' for r in records)
    observer_error = any(r['event'] == 'observer_error' for r in selected)
    coverage = ('unavailable' if not records and not (invalid or read_failed or sink_failed) else 'bounded' if window and all(ready.values()) and compiler_ready and not (invalid or read_failed or sink_failed or limited or observer_error) else 'incomplete')
    if not records and not (invalid or read_failed or sink_failed):
        return {'format': 'cart_request_lifecycle_v1', 'scope': 'initial_seeded_pdp_only', 'coverage': 'unavailable'}
    sdk_error = next((r['error'] for r in selected if r['role'] == 'sdk' and r['operation'] == 'pdp' and r['event'] == 'error'), 'none')
    data = {}
    for operation in ('product', 'comparison', 'related', 'reviews', 'enquiries'):
        started = count('customer', operation, 'created')
        ended = count('customer', operation, 'end')
        failed = count('customer', operation, 'error')
        data[operation] = {'started': started, 'headers': count('customer', operation, 'headers'),
                           'body_end': ended, 'errors': failed, 'pending': max(0, started - ended - failed),
                           'first_start_ms': first('customer', operation, 'created'),
                           'first_headers_ms': first('customer', operation, 'headers'),
                           'first_body_end_ms': first('customer', operation, 'end')}
    compile_started = count('customer', 'compiler', 'compile_begin')
    compile_settled = count('customer', 'compiler', 'compile_settled')
    compile_failed = count('customer', 'compiler', 'compile_error')
    return {'format': 'cart_request_lifecycle_v1', 'scope': 'initial_seeded_pdp_only',
            'coverage': coverage, 'invalid_records': invalid, 'read_failed': read_failed, 'sink_failed': sink_failed,
            'record_limit': limited, 'observer_error': observer_error,
            'window_ms': (ends[0] - starts[0]) // 1000 if window else None,
            'sdk': {'observer_ready': ready['sdk'], 'created': count('sdk', 'pdp', 'created'),
                    'body_scope': 'http_incoming_message_end',
                    'sent': count('sdk', 'pdp', 'sent'), 'headers': count('sdk', 'pdp', 'headers'),
                    'body_end': count('sdk', 'pdp', 'end'), 'error': sdk_error,
                    'first_headers_ms': first('sdk', 'pdp', 'headers'),
                    'first_body_end_ms': first('sdk', 'pdp', 'end')},
            'customer': {'observer_ready': ready['customer'], 'received': count('customer', 'pdp', 'received'),
                         'finished': count('customer', 'pdp', 'finish'),
                         'first_received_ms': first('customer', 'pdp', 'received'),
                         'first_finish_ms': first('customer', 'pdp', 'finish')},
            'compiler': {'observer_ready': compiler_ready, 'started': compile_started,
                         'scope': 'ensure_page_entry_and_settlement_including_rejections_and_cache_hits',
                         'settled': compile_settled, 'synchronous_errors': compile_failed,
                         'pending': max(0, compile_started - compile_settled - compile_failed),
                         'first_start_ms': first('customer', 'compiler', 'compile_begin'),
                         'first_settled_ms': first('customer', 'compiler', 'compile_settled')},
            'ssr_data': data}

d = {'phase': sys.argv[2], 'exit': int(sys.argv[3]), 'api_log_categories': categories('private-api.log'),
     'api_launcher_status': sys.argv[4], 'customer_launcher_status': sys.argv[5],
     'python_probe_categories': categories('private-python-probe.log'),
     'customer_log_categories': categories('private-customer.log'),
     'customer_missing_module': module, 'customer_missing_module_category': module_category,
     'customer_missing_relative_path': module_path, 'customer_require_chain': customer_require_chain(),
     'customer_require_chain_format': 'allowlisted_public_module_relative_v1',
     'customer_native_error_summary': native_summary,
     'customer_log_tail_truncated': log_truncated.get('private-customer.log', False),
     'raw_logs_retained_privately_only': True}
d['request_lifecycle'] = request_lifecycle()
try:
    health = json.loads((p / 'private-health-probe.json').read_text())
    assert isinstance(health, list) and len(health) == 2
    assert {row['name'] for row in health} == {'api', 'customer'}
    assert all(type(row['ok']) is bool for row in health)
    d['latest_health'] = [{'name': row['name'], 'ok': row['ok']} for row in health]
except (OSError, ValueError, TypeError, KeyError, AssertionError):
    d['health_evidence'] = 'unavailable_or_malformed'
(p / 'diagnostics.json').write_text(json.dumps(d, indent=2) + '\n')
# Only this finite literal schema goes to the ordinary job log. Raw launcher
# logs, messages, paths, env and cause arrays remain private.
print('cart-drill-native-error-summary: ' + json.dumps(native_summary, separators=(',', ':')))
PY
    then drill_cleanup_ok=false; fi
  fi
  if [ "$drill_swc_cache_requested" = true ]; then
    if [ "$drill_cleanup_ok" = true ] && [ -n "$drill_swc_cache_record" ]; then
      # Only pgrep's explicit no-process status permits cache deletion. Errors
      # and live processes retain the account/resources and fail cleanup.
      if sudo pgrep -u "$drill_uid" >/dev/null; then drill_cleanup_ok=false
      else
        if [ "$?" -eq 1 ]; then
          if ! drill_native_cache remove; then drill_cleanup_ok=false; fi
        else drill_cleanup_ok=false; fi
      fi
    else drill_cleanup_ok=false; fi
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
  local drill_workdir="$drill_root"
  local drill_lifecycle_role=none
  if [ "${1:-}" = --customer-project ]; then
    drill_workdir="$drill_root/apps/customer"
    drill_lifecycle_role=customer
    shift
  elif [ "${1:-}" = "$drill_node" ] && [ "${2:-}" = --require ] && \
       [ "${3:-}" = "$drill_root/scripts/qa/cart-response-drill-lifecycle.cjs" ] && \
       [ "${4:-}" = "$drill_root/e2e/scripts/cart-response-drill.mjs" ]; then
    drill_lifecycle_role=sdk
  fi
  (
  cd "$drill_workdir"
  sudo -u cartdrill env -i PATH=/usr/bin:/bin CART_DRILL_LOCAL=1 CART_DRILL_UID="$drill_uid" \
    CART_DRILL_LIFECYCLE_ROLE="$drill_lifecycle_role" \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$drill_package_root/tmp" XDG_CACHE_HOME="$drill_package_root/cache" XDG_CONFIG_HOME="$drill_package_root/config" \
    SWC_NATIVE_BINDING_CACHE="$drill_swc_cache_root" \
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
drill_gid=$(id -g cartdrill)
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
drill_phase=native_cache_preflight
drill_swc_cache_requested=true
drill_swc_cache_record=$(drill_native_cache allocate)
drill_swc_cache_root=$(drill_native_cache verify)
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
drill_as_user --customer-project "$drill_node" --require "$drill_root/scripts/qa/cart-response-drill-lifecycle.cjs" "$drill_root/apps/customer/node_modules/next/dist/bin/next" dev "$drill_root/apps/customer" --hostname 127.0.0.1 --port 3000 > "$drill_output/private-customer.log" 2>&1 &
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
drill_as_user "$drill_node" --require "$drill_root/scripts/qa/cart-response-drill-lifecycle.cjs" "$drill_root/e2e/scripts/cart-response-drill.mjs"
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

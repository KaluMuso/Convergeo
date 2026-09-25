"""One-use exact-payload importer. Stores blobs only; never changes refs."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.error
import urllib.request
import zlib

REPO = 'KaluMuso/Convergeo'
BRANCH = 'hardening/20260925-ci-recovery'
BASE = '8f745dd1e51ce217f81329748e967c9e5f373ce9'
BASE_TREE = 'c2fcf1e33c8ef5ba688f28dbdef321a42c3bfc8f'
PATCH_SHA256 = '361c8184a3e55d6d4d66a1f5dc1d23481b8730b96c9b9a43093dea4a59996da1'
REPORTED_TREE = '604215b6c92498877764237b254ea0fc30601ffa'
PATHS = sorted([
    '.github/workflows/ci.yml', 'apps/admin/vercel.json',
    'apps/customer/vercel.json', 'apps/vendor/vercel.json',
    'scripts/ci/migration-replay.sh', 'scripts/ci/prefetch-postgres-meta.sh',
    'scripts/ci/verify-postgres-runtime.sh', 'scripts/gen-types.sh',
    'services/api/tests/fixtures/demo/entities.json',
    'services/api/tests/fixtures/demo/ids.json',
    'services/api/tests/rls/conftest.py', 'services/api/tests/rls/test_matrix.py',
    'services/api/tests/test_ci_database_helpers.py',
    'services/api/tests/test_reconcile_staging_migrations.py',
    'services/api/tests/test_schema_convergence.py', 'vercel.json',
])

def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()

def main() -> None:
    if os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise RuntimeError('Unexpected repository')
    if os.environ.get('GITHUB_REF') != f'refs/heads/{BRANCH}':
        raise RuntimeError('Unexpected source ref')
    seed = os.environ['GITHUB_SHA']
    if git('rev-parse', 'HEAD') != seed:
        raise RuntimeError('Checkout does not match push event')
    if git('rev-parse', f'{BASE}^{{tree}}') != BASE_TREE:
        raise RuntimeError('Base tree mismatch')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, seed], check=True)
    compressed = base64.b64decode(Path('.ci-recovery-transport/payload.b64').read_text().strip(), validate=True)
    decoder = zlib.decompressobj(wbits=31)
    patch = decoder.decompress(compressed, 100_001)
    if not decoder.eof or decoder.unused_data or len(patch) != 39_034:
        raise RuntimeError('Unexpected compressed payload')
    if hashlib.sha256(patch).hexdigest() != PATCH_SHA256:
        raise RuntimeError('Patch SHA-256 mismatch')
    out = Path(os.environ['RUNNER_TEMP']) / 'ci-recovery-export'
    out.mkdir(exist_ok=True)
    patch_path = out / 'convergeo-ci-recovery.patch'
    patch_path.write_bytes(patch)
    work = Path(os.environ['RUNNER_TEMP']) / 'ci-recovery-applied'
    subprocess.run(['git', 'worktree', 'add', '--detach', str(work), BASE], check=True)
    subprocess.run(['git', '-C', str(work), 'apply', '--check', '--index', str(patch_path)], check=True)
    subprocess.run(['git', '-C', str(work), 'apply', '--index', '--whitespace=error-all', str(patch_path)], check=True)
    if sorted(git('diff', '--cached', '--name-only', cwd=work).splitlines()) != PATHS:
        raise RuntimeError('Changed-path inventory mismatch')
    subprocess.run(['git', '-C', str(work), 'diff', '--cached', '--check'], check=True)
    tree = git('write-tree', cwd=work)
    files = []
    for name in PATHS:
        p = work / name
        if p.is_symlink() or not p.is_file():
            raise RuntimeError(f'Not a regular source file: {name}')
        data = p.read_bytes()
        mode, blob, _ = git('ls-files', '--stage', '--', name, cwd=work).split(maxsplit=2)
        if mode not in {'100644', '100755'}:
            raise RuntimeError('Unexpected file mode')
        files.append({'path': name, 'mode': mode, 'type': 'blob', 'sha': blob,
                      'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    for name in ['vercel.json', 'apps/customer/vercel.json', 'apps/vendor/vercel.json', 'apps/admin/vercel.json']:
        guards = json.loads((work / name).read_text())['git']['deploymentEnabled']
        if guards.get(BRANCH) is not False or guards.get('hardening/20260924-converged-implementation') is not False:
            raise RuntimeError('Missing deployment guard')
    manifest = {'source_base': BASE, 'source_base_tree': BASE_TREE,
                'transport_seed': seed, 'patch_sha256': PATCH_SHA256,
                'computed_tree': tree, 'reported_tree': REPORTED_TREE,
                'matches_reported_tree': tree == REPORTED_TREE,
                'changed_files': files, 'application_tests': 'NOT_RUN',
                'workflow_run_id': os.environ['GITHUB_RUN_ID']}
    (out / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with tarfile.open(out / 'applied-files.tar.gz', 'w:gz') as archive:
        for name in PATHS:
            archive.add(work / name, arcname=name, recursive=False)
    print('VERIFIED_IMPORT_MANIFEST=' + json.dumps(manifest), flush=True)
    uploaded = []
    try:
        for entry in files:
            data = (work / entry['path']).read_bytes()
            body = json.dumps({'encoding': 'base64', 'content': base64.b64encode(data).decode()}).encode()
            request = urllib.request.Request(
                f'https://api.github.com/repos/{REPO}/git/blobs', data=body, method='POST',
                headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                         'Accept': 'application/vnd.github+json',
                         'X-GitHub-Api-Version': '2022-11-28',
                         'User-Agent': 'convergeo-exact-patch-import',
                         'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=60) as response:
                remote = json.load(response)
            if remote.get('sha') != entry['sha']:
                raise RuntimeError('Uploaded blob hash mismatch')
            uploaded.append({'path': entry['path'], 'sha': remote['sha']})
            print('VERIFIED_REMOTE_BLOB=' + json.dumps(uploaded[-1]), flush=True)
    except urllib.error.HTTPError as error:
        print('BLOB_API_FAILURE=' + error.read(4096).decode('utf-8', errors='replace'), flush=True)
        raise
    finally:
        (out / 'uploaded-blobs.json').write_text(json.dumps(uploaded, indent=2) + '\n')
        lines = [hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name
                 for p in sorted(out.iterdir()) if p.is_file() and p.name != 'SHA256SUMS']
        (out / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(f'Exact patch applied: `{tree}`; all 16 blobs verified.\n\n')
        summary.write('No tree, commit, ref, database, deployment or money action. '
                      'Final tree/ref publication remains with the authorized MCP.\n')

if __name__ == '__main__':
    main()

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import test from "node:test";
import { URL } from "node:url";

const workflow = readFileSync(new URL("../../.github/workflows/ci.yml", import.meta.url), "utf8");

function job(source, id) {
  const match = source.match(
    new RegExp(`^  ${id}:\\n[\\s\\S]*?(?=^  [a-z0-9-]+:\\n|$(?![\\s\\S]))`, "m"),
  );
  assert.ok(match, `Missing ${id} job`);
  return match[0];
}

function step(block, name) {
  const steps = block.split(/(?=^ {6}- name: )/m);
  const matches = steps.filter((item) => item.startsWith(`      - name: ${name}\n`));
  assert.equal(matches.length, 1, `Expected one ${name} step`);
  return matches[0];
}

const auditCommands = new Map([
  ["pnpm production audit (fail on high)", "pnpm audit --prod --audit-level high"],
  ["pnpm full dependency audit (fail on high)", "pnpm audit --audit-level high"],
]);

function assertStrictAudit(source) {
  const audit = job(source, "deps-audit");
  assert.match(audit, /^ {4}name: Dependency audit$/m);
  assert.doesNotMatch(audit, /^\s+(?:if|continue-on-error):/m);
  assert.doesNotMatch(audit, /ALLOWLIST|github_advisory_id|--ignore|\|\|\s*true/);
  assert.equal((audit.match(/run: pnpm audit /g) ?? []).length, 2);
  for (const [name, command] of auditCommands) {
    // Exact step contents prohibit shell/exit-status suppression and threshold drift.
    const content = step(audit, name)
      .replace(/^ {8}#.*\n/gm, "")
      .trimEnd();
    assert.equal(content, `      - name: ${name}\n        run: ${command}`);
  }
  const contract = step(audit, "Dependency audit workflow contract tests");
  assert.match(contract, /run: node --test scripts\/ci\/dependency-audit-contract\.test\.mjs/);
  assert.ok(audit.indexOf(contract) < audit.indexOf("      - name: pnpm production audit"));
  assert.match(audit, /run: pnpm i --frozen-lockfile/);
  const api = step(audit, "pip-audit (API, fail on high)");
  const shell = apiShell(api).replace(/[ \t]*\\\n[ \t]*/g, " ");
  assert.match(api, /^ {8}working-directory: services\/api$/m);
  assert.match(shell, /^set -euo pipefail$/m);
  assert.match(shell, /^uv sync --locked --all-groups --no-install-project$/m);
  assert.match(
    shell,
    /^uv export --locked --all-groups --no-emit-project --no-hashes --format requirements-txt --output-file api-audit-requirements\.txt$/m,
  );
  assert.match(shell, /^IFS= read -r API_AUDIT_SITE < api-audit-site\.txt$/m);
  assert.match(shell, /^test -n "\$API_AUDIT_SITE"$/m);
  assert.match(shell, /^test -d "\$API_AUDIT_SITE"$/m);
  assert.match(shell, /^\.venv\/bin\/python - "\$API_AUDIT_SITE" <<'PY'$/m);
  assert.match(
    shell,
    /^uv tool run --from pip-audit==2\.10\.1 pip-audit --path "\$API_AUDIT_SITE" --strict --format json --progress-spinner off \| tee api-audit\.json$/m,
  );
  assert.doesNotMatch(shell, /--(?:ignore|skip|fix)|\|\||set \+|^exit 0$/m);
  assert.equal((shell.match(/^uv tool run /gm) ?? []).length, 1);
  assert.equal((shell.match(/^sha256sum --check api-audit-inputs\.sha256$/gm) ?? []).length, 2);
}

function apiShell(block = step(job(workflow, "deps-audit"), "pip-audit (API, fail on high)")) {
  const shell = block.split("        run: |\n")[1];
  assert.ok(shell, "Missing API shell block");
  return shell.trimEnd().replace(/^ {10}/gm, "") + "\n";
}

test("both audit scopes and API audit are mandatory without advisory waivers", () => {
  assertStrictAudit(workflow);
});

const regressions = [
  [
    "missing production scope",
    (source) =>
      source.replace("pnpm audit --prod --audit-level high", "pnpm audit --audit-level high"),
  ],
  [
    "lowered severity gate",
    (source) =>
      source.replace(
        "pnpm audit --prod --audit-level high",
        "pnpm audit --prod --audit-level critical",
      ),
  ],
  [
    "suppressed command failure",
    (source) =>
      source.replace("pnpm audit --audit-level high", "pnpm audit --audit-level high || true"),
  ],
  [
    "advisory allowlist",
    (source) =>
      source.replace(
        "pnpm audit --audit-level high",
        "pnpm audit --audit-level high --ignore GHSA-ph9p-34f9-6g65",
      ),
  ],
  [
    "optional job",
    (source) => source.replace("  deps-audit:\n", "  deps-audit:\n    continue-on-error: true\n"),
  ],
  [
    "conditional audit step",
    (source) =>
      source.replace(
        "      - name: pnpm production audit (fail on high)\n",
        "      - name: pnpm production audit (fail on high)\n        if: false\n",
      ),
  ],
];
for (const [name, mutate] of regressions) {
  test(`rejects regression: ${name}`, () =>
    assert.throws(() => assertStrictAudit(mutate(workflow))));
}

for (const [name, command] of auditCommands) {
  test(`${name} propagates successful, advisory and infrastructure exit statuses`, () => {
    // Execute the real workflow command with a local pnpm stub. No install,
    // registry/advisory request or real dependency audit occurs in this test.
    const directory = mkdtempSync(join(tmpdir(), "dependency-audit-contract-"));
    try {
      writeFileSync(
        join(directory, "pnpm"),
        '#!/bin/bash\nprintf "%s\\n" "$@" > "$AUDIT_TEST_ARGS"\nexit "$AUDIT_TEST_EXIT"\n',
        { mode: 0o700 },
      );
      for (const exitCode of [0, 1, 2, 17]) {
        const result = spawnSync(
          "/bin/bash",
          ["--noprofile", "--norc", "-eo", "pipefail", "-c", command],
          {
            env: {
              PATH: directory,
              AUDIT_TEST_ARGS: join(directory, "args"),
              AUDIT_TEST_EXIT: String(exitCode),
            },
            encoding: "utf8",
          },
        );
        assert.equal(result.error, undefined);
        assert.equal(result.status, exitCode, result.stderr);
        assert.deepEqual(
          readFileSync(join(directory, "args"), "utf8").trimEnd().split("\n"),
          command.split(" ").slice(1),
        );
      }
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
}

// Execute the real workflow shell and embedded Python against disposable metadata.
// uv, the auditor, interpreter discovery and packaging's synthetic-input parser
// are doubles. The exact coverage checks use real metadata and filesystem reads.
// Python -S proves these fixtures need no preinstalled third-party modules before
// CI's Setup Python step. Real packaging/export compatibility is qualified apart.
let python;
function fixture(mode) {
  if (!python) {
    const result = spawnSync(
      process.env.API_AUDIT_TEST_PYTHON ?? "python3",
      ["-S", "-c", "import sys; print(sys.executable)"],
      { encoding: "utf8", env: { PATH: process.env.PATH } },
    );
    assert.equal(result.status, 0, result.stderr);
    python = result.stdout.trim();
    assert.ok(python.startsWith("/") && !python.includes("\n"));
  }
  const root = mkdtempSync(join(tmpdir(), "api-audit-contract-"));
  const bin = join(root, "bin"),
    prefix = join(root, ".venv");
  const site = join(prefix, "lib", "site-packages");
  mkdirSync(bin);
  mkdirSync(join(prefix, "bin"), { recursive: true });
  mkdirSync(site, { recursive: true });
  mkdirSync(join(prefix, "other-site"));
  mkdirSync(join(root, "foreign-site"));
  const packages = Object.fromEntries(
    Array.from({ length: 63 }, (_, i) => [`fixture-${String(i).padStart(2, "0")}`, "1.0"]),
  );
  const metadata = (name, version, suffix = "") => {
    const path = join(site, `${name}${suffix}-${version}.dist-info`);
    mkdirSync(path);
    writeFileSync(
      join(path, "METADATA"),
      `Metadata-Version: 2.1\nName: ${name}\nVersion: ${version}\n`,
    );
  };
  for (const [name, version] of Object.entries(packages)) metadata(name, version);
  const registry = { ...packages, colorama: "1.0", tzdata: "1.0" };
  let requirements = Object.entries(packages).map(([n, v]) => `${n}==${v}`);
  requirements.push('colorama==1.0; sys_platform == "win32"', 'tzdata==1.0; python_version < "0"');
  if (mode === "empty-export") requirements = [];
  if (mode === "missing-export") requirements.shift();
  if (mode === "duplicate-export") requirements.push(requirements[0]);
  if (mode === "wrong-export-version") requirements[0] = "fixture-00==2.0";
  if (mode === "unpinned-export") requirements[0] = "fixture-00>=1.0";
  if (mode === "url-export") requirements[0] = "fixture-00 @ https://invalid.example/package.whl";
  if (mode === "wrong-marker") requirements[0] += '; python_version < "0"';
  if (mode === "empty-installed")
    for (const name of Object.keys(packages))
      rmSync(join(site, `${name}-1.0.dist-info`), { recursive: true });
  if (mode === "missing-installed")
    rmSync(join(site, "fixture-00-1.0.dist-info"), { recursive: true });
  if (mode === "extra-installed") metadata("extra", "1.0");
  if (mode === "duplicate-installed") metadata("fixture-00", "1.0", "-duplicate");
  if (mode === "wrong-installed-version")
    writeFileSync(
      join(site, "fixture-00-1.0.dist-info", "METADATA"),
      "Name: fixture-00\nVersion: 2.0\n",
    );
  writeFileSync(join(root, "pyproject.toml"), '[project]\nname = "fixture"\nversion = "1.0"\n');
  writeFileSync(
    join(root, "uv.lock"),
    Object.entries(registry)
      .map(
        ([name, version]) =>
          `[[package]]\nname = "${name}"\nversion = "${version}"\nsource = { registry = "https://invalid.example/simple" }\n`,
      )
      .join("\n"),
  );
  writeFileSync(join(root, "export-source"), requirements.join("\n") + "\n");
  const report = {
    dependencies: Object.entries(packages).map(([name, version]) => ({ name, version, vulns: [] })),
    fixes: [],
  };
  if (mode === "missing-report-package") report.dependencies.shift();
  if (mode === "extra-report-package")
    report.dependencies.push({ name: "extra", version: "1.0", vulns: [] });
  if (mode === "duplicate-report-package") report.dependencies.push(report.dependencies[0]);
  if (mode === "wrong-report-version") report.dependencies[0].version = "2.0";
  if (mode === "skipped-report-package")
    report.dependencies[0].skip_reason = "fixture collection failure";
  if (mode === "vulnerable-success-report")
    report.dependencies[0].vulns = [{ id: "FIXTURE-ADVISORY" }];
  if (mode === "missing-vulns") delete report.dependencies[0].vulns;
  if (mode === "unexpected-fixes") report.fixes.push({ name: "fixture-00" });
  if (mode === "empty-report-inventory") report.dependencies = [];
  const reportText =
    mode === "invalid-json-report"
      ? "invalid"
      : mode === "empty-report"
        ? ""
        : JSON.stringify(report) + "\n";
  writeFileSync(join(root, "report-source"), reportText);
  writeFileSync(
    join(bin, "uv"),
    `#!/bin/bash
set -eu
printf '%s\\n' "$1" >> events
case "$1" in
  sync)
    if [[ "$AUDIT_TEST_MODE" == sync-failure ]]; then exit 9; fi
    if [[ "$AUDIT_TEST_MODE" == changed-input ]]; then printf '\\n# changed\\n' >> uv.lock; fi
    ;;
  export)
    if [[ "$AUDIT_TEST_MODE" == export-failure ]]; then exit 11; fi
    /bin/cp export-source api-audit-requirements.txt
    ;;
  tool)
    printf '%s\\n' "$@" > auditor-args
    /bin/cat report-source
    exit "$AUDIT_TEST_EXIT"
    ;;
  *) exit 97 ;;
esac
`,
    { mode: 0o700 },
  );
  writeFileSync(
    join(prefix, "bin", "python"),
    `#!${python} -S
import os, re, sys, sysconfig, types
from pathlib import Path
# Narrow doubles for this fixture grammar, not a replacement production parser.
class Marker:
    def __init__(self, text):
        self.text = text.strip()
    def evaluate(self):
        if self.text == 'sys_platform == "win32"': return sys.platform == 'win32'
        if self.text == 'python_version < "0"': return False
        raise ValueError('Unsupported synthetic marker')
class Requirement:
    def __init__(self, text):
        requirement, separator, marker = text.partition(';')
        self.marker = Marker(marker) if separator else None
        self.url = requirement if '@' in requirement else None
        self.specifier = []
        self.name = 'fixture-url' if self.url else None
        if not self.url:
            match = re.fullmatch('([a-zA-Z0-9_.-]+)(==|>=)([a-zA-Z0-9.]+)', requirement.strip())
            if not match: raise ValueError('Unsupported synthetic requirement')
            self.name, operator, version = match.groups()
            self.specifier = [types.SimpleNamespace(operator=operator, version=version)]
for module in ('packaging', 'packaging.requirements', 'packaging.utils'):
    sys.modules[module] = types.ModuleType(module)
sys.modules['packaging.requirements'].Requirement = Requirement
sys.modules['packaging.utils'].canonicalize_name = lambda value: re.sub('[-_.]+', '-', value).lower()
root = Path.cwd()
mode = os.environ['AUDIT_TEST_MODE']
code = sys.stdin.read()
stage = 'preflight' if 'import hashlib' in code else 'report' if 'report = ' in code else 'path'
with Path('events').open('a') as f:
    f.write(stage + '\\n')
if stage == 'preflight' and mode == 'path-resolution-failure':
    raise SystemExit(19)
sys.argv = sys.argv[1:]
sys.prefix = str(root / ('wrong-prefix' if mode == 'wrong-interpreter' else '.venv'))
original = sysconfig.get_path
def get_path(key, *args, **kwargs):
    if key not in ('purelib', 'platlib'):
        return original(key, *args, **kwargs)
    if mode == 'foreign-site':
        return str(root / 'foreign-site')
    if mode == 'missing-site':
        return str(root / '.venv' / 'missing')
    if key == 'platlib' and mode == 'split-site':
        return str(root / '.venv' / 'other-site')
    return str(root / '.venv' / 'lib' / 'site-packages')
sysconfig.get_path = get_path
exec(compile(code, '<exact-workflow-' + stage + '>', 'exec'))
if stage == 'preflight':
    path = Path('api-audit-site.txt')
    if mode == 'missing-path-file': path.unlink()
    if mode == 'empty-path': path.write_text('\\n')
    if mode == 'nonexistent-path': path.write_text(str(root / 'missing') + '\\n')
    if mode == 'foreign-path': path.write_text(str(root / 'foreign-site') + '\\n')
    if mode == 'unbound-path': path.write_text(str(root / '.venv' / 'other-site') + '\\n')
if stage == 'report' and mode == 'late-input-change':
    with Path('uv.lock').open('a') as f: f.write('\\n# changed late\\n')
`,
    { mode: 0o700 },
  );
  if (mode === "symlink-environment") {
    cpSync(prefix, join(root, "other-env"), { recursive: true });
    rmSync(prefix, { recursive: true });
    symlinkSync(join(root, "other-env"), prefix, "dir");
  }
  if (mode === "missing-interpreter") rmSync(join(prefix, "bin", "python"));
  return { root, site };
}

function executeApi(mode = "pass", exit = 0, shell = apiShell(), optimize = false) {
  const { root, site } = fixture(mode);
  try {
    const result = spawnSync("/bin/bash", ["--noprofile", "--norc", "-c", shell], {
      cwd: root,
      encoding: "utf8",
      timeout: 15000,
      env: {
        PATH: `${join(root, "bin")}:/usr/bin:/bin`,
        LANG: "C.UTF-8",
        GITHUB_SHA: "a".repeat(40),
        AUDIT_TEST_MODE: mode,
        AUDIT_TEST_EXIT: String(exit),
        PYTHONOPTIMIZE: optimize ? "1" : "0",
        PYTHONDONTWRITEBYTECODE: "1",
      },
    });
    assert.equal(result.error, undefined);
    const events = readFileSync(join(root, "events"), "utf8").trim().split("\n");
    const args = events.includes("tool")
      ? readFileSync(join(root, "auditor-args"), "utf8").trim().split("\n")
      : [];
    return { ...result, events, args, site };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test("API audit binds all 63 installed distributions to the 65-record locked export", () => {
  const result = executeApi();
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.events, ["sync", "export", "preflight", "path", "tool", "report"]);
  assert.deepEqual(result.args, [
    "tool",
    "run",
    "--from",
    "pip-audit==2.10.1",
    "pip-audit",
    "--path",
    result.site,
    "--strict",
    "--format",
    "json",
    "--progress-spinner",
    "off",
  ]);
  const verified = JSON.parse(
    result.stdout
      .trim()
      .split("\n")
      .find((line) => line.startsWith('{"coverage":')),
  );
  assert.equal(verified.verifiedAuditCount, 63);
  assert.equal(verified.coverage.registryCount, 65);
  assert.deepEqual(verified.coverage.inactive, ["colorama", "tzdata"]);
});

for (const exit of [1, 2, 17])
  test(`API auditor exit ${exit} propagates through tee`, () => {
    const result = executeApi("pass", exit);
    assert.equal(result.status, exit, result.stderr);
    assert.ok(result.events.includes("tool"));
    assert.ok(!result.events.includes("report"));
  });

const preflightFailures = [
  "sync-failure",
  "export-failure",
  "changed-input",
  "path-resolution-failure",
  "wrong-interpreter",
  "foreign-site",
  "missing-site",
  "split-site",
  "symlink-environment",
  "missing-interpreter",
  "empty-export",
  "missing-export",
  "duplicate-export",
  "wrong-export-version",
  "unpinned-export",
  "url-export",
  "wrong-marker",
  "empty-installed",
  "missing-installed",
  "extra-installed",
  "duplicate-installed",
  "wrong-installed-version",
  "missing-path-file",
  "empty-path",
  "nonexistent-path",
  "foreign-path",
  "unbound-path",
];
for (const mode of preflightFailures)
  test(`API rejects ${mode} before auditing`, () => {
    const result = executeApi(mode);
    assert.notEqual(result.status, 0, result.stdout);
    const expected = { "sync-failure": 9, "export-failure": 11, "path-resolution-failure": 19 }[
      mode
    ];
    if (expected) assert.equal(result.status, expected, result.stderr);
    assert.ok(!result.events.includes("tool"), result.events.join(","));
  });
for (const mode of [
  "missing-report-package",
  "extra-report-package",
  "duplicate-report-package",
  "wrong-report-version",
  "skipped-report-package",
  "vulnerable-success-report",
  "missing-vulns",
  "unexpected-fixes",
  "empty-report-inventory",
  "invalid-json-report",
  "empty-report",
  "late-input-change",
])
  test(`API rejects ${mode} despite auditor success`, () => {
    const result = executeApi(mode);
    assert.notEqual(result.status, 0, result.stdout);
    assert.ok(result.events.includes("tool"));
  });
for (const mode of [
  "foreign-site",
  "empty-path",
  "unbound-path",
  "missing-installed",
  "missing-report-package",
  "vulnerable-success-report",
])
  test(`API rejects ${mode} with Python optimization enabled`, () => {
    assert.notEqual(executeApi(mode, 0, apiShell(), true).status, 0);
  });

for (const [name, before, after] of [
  [
    "bare tool environment",
    "uv tool run --from pip-audit==2.10.1 pip-audit \\\n",
    "uv tool run pip-audit \\\n",
  ],
  ["missing explicit target", '--path "$API_AUDIT_SITE" ', ""],
  ["empty target", '--path "$API_AUDIT_SITE"', '--path ""'],
  ["foreign target", '--path "$API_AUDIT_SITE"', "--path /tool/environment"],
  ["missing strict collection", "--strict ", ""],
  ["advisory exclusion", "--strict --format", "--strict --ignore-vuln FIXTURE --format"],
  ["collection waiver", "--strict --format", "--strict --skip-editable --format"],
  ["unlocked sync", "sync --locked", "sync"],
  ["unlocked export", "export --locked", "export"],
  ["reduced groups", "sync --locked --all-groups", "sync --locked --dev"],
  ["installed project", " --no-install-project", ""],
  ["exported project", " --no-emit-project", ""],
  ["suppressed audit exit", "| tee api-audit.json", "| tee api-audit.json || true"],
  ["lost pipeline failure", "set -euo pipefail", "set -eu"],
])
  test(`API workflow contract rejects ${name}`, () => {
    const api = step(job(workflow, "deps-audit"), "pip-audit (API, fail on high)");
    assert.ok(api.includes(before), `Missing mutation anchor: ${name}`);
    assert.throws(() => assertStrictAudit(workflow.replace(api, api.replace(before, after))));
  });

test("secret scan stays blocking, pinned, redacted and includes its boundary tests", () => {
  const scanner = job(workflow, "secret-scan");
  assert.doesNotMatch(scanner, /^\s+(?:if|continue-on-error):/m);
  assert.match(scanner, /GITLEAKS_VERSION: "8\.28\.0"/);
  assert.match(
    step(scanner, "Self-test scanner catches planted secret"),
    /run: bash scripts\/ci\/gitleaks-self-test\.sh/,
  );
  assert.match(
    step(scanner, "Validate n8n workflows have no plaintext secrets"),
    /run: bash scripts\/ci\/validate-n8n-no-plaintext-secrets\.sh/,
  );
  assert.equal(
    step(scanner, "Run gitleaks").trimEnd(),
    "      - name: Run gitleaks\n        run: gitleaks detect --source . --config .gitleaks.toml --verbose --redact",
  );
});

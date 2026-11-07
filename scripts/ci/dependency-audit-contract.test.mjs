import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const workflow = readFileSync(new URL("../../.github/workflows/ci.yml", import.meta.url), "utf8");

function job(source, id) {
  const match = source.match(
    new RegExp(`^  ${id}:\\n[\\s\\S]*?(?=^  [a-z0-9-]+:\\n|$(?![\\s\\S]))`, "m"),
  );
  assert.ok(match, `Missing ${id} job`);
  return match[0];
}

function step(block, name) {
  const steps = block.split(/(?=^      - name: )/m);
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
  assert.match(audit, /^    name: Dependency audit$/m);
  assert.doesNotMatch(audit, /^\s+(?:if|continue-on-error):/m);
  assert.doesNotMatch(audit, /ALLOWLIST|github_advisory_id|--ignore|\|\|\s*true/);
  assert.equal((audit.match(/run: pnpm audit /g) ?? []).length, 2);
  for (const [name, command] of auditCommands) {
    // Exact step contents prohibit shell/exit-status suppression and threshold drift.
    const content = step(audit, name)
      .replace(/^        #.*\n/gm, "")
      .trimEnd();
    assert.equal(content, `      - name: ${name}\n        run: ${command}`);
  }
  const contract = step(audit, "Dependency audit workflow contract tests");
  assert.match(contract, /run: node --test scripts\/ci\/dependency-audit-contract\.test\.mjs/);
  assert.ok(audit.indexOf(contract) < audit.indexOf("      - name: pnpm production audit"));
  assert.match(audit, /run: pnpm i --frozen-lockfile/);
  assert.match(
    step(audit, "pip-audit (API, fail on high)"),
    /uv sync --dev\n          uv tool run pip-audit/,
  );
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

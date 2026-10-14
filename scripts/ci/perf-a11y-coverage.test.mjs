import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const workflow = readFileSync(path.join(root, ".github/workflows/perf.yml"), "utf8");
const smokeStep = workflow.match(
  /      - name: a11y smoke[^\n]*\n([\s\S]*?)(?=\n      - name:)/,
)?.[1];

test("Performance keeps the two-viewport accessibility smoke blocking", () => {
  assert.ok(smokeStep, "the blocking accessibility smoke step must exist");
  assert.doesNotMatch(smokeStep, /continue-on-error:\s*true|--pass-with-no-tests/);
  assert.match(workflow, /node --test scripts\/ci\/perf-a11y-coverage\.test\.mjs/);
});

function discover(extraArgs = []) {
  const command = smokeStep?.match(/^\s*run:\s*(npx playwright test[^\n]*)$/m)?.[1];
  assert.ok(command, "the workflow must expose its Playwright smoke command");
  const args = command.split(/\s+/).slice(2);
  const output = execFileSync(
    process.execPath,
    [
      path.join(root, "e2e/node_modules/@playwright/test/cli.js"),
      ...args,
      ...extraArgs,
      "--list",
      "--reporter=json",
    ],
    { cwd: path.join(root, "e2e"), encoding: "utf8", maxBuffer: 2 * 1024 * 1024 },
  );
  return JSON.parse(output);
}

function assertCoverage(report, requireExecution = false) {
  assert.deepEqual(report.errors, []);
  assert.deepEqual(
    report.config.projects.map((project) => [project.name, project.metadata.perfA11yViewport]),
    [
      ["mobile-360", { width: 360, height: 800 }],
      ["mobile-390", { width: 390, height: 844 }],
    ],
  );
  const cases = [];
  const visit = (suite) => {
    for (const spec of suite.specs ?? []) {
      for (const execution of spec.tests ?? []) {
        assert.equal(execution.expectedStatus, "passed", "required axe cases must not be skipped");
        if (requireExecution) {
          assert.equal(
            execution.results?.at(-1)?.status,
            "passed",
            `${execution.projectName}: ${spec.title} must actually finish successfully`,
          );
        }
        cases.push([execution.projectName, spec.title]);
      }
    }
    for (const child of suite.suites ?? []) visit(child);
  };
  for (const suite of report.suites) visit(suite);
  const expected = ["mobile-360", "mobile-390"].flatMap((project) =>
    ["/", "/cart", "/checkout"].map((route) => [project, `axe critical/serious on ${route}`]),
  );
  assert.deepEqual(cases.sort(), expected.sort());
}

test("the actual Performance command discovers all three routes at 360px and 390px", () => {
  assertCoverage(discover());
});

test("a selector that drops 360px coverage is rejected", () => {
  assert.throws(() => assertCoverage(discover(["--project=mobile-390"])), assert.AssertionError);
});

test("discovery alone cannot qualify completed accessibility coverage", () => {
  assert.throws(() => assertCoverage(discover(), true), assert.AssertionError);
});

if (process.env.PERF_A11Y_RESULTS) {
  test("both viewport runs actually completed every required axe route", () => {
    const report = JSON.parse(
      readFileSync(path.resolve(root, process.env.PERF_A11Y_RESULTS), "utf8"),
    );
    assertCoverage(report, true);
  });
}

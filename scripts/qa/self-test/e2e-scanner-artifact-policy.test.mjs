import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

const read = (path) => readFileSync(new URL(`../../../${path}`, import.meta.url), "utf8");

test("ordinary Playwright tests retain the standard diagnostic policy", () => {
  const config = read("e2e/playwright.config.ts");
  assert.match(config, /trace:\s*"on-first-retry"/);
  assert.match(config, /video:\s*"retain-on-failure"/);
  assert.match(config, /screenshot:\s*"only-on-failure"/);
});

test("only the scanner journey opts into the secret-safe policy", () => {
  const scanner = read("e2e/specs/event-ticket.spec.ts");
  assert.match(scanner, /fixtures\/scanner-artifact-test/);
  assert.match(scanner, /test\.use\(SCANNER_ARTIFACT_POLICY\)/);

  for (const file of readdirSync(new URL("../../../e2e/specs", import.meta.url))) {
    if (!file.endsWith(".spec.ts") || file === "event-ticket.spec.ts") continue;
    assert.doesNotMatch(
      read(`e2e/specs/${file}`),
      /SCANNER_ARTIFACT_POLICY|scanner-artifact-test/,
    );
  }
});

test("scanner fixture suppresses prompt snapshots and restores the environment", () => {
  const fixture = read("e2e/fixtures/scanner-artifact-test.ts");
  assert.match(fixture, /trace:\s*"off"/);
  assert.match(fixture, /video:\s*"off"/);
  assert.match(fixture, /screenshot:\s*"off"/);
  assert.match(fixture, /PLAYWRIGHT_NO_COPY_PROMPT\s*=\s*"1"/);
  assert.match(fixture, /scope:\s*"worker"/);
  assert.match(fixture, /delete process\.env\.PLAYWRIGHT_NO_COPY_PROMPT/);
  assert.match(fixture, /process\.env\.PLAYWRIGHT_NO_COPY_PROMPT\s*=\s*previous/);
});

test("CI runs the behavioral sentinel regression before the suite", () => {
  const workflow = read(".github/workflows/e2e.yml");
  assert.match(workflow, /npm run test:scanner-artifacts/);
  assert.ok(
    workflow.indexOf("npm run test:scanner-artifacts") < workflow.indexOf("- name: Run E2E suite"),
  );
});

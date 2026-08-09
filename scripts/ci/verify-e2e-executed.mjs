#!/usr/bin/env node
/**
 * Fail closed when Playwright produced no executed tests (vacuous green guard).
 */
import fs from "node:fs";
import path from "node:path";

const resultsPath = process.argv[2] ?? "e2e/results/results.json";

function fail(msg) {
  console.error(`::error::${msg}`);
  process.exit(1);
}

if (!fs.existsSync(resultsPath)) {
  fail(`Playwright results missing at ${resultsPath} — no browser tests executed`);
}

const raw = fs.readFileSync(resultsPath, "utf8");
let doc;
try {
  doc = JSON.parse(raw);
} catch {
  fail(`Playwright results at ${resultsPath} are not valid JSON`);
}

const suites = Array.isArray(doc.suites) ? doc.suites : [];
let tests = 0;
/** @param {import('@playwright/test/reporter').JSONReportSuite[]} nodes */
function walk(nodes) {
  for (const suite of nodes) {
    if (Array.isArray(suite.specs)) {
      for (const spec of suite.specs) {
        tests += Array.isArray(spec.tests) ? spec.tests.length : 0;
      }
    }
    if (Array.isArray(suite.suites)) walk(suite.suites);
  }
}
walk(suites);

if (tests === 0) {
  fail("Playwright executed 0 tests — staging E2E must not pass without browser coverage");
}

console.log(JSON.stringify({ testsExecuted: tests, resultsPath: path.normalize(resultsPath) }));

#!/usr/bin/env node
/**
 * Execution-completeness contract for the staging E2E run.
 *
 * verify-e2e-executed.mjs only catches "0 tests executed" (a vacuous green).
 * This closes the more specific gaps the certification matrix needs:
 *
 *   - EXPECTED_TESTS (Playwright's own static `--list`) == DISCOVERED_TESTS
 *     (what the actual run's results.json reports) — a testMatch/config
 *     regression that silently drops specs from the matrix would otherwise
 *     still exit 0.
 *   - PASSED + FAILED + INTENTIONAL_SKIPPED == DISCOVERED_TESTS, and
 *     DID_NOT_RUN == 0 — an interruption (e.g. globalTimeout) that leaves
 *     some discovered tests with no recorded attempt must not pass silently.
 *   - STRICT_REQUIRED_SKIPS == 0 — a REQUIRED_STRICT journey (see
 *     fixtures/gating.ts) that skipped instead of failing means
 *     enforceGate() was bypassed; that is a certification bug, not a green.
 *   - INVALID_STRICT_SKIP == 0 — every skip must trace to one of the three
 *     kinds fixtures/gating-policy.ts allows to skip (OPTIONAL_GATE /
 *     FEATURE_DISABLED / VIEWPORT_NOT_APPLICABLE); a skip with no such
 *     annotation bypassed the gating.ts contract entirely.
 *   - FAILED == 0 — re-derived from the JSON independently of Playwright's
 *     own process exit code.
 *
 * Usage: node scripts/ci/verify-e2e-matrix.mjs <list.json> <results.json>
 * `list.json` is produced by `playwright test --list --reporter=json` (no
 * browser required, runs before the real suite); `results.json` is the real
 * run's JSON reporter output.
 */
import fs from "node:fs";

const GATE_KIND_PATTERN =
  /^(REQUIRED_STRICT|OPTIONAL_GATE|FEATURE_DISABLED|VIEWPORT_NOT_APPLICABLE):/;
const ALLOWED_SKIP_KINDS = new Set([
  "OPTIONAL_GATE",
  "FEATURE_DISABLED",
  "VIEWPORT_NOT_APPLICABLE",
]);

function fail(msg) {
  console.error(`::error::${msg}`);
  process.exit(1);
}

function readJson(filePath, label) {
  if (!fs.existsSync(filePath)) {
    fail(`${label} missing at ${filePath}`);
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    fail(`${label} at ${filePath} is not valid JSON`);
  }
  return undefined;
}

/** Flatten the JSON reporter's suites → suites → specs → tests tree. */
export function flattenTests(doc) {
  const out = [];
  function walk(nodes) {
    for (const suite of nodes ?? []) {
      for (const spec of suite.specs ?? []) {
        for (const t of spec.tests ?? []) {
          out.push({ file: spec.file, title: spec.title, ...t });
        }
      }
      walk(suite.suites);
    }
  }
  walk(doc?.suites);
  return out;
}

function gateKindOf(test) {
  for (const annotation of test.annotations ?? []) {
    const match = GATE_KIND_PATTERN.exec(annotation.description ?? "");
    if (match) return match[1];
  }
  return null;
}

export function computeCompleteness(listDoc, resultsDoc) {
  const expected = flattenTests(listDoc);
  const discovered = flattenTests(resultsDoc);

  const EXPECTED_TESTS = expected.length;
  const DISCOVERED_TESTS = discovered.length;

  let PASSED = 0;
  let FAILED = 0;
  let INTENTIONAL_SKIPPED = 0;
  let STRICT_REQUIRED_SKIPS = 0;
  let INVALID_STRICT_SKIP = 0;
  let DID_NOT_RUN = 0;

  for (const t of discovered) {
    const attempted = Array.isArray(t.results) && t.results.length > 0;
    if (!attempted) {
      DID_NOT_RUN += 1;
      continue;
    }
    if (t.status === "skipped") {
      const kind = gateKindOf(t);
      if (kind === "REQUIRED_STRICT") {
        STRICT_REQUIRED_SKIPS += 1;
      } else if (kind && ALLOWED_SKIP_KINDS.has(kind)) {
        INTENTIONAL_SKIPPED += 1;
      } else {
        INVALID_STRICT_SKIP += 1;
      }
    } else if (t.status === "expected" || t.status === "flaky") {
      PASSED += 1;
    } else {
      // "unexpected" — Playwright's overall-failed status.
      FAILED += 1;
    }
  }

  return {
    EXPECTED_TESTS,
    DISCOVERED_TESTS,
    PASSED,
    FAILED,
    INTENTIONAL_SKIPPED,
    STRICT_REQUIRED_SKIPS,
    INVALID_STRICT_SKIP,
    DID_NOT_RUN,
  };
}

export function evaluateCompleteness(report) {
  const problems = [];
  if (report.EXPECTED_TESTS !== report.DISCOVERED_TESTS) {
    problems.push(
      `EXPECTED_TESTS(${report.EXPECTED_TESTS}) != DISCOVERED_TESTS(${report.DISCOVERED_TESTS}) — the statically-discovered matrix does not match what the run reported; a testMatch/config regression may have silently dropped specs`,
    );
  }
  const accounted = report.PASSED + report.FAILED + report.INTENTIONAL_SKIPPED;
  if (accounted !== report.DISCOVERED_TESTS) {
    problems.push(
      `PASSED+FAILED+INTENTIONAL_SKIPPED(${accounted}) != DISCOVERED_TESTS(${report.DISCOVERED_TESTS})`,
    );
  }
  if (report.DID_NOT_RUN !== 0) {
    problems.push(
      `DID_NOT_RUN=${report.DID_NOT_RUN} — the suite was interrupted (e.g. globalTimeout) before every discovered test was attempted`,
    );
  }
  if (report.STRICT_REQUIRED_SKIPS !== 0) {
    problems.push(
      `STRICT_REQUIRED_SKIPS=${report.STRICT_REQUIRED_SKIPS} — a REQUIRED_STRICT journey skipped instead of failing (enforceGate() bypassed)`,
    );
  }
  if (report.INVALID_STRICT_SKIP !== 0) {
    problems.push(
      `INVALID_STRICT_SKIP=${report.INVALID_STRICT_SKIP} — a test skipped without a recognised gate-kind annotation (outside the fixtures/gating.ts contract)`,
    );
  }
  if (report.FAILED !== 0) {
    problems.push(`FAILED=${report.FAILED} — one or more tests failed`);
  }
  return problems;
}

// Only run as a CLI when invoked directly (so self-tests can import the pure functions above).
if (import.meta.url === `file://${process.argv[1]}`) {
  const [, , listPath = "e2e/results/list.json", resultsPath = "e2e/results/results.json"] =
    process.argv;

  const listDoc = readJson(listPath, "Playwright --list output");
  const resultsDoc = readJson(resultsPath, "Playwright results");

  const report = computeCompleteness(listDoc, resultsDoc);
  console.log(JSON.stringify(report, null, 2));

  const problems = evaluateCompleteness(report);
  if (problems.length > 0) {
    fail(`E2E execution-completeness contract violated:\n  - ${problems.join("\n  - ")}`);
  }
  console.log("E2E execution-completeness contract satisfied.");
}

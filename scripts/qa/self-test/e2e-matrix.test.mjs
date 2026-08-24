import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import {
  CANONICAL_PROJECT,
  FAST_3G_PROJECT,
  RESPONSIVE_PROJECTS,
  SPEC_CLASSIFICATION,
  allProjectNames,
  projectsForClass,
  specsForProject,
} from "../../../e2e/fixtures/spec-classification.ts";
import { CERTIFICATION_VIEWPORTS } from "../../../e2e/fixtures/viewports.ts";
import {
  computeCompleteness,
  evaluateCompleteness,
  flattenTests,
} from "../../ci/verify-e2e-matrix.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const SPEC_DIR = path.join(REPO_ROOT, "e2e", "specs");

function specSource(file) {
  return readFileSync(path.join(SPEC_DIR, file), "utf8");
}

/**
 * PR B contract: the certification matrix must be bounded, deterministic and
 * free of the 325-vs-65 double-multiplication that caused run #47's
 * globalTimeout. These per-file counts are the LOGICAL (source-level) test
 * counts, verified once against a real `npx playwright test --list
 * --reporter=json` run against this exact matrix (65 project-test instances,
 * 49 distinct logical tests — see the PR description for the full
 * breakdown). They are a deliberate, minimal duplication of a fact that only
 * Playwright's own parser truly owns; `scripts/ci/verify-e2e-matrix.mjs`'s
 * EXPECTED_TESTS check (driven by a live `--list` in CI) is the authoritative,
 * self-updating guard — this table exists so a matrix regression is caught
 * here too, fast and without a browser.
 */
const LOGICAL_TEST_COUNTS = {
  "a11y-smoke.spec.ts": 3,
  "auth-otp.spec.ts": 1,
  "browse-journey.spec.ts": 1,
  "checkout-false-success.spec.ts": 10,
  "clips-commerce.spec.ts": 4,
  "clips-feed.spec.ts": 4,
  "critical-path.spec.ts": 2,
  "data-quality.spec.ts": 4,
  "event-ticket.spec.ts": 1,
  "mobile-layout.spec.ts": 4,
  "performance-smoke.spec.ts": 3,
  "shop-checkout-momo.spec.ts": 1,
  "shop-cod.spec.ts": 1,
  "staging-access-smoke.spec.ts": 1,
  "ux-surfaces.spec.ts": 8,
  "vendor-sell.spec.ts": 1,
};

describe("spec-classification — every spec is covered exactly once per intended project", () => {
  it("SPEC_CLASSIFICATION and LOGICAL_TEST_COUNTS cover the same 16 files", () => {
    const classified = SPEC_CLASSIFICATION.map((e) => e.file).sort();
    const counted = Object.keys(LOGICAL_TEST_COUNTS).sort();
    assert.deepEqual(classified, counted);
    assert.equal(classified.length, 16);
  });

  it("no spec is assigned to zero projects", () => {
    for (const entry of SPEC_CLASSIFICATION) {
      const projects = projectsForClass(entry.class);
      assert.ok(
        projects.length > 0,
        `${entry.file} (class ${entry.class}) resolves to zero Playwright projects`,
      );
    }
  });

  it("every real spec file appears in at least one project's spec list", () => {
    for (const entry of SPEC_CLASSIFICATION) {
      const owningProjects = allProjectNames().filter((name) =>
        specsForProject(name).includes(entry.file),
      );
      assert.ok(owningProjects.length > 0, `${entry.file} is not assigned to any project`);
    }
  });
});

describe("responsive viewport coverage", () => {
  it("RESPONSIVE_PROJECTS is exactly the 5 CERTIFICATION_VIEWPORTS, in the same order", () => {
    assert.deepEqual(
      [...RESPONSIVE_PROJECTS],
      CERTIFICATION_VIEWPORTS.map((v) => v.name),
    );
    assert.equal(RESPONSIVE_PROJECTS.length, 5);
  });

  it("mobile-layout.spec.ts is the only RESPONSIVE_ALL_VIEWPORTS spec, and runs on all 5", () => {
    const responsive = SPEC_CLASSIFICATION.filter((e) => e.class === "RESPONSIVE_ALL_VIEWPORTS");
    assert.deepEqual(
      responsive.map((e) => e.file),
      ["mobile-layout.spec.ts"],
    );
    for (const project of RESPONSIVE_PROJECTS) {
      assert.ok(
        specsForProject(project).includes("mobile-layout.spec.ts"),
        `mobile-layout.spec.ts missing from responsive project "${project}"`,
      );
    }
  });

  it("mobile-layout.spec.ts is not double-multiplied: no internal viewport loop", () => {
    const source = specSource("mobile-layout.spec.ts");
    // The PR #47 bug: `for (const vp of CERTIFICATION_VIEWPORTS)` wrapping
    // test.describe/test() so each of the 4 tests ran 5x per project
    // (20x per file instead of 4x). Viewport must now come solely from the
    // Playwright project (page.viewportSize()), never a source-level loop.
    assert.ok(
      !source.includes("CERTIFICATION_VIEWPORTS"),
      "mobile-layout.spec.ts still references CERTIFICATION_VIEWPORTS — the internal viewport loop regressed",
    );
    assert.ok(
      !/for\s*\(\s*const\s+vp\s+of/.test(source),
      "mobile-layout.spec.ts still loops over viewports internally",
    );
    assert.ok(
      source.includes("page.viewportSize()"),
      "mobile-layout.spec.ts must read the live viewport at runtime",
    );
    const testCount = (source.match(/^\s*test\(/gm) ?? []).length;
    assert.equal(testCount, LOGICAL_TEST_COUNTS["mobile-layout.spec.ts"]);
  });
});

describe("Fast-3G coverage", () => {
  it("FAST_3G_PROJECT carries at least one spec, and is a distinct identity from mobile-360", () => {
    const specs = specsForProject(FAST_3G_PROJECT);
    assert.ok(specs.length > 0, "fast-3g project has zero specs assigned");
    assert.notEqual(FAST_3G_PROJECT, "mobile-360");
    // The fast3g auto-fixture throttles on `.includes("3g")` in the project name.
    assert.ok(FAST_3G_PROJECT.toLowerCase().includes("3g"));
  });

  it("performance-smoke.spec.ts (LCP budget is defined against Fast-3G/360px) runs on fast-3g", () => {
    assert.ok(specsForProject(FAST_3G_PROJECT).includes("performance-smoke.spec.ts"));
  });

  it("clips-feed.spec.ts (byte-budget, 'on Fast-3G' per its own doc comment) runs on fast-3g", () => {
    assert.ok(specsForProject(FAST_3G_PROJECT).includes("clips-feed.spec.ts"));
  });

  it("no NETWORK_THROTTLED_ONLY spec also runs on the canonical (non-throttled) project", () => {
    for (const entry of SPEC_CLASSIFICATION.filter((e) => e.class === "NETWORK_THROTTLED_ONLY")) {
      assert.ok(!specsForProject(CANONICAL_PROJECT).includes(entry.file));
    }
  });
});

describe("expected project-test count is deterministic", () => {
  it("computes to exactly 65 total project-test instances (down from OLD_PROJECT_TESTS=325)", () => {
    let total = 0;
    const perProject = {};
    for (const project of allProjectNames()) {
      const count = specsForProject(project).reduce(
        (sum, file) => sum + (LOGICAL_TEST_COUNTS[file] ?? 0),
        0,
      );
      perProject[project] = count;
      total += count;
    }
    assert.deepEqual(perProject, {
      "mobile-360": 4,
      "mobile-390": 42,
      "mobile-430": 4,
      "tablet-768": 4,
      "desktop-1440": 4,
      "fast-3g": 7,
    });
    assert.equal(total, 65);
  });

  it("computes to exactly 49 distinct logical tests (source-level identities)", () => {
    const total = Object.values(LOGICAL_TEST_COUNTS).reduce((a, b) => a + b, 0);
    assert.equal(total, 49);
  });
});

describe("REQUIRED_STRICT journeys are present and matrix-covered", () => {
  // Conceptually 6 journeys (customer OTP, vendor OTP/login, vendor seller
  // journey, event scanner verify, event duplicate-reject, critical
  // checkout/payment-surface reachability) resolve to 4 distinct gate call
  // sites: the vendor pair shares one gate (login is a precondition of the
  // sell flow), and the event pair shares one gate (verify + duplicate-reject
  // are asserted by the same test).
  const REQUIRED_SITES = [
    ["auth-otp.spec.ts", "customer OTP verification"],
    ["vendor-sell.spec.ts", "vendor authenticated sell flow"],
    ["event-ticket.spec.ts", "event scanner verify + duplicate-reject"],
    ["critical-path.spec.ts", "checkout place-order -> payment surface"],
  ];

  for (const [file, journey] of REQUIRED_SITES) {
    it(`${file} declares "${journey}" as REQUIRED_STRICT and is assigned to a project`, () => {
      const source = specSource(file);
      assert.ok(source.includes(journey), `${file} lost its REQUIRED_STRICT journey label`);
      assert.ok(source.includes('kind: "REQUIRED_STRICT"'));
      const entry = SPEC_CLASSIFICATION.find((e) => e.file === file);
      assert.ok(entry, `${file} is missing from SPEC_CLASSIFICATION entirely`);
      assert.ok(projectsForClass(entry.class).length > 0);
    });
  }
});

describe("auth-otp locator fix", () => {
  it("uses a single unambiguous getByRole locator, not the old ambiguous getByLabel().or() union", () => {
    const source = specSource("auth-otp.spec.ts");
    assert.ok(
      source.includes('page.getByRole("textbox", { name: /phone|mobile/i })'),
      "auth-otp.spec.ts no longer uses the semantic getByRole locator",
    );
    assert.ok(
      !/getByLabel\(\/phone\|mobile\/i\)\s*\n?\s*\.or\(/.test(source),
      "auth-otp.spec.ts still unions getByLabel with getByRole — the ambiguous locator regressed",
    );
    // No data-testid was added to work around the locator — the fix is semantic.
    assert.ok(!/getByTestId\(["']phone|["']mobile/.test(source));
  });
});

describe("verify-e2e-matrix.mjs — execution-completeness contract", () => {
  function test_(status, { ran = true, annotations = [] } = {}) {
    return {
      timeout: 90000,
      annotations,
      expectedStatus: "passed",
      projectName: "p",
      projectId: "p",
      status,
      results: ran ? [{ status: status === "expected" ? "passed" : "failed", duration: 1 }] : [],
    };
  }
  function doc(tests) {
    return {
      suites: [
        {
          title: "file.spec.ts",
          file: "file.spec.ts",
          specs: [],
          suites: [
            {
              title: "describe",
              specs: [{ title: "t", file: "file.spec.ts", tests }],
            },
          ],
        },
      ],
    };
  }

  it("flattenTests walks the real nested suites→suites→specs→tests shape", () => {
    const flat = flattenTests(doc([test_("expected")]));
    assert.equal(flat.length, 1);
    assert.equal(flat[0].file, "file.spec.ts");
  });

  it("a clean, fully-passing run satisfies the contract", () => {
    const listDoc = doc([test_("expected", { ran: false })]);
    const resultsDoc = doc([test_("expected")]);
    const report = computeCompleteness(listDoc, resultsDoc);
    assert.deepEqual(evaluateCompleteness(report), []);
    assert.equal(report.PASSED, 1);
    assert.equal(report.FAILED, 0);
    assert.equal(report.DID_NOT_RUN, 0);
  });

  it("EXPECTED_TESTS != DISCOVERED_TESTS is flagged (matrix silently shrank)", () => {
    const listDoc = doc([test_("expected", { ran: false }), test_("expected", { ran: false })]);
    const resultsDoc = doc([test_("expected")]);
    const problems = evaluateCompleteness(computeCompleteness(listDoc, resultsDoc));
    assert.ok(problems.some((p) => p.includes("EXPECTED_TESTS")));
  });

  it("a test with zero results (interrupted run) is DID_NOT_RUN, not silently passed", () => {
    const listDoc = doc([test_("expected", { ran: false })]);
    const resultsDoc = doc([test_("expected", { ran: false })]);
    const report = computeCompleteness(listDoc, resultsDoc);
    assert.equal(report.DID_NOT_RUN, 1);
    assert.ok(evaluateCompleteness(report).some((p) => p.includes("DID_NOT_RUN")));
  });

  it("a REQUIRED_STRICT skip is flagged as STRICT_REQUIRED_SKIPS, never counted as a clean skip", () => {
    const t = test_("skipped", {
      annotations: [
        {
          type: "founder-gated",
          description: "REQUIRED_STRICT: customer OTP verification is part of...",
        },
      ],
    });
    const report = computeCompleteness(doc([t]), doc([t]));
    assert.equal(report.STRICT_REQUIRED_SKIPS, 1);
    assert.equal(report.INTENTIONAL_SKIPPED, 0);
    assert.ok(evaluateCompleteness(report).some((p) => p.includes("STRICT_REQUIRED_SKIPS")));
  });

  it("an allowed OPTIONAL_GATE/FEATURE_DISABLED/VIEWPORT_NOT_APPLICABLE skip passes cleanly", () => {
    for (const kind of ["OPTIONAL_GATE", "FEATURE_DISABLED", "VIEWPORT_NOT_APPLICABLE"]) {
      const t = test_("skipped", {
        annotations: [{ type: "x", description: `${kind}: some leg skipped` }],
      });
      const report = computeCompleteness(doc([t]), doc([t]));
      assert.equal(report.INTENTIONAL_SKIPPED, 1, kind);
      assert.equal(report.INVALID_STRICT_SKIP, 0, kind);
      assert.deepEqual(evaluateCompleteness(report), [], kind);
    }
  });

  it("a skip with no recognised gate-kind annotation is INVALID_STRICT_SKIP", () => {
    const t = test_("skipped", { annotations: [{ type: "note", description: "just because" }] });
    const report = computeCompleteness(doc([t]), doc([t]));
    assert.equal(report.INVALID_STRICT_SKIP, 1);
    assert.ok(evaluateCompleteness(report).some((p) => p.includes("INVALID_STRICT_SKIP")));
  });

  it("an unexpected (failed) test is flagged even though the process could still exit 0", () => {
    const t = test_("unexpected");
    const report = computeCompleteness(doc([t]), doc([t]));
    assert.equal(report.FAILED, 1);
    assert.ok(evaluateCompleteness(report).some((p) => p.startsWith("FAILED=1")));
  });

  it("a flaky test (failed then passed on retry) counts as PASSED, not FAILED", () => {
    const t = test_("flaky");
    const report = computeCompleteness(doc([t]), doc([t]));
    assert.equal(report.PASSED, 1);
    assert.equal(report.FAILED, 0);
  });
});

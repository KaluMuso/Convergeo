import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  classifyRlsOutcome,
  deriveCertification,
  exitCodeForVerdict,
  normalizeMode,
  normalizeStatus,
  requiredGateBlocks,
  requiredGateSatisfied,
} from "../gate-status.mjs";

describe("gate-status vocabulary", () => {
  it("normalizes unknown statuses to UNKNOWN", () => {
    assert.equal(normalizeStatus("pass"), "PASS");
    assert.equal(normalizeStatus("wat"), "UNKNOWN");
  });

  it("maps legacy mode aliases", () => {
    assert.equal(normalizeMode("local"), "local-development");
    assert.equal(normalizeMode("staging"), "integrated-staging");
    assert.equal(normalizeMode("ci"), "ci");
  });

  it("treats missing required gate as blocking (never PASS)", () => {
    assert.equal(requiredGateSatisfied(null), false);
    assert.equal(requiredGateSatisfied(undefined), false);
    assert.equal(requiredGateSatisfied("PASS"), true);
    for (const s of ["FAIL", "BLOCKED_EXTERNAL", "NOT_RUN", "UNKNOWN", "MEASUREMENT_UNSTABLE"]) {
      assert.equal(requiredGateBlocks(s), true);
    }
  });
});

describe("strict exit semantics", () => {
  it("only CERTIFIABLE_AFTER_INTEGRATION exits 0 in promotion modes", () => {
    assert.equal(exitCodeForVerdict("CERTIFIABLE_AFTER_INTEGRATION", "integrated-staging"), 0);
    assert.equal(exitCodeForVerdict("BASELINE_FAILING", "integrated-staging"), 1);
    assert.equal(exitCodeForVerdict("BLOCKED_EXTERNAL", "integrated-staging"), 1);
    assert.equal(exitCodeForVerdict("INCOMPLETE_REQUIRED_GATES", "ci"), 1);
    assert.equal(exitCodeForVerdict("LOCAL_DEVELOPMENT_REPORT", "local-development"), 0);
  });

  it("local-development always reports LOCAL_DEVELOPMENT_REPORT", () => {
    const v = deriveCertification({ lint: { status: "PASS" } }, { mode: "local-development" });
    assert.equal(v, "LOCAL_DEVELOPMENT_REPORT");
  });
});

describe("RLS classification", () => {
  it("tool unavailable → BLOCKED_EXTERNAL", () => {
    const r = classifyRlsOutcome({ toolAvailable: false, setupOk: null, testExitCode: null });
    assert.equal(r.status, "BLOCKED_EXTERNAL");
  });

  it("setup defect → FAIL (never BLOCKED_EXTERNAL)", () => {
    const r = classifyRlsOutcome({ toolAvailable: true, setupOk: false, testExitCode: null });
    assert.equal(r.status, "FAIL");
  });

  it("assertion failure → FAIL", () => {
    const r = classifyRlsOutcome({ toolAvailable: true, setupOk: true, testExitCode: 1 });
    assert.equal(r.status, "FAIL");
  });

  it("success → PASS", () => {
    const r = classifyRlsOutcome({ toolAvailable: true, setupOk: true, testExitCode: 0 });
    assert.equal(r.status, "PASS");
  });
});

describe("required-gate manifest enforcement", () => {
  it("missing required gate → INCOMPLETE_REQUIRED_GATES", () => {
    const v = deriveCertification(
      { lint: { status: "PASS" } },
      { mode: "integrated-staging", requiredGateIds: ["lint", "rls-isolation"] },
    );
    assert.equal(v, "INCOMPLETE_REQUIRED_GATES");
  });

  it("NOT_RUN required gate blocks certification", () => {
    const v = deriveCertification(
      { lint: { status: "PASS" }, "rls-isolation": { status: "NOT_RUN" } },
      { mode: "ci", requiredGateIds: ["lint", "rls-isolation"] },
    );
    assert.notEqual(v, "CERTIFIABLE_AFTER_INTEGRATION");
    assert.equal(exitCodeForVerdict(v, "ci"), 1);
  });

  it("MEASUREMENT_UNSTABLE required gate blocks certification", () => {
    const v = deriveCertification(
      { "perf-web-vitals-smoke": { status: "MEASUREMENT_UNSTABLE" } },
      { mode: "integrated-staging", requiredGateIds: ["perf-web-vitals-smoke"] },
    );
    assert.notEqual(v, "CERTIFIABLE_AFTER_INTEGRATION");
  });

  it("all required PASS → CERTIFIABLE_AFTER_INTEGRATION", () => {
    const v = deriveCertification(
      { lint: { status: "PASS" }, typecheck: { status: "PASS" } },
      { mode: "ci", requiredGateIds: ["lint", "typecheck"] },
    );
    assert.equal(v, "CERTIFIABLE_AFTER_INTEGRATION");
    assert.equal(exitCodeForVerdict(v, "ci"), 0);
  });
});

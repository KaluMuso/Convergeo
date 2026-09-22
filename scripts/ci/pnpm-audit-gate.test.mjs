import assert from "node:assert/strict";
import test from "node:test";

import { assessAuditProcess } from "./pnpm-audit-gate.mjs";

function auditJson(advisories = {}) {
  return JSON.stringify({
    advisories,
    metadata: {
      vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0 },
    },
  });
}

test("fails closed on empty audit output", () => {
  assert.throws(
    () => assessAuditProcess({ status: 0, stdout: "" }),
    /empty output/,
  );
});

test("fails closed on malformed audit output", () => {
  assert.throws(
    () => assessAuditProcess({ status: 1, stdout: "not-json" }),
    /malformed JSON/,
  );
});

test("fails closed when the audit command fails", () => {
  assert.throws(
    () =>
      assessAuditProcess({
        status: 2,
        stdout: auditJson(),
        stderr: "registry unavailable",
      }),
    /exit code 2: registry unavailable/,
  );
});

test("fails closed when pnpm returns an error payload", () => {
  const stdout = JSON.stringify({ error: { message: "registry unavailable" } });
  assert.throws(
    () => assessAuditProcess({ status: 1, stdout }),
    /reported a command error/,
  );
});

test("reports a planted blocking advisory", () => {
  const stdout = auditJson({
    planted: {
      github_advisory_id: "GHSA-0000-0000-0000",
      module_name: "planted-package",
      severity: "high",
      vulnerable_versions: "<2.0.0",
      patched_versions: ">=2.0.0",
    },
  });

  const result = assessAuditProcess({ status: 1, stdout });
  assert.deepEqual(result.blockers, [
    {
      id: "GHSA-0000-0000-0000",
      module: "planted-package",
      severity: "high",
      vulnerableVersions: "<2.0.0",
      patchedVersions: ">=2.0.0",
    },
  ]);
});

test("allows valid non-blocking audit findings", () => {
  const stdout = auditJson({
    moderate: {
      github_advisory_id: "GHSA-1111-1111-1111",
      module_name: "moderate-package",
      severity: "moderate",
    },
  });

  const result = assessAuditProcess({ status: 1, stdout });
  assert.deepEqual(result.blockers, []);
});

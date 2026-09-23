import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  assessAuditProcess,
  gateExitCode,
  runAudit,
} from "./pnpm-audit-gate.mjs";

const SEVERITIES = ["info", "low", "moderate", "high", "critical"];

function advisory(severity, overrides = {}) {
  return {
    module_name: "planted-package",
    severity,
    findings: [{ version: "1.0.0", paths: [". > planted-package@1.0.0"] }],
    ...overrides,
  };
}

function auditJson(advisories = {}, countOverrides = {}, extra = {}) {
  const vulnerabilities = Object.fromEntries(
    SEVERITIES.map((severity) => [severity, 0]),
  );
  for (const entry of Object.values(advisories)) {
    if (
      entry &&
      typeof entry === "object" &&
      SEVERITIES.includes(entry.severity)
    ) {
      vulnerabilities[entry.severity] += Array.isArray(entry.findings)
        ? entry.findings.length
        : 0;
    }
  }
  return JSON.stringify({
    advisories,
    muted: [],
    metadata: { vulnerabilities: { ...vulnerabilities, ...countOverrides } },
    ...extra,
  });
}

function assess(status, stdout, other = {}) {
  return assessAuditProcess({ status, stdout, ...other });
}

test("rejects empty, malformed, truncated, and nonobject output", () => {
  assert.throws(() => assess(0, ""), /empty output/);
  assert.throws(() => assess(1, "not-json"), /malformed JSON/);
  assert.throws(() => assess(1, '{"advisories":'), /malformed JSON/);
  assert.throws(() => assess(0, "[]"), /root must be an object/);
});

test("rejects missing advisory and metadata containers", () => {
  assert.throws(
    () => assess(0, JSON.stringify({ metadata: { vulnerabilities: {} } })),
    /missing the advisories object/,
  );
  assert.throws(
    () => assess(0, JSON.stringify({ advisories: {} })),
    /missing vulnerability metadata/,
  );
});

test("rejects malformed advisory records instead of dropping them", () => {
  assert.throws(
    () => assess(1, auditJson({ planted: "not-an-advisory" }, { high: 1 })),
    /advisory planted must be an object/,
  );
});

test("rejects a reported high with an empty advisory map", () => {
  assert.throws(
    () => assess(1, auditJson({}, { high: 1 })),
    /high count does not match advisory findings/,
  );
});

test("rejects missing, negative, string, fractional, and unsafe counts", () => {
  for (const severity of SEVERITIES) {
    const missing = JSON.parse(auditJson());
    delete missing.metadata.vulnerabilities[severity];
    assert.throws(
      () => assess(0, JSON.stringify(missing)),
      new RegExp(`invalid ${severity} vulnerability count`),
    );
  }
  for (const bad of [-1, "1", 0.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(
      () => assess(0, auditJson({}, { high: bad })),
      /invalid high vulnerability count/,
    );
  }
  assert.throws(
    () => assess(0, auditJson({}, { urgent: 1 })),
    /unknown urgent severity count/,
  );
});

test("rejects invalid severity and missing or malformed findings", () => {
  assert.throws(
    () => assess(1, auditJson({ planted: advisory("unknown") })),
    /invalid severity/,
  );
  assert.throws(
    () => assess(1, auditJson({ planted: advisory("high", { findings: [] }) })),
    /has no findings/,
  );
  assert.throws(
    () =>
      assess(
        1,
        auditJson({
          planted: advisory("high", {
            findings: [{ version: "1.0.0", paths: [] }],
          }),
        }),
      ),
    /malformed finding/,
  );
  assert.throws(
    () =>
      assess(1, auditJson({ planted: advisory("high", { module_name: "" }) })),
    /no module name/,
  );
});

test("rejects mismatched high or critical counts in either direction", () => {
  assert.throws(
    () => assess(1, auditJson({ planted: advisory("high") }, { high: 0 })),
    /high count does not match advisory findings/,
  );
  assert.throws(
    () => assess(1, auditJson({}, { critical: 1 })),
    /critical count does not match advisory findings/,
  );
});

test("rejects report-shaped errors and muted findings", () => {
  assert.throws(
    () =>
      assess(
        1,
        auditJson({}, {}, { error: { message: "registry unavailable" } }),
      ),
    /reported a command error/,
  );
  assert.throws(
    () => assess(1, auditJson({}, {}, { error: "registry unavailable" })),
    /reported a command error/,
  );
  assert.throws(
    () => assess(1, auditJson({}, {}, { muted: [{ severity: "high" }] })),
    /muted or malformed advisories/,
  );
});

test("distinguishes command and transport failures from findings", () => {
  assert.throws(
    () => assess(2, auditJson(), { stderr: "registry unavailable" }),
    /exit code 2: registry unavailable/,
  );
  assert.throws(() => assess(null, ""), /did not return an exit status/);
  assert.throws(
    () => assess(null, "", { error: new Error("spawn failed") }),
    /failed to execute pnpm audit: spawn failed/,
  );
});

test("rejects command status that disagrees with its report", () => {
  assert.throws(() => assess(1, auditJson()), /exit status disagrees/);
  assert.throws(
    () => assess(0, auditJson({ planted: advisory("high") })),
    /exit status disagrees/,
  );
});

test("blocks high and critical findings without advisory IDs", () => {
  const result = assess(
    1,
    auditJson({
      highKey: advisory("high"),
      criticalKey: advisory("critical"),
    }),
  );
  assert.deepEqual(
    result.blockers.map(({ id, severity }) => ({ id, severity })),
    [
      { id: "criticalKey", severity: "critical" },
      { id: "highKey", severity: "high" },
    ],
  );
  assert.equal(gateExitCode(result), 1);
});

test("counts finding records rather than unique advisory keys or paths", () => {
  const result = assess(
    1,
    auditJson({
      planted: advisory("high", {
        findings: [
          { version: "1.0.0", paths: [". > a", ". > b"] },
          { version: "1.0.1", paths: [". > c"] },
        ],
      }),
    }),
  );
  assert.equal(result.data.metadata.vulnerabilities.high, 2);
  assert.equal(result.blockers.length, 1);
});

test("allows valid moderate-only findings despite raw audit exit 1", () => {
  const result = assess(1, auditJson({ moderate: advisory("moderate") }));
  assert.deepEqual(result.blockers, []);
  assert.equal(gateExitCode(result), 0);
});

test("allows a valid clean report with raw audit exit 0", () => {
  const result = assess(0, auditJson());
  assert.deepEqual(result.blockers, []);
  assert.equal(gateExitCode(result), 0);
});

test("retains raw stdout, stderr, and command status on a finding", () => {
  const dir = mkdtempSync(join(tmpdir(), "pnpm-audit-gate-"));
  try {
    const output = join(dir, "stdout.json");
    const stderrOutput = join(dir, "stderr.txt");
    const statusOutput = join(dir, "status.json");
    const stdout = auditJson({ planted: advisory("high") });
    const result = runAudit({
      args: [
        "--output",
        output,
        "--stderr-output",
        stderrOutput,
        "--status-output",
        statusOutput,
      ],
      spawn: () => ({
        status: 1,
        stdout,
        stderr: "audit warning",
        signal: null,
      }),
    });
    assert.equal(gateExitCode(result), 1);
    assert.equal(readFileSync(output, "utf8"), stdout);
    assert.equal(readFileSync(stderrOutput, "utf8"), "audit warning");
    assert.deepEqual(JSON.parse(readFileSync(statusOutput, "utf8")), {
      exitCode: 1,
      signal: null,
      spawnError: null,
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("retains raw evidence on tool failure before rejecting it", () => {
  const dir = mkdtempSync(join(tmpdir(), "pnpm-audit-gate-"));
  try {
    const output = join(dir, "stdout.json");
    const stderrOutput = join(dir, "stderr.txt");
    const statusOutput = join(dir, "status.json");
    assert.throws(
      () =>
        runAudit({
          args: [
            "--output",
            output,
            "--stderr-output",
            stderrOutput,
            "--status-output",
            statusOutput,
          ],
          spawn: () => ({
            status: 2,
            stdout: '{"error":{"message":"registry unavailable"}}',
            stderr: "network timeout",
            signal: null,
          }),
        }),
      /exit code 2: network timeout/,
    );
    assert.match(readFileSync(output, "utf8"), /registry unavailable/);
    assert.equal(readFileSync(stderrOutput, "utf8"), "network timeout");
    assert.equal(JSON.parse(readFileSync(statusOutput, "utf8")).exitCode, 2);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

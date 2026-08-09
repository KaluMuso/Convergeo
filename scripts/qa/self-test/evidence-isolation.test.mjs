import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it, after } from "node:test";

import {
  evidenceNamespacePath,
  loadIsolatedGateFragments,
  prepareEvidenceNamespace,
} from "../evidence-ns.mjs";
import { collectCertificateFromArgs } from "../collect-certificate.mjs";

const root = mkdtempSync(join(tmpdir(), "cert-evidence-"));
after(() => rmSync(root, { recursive: true, force: true }));

describe("evidence namespace isolation", () => {
  it("builds path with sha/environment/runId", () => {
    const p = evidenceNamespacePath({
      root,
      sha: "abc123",
      environment: "staging",
      runId: "run-1",
    });
    assert.match(p, /abc123[/\\]staging[/\\]run-1$/);
  });

  it("prepareEvidenceNamespace wipes prior gate fragments in the namespace", () => {
    const ns = join(root, "wipe-sha", "local", "run-a");
    mkdirSync(ns, { recursive: true });
    writeFileSync(join(ns, "gate-stale.json"), JSON.stringify({ id: "stale", status: "PASS" }));
    writeFileSync(join(ns, "release-certificate.json"), "{}");
    prepareEvidenceNamespace(ns);
    assert.equal(existsSync(join(ns, "gate-stale.json")), false);
    assert.equal(existsSync(join(ns, "release-certificate.json")), true);
  });

  it("rejects stale fragments from another SHA/run (cannot contaminate certificate)", () => {
    const sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const env = "staging";
    const runId = "run-new";
    const ns = evidenceNamespacePath({ root, sha, environment: env, runId });
    prepareEvidenceNamespace(ns);

    // Plant a stale fragment claiming a different SHA inside the directory
    // (simulates accidental copy / race). Collector must reject it.
    writeFileSync(
      join(ns, "gate-lint.json"),
      JSON.stringify({
        id: "lint",
        status: "PASS",
        sha: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        environment: env,
        run_id: runId,
      }),
    );
    // Valid fragment for typecheck
    writeFileSync(
      join(ns, "gate-typecheck.json"),
      JSON.stringify({
        id: "typecheck",
        status: "PASS",
        sha,
        environment: env,
        run_id: runId,
      }),
    );
    // Sibling namespace contamination — should never be loaded
    const sibling = evidenceNamespacePath({
      root,
      sha: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      environment: env,
      runId: "run-old",
    });
    mkdirSync(sibling, { recursive: true });
    writeFileSync(
      join(sibling, "gate-unit-js.json"),
      JSON.stringify({
        id: "unit-js",
        status: "PASS",
        sha: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        environment: env,
        run_id: "run-old",
      }),
    );

    const { gates, rejected } = loadIsolatedGateFragments(ns, {
      expectedSha: sha,
      expectedEnvironment: env,
      expectedRunId: runId,
    });

    assert.equal(gates.lint, undefined, "stale SHA fragment must be rejected");
    assert.ok(
      rejected.some((r) => r.file === "gate-lint.json" && r.reason.startsWith("sha-mismatch")),
    );
    assert.equal(gates.typecheck?.status, "PASS");
    assert.equal(gates["unit-js"], undefined, "sibling namespace must not contaminate");

    // End-to-end through collector: planted critical FAIL in sibling must not greenwash,
    // and stale PASS must not satisfy required lint.
    const requiredPath = join(root, "required-gates.json");
    writeFileSync(
      requiredPath,
      JSON.stringify({
        version: 1,
        modes: {
          "integrated-staging": {
            report_only: false,
            certificate_title: "Test Cert",
            required_gates: ["lint", "typecheck"],
          },
        },
      }),
    );

    const { cert, exitCode } = collectCertificateFromArgs([
      "node",
      "collect-certificate.mjs",
      "--evidence-dir",
      ns,
      "--sha",
      sha,
      "--environment",
      env,
      "--mode",
      "integrated-staging",
      "--run-id",
      runId,
      "--required-gates",
      requiredPath,
      "--branch",
      "test",
    ]);

    assert.notEqual(cert.certification, "CERTIFIABLE_AFTER_INTEGRATION");
    assert.equal(exitCode, 1);
    assert.equal(cert.gates.lint?.status, "NOT_RUN"); // missing after rejection
    assert.ok(cert.rejected_fragments.length >= 1);
  });
});

describe("planted critical failure makes certification red", () => {
  it("FAIL on required gate exits non-zero", () => {
    const sha = "cccccccccccccccccccccccccccccccccccccccc";
    const env = "ci";
    const runId = "planted-fail";
    const ns = evidenceNamespacePath({ root, sha, environment: env, runId });
    prepareEvidenceNamespace(ns);
    writeFileSync(
      join(ns, "gate-lint.json"),
      JSON.stringify({
        id: "lint",
        status: "FAIL",
        sha,
        environment: env,
        run_id: runId,
        detail: "planted",
      }),
    );
    writeFileSync(
      join(ns, "gate-typecheck.json"),
      JSON.stringify({ id: "typecheck", status: "PASS", sha, environment: env, run_id: runId }),
    );
    const requiredPath = join(root, "required-gates-ci.json");
    writeFileSync(
      requiredPath,
      JSON.stringify({
        version: 1,
        modes: {
          ci: {
            report_only: false,
            certificate_title: "CI Cert",
            required_gates: ["lint", "typecheck"],
          },
        },
      }),
    );

    const { cert, exitCode } = collectCertificateFromArgs([
      "node",
      "collect-certificate.mjs",
      "--evidence-dir",
      ns,
      "--sha",
      sha,
      "--environment",
      env,
      "--mode",
      "ci",
      "--run-id",
      runId,
      "--required-gates",
      requiredPath,
    ]);

    assert.equal(cert.certification, "BASELINE_FAILING");
    assert.equal(exitCode, 1);
    assert.equal(cert.gates.lint.status, "FAIL");
  });
});

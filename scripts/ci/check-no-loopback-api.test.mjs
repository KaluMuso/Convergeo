import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it } from "node:test";

import {
  evaluateGuard,
  frontendAppsFromTurboDryRun,
  inspectBundleSource,
  parseCliArgs,
  planeApiMismatch,
  resolveRequiredApps,
} from "./check-no-loopback-api.mjs";

function writeBundle(root, app, source) {
  const dir = join(root, "apps", app, ".next", "static", "chunks");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "main.js"), source);
}

function writeMiddleware(root, app, source) {
  const dir = join(root, "apps", app, ".next", "server");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "middleware.js"), source);
}

describe("parseCliArgs / required apps", () => {
  it("defaults to all three frontends when unscoped", () => {
    const args = parseCliArgs([], {});
    assert.deepEqual(resolveRequiredApps(args), ["customer", "vendor", "admin"]);
  });

  it("honors --require-apps and REQUIRE_FRONTEND_BUILD", () => {
    assert.deepEqual(resolveRequiredApps(parseCliArgs(["--require-apps=customer,admin"], {})), [
      "customer",
      "admin",
    ]);
    assert.deepEqual(resolveRequiredApps(parseCliArgs([], { REQUIRE_FRONTEND_BUILD: "1" })), [
      "customer",
      "vendor",
      "admin",
    ]);
  });

  it("reads affected frontends from turbo dry-run JSON", () => {
    const json = JSON.stringify({
      tasks: [
        { taskId: "customer#build", package: "customer" },
        { taskId: "@vergeo/config#build", package: "@vergeo/config" },
        { taskId: "vendor#build", package: "vendor" },
      ],
    });
    assert.deepEqual(frontendAppsFromTurboDryRun(json), ["customer", "vendor"]);
    assert.deepEqual(
      resolveRequiredApps({ requireAffected: true, requireApps: null }, { turboDryRunJson: json }),
      ["customer", "vendor"],
    );
    assert.deepEqual(
      resolveRequiredApps(
        { requireAffected: true, requireApps: null },
        { turboDryRunJson: JSON.stringify({ tasks: [{ taskId: "api#test", package: "api" }] }) },
      ),
      [],
    );
  });
});

describe("planeApiMismatch", () => {
  it("fails when Preview/staging env points at the production API", () => {
    assert.equal(
      planeApiMismatch({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
      }),
      "staging_or_preview_targets_production_api",
    );
    assert.equal(
      planeApiMismatch({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging",
        NEXT_PUBLIC_VERGEO_API_URL: "https://api.vergeo5.com/",
      }),
      "staging_or_preview_targets_production_api",
    );
  });

  it("fails when the production plane points at staging or loopback", () => {
    assert.equal(
      planeApiMismatch({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
      }),
      "production_targets_staging_api",
    );
    assert.equal(
      planeApiMismatch({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
      }),
      "deployed_plane_targets_loopback",
    );
  });

  it("allows staging API on Preview and production API on Production", () => {
    assert.equal(
      planeApiMismatch({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
      }),
      null,
    );
    assert.equal(
      planeApiMismatch({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
      }),
      null,
    );
  });
});

describe("inspectBundleSource", () => {
  it("flags a loopback API origin", () => {
    const hits = inspectBundleSource('fetch("http://localhost:8000/healthz")');
    assert.equal(hits[0]?.kind, "loopback");
  });

  it("does not flag Next internals that mention port 3000", () => {
    assert.deepEqual(inspectBundleSource("http://localhost:3000/_next/static"), []);
  });

  it("flags Preview → production API and production → staging API", () => {
    const preview = inspectBundleSource('const api="https://api.vergeo5.com"', {
      expectedPlane: "preview",
    });
    assert.equal(preview[0]?.kind, "preview_or_staging_targets_production");
    const mismatch = inspectBundleSource('const api="https://api.staging.vergeo5.com"', {
      expectedPlane: "production",
    });
    assert.equal(mismatch[0]?.kind, "production_targets_staging");
  });

  it("classifies plane from the inlined bundle marker", () => {
    const preview = inspectBundleSource(
      'vergeo5-deployment-plane=preview; const api="https://api.vergeo5.com"',
    );
    assert.equal(preview[0]?.kind, "preview_or_staging_targets_production");
    const production = inspectBundleSource(
      'vergeo5-deployment-plane=production; const api="https://api.vergeo5.com"',
    );
    assert.deepEqual(production, []);
  });

  it("loopback-only mode ignores CSP staging/production API allowlists", () => {
    const hits = inspectBundleSource(
      "connect-src https://api.vergeo5.com https://api.staging.vergeo5.com",
      { expectedPlane: "production", loopbackOnly: true },
    );
    assert.deepEqual(hits, []);
  });
});

describe("evaluateGuard fixtures", () => {
  it("fails when a required app has no .next output", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-missing-"));
    try {
      const result = evaluateGuard({ root, requiredApps: ["customer"] });
      assert.equal(result.ok, false);
      assert.ok(result.failures.includes("missing_build:customer"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails a loopback bundle", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-loop-"));
    try {
      writeBundle(root, "customer", 'export const api="http://127.0.0.1:8000"');
      const result = evaluateGuard({ root, requiredApps: ["customer"] });
      assert.equal(result.ok, false);
      assert.ok(result.failures.includes("bundle:customer"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails loopback in middleware.js and allows CSP API allowlists there", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-mw-"));
    try {
      writeBundle(root, "customer", 'export const api="https://api.vergeo5.com"');
      writeMiddleware(
        root,
        "customer",
        'export const csp="connect-src http://localhost:8000 https://api.vergeo5.com"',
      );
      const loopback = evaluateGuard({
        root,
        requiredApps: ["customer"],
        expectedPlane: "production",
      });
      assert.equal(loopback.ok, false);
      assert.ok(loopback.failures.includes("bundle:customer"));

      writeMiddleware(
        root,
        "customer",
        'export const csp="connect-src https://api.vergeo5.com https://api.staging.vergeo5.com"',
      );
      const csp = evaluateGuard({
        root,
        requiredApps: ["customer"],
        expectedPlane: "production",
      });
      assert.equal(csp.ok, true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails a Preview bundle that targets the production API", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-preview-"));
    try {
      writeBundle(root, "vendor", 'export const api="https://api.vergeo5.com"');
      const result = evaluateGuard({
        root,
        requiredApps: ["vendor"],
        expectedPlane: "preview",
      });
      assert.equal(result.ok, false);
      assert.ok(result.failures.includes("bundle:vendor"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("passes a staging bundle that targets the staging API", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-staging-"));
    try {
      writeBundle(root, "admin", 'export const api="https://api.staging.vergeo5.com"');
      const result = evaluateGuard({
        root,
        requiredApps: ["admin"],
        expectedPlane: "staging",
      });
      assert.equal(result.ok, true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("passes a production bundle that targets the production API", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-prod-"));
    try {
      writeBundle(root, "customer", 'export const api="https://api.vergeo5.com"');
      const result = evaluateGuard({
        root,
        requiredApps: ["customer"],
        expectedPlane: "production",
      });
      assert.equal(result.ok, true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails a production/staging plane mismatch in env or bundle", () => {
    const root = mkdtempSync(join(tmpdir(), "loopback-guard-mismatch-"));
    try {
      writeBundle(root, "customer", 'export const api="https://api.staging.vergeo5.com"');
      const bundle = evaluateGuard({
        root,
        requiredApps: ["customer"],
        expectedPlane: "production",
      });
      assert.equal(bundle.ok, false);
      const env = evaluateGuard({
        root,
        requiredApps: [],
        env: {
          NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
          NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
        },
      });
      assert.equal(env.ok, false);
      assert.ok(env.failures.includes("production_targets_staging_api"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("passes when no frontend apps are in the affected set", () => {
    const result = evaluateGuard({ root: "/tmp/does-not-matter", requiredApps: [] });
    assert.equal(result.ok, true);
    assert.ok(result.messages[0]?.includes("no customer/vendor/admin"));
  });
});

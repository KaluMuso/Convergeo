import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  detectProtectionChallenge,
  exitCodeForProbeVerdict,
  parseBaseUrl,
  probeStagingAccess,
  validateBuildSha,
  validateHealthPayload,
} from "../../ci/e2e-staging-probe.mjs";

describe("e2e-staging-probe base URL guard", () => {
  it("missing URL → FAIL", () => {
    const r = parseBaseUrl("");
    assert.equal(r.ok, false);
  });

  it("localhost → FAIL", () => {
    const r = parseBaseUrl("http://localhost:3000");
    assert.equal(r.ok, false);
    assert.match(r.reason, /localhost/i);
  });

  it("valid staging host → ok", () => {
    const r = parseBaseUrl("https://convergeo-customer-git-staging-vergeo-projects.vercel.app");
    assert.equal(r.ok, true);
    if (r.ok) {
      assert.equal(r.host, "convergeo-customer-git-staging-vergeo-projects.vercel.app");
    }
  });
});

describe("e2e-staging-probe SSO / protection detection", () => {
  it("302 to vercel.com/sso-api → challenge", () => {
    const response = new Response("", {
      status: 302,
      headers: { location: "https://vercel.com/sso-api?url=..." },
    });
    assert.equal(detectProtectionChallenge(response, "Redirecting..."), true);
  });

  it("200 JSON health → not challenge", () => {
    const response = new Response('{"status":"ok"}', { status: 200 });
    assert.equal(detectProtectionChallenge(response, '{"status":"ok"}'), false);
  });
});

describe("e2e-staging-probe health identity", () => {
  it("correct customer health → ok", () => {
    const r = validateHealthPayload({
      status: "ok",
      app: "customer",
      env: "staging",
      buildId: "abc",
    });
    assert.equal(r.ok, true);
  });

  it("wrong app → fail", () => {
    const r = validateHealthPayload({ status: "ok", app: "vendor", env: "staging" });
    assert.equal(r.ok, false);
    assert.match(r.reason, /vendor/);
  });

  it("production env label → fail", () => {
    const r = validateHealthPayload({ status: "ok", app: "customer", env: "production" });
    assert.equal(r.ok, false);
  });
});

describe("e2e-staging-probe SHA proof", () => {
  const sha = "deadbeefcafebabe0123456789abcdef01234567";

  it("matching full SHA → ok", () => {
    const r = validateBuildSha(sha, sha, { strict: true });
    assert.equal(r.ok, true);
  });

  it("matching prefix → ok", () => {
    const r = validateBuildSha(sha.slice(0, 12), sha, { strict: true });
    assert.equal(r.ok, true);
  });

  it("wrong SHA strict → fail", () => {
    const r = validateBuildSha("000000000000", sha, { strict: true });
    assert.equal(r.ok, false);
  });

  it("missing buildId non-strict → skip with warning", () => {
    const r = validateBuildSha("unknown", sha, { strict: false });
    assert.equal(r.ok, true);
    assert.equal(r.skipped, true);
  });

  it("missing buildId strict → fail", () => {
    const r = validateBuildSha("unknown", sha, { strict: true });
    assert.equal(r.ok, false);
  });
});

describe("e2e-staging-probe integrated fetch", () => {
  it("SSO HTML without bypass → BLOCKED_EXTERNAL", async () => {
    const fetchImpl = async () =>
      new Response("Redirecting to https://vercel.com/sso-api", {
        status: 302,
        headers: { location: "https://vercel.com/sso-api?url=..." },
      });

    const r = await probeStagingAccess(
      { E2E_BASE_URL: "https://convergeo-customer-git-staging-vergeo-projects.vercel.app" },
      { fetchImpl },
    );
    assert.equal(r.verdict, "BLOCKED_EXTERNAL");
  });

  it("correct health JSON → PASS", async () => {
    const body = {
      status: "ok",
      app: "customer",
      env: "staging",
      buildId: "deadbeefcafe",
    };
    const fetchImpl = async () => new Response(JSON.stringify(body), { status: 200 });

    const r = await probeStagingAccess(
      {
        E2E_BASE_URL: "https://convergeo-customer-git-staging-vergeo-projects.vercel.app",
        E2E_EXPECT_SHA: "deadbeefcafebabe0123456789abcdef01234567",
      },
      { fetchImpl },
    );
    assert.equal(r.verdict, "PASS");
  });

  it("wrong app JSON → FAIL", async () => {
    const fetchImpl = async () =>
      new Response(JSON.stringify({ status: "ok", app: "admin", env: "staging" }), { status: 200 });

    const r = await probeStagingAccess(
      { E2E_BASE_URL: "https://example-staging.vercel.app" },
      { fetchImpl },
    );
    assert.equal(r.verdict, "FAIL");
  });
});

describe("e2e-staging-probe exit codes", () => {
  it("maps verdicts to process exit codes", () => {
    assert.equal(exitCodeForProbeVerdict("PASS"), 0);
    assert.equal(exitCodeForProbeVerdict("FAIL"), 1);
    assert.equal(exitCodeForProbeVerdict("BLOCKED_EXTERNAL"), 2);
  });
});

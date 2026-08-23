import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  detectProtectionChallenge,
  exitCodeForProbeVerdict,
  parseBaseUrl,
  PORTALS,
  probeStagingAccess,
  resolveBypassSecret,
  resolvePortal,
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

  it("strict + missing env → fail", () => {
    const r = validateHealthPayload(
      { status: "ok", app: "customer", buildId: "abc" },
      { strictEnv: true },
    );
    assert.equal(r.ok, false);
    assert.match(r.reason, /env missing/i);
  });

  it("strict + production env → fail", () => {
    const r = validateHealthPayload(
      { status: "ok", app: "customer", env: "production" },
      { strictEnv: true },
    );
    assert.equal(r.ok, false);
    assert.match(r.reason, /integrated-staging/);
  });

  it("strict + development env → fail", () => {
    const r = validateHealthPayload(
      { status: "ok", app: "customer", env: "development" },
      { strictEnv: true },
    );
    assert.equal(r.ok, false);
    assert.match(r.reason, /integrated-staging/);
  });

  it("strict + preview env → pass", () => {
    const r = validateHealthPayload(
      { status: "ok", app: "customer", env: "preview", buildId: "abc" },
      { strictEnv: true },
    );
    assert.equal(r.ok, true);
  });

  it("strict + staging env → pass", () => {
    const r = validateHealthPayload(
      { status: "ok", app: "customer", env: "staging", buildId: "abc" },
      { strictEnv: true },
    );
    assert.equal(r.ok, true);
  });

  it("non-strict + missing env → pass with envMissing flag", () => {
    const r = validateHealthPayload({ status: "ok", app: "customer", buildId: "abc" });
    assert.equal(r.ok, true);
    assert.equal(r.envMissing, true);
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

  it("strict certification + missing env → FAIL", async () => {
    const fetchImpl = async () =>
      new Response(JSON.stringify({ status: "ok", app: "customer", buildId: "abc" }), {
        status: 200,
      });

    const r = await probeStagingAccess(
      {
        E2E_BASE_URL: "https://convergeo-customer-git-staging-vergeo-projects.vercel.app",
        CERTIFICATION_MODE: "integrated-staging",
      },
      { fetchImpl },
    );
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /env missing/i);
  });

  it("strict certification + staging env → PASS", async () => {
    const fetchImpl = async () =>
      new Response(
        JSON.stringify({ status: "ok", app: "customer", env: "staging", buildId: "deadbeef" }),
        { status: 200 },
      );

    const r = await probeStagingAccess(
      {
        E2E_BASE_URL: "https://convergeo-customer-git-staging-vergeo-projects.vercel.app",
        CERTIFICATION_MODE: "integrated-staging",
        E2E_EXPECT_SHA: "deadbeefcafebabe0123456789abcdef01234567",
      },
      { fetchImpl },
    );
    assert.equal(r.verdict, "PASS");
  });
});

describe("e2e-staging-probe exit codes", () => {
  it("maps verdicts to process exit codes", () => {
    assert.equal(exitCodeForProbeVerdict("PASS"), 0);
    assert.equal(exitCodeForProbeVerdict("FAIL"), 1);
    assert.equal(exitCodeForProbeVerdict("BLOCKED_EXTERNAL"), 2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Multi-portal identity contract (Workstream A).
//
// Playwright navigates the customer AND vendor origins directly, so a release
// baseline must prove BOTH are the expected app on the exact candidate SHA. A
// pass against the wrong origin is worse than a failure, so every degenerate
// target configuration below fails closed in strict mode.
// ─────────────────────────────────────────────────────────────────────────────

const CANDIDATE_SHA = "269877a9454f8037a747e87a69585b62c3f4ffc1";
const CUSTOMER_URL = "https://convergeo-customer-jg7lbgpg4-vergeo-projects.vercel.app";
const VENDOR_URL = "https://convergeo-vendor-4156u34wk-vergeo-projects.vercel.app";
const CUSTOMER_BYPASS = "customer-bypass-secret-value";
const VENDOR_BYPASS = "vendor-bypass-secret-value";
const GENERIC_BYPASS = "generic-bypass-secret-value";

/** Health responder that records the URL + headers each request carried. */
function recordingHealth(bodyByHost, sink) {
  return async (url, init) => {
    const host = new URL(url).hostname;
    sink.push({ url, headers: { ...(init?.headers ?? {}) } });
    const body = bodyByHost[host];
    if (!body) {
      return new Response("not found", { status: 404 });
    }
    return new Response(JSON.stringify(body), { status: 200 });
  };
}

function health(app, sha, env = "staging") {
  return { status: "ok", app, env, buildId: sha, apiHost: "api.staging.vergeo5.com" };
}

function strictEnvFor(overrides = {}) {
  return {
    E2E_BASE_URL: CUSTOMER_URL,
    E2E_VENDOR_BASE_URL: VENDOR_URL,
    E2E_EXPECT_SHA: CANDIDATE_SHA,
    CERTIFICATION_MODE: "integrated-staging",
    ...overrides,
  };
}

describe("e2e-staging-probe portal registry", () => {
  it("knows customer and vendor only — admin has no directly-navigated spec", () => {
    assert.deepEqual(Object.keys(PORTALS).sort(), ["customer", "vendor"]);
    assert.equal(resolvePortal("admin"), null);
  });

  it("unknown portal → FAIL rather than defaulting to customer", async () => {
    const r = await probeStagingAccess(strictEnvFor(), { portal: "admin" });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /unknown portal/i);
  });
});

describe("e2e-staging-probe strict portal identity", () => {
  it("customer on the candidate SHA → PASS", async () => {
    const calls = [];
    const fetchImpl = recordingHealth(
      { [new URL(CUSTOMER_URL).hostname]: health("customer", CANDIDATE_SHA) },
      calls,
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "customer", fetchImpl });
    assert.equal(r.verdict, "PASS");
    assert.equal(r.portal, "customer");
    assert.equal(r.shaVerified, true);
  });

  it("vendor on the candidate SHA → PASS", async () => {
    const calls = [];
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("vendor", CANDIDATE_SHA) },
      calls,
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "PASS");
    assert.equal(r.portal, "vendor");
    assert.equal(r.shaVerified, true);
    assert.equal(new URL(calls[0].url).hostname, new URL(VENDOR_URL).hostname);
  });

  it("customer on a different SHA → FAIL", async () => {
    const fetchImpl = recordingHealth(
      {
        [new URL(CUSTOMER_URL).hostname]: health(
          "customer",
          "0000000000000000000000000000000000000000",
        ),
      },
      [],
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "customer", fetchImpl });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /buildId prefix mismatch/i);
  });

  it("vendor on a different SHA → FAIL (version skew is never a baseline)", async () => {
    const fetchImpl = recordingHealth(
      {
        [new URL(VENDOR_URL).hostname]: health(
          "vendor",
          "0000000000000000000000000000000000000000",
        ),
      },
      [],
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /buildId prefix mismatch/i);
  });

  it("vendor target serving the customer app → FAIL", async () => {
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("customer", CANDIDATE_SHA) },
      [],
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /app=customer want vendor/);
  });

  it("vendor reporting a production plane → FAIL", async () => {
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("vendor", CANDIDATE_SHA, "production") },
      [],
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /integrated-staging/);
  });

  it("vendor buildId missing → FAIL (all three projects expose it)", async () => {
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("vendor", "unknown") },
      [],
    );
    const r = await probeStagingAccess(strictEnvFor(), { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /buildId missing/i);
  });
});

describe("e2e-staging-probe degenerate vendor targets", () => {
  const unreachable = async () => {
    throw new Error("probe must not issue a request for a degenerate target");
  };

  it("missing vendor base in strict mode → FAIL", async () => {
    const env = strictEnvFor({ E2E_VENDOR_BASE_URL: "" });
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl: unreachable });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /E2E_VENDOR_BASE_URL is not set/);
    assert.equal(exitCodeForProbeVerdict(r.verdict), 1);
  });

  it("vendor origin collapsing onto the customer origin in strict mode → FAIL", async () => {
    const env = strictEnvFor({ E2E_VENDOR_BASE_URL: CUSTOMER_URL });
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl: unreachable });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /same origin/i);
  });

  it("missing vendor base in a non-strict run → SKIPPED, exit 0", async () => {
    const env = { E2E_BASE_URL: CUSTOMER_URL, E2E_VENDOR_BASE_URL: "" };
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl: unreachable });
    assert.equal(r.verdict, "SKIPPED");
    assert.equal(exitCodeForProbeVerdict(r.verdict), 0);
  });

  it("non-strict origin collapse → SKIPPED, not a false PASS", async () => {
    const env = { E2E_BASE_URL: CUSTOMER_URL, E2E_VENDOR_BASE_URL: CUSTOMER_URL };
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl: unreachable });
    assert.equal(r.verdict, "SKIPPED");
    assert.notEqual(r.verdict, "PASS");
  });

  it("a malformed vendor base fails even in a non-strict run", async () => {
    const env = { E2E_BASE_URL: CUSTOMER_URL, E2E_VENDOR_BASE_URL: "http://localhost:3001" };
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl: unreachable });
    assert.equal(r.verdict, "FAIL");
    assert.match(r.detail, /localhost/i);
  });
});

describe("e2e-staging-probe bypass secret selection", () => {
  it("each portal prefers its own project secret", () => {
    const env = {
      VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER: CUSTOMER_BYPASS,
      VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR: VENDOR_BYPASS,
      VERCEL_AUTOMATION_BYPASS_SECRET: GENERIC_BYPASS,
    };
    assert.deepEqual(resolveBypassSecret(env, PORTALS.customer), {
      secret: CUSTOMER_BYPASS,
      sourceVar: "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER",
    });
    assert.deepEqual(resolveBypassSecret(env, PORTALS.vendor), {
      secret: VENDOR_BYPASS,
      sourceVar: "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR",
    });
  });

  it("falls back to the repository-wide secret when no project secret is set", () => {
    const env = { VERCEL_AUTOMATION_BYPASS_SECRET: GENERIC_BYPASS };
    assert.deepEqual(resolveBypassSecret(env, PORTALS.vendor), {
      secret: GENERIC_BYPASS,
      sourceVar: "VERCEL_AUTOMATION_BYPASS_SECRET",
    });
  });

  it("no secret configured → empty, with no source claimed", () => {
    assert.deepEqual(resolveBypassSecret({}, PORTALS.vendor), { secret: "", sourceVar: null });
  });

  it("the vendor probe sends the VENDOR project's secret, not the customer's", async () => {
    const calls = [];
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("vendor", CANDIDATE_SHA) },
      calls,
    );
    const env = strictEnvFor({
      VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER: CUSTOMER_BYPASS,
      VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR: VENDOR_BYPASS,
    });
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "PASS");
    assert.equal(calls[0].headers["x-vercel-protection-bypass"], VENDOR_BYPASS);
    assert.notEqual(calls[0].headers["x-vercel-protection-bypass"], CUSTOMER_BYPASS);
    // One-shot request: no cookie handshake, so no redirect to follow.
    assert.equal(calls[0].headers["x-vercel-set-bypass-cookie"], undefined);
  });
});

describe("e2e-staging-probe secret hygiene", () => {
  it("the probe result names the source variable but never carries a secret value", async () => {
    const calls = [];
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("vendor", CANDIDATE_SHA) },
      calls,
    );
    const env = strictEnvFor({ VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR: VENDOR_BYPASS });
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl });

    assert.equal(r.bypassSourceVar, "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR");
    const serialized = JSON.stringify(r);
    assert.ok(!serialized.includes(VENDOR_BYPASS), "bypass secret leaked into probe result");
    assert.ok(!serialized.includes(CUSTOMER_BYPASS));
    assert.ok(!serialized.includes(GENERIC_BYPASS));
  });

  it("a protection challenge names the variables to set, never their values", async () => {
    const fetchImpl = async () =>
      new Response("Redirecting to https://vercel.com/sso-api", {
        status: 302,
        headers: { location: "https://vercel.com/sso-api?url=..." },
      });
    const env = strictEnvFor({ VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR: VENDOR_BYPASS });
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl });

    assert.equal(r.verdict, "BLOCKED_EXTERNAL");
    assert.match(r.detail, /VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR/);
    assert.ok(
      !JSON.stringify(r).includes(VENDOR_BYPASS),
      "bypass secret leaked into challenge detail",
    );
  });

  it("failure details never echo a configured base URL, only its hostname", async () => {
    const secretish = `${VENDOR_URL}/private-path?token=do-not-log`;
    const env = strictEnvFor({ E2E_VENDOR_BASE_URL: secretish });
    const fetchImpl = recordingHealth(
      { [new URL(VENDOR_URL).hostname]: health("vendor", "unknown") },
      [],
    );
    const r = await probeStagingAccess(env, { portal: "vendor", fetchImpl });
    assert.equal(r.verdict, "FAIL");
    const serialized = JSON.stringify(r);
    assert.ok(!serialized.includes("do-not-log"), "query string leaked into probe result");
    assert.ok(!serialized.includes("private-path"), "path leaked into probe result");
    assert.equal(r.host, new URL(VENDOR_URL).hostname);
  });
});

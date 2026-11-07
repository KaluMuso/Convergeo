import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import {
  allowedEmailAcceptanceRequest,
  assertEmailCaptureDisabled,
  assertEmptyEmailContext,
  assertFreshPasswordReceipt,
  isExactPasswordTokenRequest,
  assertExpectedLoginLocation,
  emailAcceptanceConfig,
  isPasswordTokenRequest,
  STAGING_AUTH_ORIGIN,
} from "../../../e2e/email-acceptance/safety.ts";
import { EventEmitter } from "node:events";

import {
  executePlaywright,
  privateEmailEnvironment,
  runEmailAcceptance,
} from "../../ci/run-email-acceptance.mjs";

const ready = {
  E2E_EXPECT_SHA: "a".repeat(40),
  E2E_EMAIL_PROBE_SHA: "a".repeat(40),
  E2E_BASE_URL: "https://convergeo-customer-preview-vergeo-projects.vercel.app",
  E2E_VENDOR_BASE_URL: "https://convergeo-vendor-preview-vergeo-projects.vercel.app",
  E2E_CUSTOMER_EMAIL_PASSWORD: "synthetic-password-1",
  E2E_VENDOR_EMAIL_PASSWORD: "synthetic-password-2",
};

const source = async () => ({ sha: ready.E2E_EXPECT_SHA, clean: true });
const runtime = async () => {};
const pass = (portal) => ({
  verdict: "PASS",
  shaVerified: true,
  shaSkipped: false,
  portal,
  host: new URL(portal === "customer" ? ready.E2E_BASE_URL : ready.E2E_VENDOR_BASE_URL).host,
  env: "staging",
  buildIdPrefix: ready.E2E_EXPECT_SHA.slice(0, 12),
});
const realFetch = globalThis.fetch;
let outboundCalls = 0;
globalThis.fetch = () => {
  outboundCalls++;
  throw new Error("offline suite forbids fetch");
};
after(() => {
  globalThis.fetch = realFetch;
  assert.equal(outboundCalls, 0);
});
const identity = "00000000-0000-4000-8000-000000000001";
const now = 1700000000;
function token(changes = {}) {
  const claims = {
    iss: `${STAGING_AUTH_ORIGIN}/auth/v1`,
    sub: identity,
    aud: "authenticated",
    iat: now - 1,
    exp: now + 60,
    ...changes,
  };
  return `fixture.${Buffer.from(JSON.stringify(claims)).toString("base64url")}.fixture`;
}
function receipt(changes = {}) {
  return {
    access_token: token(),
    token_type: "bearer",
    expires_in: 60,
    user: { id: identity, email: emailAcceptanceConfig(ready).customer.email },
    ...changes,
  };
}

describe("email-only staging diagnostic", () => {
  it("binds fixed synthetic accounts and separate staging origins", () => {
    const config = emailAcceptanceConfig(ready);
    assert.match(config.customer.email, /^stg-rv-.*@staging\.vergeo5\.test$/);
    assert.match(config.vendor.email, /^stg-rv-.*@staging\.vergeo5\.test$/);
    assert.notEqual(config.customer.origin, config.vendor.origin);
  });

  it("rejects missing credentials, SHA, and non-staging origins before navigation", () => {
    for (const input of [
      { ...ready, E2E_EXPECT_SHA: "" },
      { ...ready, E2E_EMAIL_PROBE_SHA: "" },
      { ...ready, E2E_EMAIL_PROBE_SHA: "b".repeat(40) },
      { ...ready, E2E_CUSTOMER_EMAIL_PASSWORD: "" },
      { ...ready, E2E_VENDOR_EMAIL_PASSWORD: "" },
      { ...ready, E2E_BASE_URL: "https://www.vergeo5.com" },
      { ...ready, E2E_VENDOR_BASE_URL: "https://example.com" },
      { ...ready, E2E_VENDOR_BASE_URL: "https://attacker.vercel.app" },
      { ...ready, E2E_VENDOR_BASE_URL: ready.E2E_BASE_URL },
    ]) {
      assert.throws(() => emailAcceptanceConfig(input));
    }
  });

  it("allows only exact staging Auth password exchange and non-sensitive assets", () => {
    const portal = ready.E2E_BASE_URL;
    const allowed = (target, method = "GET", type = "fetch") =>
      allowedEmailAcceptanceRequest(new URL(target), method, type, portal);
    assert.equal(allowed(`${portal}/en/login`, "GET", "document"), true);
    assert.equal(allowed(`${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=password`, "POST"), true);
    assert.equal(allowed(`${STAGING_AUTH_ORIGIN}/auth/v1/user`), true);
    assert.equal(allowed("https://fonts.gstatic.com/font.woff2", "GET", "font"), true);
    assert.equal(allowed("https://res.cloudinary.com/demo/image.jpg", "GET", "image"), true);
    assert.equal(
      allowedEmailAcceptanceRequest(
        new URL("https://res.cloudinary.com/demo/image.jpg"),
        "GET",
        "image",
        portal,
        false,
      ),
      false,
    );
    assert.equal(allowed("https://fonts.gstatic.com/script.js", "GET", "script"), false);
    for (const target of [
      `${STAGING_AUTH_ORIGIN}/auth/v1/otp`,
      `${STAGING_AUTH_ORIGIN}/functions/v1/send-sms-otp`,
      "https://api.sandbox.lenco.co/access/v2/collections",
      "https://api.africastalking.com/version1/messaging",
      "https://api.staging.vergeo5.com/orders",
      "https://api.staging.vergeo5.com/internal/dispatch/tick",
      "https://dpadrlxukcjbewpqympu.supabase.co/auth/v1/token?grant_type=password",
      "https://www.vergeo5.com/en/login",
    ]) {
      assert.equal(allowed(target, "POST"), false, target);
    }
    assert.equal(
      allowed(`${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=refresh_token`, "POST"),
      false,
    );
  });

  it("rejects redirected login before either credential is filled", () => {
    assert.doesNotThrow(() =>
      assertExpectedLoginLocation(
        `${ready.E2E_BASE_URL}/en/login?next=%2Fen%2Faccount`,
        ready.E2E_BASE_URL,
      ),
    );
    assert.throws(() =>
      assertExpectedLoginLocation("https://www.vergeo5.com/en/login", ready.E2E_BASE_URL),
    );
    assert.throws(() =>
      assertExpectedLoginLocation(`${ready.E2E_BASE_URL}/en/otp`, ready.E2E_BASE_URL),
    );
  });

  it("recognizes only password token requests for the intercepted dummy probe", () => {
    assert.equal(
      isPasswordTokenRequest(
        new URL(`${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=password`),
        "POST",
      ),
      true,
    );
    assert.equal(
      isPasswordTokenRequest(new URL(`${STAGING_AUTH_ORIGIN}/auth/v1/otp`), "POST"),
      false,
    );
  });

  it("refuses missing or wrong-SHA portal proof without launching Playwright", async () => {
    for (const outcome of [null, { verdict: "FAIL" }, { verdict: "PASS", shaVerified: false }]) {
      let launched = 0;
      await assert.rejects(
        runEmailAcceptance(ready, {
          verifySource: source,
          runtime,
          probe: async () => outcome,
          execute: async () => {
            launched += 1;
            return 0;
          },
        }),
        /private details suppressed/,
      );
      assert.equal(launched, 0);
    }
  });

  it("launches only after both strict portal probes pass", async () => {
    const portals = [];
    let launched = 0;
    const exitCode = await runEmailAcceptance(ready, {
      verifySource: source,
      runtime,
      probe: async (env, { portal }) => {
        assert.equal(env.E2E_STRICT_SHA, "true");
        portals.push(portal);
        return pass(portal);
      },
      execute: async (env) => {
        launched += 1;
        assert.equal(env.E2E_EMAIL_PROBE_SHA, ready.E2E_EXPECT_SHA);
        return 0;
      },
    });
    assert.deepEqual(portals, ["customer", "vendor"]);
    assert.equal(launched, 1);
    assert.equal(exitCode, 0);
  });
});

describe("private diagnostic failure boundaries", () => {
  it("requires snapshot suppression and rejects all inherited session state", () => {
    assert.throws(() => assertEmailCaptureDisabled({}));
    assertEmailCaptureDisabled({ PLAYWRIGHT_NO_COPY_PROMPT: "1" });
    assertEmptyEmailContext({ cookies: [], origins: [] });
    for (const state of [
      { cookies: [{ value: "private-session" }], origins: [] },
      { cookies: [], origins: [{ localStorage: "private-session" }] },
    ]) {
      assert.throws(
        () => assertEmptyEmailContext(state),
        (error) => !error.message.includes("private-session"),
      );
    }
  });

  it("accepts a consistent unexpired password receipt without granting authority", () => {
    assertFreshPasswordReceipt(receipt(), emailAcceptanceConfig(ready).customer.email, now);
  });

  it("rejects expired, invalid, wrong-plane and mismatched identity receipts without private values", () => {
    const email = emailAcceptanceConfig(ready).customer.email;
    const sentinel = "never-print-private-session";
    for (const raw of [
      null,
      {},
      { message: sentinel },
      receipt({ access_token: sentinel }),
      receipt({ access_token: token({ exp: now }) }),
      receipt({ access_token: token({ iss: "https://wrong.supabase.co/auth/v1" }) }),
      receipt({ access_token: token({ sub: "other-user" }) }),
      receipt({ access_token: token({ aud: "anon" }) }),
      receipt({ access_token: token({ iat: now + 61 }) }),
      receipt({ access_token: token({ iat: now - 61 }) }),
      receipt({ expires_in: Infinity }),
      receipt({ access_token: token({ exp: "tomorrow" }) }),
      receipt({ expires_in: 0 }),
      receipt({ token_type: "other" }),
      receipt({ user: { id: identity, email: "other@example.test" } }),
    ]) {
      assert.throws(
        () => assertFreshPasswordReceipt(raw, email, now),
        (error) =>
          error.message === "email diagnostic did not receive a fresh staging password session",
      );
    }
  });

  it("blocks encoded financial paths, recovery reads and credential URL channels", () => {
    for (const target of [
      `${ready.E2E_BASE_URL}/en/orders`,
      `${ready.E2E_BASE_URL}/en/reset-password`,
      "https://api.staging.vergeo5.com/%6frders",
      "https://api.staging.vergeo5.com/vendor/payouts",
      `${STAGING_AUTH_ORIGIN}/auth/v1/recover`,
      `${STAGING_AUTH_ORIGIN}/auth/v1/logout`,
      `${ready.E2E_BASE_URL}/en/login?password=private`,
      `${ready.E2E_BASE_URL}/en/login#private`,
      `${ready.E2E_BASE_URL.replace("https://", "https://private@")}/en/login`,
      `${ready.E2E_BASE_URL}:444/en/login`,
    ])
      assert.equal(
        allowedEmailAcceptanceRequest(new URL(target), "GET", "fetch", ready.E2E_BASE_URL),
        false,
      );
    assert.equal(
      allowedEmailAcceptanceRequest(
        new URL("https://api.staging.vergeo5.com/vendor/services"),
        "GET",
        "fetch",
        ready.E2E_VENDOR_BASE_URL,
      ),
      true,
    );
  });

  it("requires exactly the password grant on the pinned Auth endpoint", () => {
    assert.equal(
      isExactPasswordTokenRequest(
        new URL(`${STAGING_AUTH_ORIGIN}/auth/v1/token?grant_type=password`),
        "POST",
      ),
      true,
    );
    for (const suffix of [
      "?grant_type=password&grant_type=password",
      "?grant_type=password&redirect_to=x",
      "?grant_type=refresh_token",
      "?grant_type=password#x",
    ]) {
      assert.equal(
        isExactPasswordTokenRequest(
          new URL(`${STAGING_AUTH_ORIGIN}/auth/v1/token${suffix}`),
          "POST",
        ),
        false,
      );
    }
    assert.equal(
      isExactPasswordTokenRequest(
        new URL("https://wrong.supabase.co/auth/v1/token?grant_type=password"),
        "POST",
      ),
      false,
    );
  });

  it("does not inherit debug hooks, arbitrary credentials or phone activation", () => {
    const privateEnv = privateEmailEnvironment({
      ...ready,
      DEBUG: "pw:*",
      PWDEBUG: "1",
      NODE_OPTIONS: "untrusted",
      SUPABASE_SERVICE_ROLE_KEY: "private",
      SMS_OTP_TRANSPORT: "waha",
      WAHA_OTP_READY: "true",
      VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER: "customer-fixture",
      VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR: "vendor-fixture",
    });
    for (const key of ["DEBUG", "PWDEBUG", "NODE_OPTIONS", "SUPABASE_SERVICE_ROLE_KEY"])
      assert.equal(key in privateEnv, false);
    assert.equal(privateEnv.PLAYWRIGHT_NO_COPY_PROMPT, "1");
    assert.equal(privateEnv.SMS_OTP_TRANSPORT, "disabled");
    assert.equal(privateEnv.WAHA_OTP_READY, "false");
    assert.equal(privateEnv.CERTIFICATION_MODE, "diagnostic-staging");
    assert.equal(privateEnv.VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER, "customer-fixture");
    assert.equal(privateEnv.VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR, "vendor-fixture");
  });

  it("keeps child output private and normalizes launch failures", async () => {
    for (const event of ["error", "exit"]) {
      const code = executePlaywright(privateEmailEnvironment(ready), (_command, args, options) => {
        assert.deepEqual(args, ["test", "--config=playwright.email-acceptance.config.ts"]);
        assert.equal(options.stdio, "ignore");
        assert.equal(options.shell, false);
        const child = new EventEmitter();
        queueMicrotask(() =>
          child.emit(event, event === "error" ? new Error("private-password") : 0),
        );
        return child;
      });
      if (event === "error")
        await assert.rejects(
          code,
          (error) => error.message === "private email diagnostic could not start",
        );
      else assert.equal(await code, 0);
    }
  });

  it("requires exact checkout identity and clean source before any portal call", async () => {
    for (const proof of [
      null,
      { sha: "b".repeat(40), clean: true },
      { sha: ready.E2E_EXPECT_SHA, clean: false },
    ]) {
      let probes = 0;
      await assert.rejects(
        runEmailAcceptance(ready, {
          verifySource: async () => proof,
          runtime,
          probe: async () => {
            probes++;
          },
          execute: async () => 0,
        }),
      );
      assert.equal(probes, 0);
    }
  });

  it("rejects mismatched portal receipts before browser start", async () => {
    for (const changes of [
      { portal: "admin" },
      { host: "wrong.example.test" },
      { env: "production" },
      { buildIdPrefix: "b".repeat(12) },
      { shaSkipped: true },
      { shaSkipped: undefined },
    ]) {
      let launches = 0;
      await assert.rejects(
        runEmailAcceptance(ready, {
          verifySource: source,
          runtime,
          probe: async (_env, { portal }) => ({ ...pass(portal), ...changes }),
          execute: async () => {
            launches++;
            return 0;
          },
        }),
      );
      assert.equal(launches, 0);
    }
  });

  it("rechecks source before and after browser execution", async () => {
    for (const failAt of [2, 3]) {
      let proofs = 0,
        launches = 0;
      await assert.rejects(
        runEmailAcceptance(ready, {
          verifySource: async () => ({
            sha: ++proofs === failAt ? "b".repeat(40) : ready.E2E_EXPECT_SHA,
            clean: true,
          }),
          runtime,
          probe: async (_env, { portal }) => pass(portal),
          execute: async () => {
            launches++;
            return 0;
          },
        }),
      );
      assert.equal(launches, failAt === 2 ? 0 : 1);
    }
  });

  it("redacts raw source, probe, runtime and execution failures", async () => {
    for (const stage of ["verifySource", "probe", "runtime", "execute"]) {
      const options = {
        verifySource: source,
        runtime,
        probe: async (_env, { portal }) => pass(portal),
        execute: async () => 0,
      };
      options[stage] = async () => {
        throw new Error("private-password private-token private-body");
      };
      await assert.rejects(
        runEmailAcceptance(ready, options),
        (error) =>
          error.message === "email/password diagnostic failed; private details suppressed" &&
          !error.cause,
      );
    }
  });

  it("refuses invalid input before source or portal operations", async () => {
    let operations = 0;
    await assert.rejects(
      runEmailAcceptance(
        { ...ready, E2E_CUSTOMER_EMAIL_PASSWORD: "" },
        {
          verifySource: async () => {
            operations++;
          },
          probe: async () => {
            operations++;
          },
          execute: async () => {
            operations++;
          },
        },
      ),
    );
    assert.equal(operations, 0);
  });

  it("returns failure for a nonzero or ambiguous private child exit", async () => {
    for (const exit of [1, 42, null, undefined]) {
      assert.equal(
        await runEmailAcceptance(ready, {
          verifySource: source,
          runtime,
          probe: async (_env, { portal }) => pass(portal),
          execute: async () => exit,
        }),
        1,
      );
    }
  });
});

it("binds receipt issuance to the password attempt with bounded clock skew", () => {
  const email = emailAcceptanceConfig(ready).customer.email;
  assertFreshPasswordReceipt(
    receipt({ access_token: token({ iat: now - 60 }) }),
    email,
    now + 20,
    now,
  );
  assert.throws(() =>
    assertFreshPasswordReceipt(
      receipt({ access_token: token({ iat: now - 61 }) }),
      email,
      now + 20,
      now,
    ),
  );
  assert.throws(() => assertFreshPasswordReceipt(receipt(), email, now + 61, now));
});

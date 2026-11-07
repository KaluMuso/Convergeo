import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { SEED } from "../../../e2e/fixtures/seed.generated.ts";
import {
  evaluatePhoneOtpSafety,
  evaluatePreflightConfig,
  runPreflight,
} from "../../ci/preflight-e2e-test-otp.mjs";

const originalFetch = globalThis.fetch;
let unexpectedNetworkCalls = 0;
globalThis.fetch = async () => {
  unexpectedNetworkCalls++;
  throw new Error("external I/O is forbidden in these helper tests");
};
after(() => {
  globalThis.fetch = originalFetch;
  assert.equal(unexpectedNetworkCalls, 0, "helper tests attempted external I/O");
});

const CUSTOMER_OTP = "111111";
const VENDOR_OTP = "222222";
const CUSTOMER_ID = "a1000000-0000-4000-8000-000000000001";
const VENDOR_ID = "a1000000-0000-4000-8000-000000000004";

function sessionFor(phone, overrides = {}) {
  const customer = phone === SEED.personas.customer.phone;
  const user = { id: customer ? CUSTOMER_ID : VENDOR_ID, phone, ...overrides.user };
  const claims = {
    sub: user.id,
    phone,
    aud: "authenticated",
    app_metadata: { roles: [customer ? "customer" : "vendor"] },
    ...overrides.claims,
  };
  const token = `${Buffer.from("{}").toString("base64url")}.${Buffer.from(JSON.stringify(claims)).toString("base64url")}.signature`;
  return { user, access_token: token, ...overrides.session };
}
const ATTESTED = {
  // Run-scoped outbound approval for the synthetic recipients and sandbox target.
  STAGING_SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  STAGING_SUPABASE_PROJECT_ID: "iyasmrmbcrvlfxpzescb",
  E2E_OTP_RECIPIENT_APPROVED: "1",
  E2E_APPROVED_CUSTOMER_PHONE: SEED.personas.customer.phone,
  E2E_APPROVED_VENDOR_PHONE: SEED.personas.vendor.phone,
  GITHUB_RUN_ID: "1234",
  GITHUB_RUN_ATTEMPT: "2",
  E2E_APPROVED_RUN_ID: "1234",
  E2E_APPROVED_RUN_ATTEMPT: "2",
  E2E_STAGING_SETUP: "true",
  E2E_STRICT_SHA: "true",
  E2E_EXPECT_SHA: "a".repeat(40),
  GITHUB_SHA: "a".repeat(40),
  SMS_OTP_TRANSPORT: "waha",
  WAHA_OTP_ENABLED: "true",
  STAGING_SMS_SANDBOX_ATTESTED: "true",
  STAGING_TEST_OTP_MAP_ATTESTED: "true",
};

function personasFromEnv(env) {
  return [
    {
      label: "customer",
      phone: SEED.personas.customer.phone,
      otp: env.E2E_CUSTOMER_TEST_OTP ?? "",
      otpEnv: "E2E_CUSTOMER_TEST_OTP",
    },
    {
      label: "vendor",
      phone: SEED.personas.vendor.phone,
      otp: env.E2E_VENDOR_TEST_OTP ?? "",
      otpEnv: "E2E_VENDOR_TEST_OTP",
    },
  ];
}

describe("preflight config — strict both personas required", () => {
  it("both configured → READY", () => {
    const verdict = evaluatePreflightConfig(
      personasFromEnv({
        E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
        E2E_VENDOR_TEST_OTP: VENDOR_OTP,
      }),
      { strict: true },
    );
    assert.equal(verdict.verdict, "READY");
    assert.equal(verdict.configured.length, 2);
  });

  it("neither configured → FAIL in strict mode", () => {
    const verdict = evaluatePreflightConfig(personasFromEnv({}), {
      strict: true,
    });
    assert.equal(verdict.verdict, "FAIL");
    assert.match(verdict.detail, /both OTP secrets/);
  });

  it("customer only → FAIL", () => {
    const verdict = evaluatePreflightConfig(
      personasFromEnv({ E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP }),
      { strict: true },
    );
    assert.equal(verdict.verdict, "FAIL");
    assert.match(verdict.detail, /E2E_VENDOR_TEST_OTP/);
  });

  it("vendor only → FAIL", () => {
    const verdict = evaluatePreflightConfig(personasFromEnv({ E2E_VENDOR_TEST_OTP: VENDOR_OTP }), {
      strict: true,
    });
    assert.equal(verdict.verdict, "FAIL");
    assert.match(verdict.detail, /E2E_CUSTOMER_TEST_OTP/);
  });

  it("one OTP missing in non-strict partial config → FAIL", () => {
    const verdict = evaluatePreflightConfig(
      personasFromEnv({ E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP }),
      { strict: false },
    );
    assert.equal(verdict.verdict, "FAIL");
    assert.match(verdict.detail, /partial OTP configuration/);
  });
});

describe("preflight verify — mocked Supabase Auth", () => {
  it("rejects missing or partial attestations before any OTP request", async () => {
    for (const attestations of [
      {},
      { STAGING_SMS_SANDBOX_ATTESTED: "true" },
      { STAGING_TEST_OTP_MAP_ATTESTED: "true" },
      { ...ATTESTED, STAGING_SMS_SANDBOX_ATTESTED: "yes" },
    ]) {
      let requests = 0;
      const result = await runPreflight(
        {
          SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
          SUPABASE_ANON_KEY: "anon-key",
          E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
          E2E_VENDOR_TEST_OTP: VENDOR_OTP,
          CERTIFICATION_MODE: "integrated-staging",
          SMS_OTP_TRANSPORT: "waha",
          WAHA_OTP_ENABLED: "true",
          ...attestations,
        },
        {
          fetchImpl: async () => {
            requests += 1;
            throw new Error("OTP request must not occur");
          },
        },
      );
      assert.equal(result.verdict, "FAIL");
      assert.match(result.detail, /owner attestations required/);
      assert.equal(requests, 0);
    }
    assert.equal(evaluatePhoneOtpSafety(ATTESTED).verdict, "READY");
  });

  it("both valid → PASS", async () => {
    const fetchImpl = async (url, init) => {
      const target = String(url);
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      if (target.endsWith("/auth/v1/verify")) {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const expected = body.phone === SEED.personas.customer.phone ? CUSTOMER_OTP : VENDOR_OTP;
        if (body.token === expected) {
          return new Response(
            JSON.stringify(sessionFor(body.phone)),
            { status: 200 },
          );
        }
        return new Response("invalid", { status: 400 });
      }
      return new Response("not found", { status: 404 });
    };

    const result = await runPreflight(
      {
        SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
        SUPABASE_ANON_KEY: "anon-key",
        E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
        E2E_VENDOR_TEST_OTP: VENDOR_OTP,
        CERTIFICATION_MODE: "integrated-staging",
        ...ATTESTED,
      },
      { fetchImpl, strict: true },
    );

    assert.equal(result.verdict, "PASS");
    assert.equal(result.results?.length, 2);
  });

  it("wrong OTP → FAIL", async () => {
    const fetchImpl = async (url) => {
      const target = String(url);
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      return new Response("invalid", { status: 400 });
    };

    const result = await runPreflight(
      {
        SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
        SUPABASE_ANON_KEY: "anon-key",
        E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
        E2E_VENDOR_TEST_OTP: VENDOR_OTP,
        CERTIFICATION_MODE: "integrated-staging",
        ...ATTESTED,
      },
      { fetchImpl, strict: true },
    );

    assert.equal(result.verdict, "FAIL");
    assert.match(result.detail, /test-OTP verify failed/);
  });

  it("never logs OTP values", async () => {
    const lines = [];
    const originalLog = console.log;
    console.log = (...args) => {
      lines.push(args.join(" "));
    };

    const fetchImpl = async (url, init) => {
      const target = String(url);
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      const body = JSON.parse(init.body);
      return new Response(
        JSON.stringify(sessionFor(body.phone)),
        { status: 200 },
      );
    };

    try {
      await runPreflight(
        {
          SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
          SUPABASE_ANON_KEY: "anon-key",
          E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
          E2E_VENDOR_TEST_OTP: VENDOR_OTP,
          CERTIFICATION_MODE: "integrated-staging",
          ...ATTESTED,
        },
        { fetchImpl, strict: true },
      );
    } finally {
      console.log = originalLog;
    }

    const serialized = lines.join("\n");
    assert.equal(serialized.includes(CUSTOMER_OTP), false);
    assert.equal(serialized.includes(VENDOR_OTP), false);
  });
});

const SAFE_ENV = {
  SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  SUPABASE_ANON_KEY: "synthetic-anon-key",
  E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
  E2E_VENDOR_TEST_OTP: VENDOR_OTP,
  CERTIFICATION_MODE: "integrated-staging",
  ...ATTESTED,
};
const session = (phone) => sessionFor(phone);

describe("phone preflight safety and confirmation", () => {
  it("an invalid later persona fails before any earlier persona is sent", async () => {
    const original = SEED.personas.vendor.phone;
    let calls = 0;
    try {
      SEED.personas.vendor.phone = "raw-private-marker";
      // Canonical persona metadata is captured at module load; import a fresh
      // test instance while the synthetic fixture is deliberately malformed.
      const isolated = await import("../../ci/preflight-e2e-test-otp.mjs?invalid-later-fixture");
      const result = await isolated.runPreflight(
        { ...SAFE_ENV },
        {
          fetchImpl: () => {
            calls++;
            throw Error("network");
          },
        },
      );
      assert.equal(result.verdict, "FAIL");
      assert.equal(calls, 0);
      assert.equal(JSON.stringify(result).includes("raw-private-marker"), false);
    } finally {
      SEED.personas.vendor.phone = original;
    }
  });

  it("disabled, missing, implicit or paid transport declarations send nothing", async () => {
    for (const change of [
      { SMS_OTP_TRANSPORT: "" },
      { SMS_OTP_TRANSPORT: "disabled" },
      { SMS_OTP_TRANSPORT: "africas_talking" },
      { WAHA_OTP_ENABLED: "false" },
      { WAHA_OTP_ENABLED: "yes" },
    ]) {
      let calls = 0;
      const result = await runPreflight(
        { ...SAFE_ENV, ...change },
        {
          fetchImpl: () => {
            calls++;
            throw Error("network");
          },
        },
      );
      assert.equal(result.verdict, "FAIL");
      assert.equal(calls, 0);
    }
  });
  it("missing and malformed codes fail before any request without leaking configuration", async () => {
    for (const code of ["", "12345", "1234567", "bad-code-marker"]) {
      let calls = 0;
      const result = await runPreflight(
        { ...SAFE_ENV, E2E_VENDOR_TEST_OTP: code },
        {
          fetchImpl: () => {
            calls++;
            throw Error("network");
          },
        },
      );
      assert.equal(result.verdict, "FAIL");
      assert.equal(calls, 0);
      assert.equal(JSON.stringify(result).includes(CUSTOMER_OTP), false);
      assert.equal(JSON.stringify(result).includes("bad-code-marker"), false);
    }
  });
  it("non-staging targets and credentials in URLs are denied before sending", async () => {
    for (const url of [
      "https://example.supabase.co",
      "http://iyasmrmbcrvlfxpzescb.supabase.co",
      "https://user:synthetic-marker@iyasmrmbcrvlfxpzescb.supabase.co",
      "https://iyasmrmbcrvlfxpzescb.supabase.co/?secret=synthetic-marker",
    ]) {
      let calls = 0;
      const result = await runPreflight(
        { ...SAFE_ENV, SUPABASE_URL: url },
        {
          fetchImpl: () => {
            calls++;
            throw Error("network");
          },
        },
      );
      assert.equal(result.verdict, "FAIL");
      assert.equal(calls, 0);
      assert.equal(JSON.stringify(result).includes("synthetic-marker"), false);
    }
  });
  it("delivery acceptance alone cannot confirm an empty or mismatched Auth result", async () => {
    for (const body of [
      {},
      { access_token: "synthetic-access-token" },
      session(SEED.personas.vendor.phone),
    ]) {
      let calls = 0;
      const result = await runPreflight(
        { ...SAFE_ENV },
        {
          fetchImpl: async () =>
            new Response(JSON.stringify(++calls === 1 ? {} : body), { status: 200 }),
        },
      );
      assert.equal(result.verdict, "FAIL");
      assert.equal(result.results[0].deliveryAccepted, true);
      assert.equal(result.results[0].confirmed, false);
      assert.equal(calls, 2);
      assert.equal(JSON.stringify(result).includes("synthetic-access-token"), false);
    }
  });
  it("invalid and expired requests expose only safe structured codes", async () => {
    for (const [code, expected] of [
      ["otp_expired", "expired"],
      ["invalid_credentials", "invalid"],
      ["over_sms_send_rate_limit", "throttled"],
      ["synthetic-private-marker", "rejected"],
    ]) {
      let calls = 0;
      const result = await runPreflight(
        { ...SAFE_ENV },
        {
          fetchImpl: async () =>
            ++calls === 1
              ? new Response("{}", { status: 200 })
              : new Response(JSON.stringify({ error_code: code, message: "raw-secret-marker" }), {
                  status: 400,
                }),
        },
      );
      assert.equal(result.results[0].errorCode, expected);
      assert.equal(result.results[0].confirmed, false);
      assert.equal(JSON.stringify(result).includes("raw-secret-marker"), false);
      assert.equal(JSON.stringify(result).includes("synthetic-private-marker"), false);
    }
  });
  it("repeated submissions share one attempt and retain the sanitized confirmation", async () => {
    const env = { ...SAFE_ENV };
    let calls = 0;
    const fetchImpl = async (url, init) => {
      calls++;
      const body = JSON.parse(init.body);
      assert.equal(init.redirect, "error");
      assert.equal(init.cache, "no-store");
      assert.ok(init.signal instanceof AbortSignal);
      return new Response(JSON.stringify(String(url).endsWith("/otp") ? {} : session(body.phone)), {
        status: 200,
      });
    };
    const [one, two] = await Promise.all([
      runPreflight(env, { fetchImpl }),
      runPreflight(env, { fetchImpl }),
    ]);
    assert.deepEqual(one, two);
    assert.equal(one.verdict, "PASS");
    assert.equal(calls, 4);
    assert.deepEqual(await runPreflight(env, { fetchImpl }), one);
    assert.equal(calls, 4);
  });
  it("interrupted accepted requests cannot trigger a resend on resume", async () => {
    const env = { ...SAFE_ENV };
    let calls = 0;
    const fetchImpl = async () => {
      if (++calls === 1) return new Response("{}", { status: 200 });
      throw Error("raw-secret-marker");
    };
    const first = await runPreflight(env, { fetchImpl });
    const resumed = await runPreflight(env, { fetchImpl });
    assert.equal(first.results[0].deliveryAccepted, true);
    assert.equal(first.results[0].confirmed, false);
    assert.equal(first.results[0].errorCode, "interrupted");
    assert.deepEqual(resumed, first);
    assert.equal(calls, 2);
    assert.equal(JSON.stringify(first).includes("raw-secret-marker"), false);
  });
  it("send rejection never advances to verification or another persona", async () => {
    let calls = 0;
    const result = await runPreflight(
      { ...SAFE_ENV },
      {
        fetchImpl: async () => {
          calls++;
          return new Response("raw-secret-marker", { status: 500 });
        },
      },
    );
    assert.equal(calls, 1);
    assert.equal(result.results[0].deliveryAccepted, false);
    assert.equal(result.results[0].confirmed, false);
    assert.equal(JSON.stringify(result).includes("raw-secret-marker"), false);
  });
});

describe("phone preflight canonical identity binding", () => {
  it("vendor login fails when the role hook returns only a customer role", async () => {
    const calls = [];
    const result = await runPreflight(
      { ...SAFE_ENV },
      {
        strict: true,
        fetchImpl: async (url, init) => {
          calls.push(String(url));
          if (String(url).endsWith("/auth/v1/otp")) return Response.json({});
          const { phone } = JSON.parse(String(init.body));
          return Response.json(
            phone === SEED.personas.vendor.phone
              ? sessionFor(phone, { claims: { app_metadata: { roles: ["customer"] } } })
              : sessionFor(phone),
          );
        },
      },
    );
    assert.equal(result.verdict, "FAIL");
    assert.match(result.detail, /^vendor: test-OTP verify failed/);
    assert.deepEqual(
      calls.map((url) => new URL(url).pathname),
      ["/auth/v1/otp", "/auth/v1/verify", "/auth/v1/otp", "/auth/v1/verify"],
    );
  });

  it("a session for another synthetic account cannot confirm the customer", async () => {
    const result = await runPreflight(
      { ...SAFE_ENV },
      {
        strict: true,
        fetchImpl: async (url, init) => {
          if (String(url).endsWith("/auth/v1/otp")) return Response.json({});
          const { phone } = JSON.parse(String(init.body));
          return Response.json(sessionFor(phone, { claims: { sub: VENDOR_ID } }));
        },
      },
    );
    assert.equal(result.verdict, "FAIL");
    assert.match(result.detail, /^customer: test-OTP verify failed/);
  });

  it("accepts the hosted Auth phone form without the optional leading plus", async () => {
    const result = await runPreflight(
      { ...SAFE_ENV },
      {
        strict: true,
        fetchImpl: async (url, init) => {
          if (String(url).endsWith("/auth/v1/otp")) return Response.json({});
          const { phone } = JSON.parse(String(init.body));
          const stored = phone.replace(/^\+/, "");
          return Response.json(
            sessionFor(phone, { user: { phone: stored }, claims: { phone: stored } }),
          );
        },
      },
    );
    assert.equal(result.verdict, "PASS");
  });

  it("run-scoped recipient approval is required before any OTP is sent", async () => {
    let calls = 0;
    const { E2E_OTP_RECIPIENT_APPROVED: _approved, ...unapproved } = SAFE_ENV;
    const result = await runPreflight(unapproved, {
      strict: true,
      fetchImpl: async () => {
        calls++;
        return Response.json({});
      },
    });
    assert.equal(result.verdict, "FAIL");
    assert.match(result.detail, /outbound OTP approval required/);
    assert.equal(calls, 0);
  });
});

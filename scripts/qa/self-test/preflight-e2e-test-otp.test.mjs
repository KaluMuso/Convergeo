import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { SEED } from "../../../e2e/fixtures/seed.generated.ts";
import { evaluatePreflightConfig, runPreflight } from "../../ci/preflight-e2e-test-otp.mjs";

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
const approvedEnv = (overrides = {}) => ({
  SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  STAGING_SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  STAGING_SUPABASE_PROJECT_ID: "iyasmrmbcrvlfxpzescb",
  SUPABASE_ANON_KEY: "anon-key",
  E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
  E2E_VENDOR_TEST_OTP: VENDOR_OTP,
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
  CERTIFICATION_MODE: "integrated-staging",
  ...overrides,
});

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
      personasFromEnv({ E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP, E2E_VENDOR_TEST_OTP: VENDOR_OTP }),
      { strict: true },
    );
    assert.equal(verdict.verdict, "READY");
    assert.equal(verdict.configured.length, 2);
  });

  it("neither configured → FAIL in strict mode", () => {
    const verdict = evaluatePreflightConfig(personasFromEnv({}), { strict: true });
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
  it("both valid → PASS", async () => {
    const fetchImpl = async (url, init) => {
      const target = String(url);
      assert.equal(init?.redirect, "error");
      assert.ok(target.startsWith("https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/"));
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      if (target.endsWith("/auth/v1/verify")) {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const expected = body.phone === SEED.personas.customer.phone ? CUSTOMER_OTP : VENDOR_OTP;
        if (body.token === expected) {
          return Response.json(sessionFor(body.phone));
        }
        return new Response("invalid", { status: 400 });
      }
      return new Response("not found", { status: 404 });
    };

    const result = await runPreflight(approvedEnv(), { fetchImpl, strict: true });

    assert.equal(result.verdict, "PASS");
    assert.equal(result.results?.length, 2);
  });

  it("canonical user IDs remain aligned with the synthetic fixture source", () => {
    const contract = readFileSync(
      new URL("../../../services/api/app/staging/synthetic_contract.py", import.meta.url),
      "utf8",
    );
    for (const [key, id] of [
      ["CUSTOMER_A", CUSTOMER_ID],
      ["APPROVED_VENDOR_A", VENDOR_ID],
    ]) {
      const actual = contract.match(new RegExp(`key="${key}"[\\s\\S]*?user_id="([^"]+)"`))?.[1];
      assert.equal(actual, id);
    }
  });

  it("accepts the hosted Auth phone form without the optional leading plus", async () => {
    const result = await runPreflight(approvedEnv(), {
      strict: true,
      fetchImpl: async (url, init) => {
        if (String(url).endsWith("/auth/v1/otp")) return Response.json({});
        const { phone } = JSON.parse(String(init.body));
        const stored = phone.replace(/^\+/, "");
        return Response.json(
          sessionFor(phone, { user: { phone: stored }, claims: { phone: stored } }),
        );
      },
    });
    assert.equal(result.verdict, "PASS");
  });

  it("wrong OTP → FAIL", async () => {
    const fetchImpl = async (url) => {
      const target = String(url);
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      return new Response("invalid", { status: 400 });
    };

    const result = await runPreflight(approvedEnv(), { fetchImpl, strict: true });

    assert.equal(result.verdict, "FAIL");
    assert.match(result.detail, /test-OTP verify failed/);
  });

  for (const [name, session] of [
    ["empty 200 response", {}],
    [
      "wrong synthetic phone",
      sessionFor(SEED.personas.customer.phone, { user: { phone: "+260970000099" } }),
    ],
    [
      "wrong token subject",
      sessionFor(SEED.personas.customer.phone, { claims: { sub: VENDOR_ID } }),
    ],
    [
      "wrong user ID with matching phone and role",
      sessionFor(SEED.personas.customer.phone, {
        user: { id: VENDOR_ID },
        claims: { sub: VENDOR_ID },
      }),
    ],
    [
      "missing customer role",
      sessionFor(SEED.personas.customer.phone, { claims: { app_metadata: { roles: [] } } }),
    ],
    [
      "vendor role on customer",
      sessionFor(SEED.personas.customer.phone, {
        claims: { app_metadata: { roles: ["customer", "vendor"] } },
      }),
    ],
  ]) {
    it(`${name} → FAIL without contacting the vendor recipient`, async () => {
      const calls = [];
      const result = await runPreflight(approvedEnv(), {
        strict: true,
        fetchImpl: async (url) => {
          calls.push(String(url));
          if (String(url).endsWith("/auth/v1/otp")) return Response.json({});
          return Response.json(session);
        },
      });
      assert.equal(result.verdict, "FAIL");
      assert.match(result.detail, /session identity or role claim mismatch/);
      assert.deepEqual(
        calls.map((url) => new URL(url).pathname),
        ["/auth/v1/otp", "/auth/v1/verify"],
      );
    });
  }

  it("a failed customer OTP send does not contact the vendor recipient", async () => {
    const calls = [];
    const result = await runPreflight(approvedEnv(), {
      strict: true,
      fetchImpl: async (url) => {
        calls.push(String(url));
        return new Response("rejected", { status: 400 });
      },
    });
    assert.equal(result.verdict, "FAIL");
    assert.deepEqual(
      calls.map((url) => new URL(url).pathname),
      ["/auth/v1/otp"],
    );
  });

  it("vendor login fails when the role hook returns only a customer role", async () => {
    const calls = [];
    const result = await runPreflight(approvedEnv(), {
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
    });
    assert.equal(result.verdict, "FAIL");
    assert.match(result.detail, /vendor: test-OTP session identity or role claim mismatch/);
    assert.deepEqual(
      calls.map((url) => new URL(url).pathname),
      ["/auth/v1/otp", "/auth/v1/verify", "/auth/v1/otp", "/auth/v1/verify"],
    );
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
      return Response.json(sessionFor(JSON.parse(String(init.body)).phone));
    };

    try {
      await runPreflight(approvedEnv(), { fetchImpl, strict: true });
    } finally {
      console.log = originalLog;
    }

    const serialized = lines.join("\n");
    assert.equal(serialized.includes(CUSTOMER_OTP), false);
    assert.equal(serialized.includes(VENDOR_OTP), false);
  });

  it("a redirect is rejected before a second host is contacted", async () => {
    const calls = [];
    const fetchImpl = async (url, init) => {
      calls.push(String(url));
      assert.equal(init.redirect, "error");
      throw new TypeError("fetch failed: redirect disallowed");
    };
    await assert.rejects(
      runPreflight(approvedEnv(), { fetchImpl, strict: true }),
      /redirect disallowed/,
    );
    assert.deepEqual(calls, ["https://iyasmrmbcrvlfxpzescb.supabase.co/auth/v1/otp"]);
  });
});

describe("preflight approval — no outbound OTP before consent", () => {
  for (const [name, overrides] of [
    ["missing recipient approval", { E2E_OTP_RECIPIENT_APPROVED: "" }],
    ["wrong run attempt", { E2E_APPROVED_RUN_ATTEMPT: "1" }],
    ["unverified staging handoff", { E2E_STRICT_SHA: "" }],
    ["different checked-out SHA", { GITHUB_SHA: "b".repeat(40) }],
    ["unapproved vendor phone", { E2E_APPROVED_VENDOR_PHONE: "+260970000999" }],
    ["production Auth target", { SUPABASE_URL: "https://dpadrlxukcjbewpqympu.supabase.co" }],
  ]) {
    it(`${name} → FAIL with zero network calls`, async () => {
      let calls = 0;
      const result = await runPreflight(approvedEnv(overrides), {
        strict: true,
        fetchImpl: async () => {
          calls++;
          throw new Error("network must stay closed");
        },
      });
      assert.equal(result.verdict, "FAIL");
      assert.match(result.detail, /approval required/);
      assert.equal(calls, 0);
    });
  }
});

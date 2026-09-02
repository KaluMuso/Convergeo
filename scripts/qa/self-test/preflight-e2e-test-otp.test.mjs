import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { SEED } from "../../../e2e/fixtures/seed.generated.ts";
import { evaluatePreflightConfig, runPreflight } from "../../ci/preflight-e2e-test-otp.mjs";

const CUSTOMER_OTP = "111111";
const VENDOR_OTP = "222222";

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
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      if (target.endsWith("/auth/v1/verify")) {
        const body = JSON.parse(String(init?.body ?? "{}"));
        const expected = body.phone === SEED.personas.customer.phone ? CUSTOMER_OTP : VENDOR_OTP;
        if (body.token === expected) {
          return new Response("{}", { status: 200 });
        }
        return new Response("invalid", { status: 400 });
      }
      return new Response("not found", { status: 404 });
    };

    const result = await runPreflight(
      {
        SUPABASE_URL: "https://example.supabase.co",
        SUPABASE_ANON_KEY: "anon-key",
        E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
        E2E_VENDOR_TEST_OTP: VENDOR_OTP,
        CERTIFICATION_MODE: "integrated-staging",
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
        SUPABASE_URL: "https://example.supabase.co",
        SUPABASE_ANON_KEY: "anon-key",
        E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
        E2E_VENDOR_TEST_OTP: VENDOR_OTP,
        CERTIFICATION_MODE: "integrated-staging",
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

    const fetchImpl = async (url) => {
      const target = String(url);
      if (target.endsWith("/auth/v1/otp")) {
        return new Response("{}", { status: 200 });
      }
      return new Response("{}", { status: 200 });
    };

    try {
      await runPreflight(
        {
          SUPABASE_URL: "https://example.supabase.co",
          SUPABASE_ANON_KEY: "anon-key",
          E2E_CUSTOMER_TEST_OTP: CUSTOMER_OTP,
          E2E_VENDOR_TEST_OTP: VENDOR_OTP,
          CERTIFICATION_MODE: "integrated-staging",
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

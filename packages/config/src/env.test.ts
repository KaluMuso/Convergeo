import { describe, expect, it } from "vitest";

import {
  assertVercelPublicSupabaseEnv,
  type EnvSource,
  loadEnv,
  loadPublicEnv,
  loadServerEnv,
} from "./env";

const validEnv: EnvSource = {
  SUPABASE_URL: "https://example.supabase.co",
  SUPABASE_ANON_KEY: "anon-key",
  LENCO_BASE_URL: "https://api.lenco.co",
  SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
  LENCO_API_TOKEN: "lenco-token",
  OPENROUTER_API_KEY: "openrouter-key",
  WHATSAPP_TOKEN: "whatsapp-token",
  AT_API_KEY: "at-key",
  AT_USERNAME: "at-username",
  AT_SENDER_ID: "VERGEO5",
  SEND_SMS_HOOK_SECRET: "v1,whsec_dGhpcyBpcyBhIHZlcnlnZW81IHRlc3Qgc2VjcmV0IQ==",
  RESEND_API_KEY: "resend-key",
  CLOUDINARY_URL: "cloudinary://key:secret@cloud",
};

function withEnv(overrides: EnvSource = validEnv): EnvSource {
  return { ...overrides };
}

describe("loadEnv", () => {
  it("parses valid environment variables", () => {
    const env = loadEnv(withEnv());
    expect(env.public.SUPABASE_URL).toBe(validEnv.SUPABASE_URL);
    expect(env.server.LENCO_API_TOKEN).toBe(validEnv.LENCO_API_TOKEN);
  });

  it("throws when a required variable is missing", () => {
    const source = withEnv();
    delete source.LENCO_API_TOKEN;

    expect(() => loadEnv(source)).toThrow(
      "Missing or invalid required environment variable: LENCO_API_TOKEN (value redacted)",
    );
  });

  it("does not include secret values in error messages", () => {
    const source = withEnv({ ...validEnv, LENCO_API_TOKEN: "" });

    expect(() => loadServerEnv(source)).toThrow(/value redacted/);
    expect(() => loadServerEnv(source)).not.toThrow(/lenco-token/);
  });

  it("loads public env independently", () => {
    const publicEnv = loadPublicEnv(withEnv());
    expect(publicEnv.SUPABASE_ANON_KEY).toBe("anon-key");
  });
});

const validVercelPublicSupabaseEnv: EnvSource = {
  VERCEL: "1",
  NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "anon-key",
};

/**
 * PR-E: Vercel Preview/Production builds must fail closed on missing/invalid
 * public Supabase config (packages/auth/src/env.ts's getSupabaseUrl /
 * getSupabaseAnonKey are the runtime consumers) — GitHub Actions CI and
 * local `next build` must stay unaffected since neither sets VERCEL=1.
 */
describe("assertVercelPublicSupabaseEnv", () => {
  it("is inactive when VERCEL is absent", () => {
    expect(() => assertVercelPublicSupabaseEnv({})).not.toThrow();
  });

  it('is inactive when VERCEL is "0"', () => {
    expect(() =>
      assertVercelPublicSupabaseEnv({
        VERCEL: "0",
        NEXT_PUBLIC_SUPABASE_URL: undefined,
        NEXT_PUBLIC_SUPABASE_ANON_KEY: undefined,
      }),
    ).not.toThrow();
  });

  it("passes on Vercel when URL and anon key are both present and valid", () => {
    expect(() => assertVercelPublicSupabaseEnv(validVercelPublicSupabaseEnv)).not.toThrow();
  });

  it("fails closed on Vercel when the URL is missing", () => {
    const source = { ...validVercelPublicSupabaseEnv };
    delete source.NEXT_PUBLIC_SUPABASE_URL;

    expect(() => assertVercelPublicSupabaseEnv(source)).toThrow(
      "Missing or invalid required Vercel public Supabase environment variable: NEXT_PUBLIC_SUPABASE_URL",
    );
  });

  it("fails closed on Vercel when the URL is empty", () => {
    expect(() =>
      assertVercelPublicSupabaseEnv({
        ...validVercelPublicSupabaseEnv,
        NEXT_PUBLIC_SUPABASE_URL: "",
      }),
    ).toThrow("NEXT_PUBLIC_SUPABASE_URL");
  });

  it("fails closed on Vercel when the URL is whitespace-only", () => {
    expect(() =>
      assertVercelPublicSupabaseEnv({
        ...validVercelPublicSupabaseEnv,
        NEXT_PUBLIC_SUPABASE_URL: "   ",
      }),
    ).toThrow("NEXT_PUBLIC_SUPABASE_URL");
  });

  it("fails closed on Vercel when the URL is malformed", () => {
    expect(() =>
      assertVercelPublicSupabaseEnv({
        ...validVercelPublicSupabaseEnv,
        NEXT_PUBLIC_SUPABASE_URL: "not-a-url",
      }),
    ).toThrow("NEXT_PUBLIC_SUPABASE_URL (must be a valid HTTPS URL)");
  });

  it("fails closed on Vercel when the URL is a non-HTTPS scheme", () => {
    expect(() =>
      assertVercelPublicSupabaseEnv({
        ...validVercelPublicSupabaseEnv,
        NEXT_PUBLIC_SUPABASE_URL: "http://example.supabase.co",
      }),
    ).toThrow("NEXT_PUBLIC_SUPABASE_URL (must be a valid HTTPS URL)");
  });

  it("fails closed on Vercel when the anon key is missing", () => {
    const source = { ...validVercelPublicSupabaseEnv };
    delete source.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    expect(() => assertVercelPublicSupabaseEnv(source)).toThrow(
      "Missing or invalid required Vercel public Supabase environment variable: NEXT_PUBLIC_SUPABASE_ANON_KEY",
    );
  });

  it("fails closed on Vercel when the anon key is whitespace-only", () => {
    expect(() =>
      assertVercelPublicSupabaseEnv({
        ...validVercelPublicSupabaseEnv,
        NEXT_PUBLIC_SUPABASE_ANON_KEY: "   ",
      }),
    ).toThrow("NEXT_PUBLIC_SUPABASE_ANON_KEY");
  });

  it("fails closed on Vercel when both are missing, naming both", () => {
    expect(() => assertVercelPublicSupabaseEnv({ VERCEL: "1" })).toThrow(
      "Missing or invalid required Vercel public Supabase environment variables: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY",
    );
  });

  it("never includes the anon key value in the thrown error", () => {
    const secretValue = "sb-secret-anon-key-do-not-leak";
    try {
      assertVercelPublicSupabaseEnv({
        VERCEL: "1",
        NEXT_PUBLIC_SUPABASE_URL: "not-a-url",
        NEXT_PUBLIC_SUPABASE_ANON_KEY: secretValue,
      });
      expect.unreachable("must throw when the URL is malformed");
    } catch (error) {
      expect(String(error)).not.toContain(secretValue);
    }
  });

  it("never includes the malformed URL value in the thrown error", () => {
    const malformedValue = "ht!tp://leaky-token=abc123";
    try {
      assertVercelPublicSupabaseEnv({
        ...validVercelPublicSupabaseEnv,
        NEXT_PUBLIC_SUPABASE_URL: malformedValue,
      });
      expect.unreachable("must throw on a malformed URL");
    } catch (error) {
      expect(String(error)).not.toContain(malformedValue);
    }
  });
});

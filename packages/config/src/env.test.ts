import { describe, expect, it } from "vitest";

import { type EnvSource, loadEnv, loadPublicEnv, loadServerEnv } from "./env";

const validEnv: EnvSource = {
  SUPABASE_URL: "https://example.supabase.co",
  SUPABASE_ANON_KEY: "anon-key",
  LENCO_BASE_URL: "https://api.lenco.co",
  SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
  LENCO_API_TOKEN: "lenco-token",
  OPENROUTER_API_KEY: "openrouter-key",
  WHATSAPP_TOKEN: "whatsapp-token",
  AT_API_KEY: "at-key",
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

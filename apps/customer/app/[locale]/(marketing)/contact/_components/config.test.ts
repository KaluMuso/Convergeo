import { afterEach, describe, expect, it, vi } from "vitest";

import { buildWhatsappLink, getSupportPhoneDisplay, getSupportWhatsappNumber } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("support WhatsApp config", () => {
  it("is hidden (null) when unconfigured, in every environment", () => {
    for (const env of ["production", "development"]) {
      vi.stubEnv("NODE_ENV", env);
      vi.stubEnv("NEXT_PUBLIC_SUPPORT_WHATSAPP", "");
      expect(getSupportWhatsappNumber()).toBeNull();
      expect(getSupportPhoneDisplay()).toBeNull();
      expect(buildWhatsappLink()).toBeNull();
    }
  });

  it("uses the configured number (digits only) with prefill", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SUPPORT_WHATSAPP", "+260 971 234 567");
    expect(buildWhatsappLink("hi there")).toBe("https://wa.me/260971234567?text=hi%20there");
    expect(getSupportPhoneDisplay()).toBe("+260971234567");
  });
});

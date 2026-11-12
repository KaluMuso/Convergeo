import { afterEach, describe, expect, it, vi } from "vitest";

import { buildWhatsappLink, getSupportWhatsappNumber } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("support WhatsApp config", () => {
  it("falls back to the founder-confirmed support line in production (no fake number)", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SUPPORT_WHATSAPP", "");
    expect(getSupportWhatsappNumber()).toBe("260761359005");
    expect(buildWhatsappLink()).toBe("https://wa.me/260761359005");
    expect(buildWhatsappLink()).not.toContain("260970000000");
  });

  it("uses the same confirmed line outside production", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_SUPPORT_WHATSAPP", "");
    expect(buildWhatsappLink()).toBe("https://wa.me/260761359005");
  });

  it("uses the configured number (digits only) with prefill in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SUPPORT_WHATSAPP", "+260 971 234 567");
    expect(buildWhatsappLink("hi there")).toBe("https://wa.me/260971234567?text=hi%20there");
  });
});

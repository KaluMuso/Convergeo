import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { reportClientError } from "./report-client-error";

describe("reportClientError", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
    vi.stubGlobal("window", {
      location: { href: "https://vergeo5.com/en/checkout" },
    });
    vi.stubGlobal("navigator", {
      userAgent: "vitest",
      sendBeacon: vi.fn(() => true),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response())),
    );
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("posts a scrubbed payload to the telemetry API when Sentry is unset", async () => {
    await reportClientError(
      new Error("boom +260971234567"),
      {
        message: "boom",
        boundary: "route",
        application: "customer",
        locale: "en",
      },
      { apiBaseUrl: "https://api.vergeo5.com" },
    );

    expect(navigator.sendBeacon).toHaveBeenCalledOnce();
    const [endpoint, blob] = vi.mocked(navigator.sendBeacon).mock.calls[0]!;
    expect(endpoint).toBe("https://api.vergeo5.com/telemetry/frontend-errors");
    expect(blob).toBeInstanceOf(Blob);
    const body = JSON.parse(await (blob as Blob).text());
    expect(body.message).not.toContain("260971234567");
    expect(body.application).toBe("customer");
    expect(body.boundary).toBe("route");
  });
});

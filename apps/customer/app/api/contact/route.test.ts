import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRateLimits } from "../../[locale]/(marketing)/contact/_components/rate-limit";

import { POST } from "./route";

const body = {
  name: "Chanda",
  contact: "",
  message: "Please help me with my order thanks.",
};

function req(): NextRequest {
  return new NextRequest("http://localhost/api/contact", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-forwarded-for": "1.2.3.4",
    },
    body: JSON.stringify(body),
  });
}

describe("POST /api/contact email config", () => {
  beforeEach(() => {
    resetRateLimits();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns 503 in production when Resend env is missing", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("RESEND_API_KEY", "");
    vi.stubEnv("CONTACT_INBOX", "");
    const res = await POST(req());
    expect(res.status).toBe(503);
    expect((await res.json()).error.code).toBe("unavailable");
  });

  it("returns 503 in production when CONTACT_FROM is missing", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("RESEND_API_KEY", "k");
    vi.stubEnv("CONTACT_INBOX", "a@b.co");
    vi.stubEnv("CONTACT_FROM", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(req());
    expect(res.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts without sending outside production", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("RESEND_API_KEY", "");
    const res = await POST(req());
    expect(res.status).toBe(200);
  });

  it("sends via Resend in production when fully configured", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("RESEND_API_KEY", "k");
    vi.stubEnv("CONTACT_INBOX", "a@b.co");
    vi.stubEnv("CONTACT_FROM", "Vergeo5 <support@vergeo5.com>");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(req());
    expect(res.status).toBe(200);
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body).from).toBe("Vergeo5 <support@vergeo5.com>");
  });
});

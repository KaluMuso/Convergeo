import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const updateSession = vi.fn();

vi.mock("@vergeo/auth/middleware", () => ({
  CSP_NONCE_PLACEHOLDER: "{{CSP_NONCE}}",
  appendCspReporting: (v: string) => v,
  applyReportOnlyCspNonce: (_r: unknown, response: unknown) => response,
  handleCspReportRequest: vi.fn(),
  isCspReportRequest: () => false,
  mergeSessionCookies: (a: unknown) => a,
  updateSession: (...args: unknown[]) => updateSession(...args),
}));
vi.mock("next-intl/middleware", () => ({
  default: vi.fn(() => vi.fn(() => NextResponse.next())),
}));

import middleware from "./middleware";

describe("customer middleware session verification mode", () => {
  beforeEach(() => {
    updateSession.mockReset();
    updateSession.mockResolvedValue({ response: NextResponse.next(), user: null, roles: [] });
  });

  it.each([
    ["http://localhost/en", "GET", "local"],
    ["http://localhost/en/p/itel-a70", "GET", "local"],
    ["http://localhost/en/account/orders", "GET", "server"],
    ["http://localhost/en/checkout", "GET", "server"],
    ["http://localhost/en/wishlist", "GET", "server"],
    ["http://localhost/en/p/itel-a70", "POST", "server"],
  ])("%s %s -> %s", async (url, method, mode) => {
    await middleware(new NextRequest(url, { method }));
    expect(updateSession).toHaveBeenCalledWith(expect.anything(), { verify: mode });
  });
});

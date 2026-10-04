import { describe, expect, it, vi } from "vitest";

import { handleCiPerfProxy } from "./ci-perf-proxy";

import type { CiPerfServerEnv } from "./ci-perf-harness";

const env: CiPerfServerEnv = {
  CI: "true",
  GITHUB_ACTIONS: "true",
  CI_PERF_HARNESS: "1",
  NEXT_PUBLIC_CI_PERF_HARNESS: "1",
  NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
  NEXT_PUBLIC_SITE_URL: "http://localhost:3000",
  NEXT_PUBLIC_API_BASE_URL: "http://10.1.2.3:8000",
  CI_PERF_UPSTREAM_ORIGIN: "http://10.1.2.3:8000",
  NODE_ENV: "production",
  ENV: "development",
  SUPABASE_URL: "http://127.0.0.1:54321",
};
const request = (path: string, init?: RequestInit) =>
  new Request(`http://localhost:3000/api/ci-perf/${path}`, init);

describe("finite CI API proxy", () => {
  it("forwards an exact allowed GET and only caller cart authentication headers", async () => {
    const transport = vi.fn().mockResolvedValue(
      new Response('{"items":[]}', {
        headers: {
          "Content-Type": "application/json",
          "Set-Cookie": "vergeo_guest_cart=signed.jwt; HttpOnly; SameSite=lax; Path=/",
          "X-Secret": "excluded",
        },
      }),
    );
    const response = await handleCiPerfProxy(
      request("cart", {
        headers: {
          Authorization: "Bearer caller-token",
          Cookie: "sb-secret=excluded; vergeo_guest_cart=signed.jwt",
          "X-Secret": "excluded",
        },
      }),
      env,
      transport,
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ items: [] });
    const [url, options] = transport.mock.calls[0]!;
    expect(url).toBe("http://10.1.2.3:8000/cart");
    expect(options.redirect).toBe("error");
    expect(options.cache).toBe("no-store");
    expect(Object.fromEntries(options.headers)).toEqual({
      accept: "application/json",
      authorization: "Bearer caller-token",
      cookie: "vergeo_guest_cart=signed.jwt",
    });
    expect(response.headers.has("x-secret")).toBe(false);
    expect(response.headers.get("set-cookie")).toContain("vergeo_guest_cart=");
  });
  it("allows the exact product and category query without forwarding authentication", async () => {
    const transport = vi
      .fn()
      .mockImplementation(
        async () => new Response("{}", { headers: { "Content-Type": "application/json" } }),
      );
    for (const path of [
      "products/smartphone-x1",
      "catalog/listings?category_path=electronics&limit=3&sort=newest",
    ]) {
      expect(
        (
          await handleCiPerfProxy(
            request(path, {
              headers: { Authorization: "Bearer excluded", Cookie: "vergeo_guest_cart=excluded" },
            }),
            env,
            transport,
          )
        ).status,
      ).toBe(200);
    }
    expect(Object.fromEntries(transport.mock.calls[0]![1].headers)).toEqual({
      accept: "application/json",
    });
  });
  for (const path of [
    "cart?constructor=x",
    "cart?__proto__=x",
    "constructor",
    "__proto__",
    "healthz",
    "cart/items",
    "products/other",
    "catalog/listings?limit=100",
    "catalog/listings?category_path=all",
    "cart?secret=x",
    "catalog/listings?limit=3&limit=3",
    "products%2Fsmartphone-x1",
    "../cart",
  ]) {
    it(`rejects unknown or ambiguous request ${path}`, async () => {
      const transport = vi.fn();
      expect((await handleCiPerfProxy(request(path), env, transport)).status).toBe(404);
      expect(transport).not.toHaveBeenCalled();
    });
  }
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]) {
    it(`rejects ${method} inside CI and returns404 outside CI`, async () => {
      const transport = vi.fn();
      expect((await handleCiPerfProxy(request("cart", { method }), env, transport)).status).toBe(
        405,
      );
      expect(
        (
          await handleCiPerfProxy(
            request("cart", { method }),
            { ...env, CI_PERF_HARNESS: "" },
            transport,
          )
        ).status,
      ).toBe(404);
      expect(transport).not.toHaveBeenCalled();
    });
  }
  it("does not transport outside CI, on a different frontend, on redirect/error or nonJSON", async () => {
    const transport = vi.fn();
    expect(
      (await handleCiPerfProxy(request("cart"), { ...env, GITHUB_ACTIONS: undefined }, transport))
        .status,
    ).toBe(404);
    expect(
      (await handleCiPerfProxy(new Request("http://other.test/api/ci-perf/cart"), env, transport))
        .status,
    ).toBe(404);
    expect(transport).not.toHaveBeenCalled();
    transport.mockRejectedValue(new Error("redirect blocked"));
    expect((await handleCiPerfProxy(request("cart"), env, transport)).status).toBe(502);
    transport.mockResolvedValue(new Response("notJSON"));
    expect((await handleCiPerfProxy(request("cart"), env, transport)).status).toBe(502);
  });
});

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
  const fixture = "b1000000-0000-0000-0000-000000000001";
  const session = "12345678-1234-4234-8234-123456789abc";
  const post = (path: string, body?: unknown, extra: Record<string, string> = {}) =>
    request(path, {
      method: "POST",
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      headers: {
        Origin: "http://localhost:3000",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...extra,
      },
    });
  const jsonTransport = () =>
    vi
      .fn()
      .mockImplementation(
        async () => new Response("{}", { headers: { "Content-Type": "application/json" } }),
      );

  it("forwards genuinely empty cart revalidation with only caller cart credentials", async () => {
    const transport = jsonTransport();
    const response = await handleCiPerfProxy(
      post("cart/revalidate", undefined, {
        Authorization: "Bearer caller-token",
        Cookie: "sb-secret=excluded; vergeo_guest_cart=signed.jwt",
        "X-Secret": "excluded",
      }),
      env,
      transport,
    );
    expect(response.status).toBe(200);
    const [url, options] = transport.mock.calls[0]!;
    expect(url).toBe("http://10.1.2.3:8000/cart/revalidate");
    expect(options.method).toBe("POST");
    expect(options.body).toBe("");
    expect(options.redirect).toBe("error");
    expect(Object.fromEntries(options.headers)).toEqual({
      accept: "application/json",
      authorization: "Bearer caller-token",
      cookie: "vergeo_guest_cart=signed.jwt",
    });
    expect((await handleCiPerfProxy(post("cart/revalidate", {}), env, transport)).status).toBe(400);
    for (const body of ["\uFEFF", " "]) {
      expect(
        (
          await handleCiPerfProxy(
            request("cart/revalidate", {
              method: "POST",
              headers: { Origin: "http://localhost:3000" },
              body,
            }),
            env,
            transport,
          )
        ).status,
      ).toBe(400);
    }
    expect(transport).toHaveBeenCalledTimes(1);
  });

  it("forwards both real fixture view shapes and camelCase error beacons without credentials", async () => {
    const transport = jsonTransport();
    for (const [path, payload] of [
      ["telemetry/views", { session_id: session, listing_id: fixture }],
      ["telemetry/views", { session_id: session, listing_ids: [fixture] }],
      [
        "telemetry/frontend-errors",
        {
          application: "customer",
          boundary: "route",
          message: "Fixture rendering error",
          stack: "bounded stack",
          locale: "en",
          url: "http://localhost:3000/en",
          userAgent: "actual-caller-user-agent",
        },
      ],
    ] as const) {
      const response = await handleCiPerfProxy(
        post(path, payload, {
          Authorization: "Bearer excluded",
          Cookie: "vergeo_guest_cart=excluded; sb-secret=excluded",
        }),
        env,
        transport,
      );
      expect(response.status).toBe(200);
      const [url, options] = transport.mock.calls.at(-1)!;
      expect(url).toBe(`http://10.1.2.3:8000/${path}`);
      expect(JSON.parse(options.body)).toEqual(payload);
      expect(Object.fromEntries(options.headers)).toEqual({
        accept: "application/json",
        "content-type": "application/json",
      });
    }
  });

  for (const [name, path, body, headers] of [
    [
      "foreign origin",
      "telemetry/views",
      { session_id: session, listing_id: fixture },
      { Origin: "https://other.example" },
    ],
    [
      "invalid session",
      "telemetry/views",
      { session_id: "not-a-session", listing_id: fixture },
      {},
    ],
    ["other listing", "telemetry/views", { session_id: session, listing_id: session }, {}],
    [
      "mixed batch",
      "telemetry/views",
      { session_id: session, listing_ids: [fixture, session] },
      {},
    ],
    [
      "ambiguous shapes",
      "telemetry/views",
      { session_id: session, listing_id: fixture, listing_ids: [fixture] },
      {},
    ],
    [
      "unknown field",
      "telemetry/views",
      { session_id: session, listing_id: fixture, secret: "excluded" },
      {},
    ],
    ["empty batch", "telemetry/views", { session_id: session, listing_ids: [] }, {}],
    [
      "wrong content type",
      "telemetry/views",
      { session_id: session, listing_id: fixture },
      { "Content-Type": "text/plain" },
    ],
    [
      "wrong app",
      "telemetry/frontend-errors",
      { application: "admin", boundary: "route", message: "error" },
      {},
    ],
    [
      "wrong boundary type",
      "telemetry/frontend-errors",
      { application: "customer", boundary: ["route"], message: "error" },
      {},
    ],
    [
      "unbounded stack",
      "telemetry/frontend-errors",
      { application: "customer", boundary: "route", message: "error", stack: "x".repeat(8001) },
      {},
    ],
    [
      "foreign error URL",
      "telemetry/frontend-errors",
      {
        application: "customer",
        boundary: "route",
        message: "error",
        url: "https://other.example/en",
      },
      {},
    ],
    ["unknown endpoint", "telemetry/collect", {}, {}],
    ["cart write", "cart/items", {}, {}],
    ["revalidate query", "cart/revalidate?secret=x", undefined, {}],
  ] as const) {
    it(`refuses ${name} without an upstream request`, async () => {
      const transport = jsonTransport();
      expect(
        (await handleCiPerfProxy(post(path, body, headers), env, transport)).status,
      ).toBeGreaterThanOrEqual(400);
      expect(transport).not.toHaveBeenCalled();
    });
  }

  it("bounds streamed bytes and rejects malformed JSON, absent Origin and ordinary contexts", async () => {
    const transport = jsonTransport();
    const huge = request("telemetry/views", {
      method: "POST",
      headers: { Origin: "http://localhost:3000", "Content-Type": "application/json" },
      body: "x".repeat(16_385),
    });
    expect((await handleCiPerfProxy(huge, env, transport)).status).toBe(413);
    for (const body of [
      "not-json",
      "null",
      "[]",
      '{"__proto__":{},"session_id":"' + session + '","listing_id":"' + fixture + '"}',
    ]) {
      expect(
        (
          await handleCiPerfProxy(
            request("telemetry/views", {
              method: "POST",
              headers: { Origin: "http://localhost:3000", "Content-Type": "application/json" },
              body,
            }),
            env,
            transport,
          )
        ).status,
      ).toBe(400);
    }
    expect(
      (await handleCiPerfProxy(request("cart/revalidate", { method: "POST" }), env, transport))
        .status,
    ).toBe(403);
    expect(
      (await handleCiPerfProxy(post("cart/revalidate"), { ...env, CI_PERF_HARNESS: "" }, transport))
        .status,
    ).toBe(404);
    expect((await handleCiPerfProxy(request("telemetry/views"), env, transport)).status).toBe(405);
    expect(transport).not.toHaveBeenCalled();
  });

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

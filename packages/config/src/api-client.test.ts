import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./api-client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createApiClient", () => {
  it("returns typed data on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ status: "ok" }),
      }),
    );

    const client = createApiClient({ baseUrl: "https://api.example.com" });
    const data = await client.request<{ status: string }>("/healthz");

    expect(data).toEqual({ status: "ok" });
  });

  it("throws ApiError with envelope code and request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          error: {
            code: "validation_error",
            message: "Request validation failed",
            details: { field: "email" },
            request_id: "req-123",
          },
        }),
      }),
    );

    const client = createApiClient({ baseUrl: "https://api.example.com" });

    await expect(client.request("/orders")).rejects.toMatchObject({
      code: "validation_error",
      requestId: "req-123",
      status: 422,
    });
  });

  it("throws network_error on fetch failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const client = createApiClient({ baseUrl: "https://api.example.com" });

    await expect(client.request("/healthz")).rejects.toBeInstanceOf(ApiError);
    await expect(client.request("/healthz")).rejects.toMatchObject({
      code: "network_error",
    });
  });

  it("injects Authorization when getToken returns a token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient({
      baseUrl: "https://api.example.com",
      getToken: () => "secret-token",
    });

    await client.request("/me");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer secret-token");
  });
});

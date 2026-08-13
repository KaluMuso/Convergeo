import { afterEach, describe, expect, it, vi } from "vitest";

import { isApiRouteRegistered, probeApiRoute } from "./api-route-probe";

describe("isApiRouteRegistered", () => {
  it("treats 404 as unavailable", () => {
    expect(isApiRouteRegistered(404)).toBe(false);
  });

  it("treats 5xx as unavailable", () => {
    expect(isApiRouteRegistered(500)).toBe(false);
    expect(isApiRouteRegistered(503)).toBe(false);
  });

  it("treats auth-required responses as available", () => {
    expect(isApiRouteRegistered(401)).toBe(true);
    expect(isApiRouteRegistered(403)).toBe(true);
  });

  it("treats wrong-method responses as available", () => {
    expect(isApiRouteRegistered(405)).toBe(true);
    expect(isApiRouteRegistered(422)).toBe(true);
  });
});

describe("probeApiRoute", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns false when the production API base is unset", async () => {
    await expect(
      probeApiRoute("/rfq", {
        NEXT_PUBLIC_API_BASE_URL: "",
        NODE_ENV: "production",
      }),
    ).resolves.toBe(false);
  });

  it("returns false when the probe receives 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 404,
      }),
    );

    await expect(
      probeApiRoute("/rfq", {
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).resolves.toBe(false);
  });

  it("returns true when the probe receives 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 401,
      }),
    );

    await expect(
      probeApiRoute("/rfq", {
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).resolves.toBe(true);
  });
});

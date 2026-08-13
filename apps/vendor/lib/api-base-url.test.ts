import { describe, expect, it } from "vitest";

import { getApiBaseUrl, resolveApiBaseUrl } from "./api-base-url";

describe("resolveApiBaseUrl (vendor)", () => {
  it("returns the configured origin without a trailing slash", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("defaults to the production API on the production plane when unset", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
    expect(
      getApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("never infers a loopback origin when the plane is missing", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: undefined,
        NODE_ENV: "development",
      }),
    ).toBeNull();
  });

  it("never ships a loopback or production API URL from a Preview build", () => {
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolveApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });
});

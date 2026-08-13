import { describe, expect, it } from "vitest";

import {
  DEPLOYMENT_PLANE_BUNDLE_MARKER,
  isDeployedFrontendEnv,
  isLoopbackApiOrigin,
  isProductionApiOrigin,
  isStagingApiOrigin,
  resolvePublicApiBaseUrl,
} from "./api-base-url";

describe("deployment plane bundle marker", () => {
  it("emits a CI-readable plane marker", () => {
    expect(DEPLOYMENT_PLANE_BUNDLE_MARKER.startsWith("vergeo5-deployment-plane=")).toBe(true);
  });
});

describe("loopback and production API origin detection", () => {
  it("detects localhost, loopback, and IPv6 loopback", () => {
    expect(isLoopbackApiOrigin("http://localhost:8000")).toBe(true);
    expect(isLoopbackApiOrigin("http://127.0.0.1:8000")).toBe(true);
    expect(isLoopbackApiOrigin("http://[::1]:8000")).toBe(true);
    expect(isLoopbackApiOrigin("http://foo.localhost:8000")).toBe(true);
    expect(isLoopbackApiOrigin("https://api.vergeo5.com")).toBe(false);
    expect(isLoopbackApiOrigin("https://api.staging.vergeo5.com")).toBe(false);
  });

  it("detects the production and staging API hosts", () => {
    expect(isProductionApiOrigin("https://api.vergeo5.com")).toBe(true);
    expect(isProductionApiOrigin("https://api.vergeo5.com/v1")).toBe(true);
    expect(isProductionApiOrigin("https://api.staging.vergeo5.com")).toBe(false);
    expect(isStagingApiOrigin("https://api.staging.vergeo5.com")).toBe(true);
    expect(isStagingApiOrigin("https://api.vergeo5.com")).toBe(false);
  });
});

describe("resolvePublicApiBaseUrl", () => {
  it("returns the configured production origin without a trailing slash", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com/",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("defaults to the production API when the production plane has no URL", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.vergeo5.com");
  });

  it("never infers a loopback origin when the plane is missing", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(resolvePublicApiBaseUrl({ NODE_ENV: "production" })).toBeNull();
    expect(resolvePublicApiBaseUrl({ NODE_ENV: "development" })).toBeNull();
    expect(resolvePublicApiBaseUrl({ NODE_ENV: "test" })).toBeNull();
  });

  it("rejects an explicit loopback URL on every deployed plane", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://[::1]:8000",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });

  it("rejects a staging or preview plane that points at the production API", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging",
        NODE_ENV: "production",
      }),
    ).toBeNull();
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.staging.vergeo5.com");
  });

  it("defaults staging and preview planes to the staging API", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.staging.vergeo5.com");
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
        NODE_ENV: "production",
      }),
    ).toBe("https://api.staging.vergeo5.com");
  });

  it("rejects a production plane that points at the staging API", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "production",
        NODE_ENV: "production",
      }),
    ).toBeNull();
  });

  it("allows localhost only on an explicit development plane", () => {
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "development",
        NODE_ENV: "development",
      }),
    ).toBe("http://localhost:8000");
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "development",
        NODE_ENV: "development",
      }),
    ).toBe("http://127.0.0.1:8000");
    expect(
      resolvePublicApiBaseUrl({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "development",
        NODE_ENV: "development",
      }),
    ).toBeNull();
  });

  it("reads the admin-specific public env key when requested", () => {
    expect(
      resolvePublicApiBaseUrl(
        {
          NEXT_PUBLIC_VERGEO_API_URL: "https://api.staging.vergeo5.com/",
          NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging",
          NODE_ENV: "production",
        },
        ["NEXT_PUBLIC_VERGEO_API_URL"],
      ),
    ).toBe("https://api.staging.vergeo5.com");
  });

  it("treats production/staging/preview planes as deployed", () => {
    expect(isDeployedFrontendEnv({ NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview" })).toBe(true);
    expect(isDeployedFrontendEnv({ NEXT_PUBLIC_DEPLOYMENT_PLANE: "production" })).toBe(true);
    expect(isDeployedFrontendEnv({ NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging" })).toBe(true);
    expect(
      isDeployedFrontendEnv({
        NEXT_PUBLIC_DEPLOYMENT_PLANE: "development",
        NODE_ENV: "development",
      }),
    ).toBe(false);
  });
});

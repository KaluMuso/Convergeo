import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("GET /[locale]/health (vendor)", () => {
  it("HEALTH-02: reports the staging apiHost when wired to staging", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.staging.vergeo5.com");
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "staging");
    vi.stubEnv("NODE_ENV", "production");

    const body = await GET().json();

    expect(body.status).toBe("ok");
    expect(body.app).toBe("vendor");
    expect(body.apiHost).toBe("api.staging.vergeo5.com");
  });

  it("reports the production apiHost on the production plane", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.vergeo5.com");
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "production");
    vi.stubEnv("NODE_ENV", "production");

    const body = await GET().json();

    expect(body.apiHost).toBe("api.vergeo5.com");
  });

  it("reports apiHost=null for a malformed configured URL rather than substituting a default", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "not a url");
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "staging");
    vi.stubEnv("NODE_ENV", "production");

    const body = await GET().json();

    expect(body.apiHost).toBeNull();
  });

  it("reports apiHost=null when the API URL / plane is missing (fail-closed)", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", undefined);
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", undefined);
    vi.stubEnv("NODE_ENV", "production");

    const body = await GET().json();

    expect(body.apiHost).toBeNull();
    expect(body.status).toBe("ok");
  });

  it("never includes anything beyond the documented safe fields", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.staging.vergeo5.com");
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "staging");
    vi.stubEnv("NODE_ENV", "production");

    const body = await GET().json();

    expect(Object.keys(body).sort()).toEqual(["apiHost", "app", "buildId", "env", "status"]);
  });
});

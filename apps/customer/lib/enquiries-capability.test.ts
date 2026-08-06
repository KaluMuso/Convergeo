import { afterEach, describe, expect, it, vi } from "vitest";

import {
  contactVendorCapabilityAvailable,
  isEnquiriesEndpointAvailable,
} from "./enquiries-capability";

describe("isEnquiriesEndpointAvailable", () => {
  it("treats 404 as unavailable (router not deployed)", () => {
    expect(isEnquiriesEndpointAvailable(404)).toBe(false);
  });

  it("treats 5xx as unavailable", () => {
    expect(isEnquiriesEndpointAvailable(500)).toBe(false);
    expect(isEnquiriesEndpointAvailable(503)).toBe(false);
  });

  it("treats auth-required responses as available (router registered)", () => {
    expect(isEnquiriesEndpointAvailable(401)).toBe(true);
    expect(isEnquiriesEndpointAvailable(403)).toBe(true);
  });

  it("treats 200 as available", () => {
    expect(isEnquiriesEndpointAvailable(200)).toBe(true);
  });

  it("fails closed on unexpected client errors", () => {
    expect(isEnquiriesEndpointAvailable(400)).toBe(false);
    expect(isEnquiriesEndpointAvailable(422)).toBe(false);
  });
});

describe("contactVendorCapabilityAvailable", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns false when the production API base is unset", async () => {
    await expect(
      contactVendorCapabilityAvailable({
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
      contactVendorCapabilityAvailable({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
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
      contactVendorCapabilityAvailable({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NODE_ENV: "production",
      }),
    ).resolves.toBe(true);
  });

  it("returns false when the probe throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    await expect(
      contactVendorCapabilityAvailable({
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
        NODE_ENV: "production",
      }),
    ).resolves.toBe(false);
  });
});

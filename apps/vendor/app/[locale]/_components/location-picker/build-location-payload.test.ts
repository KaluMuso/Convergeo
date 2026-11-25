import { describe, expect, it } from "vitest";

import { buildLocationPayload } from "./build-location-payload";

import type { VendorProfile } from "../../profile/_lib/profile-client";

const baseProfile: VendorProfile = {
  vendor_id: "v1",
  slug: "shop",
  display_name: "Shop",
  description: null,
  logo_url: null,
  cover_url: null,
  whatsapp_msisdn: null,
  preferred_badge: false,
  kyc_tier: null,
  status: "active",
  hours: {},
  lat: -15.4167,
  lng: 28.2833,
  landmark: "Near Arcades",
  slug_locked: false,
  previous_slug: null,
  completeness_score: 80,
  completeness: {
    logo: false,
    description: false,
    hours: true,
    location: true,
    badge: false,
  },
};

describe("buildLocationPayload", () => {
  it("uses form coordinates when all fields are set", () => {
    expect(
      buildLocationPayload(baseProfile, {
        lat: "-15.5",
        lng: "28.4",
        landmark: "Opposite Shoprite",
      }),
    ).toEqual({ lat: -15.5, lng: 28.4, landmark: "Opposite Shoprite" });
  });

  it("preserves saved GPS when hours save leaves lat/lng empty", () => {
    expect(
      buildLocationPayload(baseProfile, {
        lat: "",
        lng: "",
        landmark: "Near Arcades",
      }),
    ).toEqual({ lat: -15.4167, lng: 28.2833, landmark: "Near Arcades" });
  });
});

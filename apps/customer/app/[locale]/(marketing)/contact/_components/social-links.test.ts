import { afterEach, describe, expect, it, vi } from "vitest";

import { getSocialLinks, normaliseSocialUrl } from "./social-links";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("normaliseSocialUrl", () => {
  it("rejects empty, malformed, non-https and bare-homepage values", () => {
    expect(normaliseSocialUrl(undefined)).toBeNull();
    expect(normaliseSocialUrl("   ")).toBeNull();
    expect(normaliseSocialUrl("not a url")).toBeNull();
    expect(normaliseSocialUrl("http://www.facebook.com/convergeo")).toBeNull();
    expect(normaliseSocialUrl("https://www.facebook.com/")).toBeNull();
    expect(normaliseSocialUrl("https://twitter.com")).toBeNull();
  });

  it("accepts an https profile URL", () => {
    expect(normaliseSocialUrl(" https://www.facebook.com/convergeozm ")).toBe(
      "https://www.facebook.com/convergeozm",
    );
  });
});

describe("getSocialLinks", () => {
  it("defaults to no links at all", () => {
    expect(getSocialLinks()).toEqual({ facebook: null, twitter: null, instagram: null });
  });

  it("reads each network from its own env var", () => {
    vi.stubEnv("NEXT_PUBLIC_SOCIAL_FACEBOOK_URL", "https://www.facebook.com/convergeozm");
    vi.stubEnv("NEXT_PUBLIC_SOCIAL_INSTAGRAM_URL", "https://www.instagram.com/convergeozm");
    expect(getSocialLinks()).toEqual({
      facebook: "https://www.facebook.com/convergeozm",
      twitter: null,
      instagram: "https://www.instagram.com/convergeozm",
    });
  });
});

import { describe, expect, it } from "vitest";

import { cldLqipUrl, cldSrcSet, cldUrl, sanitizePublicId } from "./cloudinary-url";

const CLOUD = "vergeo5-dev";

describe("cloudinary-url", () => {
  it("builds exact URL shape with f_auto and q_auto", () => {
    const url = cldUrl("products/phone.jpg", { width: 720, cloudName: CLOUD });
    expect(url).toBe(
      "https://res.cloudinary.com/vergeo5-dev/image/upload/f_auto,q_auto,w_720/products/phone.jpg",
    );
  });

  it("preserves slashes in publicId without encoding", () => {
    const url = cldUrl("folder/nested/image.jpg", { width: 360, cloudName: CLOUD });
    expect(url).toContain("/folder/nested/image.jpg");
    expect(url).not.toContain("%2F");
  });

  it("builds 360/720/1080 srcset string", () => {
    const srcset = cldSrcSet("hero.jpg", { cloudName: CLOUD });
    expect(srcset).toContain(" 360w");
    expect(srcset).toContain(" 720w");
    expect(srcset).toContain(" 1080w");
    expect(srcset).toContain("f_auto,q_auto");
    expect(srcset.match(/\d+w/g)?.length).toBe(3);
  });

  it("builds LQIP variant with blur params", () => {
    const url = cldLqipUrl("thumb.jpg", { cloudName: CLOUD });
    expect(url).toBe(
      "https://res.cloudinary.com/vergeo5-dev/image/upload/w_24,e_blur:1000,q_30/thumb.jpg",
    );
  });

  it("throws on empty publicId", () => {
    expect(() => cldUrl("", { width: 360, cloudName: CLOUD })).toThrow(/empty/i);
    expect(() => cldUrl("   ", { width: 360, cloudName: CLOUD })).toThrow(/empty/i);
  });

  it("neutralizes protocol-smuggling publicId", () => {
    const smuggled = "https://evil.example/steal.jpg";
    const sanitized = sanitizePublicId(smuggled);
    expect(sanitized).not.toContain("://");
    expect(sanitized).toBe("evil.example/steal.jpg");

    const url = cldUrl(smuggled, { width: 360, cloudName: CLOUD });
    expect(url.startsWith("https://res.cloudinary.com/")).toBe(true);
    expect(url).toContain("/evil.example/steal.jpg");
    expect(url).not.toContain("https://evil.example");
  });

  it("only constructs res.cloudinary.com URLs", () => {
    const url = cldUrl("safe.jpg", { width: 360, cloudName: CLOUD });
    expect(url).toMatch(/^https:\/\/res\.cloudinary\.com\//);
  });
});

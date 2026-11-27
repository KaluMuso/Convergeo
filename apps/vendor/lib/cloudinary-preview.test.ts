import { describe, expect, it } from "vitest";

import { cloudinaryPreviewUrl } from "./cloudinary-preview";

describe("cloudinaryPreviewUrl", () => {
  it("inserts format, quality and width after /image/upload/", () => {
    expect(
      cloudinaryPreviewUrl(
        "https://res.cloudinary.com/demo/image/upload/v1700/shops/logo.png",
        160,
      ),
    ).toBe(
      "https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,c_limit,w_160/v1700/shops/logo.png",
    );
  });

  it("leaves blob previews, other hosts and non-upload urls untouched", () => {
    expect(cloudinaryPreviewUrl("blob:https://x/abc", 160)).toBe("blob:https://x/abc");
    expect(cloudinaryPreviewUrl("https://example.com/a.png", 160)).toBe(
      "https://example.com/a.png",
    );
    expect(cloudinaryPreviewUrl("https://res.cloudinary.com/demo/video/upload/v1/a.mp4", 160)).toBe(
      "https://res.cloudinary.com/demo/video/upload/v1/a.mp4",
    );
  });

  it("clamps the width", () => {
    expect(
      cloudinaryPreviewUrl("https://res.cloudinary.com/d/image/upload/a.png", 99999),
    ).toContain("w_2000");
    expect(cloudinaryPreviewUrl("https://res.cloudinary.com/d/image/upload/a.png", 1)).toContain(
      "w_16",
    );
  });
});

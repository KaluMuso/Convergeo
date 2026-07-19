import { describe, expect, it } from "vitest";

import {
  assertRscSafeGalleryLabels,
  formatPdpGalleryIndicator,
  type PdpGalleryLabelStrings,
} from "./gallery-labels";

describe("PDP galleryLabels RSC boundary (digest 1378788464)", () => {
  it("accepts serializable string labels used by the server page", () => {
    const labels: PdpGalleryLabelStrings = {
      empty: "No images yet",
      previous: "Previous image",
      next: "Next image",
    };

    expect(() => assertRscSafeGalleryLabels(labels)).not.toThrow();
    expect(JSON.stringify(labels)).toContain("No images yet");
  });

  it("rejects a function indicator prop — the live digest 1378788464 shape", () => {
    const unsafe = {
      empty: "No images yet",
      previous: "Previous image",
      next: "Next image",
      indicator: (current: number, total: number) => `Image ${current} of ${total}`,
    };

    expect(() => assertRscSafeGalleryLabels(unsafe)).toThrow(/digest 1378788464/);
    // JSON.stringify silently drops functions — the failure mode is RSC serialization,
    // not JSON; the guard above is what would have caught the bug in CI.
    expect(JSON.stringify(unsafe)).not.toContain("Image");
  });

  it("formats ICU-style indicator templates for en / fr / zh", () => {
    expect(formatPdpGalleryIndicator("Image {current} of {total}", 1, 3)).toBe("Image 1 of 3");
    expect(formatPdpGalleryIndicator("Image {current} sur {total}", 2, 4)).toBe("Image 2 sur 4");
    expect(formatPdpGalleryIndicator("第 {current}/{total} 张图片", 1, 1)).toBe("第 1/1 张图片");
  });
});

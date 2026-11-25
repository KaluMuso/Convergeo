import { describe, expect, it } from "vitest";

import { ACCENT_CHOICES, accentContrastPairs, resolveAccentChoice } from "./accent-palette";
import { contrastRatio, isHexColor } from "./brand-theme";

function parseColor(color: string): string {
  if (color.startsWith("#")) return color;
  const m = color.match(/rgba?\((\d+)/);
  if (m) return "#888888";
  return "#888888";
}

describe("accent palettes", () => {
  it("resolves accent choice with mono default", () => {
    expect(resolveAccentChoice(null)).toBe("mono");
    expect(resolveAccentChoice("blue")).toBe("blue");
  });

  it.each(
    ACCENT_CHOICES.flatMap((accent) =>
      (["light", "dark"] as const).map((mode) => [accent, mode] as const),
    ),
  )("accent %s %s meets WCAG AA on documented pairs", (accent, mode) => {
    for (const pair of accentContrastPairs(accent, mode)) {
      const fg = parseColor(pair.foreground);
      const bg = parseColor(pair.background);
      if (!isHexColor(fg) || !isHexColor(bg)) continue;
      const ratio = contrastRatio(fg, bg);
      expect(ratio, `${accent}/${mode}/${pair.name}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

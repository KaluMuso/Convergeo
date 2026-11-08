import { describe, expect, it } from "vitest";

import {
  brandThemeStyle,
  contrastRatio,
  ensureContrast,
  extractBrandTheme,
  sanitizeBrandTheme,
} from "./brand-theme";

describe("brand theme", () => {
  it("darkens a too-light primary until white text reaches AA", () => {
    const fixed = ensureContrast("#FFD84D", 4.5);
    expect(contrastRatio(fixed, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps an already-compliant colour unchanged", () => {
    expect(ensureContrast("#0B5D45", 4.5)).toBe("#0B5D45");
  });

  it("rejects malformed values and clamps the rest", () => {
    expect(sanitizeBrandTheme({ primary: "red", accent: "#12" })).toBeNull();
    const theme = sanitizeBrandTheme({ primary: "#7DD3FC", accent: "#FDE68A" });
    expect(theme).not.toBeNull();
    expect(contrastRatio(theme!.primary!, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(theme!.accent!, "#FFFFFF")).toBeGreaterThanOrEqual(3);
  });

  it("emits scoped CSS variables only for valid themes", () => {
    expect(brandThemeStyle(null)).toBeUndefined();
    const style = brandThemeStyle({ primary: "#C2410C", accent: null });
    expect(style?.["--brand-primary"]).toMatch(/^#[0-9A-F]{6}$/);
    expect(style?.["--brand-primary-tint"]).toBeDefined();
  });

  it("extracts a dominant saturated colour from logo pixels, ignoring white/grey", () => {
    const px: number[] = [];
    const push = (r: number, g: number, b: number, n: number) => {
      for (let i = 0; i < n; i += 1) px.push(r, g, b, 255);
    };
    push(255, 255, 255, 500); // background
    push(128, 128, 128, 200); // grey
    push(200, 30, 40, 300); // red mark
    push(20, 90, 200, 120); // blue mark
    const theme = extractBrandTheme(px);
    expect(theme?.primary).toBeTruthy();
    const [r] = [Number.parseInt(theme!.primary!.slice(1, 3), 16)];
    expect(r).toBeGreaterThan(100); // red family wins
    expect(theme?.accent).toBeTruthy();
  });

  it("returns null when the logo has no usable colour", () => {
    expect(extractBrandTheme([255, 255, 255, 255, 0, 0, 0, 255])).toBeNull();
  });
});

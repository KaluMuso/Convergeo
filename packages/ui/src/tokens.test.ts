import { describe, expect, it } from "vitest";

import { buildTailwindTheme } from "../tailwind-preset";
import { contrastPairs, tagTint, tokens } from "./tokens";

function parseHex(hex: string): [number, number, number] {
  const normalized = hex.replace("#", "");
  const r = Number.parseInt(normalized.slice(0, 2), 16);
  const g = Number.parseInt(normalized.slice(2, 4), 16);
  const b = Number.parseInt(normalized.slice(4, 6), 16);
  return [r, g, b];
}

function parseColor(color: string): [number, number, number] {
  if (color.startsWith("#")) {
    return parseHex(color);
  }
  const rgbaMatch = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (rgbaMatch) {
    return [Number(rgbaMatch[1]), Number(rgbaMatch[2]), Number(rgbaMatch[3])];
  }
  throw new Error(`Unsupported color format: ${color}`);
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(foreground: string, background: string): number {
  const fg = relativeLuminance(parseColor(foreground));
  const bg = relativeLuminance(parseColor(background));
  const lighter = Math.max(fg, bg);
  const darker = Math.min(fg, bg);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("tokens", () => {
  it("tagTint applies alpha suffix recipe", () => {
    expect(tagTint("#C8861A")).toEqual({
      bg: "#C8861A1A",
      border: "#C8861A33",
      text: "#C8861A",
    });
  });

  it("contrast pairs meet WCAG AA (≥4.5:1) for normal text", () => {
    for (const pair of contrastPairs) {
      const ratio = contrastRatio(pair.foreground, pair.background);
      expect(ratio, `${pair.name}: ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("tailwind preset theme", () => {
  const theme = buildTailwindTheme();

  it("matches snapshot of resolved theme keys", () => {
    expect(theme).toMatchSnapshot();
  });

  it("exports all required theme namespaces", () => {
    expect(theme.colors).toBeDefined();
    expect(theme.fontFamily).toBeDefined();
    expect(theme.fontSize).toBeDefined();
    expect(theme.spacing).toBeDefined();
    expect(theme.borderRadius).toBeDefined();
    expect(theme.boxShadow).toBeDefined();
    expect(theme.transitionDuration).toBeDefined();
    expect(theme.transitionTimingFunction).toBeDefined();
  });

  it("maps token colors into theme without default Tailwind palette", () => {
    const colors = theme.colors as Record<string, unknown>;
    expect(colors.bg).toBe(tokens.colors.bg);
    expect(colors.primary).toMatchObject({ DEFAULT: tokens.colors.primary });
    expect(colors.cat).toMatchObject({ beauty: tokens.colors.catBeauty });
    expect(colors.red).toBeUndefined();
    expect(colors.blue).toBeUndefined();
    expect(colors.slate).toBeUndefined();
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const stylesDir = fileURLToPath(new URL(".", import.meta.url));
const baseCss = readFileSync(resolve(stylesDir, "base.css"), "utf8");
const themeCss = readFileSync(resolve(stylesDir, "theme.css"), "utf8");

function reducedMotionBlock(css: string) {
  const start = css.indexOf("@media (prefers-reduced-motion: reduce)");
  expect(start).toBeGreaterThanOrEqual(0);
  return css.slice(start);
}

describe("motion CSS", () => {
  it("uses tokenized transforms instead of reduced-motion keyframe overrides", () => {
    const reduced = reducedMotionBlock(baseCss);

    expect(baseCss).toContain("--motion-rise-y: 8px");
    expect(baseCss).toContain("transform: translateY(var(--motion-rise-y))");
    expect(baseCss).toContain(
      "transform: translateY(var(--motion-toast-in-y)) scale(var(--motion-toast-in-scale))",
    );
    expect(baseCss).toContain("background-position: var(--motion-shimmer-from)");
    expect(baseCss).toContain("--motion-rise-y: 0px");
    expect(baseCss).toContain("--motion-pulse-scale: 1");
    expect(reduced).not.toMatch(/@keyframes/);
  });

  it("keeps entrance utilities opacity-only and removes stagger delays under reduced motion", () => {
    const reduced = reducedMotionBlock(themeCss);

    expect(reduced).toContain(".motion-rise,");
    expect(reduced).toContain(".motion-rise-slow,");
    expect(reduced).toContain(".motion-fade,");
    expect(reduced).toContain(".motion-stagger > *");
    expect(reduced).toContain("animation-duration: var(--dur-fast) !important");
    expect(reduced).toContain("animation-delay: 0ms !important");
  });
});

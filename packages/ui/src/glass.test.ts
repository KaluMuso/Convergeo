import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { glassClass } from "./glass";

const css = readFileSync(join(__dirname, "styles/base.css"), "utf8");

describe("glassClass", () => {
  it("maps variants to classes", () => {
    expect(glassClass()).toBe("v-glass v-glass--overlay");
    expect(glassClass("bar")).toBe("v-glass v-glass--bar");
    expect(glassClass("bar-bottom")).toContain("v-glass--bar-bottom");
    expect(glassClass("card")).toBe("v-glass v-glass--card");
  });
});

describe("glass css contract", () => {
  it("gates blur behind @supports and respects reduced transparency", () => {
    expect(css).toMatch(/@supports \(\(-webkit-backdrop-filter: blur\(1px\)\) or \(backdrop-filter: blur\(1px\)\)\)/);
    expect(css).toMatch(/prefers-reduced-transparency: reduce/);
  });
  it("defines dark overrides", () => {
    expect(css).toMatch(/\[data-theme="dark"\] \{\s*--glass-border/);
  });
  it("has an opaque fallback background on .v-glass", () => {
    expect(css).toMatch(/\.v-glass \{\s*background: var\(--glass-bg-fallback\)/);
  });
});

import { describe, expect, it } from "vitest";

import {
  DEFAULT_SEASONAL_PRESET,
  isSeasonalPresetId,
  resolveSeasonalPreset,
  seasonalThemeCss,
  SEASONAL_PRESET_IDS,
  THEME_PRESET_LIST,
  THEME_PRESETS,
} from "./theme-presets";

describe("resolveSeasonalPreset", () => {
  it("passes through every known id", () => {
    for (const id of SEASONAL_PRESET_IDS) {
      expect(resolveSeasonalPreset(id)).toBe(id);
    }
  });

  it("falls back to the default for missing/invalid config", () => {
    expect(resolveSeasonalPreset(undefined)).toBe(DEFAULT_SEASONAL_PRESET);
    expect(resolveSeasonalPreset(null)).toBe(DEFAULT_SEASONAL_PRESET);
    expect(resolveSeasonalPreset("")).toBe(DEFAULT_SEASONAL_PRESET);
    expect(resolveSeasonalPreset("winter")).toBe(DEFAULT_SEASONAL_PRESET);
    // Non-string config (e.g. a mistyped env object) must not throw.
    expect(resolveSeasonalPreset(42 as unknown as string)).toBe(DEFAULT_SEASONAL_PRESET);
  });

  it("trims and lowercases so operator config is forgiving", () => {
    expect(resolveSeasonalPreset("  Harvest ")).toBe("harvest");
    expect(resolveSeasonalPreset("EVERGREEN")).toBe("evergreen");
  });
});

describe("isSeasonalPresetId", () => {
  it("recognises known ids only", () => {
    expect(isSeasonalPresetId("harvest")).toBe(true);
    expect(isSeasonalPresetId("slate")).toBe(true);
    expect(isSeasonalPresetId("winter")).toBe(false);
    expect(isSeasonalPresetId(null)).toBe(false);
    expect(isSeasonalPresetId(7)).toBe(false);
  });
});

describe("seasonalThemeCss", () => {
  it("emits nothing for the default preset (base.css stays authoritative)", () => {
    expect(seasonalThemeCss("slate")).toBe("");
    expect(seasonalThemeCss(undefined)).toBe("");
    expect(seasonalThemeCss("winter")).toBe(""); // unknown ⇒ default ⇒ empty
  });

  it("emits a :root and dark block for a seasonal preset", () => {
    const css = seasonalThemeCss("harvest");
    expect(css).toContain(":root:root{");
    expect(css).toContain("--primary:#7a5214");
    expect(css).toContain(':root[data-theme="dark"]{');
    expect(css).toContain("--primary:#e0a429");
  });

  it("doubles selectors so overrides beat base.css by specificity, not order", () => {
    const css = seasonalThemeCss("harvest");
    // Light block must precede the dark block (source order settles the tie
    // between the two 0,2,0 selectors when data-theme=dark).
    expect(css.indexOf(":root:root{")).toBeLessThan(css.indexOf(':root[data-theme="dark"]{'));
  });

  it("includes ground overrides where a preset re-skins the page (mauve)", () => {
    expect(seasonalThemeCss("mauve")).toContain("--bg:#f3e8ee");
  });

  it("is deterministic and single-line (data frugality)", () => {
    const a = seasonalThemeCss("evergreen");
    const b = seasonalThemeCss("evergreen");
    expect(a).toBe(b);
    expect(a).not.toContain("\n");
  });

  it("is injection-proof — arbitrary config can never reach the output", () => {
    const css = seasonalThemeCss("</style><script>alert(1)</script>");
    expect(css).toBe(""); // resolves to default
    expect(css).not.toContain("script");
  });
});

describe("THEME_PRESETS invariants", () => {
  it("every id maps to a preset whose .id matches its key", () => {
    for (const id of SEASONAL_PRESET_IDS) {
      expect(THEME_PRESETS[id].id).toBe(id);
    }
  });

  it("lists presets in canonical order with the default first", () => {
    expect(THEME_PRESET_LIST.map((p) => p.id)).toEqual([...SEASONAL_PRESET_IDS]);
    expect(THEME_PRESET_LIST[0]?.id).toBe(DEFAULT_SEASONAL_PRESET);
  });

  it("the default preset is a genuine no-op", () => {
    expect(THEME_PRESETS[DEFAULT_SEASONAL_PRESET].light).toHaveLength(0);
    expect(THEME_PRESETS[DEFAULT_SEASONAL_PRESET].dark).toHaveLength(0);
  });

  it("seasonal presets override both light and dark, with a 3-colour swatch", () => {
    for (const id of SEASONAL_PRESET_IDS) {
      if (id === DEFAULT_SEASONAL_PRESET) continue;
      const preset = THEME_PRESETS[id];
      expect(preset.light.length).toBeGreaterThan(0);
      expect(preset.dark.length).toBeGreaterThan(0);
      expect(preset.swatch).toHaveLength(3);
    }
  });

  it("no override value contains characters that would break the minified block", () => {
    for (const id of SEASONAL_PRESET_IDS) {
      for (const [name, value] of [...THEME_PRESETS[id].light, ...THEME_PRESETS[id].dark]) {
        expect(name.startsWith("--")).toBe(true);
        expect(value).not.toMatch(/[{};]/);
      }
    }
  });
});

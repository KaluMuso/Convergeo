/**
 * Seasonal theme presets (design intent: docs/designs/SELECTION.md §8).
 *
 * A preset is a small bundle of CSS-custom-property overrides — brand tokens
 * only — that re-skins the whole app by swapping a handful of values, proving
 * the token system supports a full seasonal re-skin (audit §1.2). Presets are
 * applied globally (operator-selected, not per-user) via a server-rendered
 * inline <style> — see `seasonal-theme.tsx` — so the palette never flashes.
 *
 * Guardrails baked in:
 *  - The default ("slate") emits ZERO overrides — base.css stays the source of
 *    truth and the common case costs nothing.
 *  - Presets touch brand tokens only (primary family + accent + focus ring, and
 *    the ground for Dusty Mauve). Body text / semantic (success/danger/warning)
 *    tokens are never overridden, so documented WCAG AA pairs in `tokens.ts`
 *    hold regardless of the active preset.
 *  - Every light `--primary` keeps white button text ≥ 4.5:1; every dark
 *    `--primary` keeps the dark button text (`--primary-btn-fg`, #141312) ≥
 *    4.5:1. Values chosen against those thresholds (see per-preset notes).
 */

export const SEASONAL_PRESET_IDS = ["slate", "harvest", "mauve", "evergreen"] as const;

export type SeasonalPresetId = (typeof SEASONAL_PRESET_IDS)[number];

/** Falls back here for missing/invalid config — the shipped base palette. */
export const DEFAULT_SEASONAL_PRESET: SeasonalPresetId = "slate";

/** One CSS custom-property override: [`--var-name`, `value`]. Ordered for
 *  deterministic serialization (stable output + testable). */
export type TokenOverride = readonly [string, string];

export type ThemePreset = {
  readonly id: SeasonalPresetId;
  /** i18n key suffix under `admin.theme.presets.*` (name + blurb). */
  readonly i18nKey: string;
  /** Admin-preview swatch: [primary, accent, ground]. Presentational only. */
  readonly swatch: readonly [string, string, string];
  /** Overrides applied at `:root` (light). Empty ⇒ default, emits nothing. */
  readonly light: readonly TokenOverride[];
  /** Overrides applied at `[data-theme="dark"]`. */
  readonly dark: readonly TokenOverride[];
};

export const THEME_PRESETS: Record<SeasonalPresetId, ThemePreset> = {
  // Vergeo Slate — the shipped default. No-op: base.css is authoritative.
  slate: {
    id: "slate",
    i18nKey: "slate",
    swatch: ["#2d4a7a", "#c8861a", "#faf7f2"],
    light: [],
    dark: [],
  },

  // Harvest Gold — Independence season (October). Deep bronze primary keeps
  // white button text ~6.9:1; bright gold rides the accent slot.
  harvest: {
    id: "harvest",
    i18nKey: "harvest",
    swatch: ["#7a5214", "#e0a429", "#faf7f2"],
    light: [
      ["--primary", "#7a5214"],
      ["--primary-deep", "#5e3e0e"],
      ["--primary-tint", "#f7eedb"],
      ["--accent", "#e0a429"],
      ["--focus-ring", "0 0 0 3px rgba(122, 82, 20, 0.22)"],
    ],
    dark: [
      // Dark button fg is #141312; gold #e0a429 (L~0.42) → ~8.5:1.
      ["--primary", "#e0a429"],
      ["--primary-deep", "#c98d1e"],
      ["--primary-tint", "#3a3120"],
      ["--accent", "#f0c060"],
      ["--primary-btn-hover", "#eab545"],
      ["--focus-ring", "0 0 0 3px rgba(224, 164, 41, 0.35)"],
    ],
  },

  // Dusty Mauve — the bundle's #ddc5d2 ground experiment, softened to a tint so
  // dark body text stays ~12:1. Plum primary keeps white button text ~8.5:1.
  mauve: {
    id: "mauve",
    i18nKey: "mauve",
    swatch: ["#6e3d5b", "#b5828a", "#f3e8ee"],
    light: [
      ["--bg", "#f3e8ee"],
      ["--bg-2", "#ebdbe3"],
      ["--primary", "#6e3d5b"],
      ["--primary-deep", "#57304a"],
      ["--primary-tint", "#f0e2ea"],
      ["--accent", "#b5828a"],
      ["--focus-ring", "0 0 0 3px rgba(110, 61, 91, 0.22)"],
    ],
    dark: [
      ["--primary", "#c99bb2"],
      ["--primary-deep", "#b083a0"],
      ["--primary-tint", "#332831"],
      ["--accent", "#e0bec8"],
      ["--primary-btn-hover", "#d3a9bd"],
      ["--focus-ring", "0 0 0 3px rgba(201, 155, 178, 0.35)"],
    ],
  },

  // Festive Evergreen — delivers the audit's "Warm Dark" festive intent as a
  // distinct re-skin (a forced-dark preset would just duplicate the shipped
  // user dark-mode toggle and risk AA). Deep evergreen keeps white text ~9.9:1.
  evergreen: {
    id: "evergreen",
    i18nKey: "evergreen",
    swatch: ["#1f4a3d", "#c8861a", "#faf7f2"],
    light: [
      ["--primary", "#1f4a3d"],
      ["--primary-deep", "#163528"],
      ["--primary-tint", "#e1efe9"],
      ["--accent", "#c8861a"],
      ["--focus-ring", "0 0 0 3px rgba(31, 74, 61, 0.22)"],
    ],
    dark: [
      ["--primary", "#6fb89e"],
      ["--primary-deep", "#57a186"],
      ["--primary-tint", "#1e2a26"],
      ["--accent", "#d4a04a"],
      ["--primary-btn-hover", "#82c6ad"],
      ["--focus-ring", "0 0 0 3px rgba(111, 184, 158, 0.35)"],
    ],
  },
};

/** All presets in canonical order (default first) — for admin galleries. */
export const THEME_PRESET_LIST: readonly ThemePreset[] = SEASONAL_PRESET_IDS.map(
  (id) => THEME_PRESETS[id],
);

/** True for a known preset id. */
export function isSeasonalPresetId(value: unknown): value is SeasonalPresetId {
  return typeof value === "string" && (SEASONAL_PRESET_IDS as readonly string[]).includes(value);
}

/**
 * Collapse operator config (env value) into a concrete preset. Unknown/missing
 * ⇒ the default. Trims + lowercases so `SEASONAL_THEME="Harvest "` resolves.
 * This is the ONLY gate into the preset table, so untrusted-ish config can
 * never select anything but a known preset.
 */
export function resolveSeasonalPreset(raw: string | null | undefined): SeasonalPresetId {
  if (typeof raw !== "string") {
    return DEFAULT_SEASONAL_PRESET;
  }
  const normalized = raw.trim().toLowerCase();
  return isSeasonalPresetId(normalized) ? normalized : DEFAULT_SEASONAL_PRESET;
}

function serializeBlock(selector: string, overrides: readonly TokenOverride[]): string {
  if (overrides.length === 0) {
    return "";
  }
  const body = overrides.map(([name, value]) => `${name}:${value}`).join(";");
  return `${selector}{${body}}`;
}

/**
 * Build the inline CSS for a preset — a minified
 * `:root:root{…}:root[data-theme="dark"]{…}` string with only the overridden
 * vars. Resolves the id through the whitelist first, so it can only ever emit
 * values from the static table (never arbitrary config). Returns "" for the
 * default preset (nothing to override).
 *
 * Selectors are doubled (`:root:root`, `:root[data-theme="dark"]` → specificity
 * 0,2,0) so they outrank base.css's `:root` / `[data-theme="dark"]` (0,1,0) on
 * SPECIFICITY, not source order. That makes the seasonal palette authoritative
 * however the framework happens to order this inline <style> against the
 * imported stylesheet. The dark block trails the light block, so when
 * `data-theme="dark"` is set both match at equal specificity and the dark
 * values win by source order — exactly as the base cascade behaves.
 */
export function seasonalThemeCss(rawId: string | null | undefined): string {
  const preset = THEME_PRESETS[resolveSeasonalPreset(rawId)];
  return (
    serializeBlock(":root:root", preset.light) +
    serializeBlock(':root[data-theme="dark"]', preset.dark)
  );
}

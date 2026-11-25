/**
 * Per-user accent palettes (mono default, green/blue/gold optional).
 * Semantic colours (success/danger/warning/info) are shared across accents.
 */

export const ACCENT_STORAGE_KEY = "vg-accent";

export const ACCENT_CHOICES = ["mono", "green", "blue", "gold"] as const;
export type AccentChoice = (typeof ACCENT_CHOICES)[number];

export type AccentMode = "light" | "dark";

export type BrandTokens = {
  bg: string;
  bg2: string;
  surface: string;
  border: string;
  text: string;
  text2: string;
  text3: string;
  displayInk: string;
  primary: string;
  primaryDeep: string;
  primaryTint: string;
  accent: string;
  accentDeep: string;
  accentTint: string;
  panel: string;
  panel2: string;
  panelText: string;
  panelMuted: string;
  primaryBtnFg: string;
  primaryBtnHover: string;
  price: string;
};

const SEMANTIC_LIGHT = {
  success: "#1E7A4C",
  danger: "#B3261E",
  warning: "#B7791F",
  info: "#1D5E8C",
  onDanger: "#FFFFFF",
  price: "#18181B",
  discount: "#B3261E",
} as const;

const SEMANTIC_DARK = {
  success: "#1E7A4C",
  danger: "#B3261E",
  warning: "#B7791F",
  info: "#1D5E8C",
  onDanger: "#FFFFFF",
  price: "#FAFAFA",
  discount: "#EF8A80",
} as const;

export const MONO_LIGHT: BrandTokens = {
  bg: "#FAFAFA",
  bg2: "#F4F4F5",
  surface: "#FFFFFF",
  border: "#E4E4E7",
  text: "#18181B",
  text2: "#52525B",
  text3: "#71717A",
  displayInk: "#09090B",
  primary: "#18181B",
  primaryDeep: "#09090B",
  primaryTint: "#F4F4F5",
  accent: "#3F3F46",
  accentDeep: "#27272A",
  accentTint: "#F4F4F5",
  panel: "#18181B",
  panel2: "#27272A",
  panelText: "#FAFAFA",
  panelMuted: "#A1A1AA",
  primaryBtnFg: "#FFFFFF",
  primaryBtnHover: "#27272A",
  price: "#18181B",
};

export const MONO_DARK: BrandTokens = {
  bg: "#0A0A0B",
  bg2: "#111113",
  surface: "#18181B",
  border: "rgba(255,255,255,0.10)",
  text: "#FAFAFA",
  text2: "#A1A1AA",
  text3: "#A1A1AA",
  displayInk: "#FAFAFA",
  primary: "#FAFAFA",
  primaryDeep: "#E4E4E7",
  primaryTint: "#27272A",
  accent: "#D4D4D8",
  accentDeep: "#F4F4F5",
  accentTint: "#27272A",
  panel: "#18181B",
  panel2: "#27272A",
  panelText: "#FAFAFA",
  panelMuted: "#A1A1AA",
  primaryBtnFg: "#18181B",
  primaryBtnHover: "#E4E4E7",
  price: "#FAFAFA",
};

/** Shipped malachite/copper identity — selectable via Green accent. */
export const GREEN_LIGHT: BrandTokens = {
  bg: "#F7F6F2",
  bg2: "#EEEDE8",
  surface: "#FFFFFF",
  border: "#E3E1DA",
  text: "#15201B",
  text2: "#4A5550",
  text3: "#5E6963",
  displayInk: "#0F2A21",
  primary: "#0B5D45",
  primaryDeep: "#08473A",
  primaryTint: "#E3F0EA",
  accent: "#A4501C",
  accentDeep: "#7E3C12",
  accentTint: "#F6E8DD",
  panel: "#0F2A21",
  panel2: "#163A2E",
  panelText: "#F3F0E8",
  panelMuted: "#A9BFB4",
  primaryBtnFg: "#FFFFFF",
  primaryBtnHover: "#08473A",
  price: "#15201B",
};

export const GREEN_DARK: BrandTokens = {
  bg: "#121614",
  bg2: "#181D1A",
  surface: "#1B201D",
  border: "rgba(255,255,255,0.10)",
  text: "#E4E8E5",
  text2: "#A8B1AC",
  text3: "#8E9892",
  displayInk: "#E4E8E5",
  primary: "#5FC49C",
  primaryDeep: "#4AAE88",
  primaryTint: "#1D2C26",
  accent: "#E39255",
  accentDeep: "#F0AE7C",
  accentTint: "#2E2219",
  panel: "#0F2A21",
  panel2: "#163A2E",
  panelText: "#F3F0E8",
  panelMuted: "#A9BFB4",
  primaryBtnFg: "#121614",
  primaryBtnHover: "#78D0AD",
  price: "#E4E8E5",
};

export const BLUE_LIGHT: BrandTokens = {
  ...MONO_LIGHT,
  primary: "#1D4ED8",
  primaryDeep: "#1E3A8A",
  primaryTint: "#DBEAFE",
  accent: "#2563EB",
  accentDeep: "#1D4ED8",
  accentTint: "#EFF6FF",
  panel: "#172554",
  panel2: "#1E3A8A",
  panelText: "#EFF6FF",
  panelMuted: "#93C5FD",
  primaryBtnFg: "#FFFFFF",
  primaryBtnHover: "#1E3A8A",
};

export const BLUE_DARK: BrandTokens = {
  ...MONO_DARK,
  primary: "#60A5FA",
  primaryDeep: "#3B82F6",
  primaryTint: "#172554",
  accent: "#93C5FD",
  accentDeep: "#BFDBFE",
  accentTint: "#1E3A8A",
  panel: "#172554",
  panel2: "#1E3A8A",
  panelText: "#EFF6FF",
  panelMuted: "#93C5FD",
  primaryBtnFg: "#0A0A0B",
  primaryBtnHover: "#93C5FD",
};

export const GOLD_LIGHT: BrandTokens = {
  ...MONO_LIGHT,
  primary: "#92400E",
  primaryDeep: "#78350F",
  primaryTint: "#FEF3C7",
  accent: "#B45309",
  accentDeep: "#92400E",
  accentTint: "#FFFBEB",
  panel: "#451A03",
  panel2: "#78350F",
  panelText: "#FFFBEB",
  panelMuted: "#FCD34D",
  primaryBtnFg: "#FFFFFF",
  primaryBtnHover: "#78350F",
};

export const GOLD_DARK: BrandTokens = {
  ...MONO_DARK,
  primary: "#FBBF24",
  primaryDeep: "#F59E0B",
  primaryTint: "#451A03",
  accent: "#FCD34D",
  accentDeep: "#FDE68A",
  accentTint: "#78350F",
  panel: "#451A03",
  panel2: "#78350F",
  panelText: "#FFFBEB",
  panelMuted: "#FCD34D",
  primaryBtnFg: "#0A0A0B",
  primaryBtnHover: "#FCD34D",
};

export const ACCENT_PALETTES: Record<AccentChoice, { light: BrandTokens; dark: BrandTokens }> = {
  mono: { light: MONO_LIGHT, dark: MONO_DARK },
  green: { light: GREEN_LIGHT, dark: GREEN_DARK },
  blue: { light: BLUE_LIGHT, dark: BLUE_DARK },
  gold: { light: GOLD_LIGHT, dark: GOLD_DARK },
};

export function resolveAccentChoice(stored: string | null): AccentChoice {
  if (stored === "green" || stored === "blue" || stored === "gold" || stored === "mono") {
    return stored;
  }
  return "mono";
}

export type ContrastPair = {
  name: string;
  foreground: string;
  background: string;
};

/** WCAG AA pairs that must hold for every accent in both modes. */
export function accentContrastPairs(
  accent: AccentChoice,
  mode: AccentMode,
): readonly ContrastPair[] {
  const brand = ACCENT_PALETTES[accent][mode];
  const semantic = mode === "light" ? SEMANTIC_LIGHT : SEMANTIC_DARK;
  return [
    { name: "text-on-bg", foreground: brand.text, background: brand.bg },
    { name: "text-on-surface", foreground: brand.text, background: brand.surface },
    { name: "text-2-on-bg", foreground: brand.text2, background: brand.bg },
    { name: "text-3-on-bg", foreground: brand.text3, background: brand.bg },
    { name: "primary-on-surface", foreground: brand.primary, background: brand.surface },
    { name: "primary-button", foreground: brand.primaryBtnFg, background: brand.primary },
    { name: "panel-text-on-panel", foreground: brand.panelText, background: brand.panel },
    {
      name: "on-danger-on-danger",
      foreground: semantic.onDanger,
      background: semantic.danger,
    },
  ];
}

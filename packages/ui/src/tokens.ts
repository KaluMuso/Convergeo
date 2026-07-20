/**
 * Vergeo5 design tokens — source of truth: docs/design/vergeo5-ui-ux-audit.md §6
 * (supersedes aubergine dark panels from docs/designs/SELECTION.md §5).
 */

export const tokens = {
  colors: {
    bg: "#FAF7F2",
    bg2: "#F3EDE3",
    surface: "#FFFFFF",
    surfaceElevated: "#FFFFFF",
    border: "#E8DFD0",
    /** Marketing chrome (footer/heroes) — warm charcoal, not page-ground alias. */
    panel: "#1A1816",
    panel2: "#242220",
    panelText: "#F2EDE6",
    panelMuted: "#A39E96",
    panelBorder: "rgba(255,255,255,0.08)",
    text: "#2A2118",
    text2: "#6B5A3E",
    /** Raised for AA on cream (~4.5:1); decorative use only if lowered again. */
    text3: "#7A6A52",
    displayInk: "#23324E",
    primary: "#2D4A7A",
    primaryDeep: "#1F3557",
    primaryTint: "#E8F0FA",
    accent: "#C8861A",
    success: "#3A7A4A",
    danger: "#C0392B",
    warning: "#D4A020",
    info: "#2A6A9A",
    /** On-color for solid danger buttons (AA in light and dark). */
    onDanger: "#FFFFFF",
    price: "#2A2118",
    discount: "#C0392B",
    catBeauty: "#C9A88A",
    catHealth: "#7AAB8A",
    catFood: "#C9836A",
    catFitness: "#7A9AB5",
    catHome: "#B5A07A",
    catAuto: "#8A8AB5",
  },
  /** Concrete dark palette (warm charcoal). Mirrored in base.css [data-theme="dark"]. */
  darkColors: {
    bg: "#141312",
    bg2: "#1C1A18",
    surface: "#22201E",
    surfaceElevated: "#2A2826",
    border: "rgba(255,255,255,0.10)",
    text: "#F2EDE6",
    text2: "#B0A99F",
    /** Raised for AA on dark surface (~4.76:1); was #8A837A (~4.34:1). */
    text3: "#918A80",
    displayInk: "#F2EDE6",
    primary: "#7AA0D4",
    primaryDeep: "#5A82B8",
    primaryTint: "#2A323C",
    accent: "#D4A04A",
    price: "#F2EDE6",
    discount: "#E57368",
    onDanger: "#FFFFFF",
    primaryBtnFg: "#141312",
    primaryBtnHover: "#8BB0DC",
  },
  fonts: {
    display: "'DM Serif Display', Georgia, serif",
    displayAlt: "'Cormorant Garamond', Georgia, serif",
    body: "'DM Sans', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
  fontSize: {
    hero: "clamp(2rem, 6vw, 3.9rem)",
    h1: "1.75rem",
    h2: "clamp(1.35rem, 2.4vw, 2.1rem)",
    h3: "1.0625rem",
    body: "0.9375rem",
    sm: "0.8125rem",
    micro: "0.6875rem",
    price: "1.02rem",
  },
  spacing: {
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    5: "20px",
    6: "24px",
    8: "32px",
    12: "48px",
    16: "64px",
  },
  container: {
    max: "80rem",
    gutter: "16px",
    gutterLg: "24px",
  },
  borderRadius: {
    sm: "8px",
    DEFAULT: "12px",
    lg: "16px",
    pill: "999px",
  },
  boxShadow: {
    1: "0 1px 4px rgba(28,19,8,0.05)",
    2: "0 4px 24px rgba(28,19,8,0.07)",
    3: "0 12px 48px rgba(28,19,8,0.13)",
    focusRing: "0 0 0 3px rgba(45,74,122,0.18)",
  },
  transitionDuration: {
    fast: "150ms",
    DEFAULT: "250ms",
    slow: "400ms",
  },
  transitionTimingFunction: {
    out: "cubic-bezier(0.2, 0.8, 0.3, 1)",
    std: "cubic-bezier(0.4, 0, 0.2, 1)",
    spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
  },
} as const;

export type Tokens = typeof tokens;

/** Alpha-tint recipe for tag pills: bg @10%, border @20%, text = base color. */
export function tagTint(hex: string): {
  bg: string;
  border: string;
  text: string;
} {
  return {
    bg: `${hex}1A`,
    border: `${hex}33`,
    text: hex,
  };
}

/** Documented WCAG AA contrast pairs (normal text ≥4.5:1). */
export const contrastPairs = [
  {
    name: "text-on-ground",
    foreground: tokens.colors.text,
    background: tokens.colors.bg,
  },
  {
    name: "text-on-surface",
    foreground: tokens.colors.text,
    background: tokens.colors.surface,
  },
  {
    name: "text-2-on-ground",
    foreground: tokens.colors.text2,
    background: tokens.colors.bg,
  },
  {
    name: "text-3-on-ground",
    foreground: tokens.colors.text3,
    background: tokens.colors.bg,
  },
  {
    name: "display-ink-on-ground",
    foreground: tokens.colors.displayInk,
    background: tokens.colors.bg,
  },
  {
    name: "primary-on-tint",
    foreground: tokens.colors.primary,
    background: tokens.colors.primaryTint,
  },
  {
    name: "primary-on-surface",
    foreground: tokens.colors.primary,
    background: tokens.colors.surface,
  },
  {
    name: "panel-text-on-panel",
    foreground: tokens.colors.panelText,
    background: tokens.colors.panel,
  },
  {
    name: "panel-muted-on-panel",
    foreground: tokens.colors.panelMuted,
    background: tokens.colors.panel,
  },
  {
    name: "success-on-ground",
    foreground: tokens.colors.success,
    background: tokens.colors.bg,
  },
  {
    name: "danger-on-ground",
    foreground: tokens.colors.danger,
    background: tokens.colors.bg,
  },
  {
    name: "on-danger-on-danger",
    foreground: tokens.colors.onDanger,
    background: tokens.colors.danger,
  },
  {
    name: "dark-text-on-bg",
    foreground: tokens.darkColors.text,
    background: tokens.darkColors.bg,
  },
  {
    name: "dark-text-2-on-bg",
    foreground: tokens.darkColors.text2,
    background: tokens.darkColors.bg,
  },
  {
    name: "dark-text-3-on-surface",
    foreground: tokens.darkColors.text3,
    background: tokens.darkColors.surface,
  },
  {
    name: "dark-text-3-on-bg",
    foreground: tokens.darkColors.text3,
    background: tokens.darkColors.bg,
  },
  {
    name: "dark-on-danger-on-danger",
    foreground: tokens.darkColors.onDanger,
    background: tokens.colors.danger,
  },
  {
    name: "dark-primary-btn-fg-on-primary",
    foreground: tokens.darkColors.primaryBtnFg,
    background: tokens.darkColors.primary,
  },
] as const;

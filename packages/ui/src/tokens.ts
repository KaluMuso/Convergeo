/**
 * Vergeo5 design tokens — "Copperbelt" system (storefront redesign, Nov 2026).
 *
 * DESIGN PLAN
 * ───────────
 * v2 default: neutral mono (zinc) light/dark, following the system theme. Users
 * can opt into Green (legacy malachite/copper), Blue, or Gold accents via
 * `data-accent` on `<html>`. Semantic colours are shared across accents.
 *
 * Colour (light, mono default)
 *   ground  #FAFAFA
 *   surface #FFFFFF
 *   ink     #18181B
 *   primary #18181B — near-black CTAs, white label text
 *   accent  #3F3F46 — secondary chrome
 * Green accent restores malachite #0B5D45 + copper #A4501C (see accent-palette.ts).
 *
 * Type
 *   display Bricolage Grotesque (variable, latin subset) — a grotesk with ink
 *           traps and optical character; set tight (-0.02em) at 600–800 for
 *           headlines, prices and wordmark-adjacent UI. Legible at 360px on
 *           low-end Android, unlike the hairline serif it replaces.
 *   body    DM Sans — retained: highly legible, already cached, low bytes.
 *   mono    JetBrains Mono — order IDs, OTP, USSD codes only.
 *   Scale (1.25 minor third-ish, clamped for 360px): micro 11 · sm 13 ·
 *   body 15 · h3 17 · h2 22→30 · h1 28→42 · hero 34→60.
 *
 * Layout & shape
 *   Left-aligned content; 4px spacing grid; container 1400px, gutter 16/28.
 *   Radii carry hierarchy: sm 8 (chips/inputs) · DEFAULT 12 (cards/buttons) ·
 *   lg 16 (sheets/media) · xl 24 (hero + promo panels) · pill (badges/search).
 *   Elevation keyed to malachite-black, three steps; hairline borders first,
 *   shadow only for things that float (menus, sheets, toasts, hover lift).
 *
 * Principles
 *   1. One bold thing: the malachite-night hero/escrow panels with the copper
 *      seal. Everything else is quiet, white, and dense like a real store.
 *   2. Trust is shown, not claimed: escrow steps, MoMo rails, verified badges
 *      reuse the same seal + malachite vocabulary everywhere.
 *   3. Every byte earns its place on 3G: one variable display face, no icon
 *      font, CSS-only motion that collapses under reduced-motion.
 */

import { GREEN_DARK, GREEN_LIGHT, MONO_DARK, MONO_LIGHT } from "./accent-palette";

export const tokens = {
  colors: {
    bg: MONO_LIGHT.bg,
    bg2: MONO_LIGHT.bg2,
    surface: "#FFFFFF",
    surfaceElevated: "#FFFFFF",
    border: MONO_LIGHT.border,
    panel: MONO_LIGHT.panel,
    panel2: MONO_LIGHT.panel2,
    panelText: MONO_LIGHT.panelText,
    panelMuted: MONO_LIGHT.panelMuted,
    panelBorder: "rgba(255,255,255,0.12)",
    text: MONO_LIGHT.text,
    text2: MONO_LIGHT.text2,
    /** AA on bg and bg-2 (~4.6:1 on #F4F4F5). */
    text3: "#5F6570",
    displayInk: MONO_LIGHT.displayInk,
    primary: MONO_LIGHT.primary,
    primaryDeep: MONO_LIGHT.primaryDeep,
    primaryTint: MONO_LIGHT.primaryTint,
    accent: MONO_LIGHT.accent,
    accentDeep: MONO_LIGHT.accentDeep,
    accentTint: MONO_LIGHT.accentTint,
    success: "#1E7A4C",
    danger: "#B3261E",
    warning: "#B7791F",
    info: "#1D5E8C",
    /** On-color for solid danger buttons (AA in light and dark). */
    onDanger: "#FFFFFF",
    price: MONO_LIGHT.text,
    discount: "#B3261E",
    catBeauty: "#C9A88A",
    catHealth: "#7AAB8A",
    catFood: "#C9836A",
    catFitness: "#7A9AB5",
    catHome: "#B5A07A",
    catAuto: "#8A8AB5",
  },
  /** Concrete dark palette (mono). Mirrored in base.css [data-theme="dark"]. */
  darkColors: {
    bg: MONO_DARK.bg,
    bg2: MONO_DARK.bg2,
    surface: MONO_DARK.surface,
    surfaceElevated: "#27272A",
    border: MONO_DARK.border,
    text: MONO_DARK.text,
    text2: MONO_DARK.text2,
    text3: MONO_DARK.text3,
    displayInk: MONO_DARK.displayInk,
    primary: MONO_DARK.primary,
    primaryDeep: MONO_DARK.primaryDeep,
    primaryTint: MONO_DARK.primaryTint,
    accent: MONO_DARK.accent,
    price: MONO_DARK.text,
    discount: "#EF8A80",
    onDanger: "#FFFFFF",
    primaryBtnFg: MONO_DARK.primaryBtnFg,
    primaryBtnHover: MONO_DARK.primaryBtnHover,
  },
  fonts: {
    display: "'Bricolage Grotesque', 'DM Sans', system-ui, sans-serif",
    /** Kept as an alias so existing `font-display-alt` utilities resolve. */
    displayAlt: "'Bricolage Grotesque', 'DM Sans', system-ui, sans-serif",
    body: "'DM Sans', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
  fontSize: {
    hero: "clamp(2.125rem, 1.4rem + 3.2vw, 3.75rem)",
    h1: "clamp(1.75rem, 1.35rem + 1.8vw, 2.625rem)",
    h2: "clamp(1.375rem, 1.15rem + 1vw, 1.875rem)",
    h3: "1.0625rem",
    body: "0.9375rem",
    sm: "0.8125rem",
    micro: "0.6875rem",
    price: "1.0625rem",
  },
  spacing: {
    0: "0px",
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    5: "20px",
    6: "24px",
    7: "28px",
    8: "32px",
    9: "36px",
    10: "40px",
    11: "44px",
    12: "48px",
    13: "52px",
    14: "56px",
    15: "60px",
    16: "64px",
    18: "72px",
  },
  container: {
    max: "87.5rem",
    gutter: "16px",
    gutterLg: "28px",
  },
  borderRadius: {
    sm: "8px",
    DEFAULT: "12px",
    lg: "16px",
    xl: "24px",
    pill: "999px",
  },
  boxShadow: {
    1: "0 1px 2px rgba(15,42,33,0.06), 0 2px 8px rgba(15,42,33,0.05)",
    2: "0 2px 4px rgba(15,42,33,0.06), 0 8px 24px rgba(15,42,33,0.10)",
    3: "0 4px 8px rgba(15,42,33,0.06), 0 20px 48px rgba(15,42,33,0.16)",
    focusRing: "0 0 0 2px #FFFFFF, 0 0 0 4px rgba(11,93,69,0.55)",
  },
  transitionDuration: {
    fast: "120ms",
    DEFAULT: "200ms",
    page: "320ms",
    slow: "400ms",
  },
  transitionTimingFunction: {
    out: "cubic-bezier(0.2, 0.8, 0.3, 1)",
    std: "cubic-bezier(0.4, 0, 0.2, 1)",
    spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
  },
} as const;

/** Legacy malachite palette — Green accent + backwards-compatible references. */
export const greenBrandTokens = { light: GREEN_LIGHT, dark: GREEN_DARK };

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
    name: "primary-button-text",
    foreground: "#FFFFFF",
    background: tokens.colors.primary,
  },
  {
    name: "accent-on-ground",
    foreground: tokens.colors.accent,
    background: tokens.colors.bg,
  },
  {
    name: "accent-on-surface",
    foreground: tokens.colors.accent,
    background: tokens.colors.surface,
  },
  {
    name: "accent-deep-on-accent-tint",
    foreground: tokens.colors.accentDeep,
    background: tokens.colors.accentTint,
  },
  {
    name: "text-3-on-ground-2",
    foreground: tokens.colors.text3,
    background: tokens.colors.bg2,
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

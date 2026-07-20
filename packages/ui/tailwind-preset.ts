import type { Config } from "tailwindcss";

import { tokens } from "./src/tokens";

/**
 * Tailwind 4 theme derived from tokens.ts.
 * Default palette is replaced (not extended) so only design-system colors resolve.
 */
export function buildTailwindTheme(): NonNullable<Config["theme"]> {
  const {
    colors,
    fonts,
    fontSize,
    spacing,
    borderRadius,
    boxShadow,
    transitionDuration,
    transitionTimingFunction,
  } = tokens;

  return {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      bg: colors.bg,
      "bg-2": colors.bg2,
      surface: colors.surface,
      "surface-elevated": colors.surfaceElevated,
      border: colors.border,
      panel: colors.panel,
      "panel-2": colors.panel2,
      "panel-text": colors.panelText,
      "panel-muted": colors.panelMuted,
      "panel-border": colors.panelBorder,
      text: colors.text,
      "text-2": colors.text2,
      "text-3": colors.text3,
      "display-ink": colors.displayInk,
      primary: {
        DEFAULT: colors.primary,
        deep: colors.primaryDeep,
        tint: colors.primaryTint,
      },
      accent: colors.accent,
      success: colors.success,
      danger: colors.danger,
      warning: colors.warning,
      info: colors.info,
      "on-danger": colors.onDanger,
      price: colors.price,
      discount: colors.discount,
      cat: {
        beauty: colors.catBeauty,
        health: colors.catHealth,
        food: colors.catFood,
        fitness: colors.catFitness,
        home: colors.catHome,
        auto: colors.catAuto,
      },
    },
    fontFamily: {
      display: [fonts.display],
      "display-alt": [fonts.displayAlt],
      body: [fonts.body],
      mono: [fonts.mono],
      sans: [fonts.body],
      serif: [fonts.display],
    },
    fontSize: {
      hero: [fontSize.hero, { lineHeight: "1.1" }],
      h1: [fontSize.h1, { lineHeight: "1.15" }],
      h2: [fontSize.h2, { lineHeight: "1.2" }],
      h3: [fontSize.h3, { lineHeight: "1.3", fontWeight: "600" }],
      body: [fontSize.body, { lineHeight: "1.55" }],
      sm: [fontSize.sm, { lineHeight: "1.45" }],
      micro: [fontSize.micro, { lineHeight: "1.3", letterSpacing: "0.08em" }],
      price: [fontSize.price, { lineHeight: "1.2", fontWeight: "700" }],
    },
    spacing,
    borderRadius,
    boxShadow,
    transitionDuration,
    transitionTimingFunction,
  };
}

const tailwindPreset: Config = {
  theme: buildTailwindTheme(),
};

export default tailwindPreset;

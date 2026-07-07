import { Cormorant_Garamond, DM_Sans, DM_Serif_Display, JetBrains_Mono } from "next/font/google";

/** Body / UI — active default. */
export const fontBody = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

/** Display serif — active default (360px-legible strokes). */
export const fontDisplay = DM_Serif_Display({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-display",
  display: "swap",
});

/** Order IDs, OTP, tabular amounts. */
export const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

/**
 * Inactive alternate display preset — desktop oversized-hero option per SELECTION.md.
 * Wire via `fontDisplayCormorant.variable` instead of `fontDisplay.variable` to activate.
 */
export const fontDisplayCormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--font-display-alt",
  display: "swap",
});

/** Class names to apply on `<html>` or `<body>` for active font CSS variables. */
export function fontVariables(activeDisplay: "dm-serif" | "cormorant" = "dm-serif"): string {
  const displayVar =
    activeDisplay === "cormorant" ? fontDisplayCormorant.variable : fontDisplay.variable;
  return [fontBody.variable, displayVar, fontMono.variable].join(" ");
}

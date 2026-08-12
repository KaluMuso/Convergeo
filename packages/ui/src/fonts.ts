import { Cormorant_Garamond, DM_Sans, DM_Serif_Display, JetBrains_Mono } from "next/font/google";

/** Body / UI — active default. */
export const fontBody = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

/** Display serif — active default from the audited design reference. */
export const fontDisplay = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

/** Order IDs, OTP, tabular amounts. */
export const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

/** Backwards-compatible name for consumers that selected Cormorant explicitly. */
export const fontDisplayCormorant = fontDisplay;

/** Optional legacy display preset; Cormorant remains the application default. */
export const fontDisplayDmSerif = DM_Serif_Display({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-display",
  display: "swap",
});

/** Class names to apply on `<html>` or `<body>` for active font CSS variables. */
export function fontVariables(activeDisplay: "dm-serif" | "cormorant" = "cormorant"): string {
  const displayVar =
    activeDisplay === "dm-serif" ? fontDisplayDmSerif.variable : fontDisplay.variable;
  return [fontBody.variable, displayVar, fontMono.variable].join(" ");
}

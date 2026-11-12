import { Bricolage_Grotesque, DM_Sans, JetBrains_Mono } from "next/font/google";

/** Body / UI — highly legible grotesk, retained from the audited reference. */
export const fontBody = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

/**
 * Display — Bricolage Grotesque (variable wght axis only, latin subset).
 * Characterful ink-trapped grotesk for headlines, prices and section titles;
 * replaces the hairline Cormorant serif, which broke down at 360px.
 */
export const fontDisplay = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  adjustFontFallback: true,
});

/** Order IDs, OTP, tabular amounts. Not preloaded — rare on first paint. */
export const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  preload: false,
});

/** Class names to apply on `<html>` for the active font CSS variables. */
export function fontVariables(): string {
  return [fontBody.variable, fontDisplay.variable, fontMono.variable].join(" ");
}

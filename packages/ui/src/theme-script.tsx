/**
 * No-FOUC theme bootstrap.
 *
 * `THEME_STORAGE_KEY` and `resolveInitialTheme` are the single source of truth for
 * how a persisted choice + OS preference collapse into the concrete `light`/`dark`
 * value written to `document.documentElement.dataset.theme`. Both the inline
 * pre-paint `<script>` (below) and the runtime `ThemeProvider` use this logic so
 * they never disagree (which would cause a flash on hydration).
 *
 * `ACCENT_STORAGE_KEY` / `data-accent` follow the same pattern for per-user brand
 * accent (mono default; green, blue, gold optional).
 */

import { ACCENT_STORAGE_KEY, resolveAccentChoice, type AccentChoice } from "./accent-palette";

export { ACCENT_STORAGE_KEY, resolveAccentChoice, type AccentChoice };

export const THEME_STORAGE_KEY = "vg-theme";

export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

/** Collapse a stored choice (or none) + OS preference into a concrete theme. */
export function resolveInitialTheme(stored: string | null, prefersDark: boolean): ResolvedTheme {
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return prefersDark ? "dark" : "light";
}

/**
 * Serialised IIFE injected into <head> before first paint. Reads localStorage +
 * `prefers-color-scheme` and stamps `data-theme` on <html> so the token palette
 * (and body bg/text) paint correctly with no flash. Self-contained, no imports,
 * wrapped in try/catch so a storage exception can never block render.
 *
 * CSP note: this is inline. The customer CSP ships script policy as
 * Content-Security-Policy-Report-Only (nonce placeholder not yet substituted),
 * so it executes and is only reported; vendor/admin set no script CSP. When a
 * live per-request nonce lands, pass it through `nonce` on <ThemeScript/>.
 */
export const THEME_SCRIPT = `(function(){try{var tk="${THEME_STORAGE_KEY}";var ak="${ACCENT_STORAGE_KEY}";var ts=localStorage.getItem(tk);var d=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=(ts==="light"||ts==="dark")?ts:(d?"dark":"light");document.documentElement.dataset.theme=t;var a=localStorage.getItem(ak);var ac=(a==="mono"||a==="green"||a==="blue"||a==="gold")?a:"mono";document.documentElement.dataset.accent=ac;}catch(e){document.documentElement.dataset.accent="mono";}})();`;

/** Renders the pre-paint bootstrap script. Place first in the app shell. */
export function ThemeScript({ nonce }: { nonce?: string }) {
  return <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />;
}

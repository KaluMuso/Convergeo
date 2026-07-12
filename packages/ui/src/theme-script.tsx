/**
 * No-FOUC theme bootstrap.
 *
 * `THEME_STORAGE_KEY` and `resolveInitialTheme` are the single source of truth for
 * how a persisted choice + OS preference collapse into the concrete `light`/`dark`
 * value written to `document.documentElement.dataset.theme`. Both the inline
 * pre-paint `<script>` (below) and the runtime `ThemeProvider` use this logic so
 * they never disagree (which would cause a flash on hydration).
 */

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
export const THEME_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}";var s=localStorage.getItem(k);var d=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=(s==="light"||s==="dark")?s:(d?"dark":"light");document.documentElement.dataset.theme=t;}catch(e){}})();`;

/** Renders the pre-paint bootstrap script. Place first in the app shell. */
export function ThemeScript({ nonce }: { nonce?: string }) {
  return <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />;
}

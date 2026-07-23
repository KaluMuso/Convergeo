/**
 * Server-rendered seasonal theme applier (design intent: SELECTION.md §8).
 *
 * Renders the active preset's brand-token overrides as an inline <style> in
 * <head>. Because it's plain server-rendered CSS (no client JS, no storage
 * read), the seasonal palette is present in the very first paint — there is no
 * flash to correct on hydration, and nothing ships to the client bundle.
 *
 * The active preset is operator-selected and global, so — unlike light/dark,
 * which is per-user and needs the pre-paint `ThemeScript` — a static <style> is
 * both sufficient and cheaper (zero per-request DB/JS cost). Its overrides beat
 * base.css by specificity (see `seasonalThemeCss`), so placement is not
 * order-sensitive; the dark block simply applies once `ThemeScript` stamps
 * `data-theme` on <html>.
 *
 * CSP: emits one <style> element. The app already relies on inline `style={…}`
 * attributes throughout (style-src must allow inline), so this adds no new
 * policy surface. Pass `nonce` through when a live per-request nonce lands.
 */
import { resolveSeasonalPreset, seasonalThemeCss } from "./theme-presets";

export type SeasonalThemeStyleProps = {
  /** Operator config (e.g. `process.env.SEASONAL_THEME`). Invalid ⇒ default. */
  preset?: string | null;
  /** CSP nonce, forwarded to the <style> element when available. */
  nonce?: string;
};

export function SeasonalThemeStyle({ preset, nonce }: SeasonalThemeStyleProps) {
  const css = seasonalThemeCss(preset);
  // Default preset ⇒ no overrides ⇒ render nothing (base.css is authoritative).
  if (css.length === 0) {
    return null;
  }
  return (
    <style
      // Resolved id (not raw config) — safe, whitelist-gated attribute value.
      data-seasonal-theme={resolveSeasonalPreset(preset)}
      nonce={nonce}
      dangerouslySetInnerHTML={{ __html: css }}
    />
  );
}

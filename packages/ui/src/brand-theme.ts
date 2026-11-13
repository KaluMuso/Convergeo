/**
 * Vendor brand theming helpers (shared by the vendor editor and the customer
 * storefront). A vendor picks a primary + accent colour, or extracts them from
 * their logo; both are clamped so the storefront stays WCAG AA:
 *  - primary: white button text on it must reach 4.5:1 (it is the CTA fill);
 *  - accent: as text/marks on white surfaces it must reach 3:1 (large UI text
 *    and graphical objects), and is darkened further when used for body text.
 * Pure functions, no DOM — safe on the server and in tests.
 */

export type BrandTheme = {
  primary: string | null;
  accent: string | null;
};

const HEX_RE = /^#[0-9a-f]{6}$/i;

export function isHexColor(value: unknown): value is string {
  return typeof value === "string" && HEX_RE.test(value);
}

export function hexToRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgbToHex([r, g, b]: [number, number, number]): string {
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  return `#${[r, g, b]
    .map((v) => clamp(v).toString(16).padStart(2, "0"))
    .join("")}`.toUpperCase();
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/**
 * Darken `hex` toward black in small steps until it reaches `min` contrast
 * against `against` (default white). Hue is preserved; returns the input when
 * it already passes.
 */
export function ensureContrast(hex: string, min = 4.5, against = "#FFFFFF"): string {
  if (!isHexColor(hex)) {
    return hex;
  }
  let [r, g, b] = hexToRgb(hex);
  let current = rgbToHex([r, g, b]);
  for (let i = 0; i < 40 && contrastRatio(current, against) < min; i += 1) {
    r *= 0.92;
    g *= 0.92;
    b *= 0.92;
    current = rgbToHex([r, g, b]);
  }
  return current;
}

/** Normalise + enforce AA on a stored/proposed theme. Invalid values → null. */
export function sanitizeBrandTheme(input: unknown): BrandTheme | null {
  if (!input || typeof input !== "object") {
    return null;
  }
  const raw = input as Record<string, unknown>;
  const primary = isHexColor(raw.primary) ? ensureContrast(raw.primary, 4.5) : null;
  const accent = isHexColor(raw.accent) ? ensureContrast(raw.accent, 3) : null;
  if (!primary && !accent) {
    return null;
  }
  return { primary, accent };
}

/** Mix `hex` with white by `amount` (0–1) — used for the tint token. */
export function tint(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex([r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount]);
}

/**
 * CSS custom properties that re-skin a storefront subtree. Applied as an
 * inline style on the storefront wrapper only — never globally. Dark mode keeps
 * the platform palette (vendor colours are tuned for light surfaces).
 */
export function brandThemeStyle(theme: BrandTheme | null): Record<string, string> | undefined {
  const safe = sanitizeBrandTheme(theme);
  if (!safe) {
    return undefined;
  }
  const style: Record<string, string> = {};
  if (safe.primary) {
    style["--brand-primary"] = safe.primary;
    style["--brand-primary-deep"] = ensureContrast(safe.primary, 7);
    style["--brand-primary-tint"] = tint(safe.primary, 0.88);
  }
  if (safe.accent) {
    style["--brand-accent"] = safe.accent;
  }
  return style;
}

/**
 * Derive a palette from logo pixels (RGBA bytes from a canvas). Quantises to a
 * 4-bit-per-channel histogram, ignores transparent, near-white, near-black and
 * grey pixels, and returns the most common saturated colour as primary and the
 * most distinct runner-up as accent — both AA-clamped.
 */
export function extractBrandTheme(pixels: ArrayLike<number>): BrandTheme | null {
  const buckets = new Map<number, { count: number; r: number; g: number; b: number }>();
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    const r = pixels[i] ?? 0;
    const g = pixels[i + 1] ?? 0;
    const b = pixels[i + 2] ?? 0;
    const a = pixels[i + 3] ?? 0;
    if (a < 128) continue;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    if (max > 240 && min > 225) continue; // near white
    if (max < 28) continue; // near black
    if (max - min < 28) continue; // grey
    const key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
    const bucket = buckets.get(key) ?? { count: 0, r: 0, g: 0, b: 0 };
    bucket.count += 1;
    bucket.r += r;
    bucket.g += g;
    bucket.b += b;
    buckets.set(key, bucket);
  }
  const ranked = [...buckets.values()]
    .sort((x, y) => y.count - x.count)
    .map((bucket) =>
      rgbToHex([bucket.r / bucket.count, bucket.g / bucket.count, bucket.b / bucket.count]),
    );
  const first = ranked[0];
  if (!first) {
    return null;
  }
  const distinct = ranked.find((hex) => colourDistance(hex, first) > 90) ?? null;
  return sanitizeBrandTheme({ primary: first, accent: distinct });
}

function colourDistance(a: string, b: string): number {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return Math.sqrt((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2);
}

// Pseudo-locale generator (`en-XA`) — a COVERAGE PROOF, not a real translation.
//
// Every EN message value is accented and wrapped in `[!! … !!]` brackets so that,
// when the app renders under `en-XA`, any string that reached the screen WITHOUT
// going through next-intl (a hardcoded literal) is instantly visible as bare,
// un-bracketed, un-accented ASCII. ICU placeholders/sub-messages (inside `{…}`)
// are left intact so interpolation and plural selection keep working.
//
// DEV/CI-ONLY: `en-XA` is deliberately NOT added to `LOCALES` (packages/i18n/
// src/locales.ts) — it never ships as a production locale. It is generated at
// build/CI time from the EN namespace files.
//
// The transform below is intentionally tiny and pure. It is MIRRORED in
// `scripts/ci/i18n-lint.mjs --pseudo-smoke`, which is the CI runner (CI pins
// Node 20 via .nvmrc and cannot execute TypeScript directly). Keep the two in
// sync — both are covered by the smoke's determinism assertions.

export const PSEUDO_LOCALE = "en-XA";

export const PSEUDO_OPEN = "[!!";
export const PSEUDO_CLOSE = "!!]";

// Readable Latin-1 accent map — foreign-looking but still legible so reviewers
// can eyeball a pseudo screen. Only these letters are substituted; others pass
// through unchanged.
export const ACCENT_MAP: Readonly<Record<string, string>> = {
  a: "á",
  b: "ƀ",
  c: "ç",
  d: "ð",
  e: "é",
  f: "ƒ",
  g: "ĝ",
  h: "ĥ",
  i: "í",
  j: "ĵ",
  k: "ķ",
  l: "ļ",
  m: "ɱ",
  n: "ñ",
  o: "ö",
  p: "þ",
  q: "ɋ",
  r: "ř",
  s: "š",
  t: "ŧ",
  u: "ú",
  v: "ʋ",
  w: "ŵ",
  x: "×",
  y: "ý",
  z: "ž",
  A: "Á",
  B: "Ɓ",
  C: "Ç",
  D: "Ð",
  E: "É",
  F: "Ƒ",
  G: "Ĝ",
  H: "Ĥ",
  I: "Í",
  J: "Ĵ",
  K: "Ķ",
  L: "Ļ",
  M: "Ṁ",
  N: "Ñ",
  O: "Ö",
  P: "Þ",
  Q: "Ɋ",
  R: "Ř",
  S: "Š",
  T: "Ŧ",
  U: "Ú",
  V: "Ʋ",
  W: "Ŵ",
  X: "Ẋ",
  Y: "Ý",
  Z: "Ž",
};

type Messages = { [key: string]: string | Messages };

/**
 * Accent every letter OUTSIDE `{…}` groups and wrap the whole value in
 * `[!! … !!]`. ICU placeholders and plural sub-messages (which live inside
 * braces) are preserved verbatim so runtime interpolation still resolves.
 */
export function pseudoString(value: string): string {
  let out = "";
  let depth = 0;
  for (const ch of value) {
    if (ch === "{") {
      depth += 1;
      out += ch;
    } else if (ch === "}") {
      depth = Math.max(0, depth - 1);
      out += ch;
    } else if (depth === 0) {
      out += ACCENT_MAP[ch] ?? ch;
    } else {
      out += ch;
    }
  }
  return `${PSEUDO_OPEN}${out}${PSEUDO_CLOSE}`;
}

/** True when a rendered string went through the pseudo transform (is bracketed). */
export function isPseudo(value: string): boolean {
  return value.startsWith(PSEUDO_OPEN) && value.endsWith(PSEUDO_CLOSE);
}

/** Deep-map a messages tree (nested objects + flat dotted keys) to `en-XA`. */
export function pseudoMessages(messages: Messages): Messages {
  const out: Messages = {};
  for (const [key, value] of Object.entries(messages)) {
    out[key] = typeof value === "string" ? pseudoString(value) : pseudoMessages(value);
  }
  return out;
}

/**
 * Throw if any leaf in a pseudo-localized tree is NOT bracketed — i.e. a raw-EN
 * string slipped through. Returns the number of leaves verified.
 */
export function assertAllPseudo(messages: Messages, path = ""): number {
  let count = 0;
  for (const [key, value] of Object.entries(messages)) {
    const here = path ? `${path}.${key}` : key;
    if (typeof value === "string") {
      if (!isPseudo(value)) {
        throw new Error(`en-XA coverage gap: "${here}" rendered raw EN → "${value}"`);
      }
      count += 1;
    } else {
      count += assertAllPseudo(value, here);
    }
  }
  return count;
}

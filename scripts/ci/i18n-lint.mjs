#!/usr/bin/env node
// i18n completeness & formatting sweep for Vergeo5 (M16-P03).
//
// Deterministic, offline, dependency-free. Builds ON the eslint rule
// `packages/config/eslint-rules/no-hardcoded-strings.js` (JSX text + a few
// user-facing string-literal attributes, WARN-only in ci.yml) by adding a
// stricter, BLOCKING repo-wide sweep with three checks:
//
//   1. Hardcoded-string scan — JSX text + user-facing attributes, extended to
//      TEMPLATE LITERALS, the full `aria-*` family, and `<meta content>` /
//      `title` / `alt` text that the eslint rule does not cover.
//   2. Missing-key detection — collects `useTranslations`/`getTranslations`/
//      `createTranslator` scopes + `t('…')` key usages and diffs them against
//      the keys DEFINED in `packages/i18n/messages/en/*.json`. Used-but-undefined
//      => error (runtime MISSING_MESSAGE guard); defined-but-unused => warning.
//   3. formatK-bypass grep — flags raw `K`+number currency prefixing and
//      `Intl.NumberFormat` OUTSIDE `packages/i18n`, protecting the single
//      money-format seam (`formatK`).
//
// Exit non-zero when any real violation (or seeded fixture) is found.
//
// Usage:
//   node scripts/ci/i18n-lint.mjs              # scan the three apps (blocking)
//   node scripts/ci/i18n-lint.mjs --paths DIR  # scan an explicit dir (fixtures)
//   node scripts/ci/i18n-lint.mjs --self-test  # prove the detectors have teeth

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..", "..");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const DEFAULT_SCAN_DIRS = ["apps/customer/app", "apps/vendor/app", "apps/admin/app"];
const MESSAGES_DIR = "packages/i18n/messages/en";
const I18N_PKG_PREFIX = "packages/i18n/";

// Files/paths excluded from the hardcoded-string + missing-key scans.
// Tests, generated output, and the dev-only component gallery ((dev)/ route)
// are not shipped user-facing locale content, matching the eslint rule's own
// ignore list (services/, tests) plus the dev gallery + our own fixtures.
const IGNORED_SEGMENTS = [
  "/node_modules/",
  "/.next/",
  "/services/",
  ".test.",
  ".spec.",
  "__tests__",
  "__fixtures__",
  "/(dev)/",
];

// Files with pre-existing missing-key debt that is DEFERRED to the owning
// feature area (see docs/plan/i18n-audit.md). The blocking gate skips
// missing-key detection for these — it still runs the hardcoded-string and
// formatK-bypass checks on them, and still catches NEW missing keys everywhere
// else + in the seeded fixture. Keep this list SHRINKING, never growing.
const DEFERRED_MISSING_KEY_FILES = new Set([
  // M04-P06 DPA page references an account.privacy.export.* / .delete.* key
  // subtree never added to account.json (legally-adjacent copy, account/DPA
  // namespace owner's fix). Tracked in docs/plan/i18n-audit.md.
  "apps/customer/app/[locale]/account/privacy/page.tsx",
]);

// User-facing attributes whose hardcoded string/template values are violations.
// Superset of the eslint rule (placeholder/title/alt/aria-label) + the full
// aria-* text family. `content` is only user-facing on <meta> (handled below).
const USER_FACING_ATTRS = new Set([
  "placeholder",
  "title",
  "alt",
  "label",
  "aria-label",
  "aria-description",
  "aria-placeholder",
  "aria-roledescription",
  "aria-valuetext",
]);

// ---------------------------------------------------------------------------
// FS helpers
// ---------------------------------------------------------------------------

function isIgnored(path, allowFixtures = false) {
  const norm = `/${path.replace(/\\/g, "/")}`;
  return IGNORED_SEGMENTS.some((seg) => {
    if (allowFixtures && seg === "__fixtures__") return false;
    return norm.includes(seg);
  });
}

function walk(dir, exts, out = [], allowFixtures = false) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (isIgnored(`${full}/`, allowFixtures)) continue;
      walk(full, exts, out, allowFixtures);
    } else if (entry.isFile() && exts.some((e) => entry.name.endsWith(e))) {
      const rel = relative(ROOT, full);
      if (!isIgnored(rel, allowFixtures)) out.push(full);
    }
  }
  return out;
}

function stripComments(src) {
  // Remove {/* jsx block */}, /* block */, and // line comments so their
  // contents never register as hardcoded strings or key usages.
  return src
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1 ");
}

// ---------------------------------------------------------------------------
// Defined-key set (from EN messages)
// ---------------------------------------------------------------------------

function flattenKeys(obj, prefix, out) {
  for (const [key, value] of Object.entries(obj)) {
    const full = `${prefix}${key}`;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      flattenKeys(value, `${full}.`, out);
    } else {
      out.add(full);
    }
  }
  return out;
}

function loadDefinedKeys() {
  const dir = join(ROOT, MESSAGES_DIR);
  const defined = new Set();
  const namespaces = new Set();
  for (const file of readdirSync(dir)) {
    if (!file.endsWith(".json")) continue;
    const namespace = file.replace(/\.json$/, "");
    namespaces.add(namespace);
    const json = JSON.parse(readFileSync(join(dir, file), "utf8"));

    // The runtime provider mounts each file's contents under
    // `messages[namespace]` ((shop)/layout: `{ ...base, catalog: <catalog.json> }`).
    // Files mix TWO styles: nested objects (`home: { nav: { home } }`) AND flat
    // dotted keys that already repeat the namespace (`"ai.ask.title"`). A key
    // used as `useTranslations(scope) + t(key)` resolves against either. So for
    // each in-file leaf path we register BOTH interpretations:
    //   nested:      `${namespace}.${path}`      (e.g. catalog.home.nav.home)
    //   self-prefixed: `${path}` when it already starts with the namespace
    //                                            (e.g. ai.ask.title, checkout.card.widgetLabel)
    const paths = flattenKeys(json, "", new Set());
    for (const path of paths) {
      defined.add(`${namespace}.${path}`);
      if (path === namespace || path.startsWith(`${namespace}.`)) defined.add(path);
    }
  }
  return { defined, namespaces };
}

// ---------------------------------------------------------------------------
// Check 1 — hardcoded strings (JSX text + attributes + template + meta)
// ---------------------------------------------------------------------------

const ATTR_NAMES = [...USER_FACING_ATTRS].join("|");
// JSX attributes are prettier-formatted with NO spaces around `=`
// (`aria-label="…"`), which distinguishes them from JS assignments
// (`export const alt = "…"` — spaces around `=`). Two shapes:
//   string literal:   attr="…"  /  attr='…'
//   template literal: attr={`…`}
const STRING_ATTR_RE = new RegExp(`(?<![-\\w])(${ATTR_NAMES})=(?:"([^"]*)"|'([^']*)')`, "g");
const TEMPLATE_ATTR_RE = new RegExp(`(?<![-\\w])(${ATTR_NAMES})=\\{\\s*\`([^\`]*)\``, "g");
const META_RE = /<meta\b[^>]*\bcontent=(?:"([^"]*)"|'([^']*)'|\{\s*`([^`]*)`)/gi;
const LETTERS_RE = /[A-Za-z]{2,}/;

function hasHardcodedWords(text) {
  if (!text) return false;
  // Drop `${…}` interpolations first — a template built purely from translated
  // vars (`aria-label={`${labels.inStock} (${n})`}`) is NOT hardcoded copy.
  const trimmed = text.replace(/\$\{[^}]*\}/g, " ").trim();
  if (!trimmed || trimmed.startsWith("{")) return false;
  if (!LETTERS_RE.test(trimmed)) return false; // pure punctuation / interpolation
  if (/^https?:\/\//.test(trimmed)) return false; // urls are not copy
  return true;
}

function lineOf(src, index) {
  return src.slice(0, index).split("\n").length;
}

function scanHardcoded(file, src) {
  const rel = relative(ROOT, file);
  const violations = [];
  const cleaned = stripComments(src);

  // (a) user-facing attributes — string literals AND template literals.
  const pushAttr = (attr, value, index) => {
    if (hasHardcodedWords(value)) {
      violations.push({
        rel,
        line: lineOf(cleaned, index),
        kind: "hardcoded-string",
        detail: `${attr}="${value.trim().slice(0, 40)}" — use a next-intl key`,
      });
    }
  };
  for (const m of cleaned.matchAll(STRING_ATTR_RE)) {
    pushAttr(m[1], m[2] ?? m[3] ?? "", m.index);
  }
  for (const m of cleaned.matchAll(TEMPLATE_ATTR_RE)) {
    pushAttr(m[1], m[2] ?? "", m.index);
  }

  // (b) <meta content="…"> copy.
  for (const m of cleaned.matchAll(META_RE)) {
    const value = m[1] ?? m[2] ?? m[3] ?? "";
    if (hasHardcodedWords(value)) {
      violations.push({
        rel,
        line: lineOf(cleaned, m.index),
        kind: "hardcoded-string",
        detail: `<meta content="${value.trim().slice(0, 40)}"> — use a next-intl key`,
      });
    }
  }

  // NOTE: bare JSX text nodes are intentionally NOT scanned here — the eslint
  // rule `@vergeo/no-hardcoded-strings` (JSXText visitor, WARN job in ci.yml)
  // already covers them accurately via AST. A regex JSX-text pass cannot
  // distinguish copy from TS generics (`Promise<T>`) without an AST, so this
  // sweep deliberately owns the coverage the eslint rule lacks: template
  // literals, the full aria-* family, and <meta content>.

  return violations;
}

// ---------------------------------------------------------------------------
// Check 2 — missing keys (used vs defined)
// ---------------------------------------------------------------------------

const SCOPE_RE = /\b(?:useTranslations|getTranslations)\s*\(\s*(?:["'`]([^"'`]*)["'`])?\s*\)/g;
const CREATE_TRANSLATOR_RE = /createTranslator\s*\(\s*\{[\s\S]*?namespace:\s*["'`]([^"'`]+)["'`]/g;
const GET_TRANSLATIONS_NS_RE = /getTranslations\s*\(\s*\{[\s\S]*?namespace:\s*["'`]([^"'`]+)["'`]/g;
const BIND_RE =
  /(?:const|let|var)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations|createTranslator)\b/g;

function collectScopesAndVars(src) {
  const scopes = new Set();
  for (const m of src.matchAll(SCOPE_RE)) scopes.add(m[1] ?? "");
  for (const m of src.matchAll(CREATE_TRANSLATOR_RE)) scopes.add(m[1]);
  for (const m of src.matchAll(GET_TRANSLATIONS_NS_RE)) scopes.add(m[1]);
  const vars = new Set();
  for (const m of src.matchAll(BIND_RE)) vars.add(m[1]);
  return { scopes, vars };
}

function scanMissingKeys(file, src, defined) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  if (DEFERRED_MISSING_KEY_FILES.has(rel)) return { violations: [], usedFull: new Set() };
  const cleaned = stripComments(src);
  const { scopes, vars } = collectScopesAndVars(cleaned);
  const violations = [];
  const usedFull = new Set();
  // Without a resolvable scope AND a translator binding we cannot statically
  // qualify keys (scope arrives via prop / hook) — skip to stay false-positive
  // free.
  if (vars.size === 0 || scopes.size === 0) return { violations, usedFull };

  for (const varName of vars) {
    const callRe = new RegExp(
      `\\b${varName}\\s*(?:\\.(?:rich|markup|raw|has))?\\s*\\(\\s*(["'])([^"'\`]*?)\\1`,
      "g",
    );
    for (const m of cleaned.matchAll(callRe)) {
      const key = m[2];
      if (!key || key.includes("${")) continue; // dynamic — cannot resolve
      const candidates = [];
      for (const scope of scopes) candidates.push(scope ? `${scope}.${key}` : key);
      candidates.push(key); // already fully-qualified?
      const hit = candidates.find((c) => defined.has(c));
      if (hit) {
        usedFull.add(hit);
      } else {
        violations.push({
          rel,
          line: lineOf(cleaned, m.index),
          kind: "missing-key",
          detail: `t("${key}") undefined for scope(s) [${[...scopes].join(", ")}]`,
        });
      }
    }
  }
  return { violations, usedFull };
}

// ---------------------------------------------------------------------------
// Check 3 — formatK bypass (money-format invariant)
// ---------------------------------------------------------------------------

// `K` immediately prefixing a numeric interpolation/concat, or Intl.NumberFormat,
// anywhere OUTSIDE packages/i18n. Date formatting (Intl.DateTimeFormat /
// toLocaleString) is a separate concern and intentionally NOT flagged here.
const K_TEMPLATE_RE = /`[^`]*\bK\$\{/g;
const K_CONCAT_RE = /["']K["']\s*\+/g;
const INTL_NUMBER_RE = /\bIntl\.NumberFormat\b/g;

function scanFormatKBypass(file, src) {
  const rel = relative(ROOT, file);
  if (rel.replace(/\\/g, "/").startsWith(I18N_PKG_PREFIX)) return [];
  const cleaned = stripComments(src);
  const violations = [];
  const push = (index, detail) =>
    violations.push({ rel, line: lineOf(cleaned, index), kind: "formatk-bypass", detail });
  for (const m of cleaned.matchAll(K_TEMPLATE_RE))
    push(m.index, "K`${…}` currency prefixing — use formatK()");
  for (const m of cleaned.matchAll(K_CONCAT_RE))
    push(m.index, '"K" + number concatenation — use formatK()');
  for (const m of cleaned.matchAll(INTL_NUMBER_RE))
    push(m.index, "Intl.NumberFormat outside packages/i18n — use formatK()/formatNumber()");
  return violations;
}

// ---------------------------------------------------------------------------
// Pseudo-locale smoke (en-XA) — CI runner
// ---------------------------------------------------------------------------

// MIRROR of packages/i18n/pseudo.ts (CI pins Node 20 via .nvmrc and cannot
// execute TypeScript directly, so the transform is duplicated here for the
// blocking smoke). Keep the two in sync.
const PSEUDO_OPEN = "[!!";
const PSEUDO_CLOSE = "!!]";
const ACCENT_MAP = {
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

function pseudoString(value) {
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

const isPseudo = (v) => v.startsWith(PSEUDO_OPEN) && v.endsWith(PSEUDO_CLOSE);

function pseudoMessages(messages) {
  const out = {};
  for (const [key, value] of Object.entries(messages)) {
    out[key] = typeof value === "string" ? pseudoString(value) : pseudoMessages(value);
  }
  return out;
}

// Fill ICU `{name}` placeholders with a sample value so a rendered "screen"
// line has no dangling braces — mirrors runtime interpolation for the smoke.
function renderSample(template) {
  return template.replace(/\{(\w+)(?:,[^{}]*(?:\{[^{}]*\}[^{}]*)*)?\}/g, (_, name) => `‹${name}›`);
}

function pseudoSmoke() {
  const dir = join(ROOT, MESSAGES_DIR);
  let leaves = 0;
  const files = readdirSync(dir).filter((f) => f.endsWith(".json"));
  const screen = [];
  for (const file of files) {
    const json = JSON.parse(readFileSync(join(dir, file), "utf8"));
    const pseudo = pseudoMessages(json);
    // Verify every leaf is bracketed (no raw EN slipped through).
    const walkAssert = (obj, path) => {
      for (const [k, v] of Object.entries(obj)) {
        const here = path ? `${path}.${k}` : k;
        if (typeof v === "string") {
          if (!isPseudo(v)) {
            console.error(`✖ en-XA coverage gap: ${file}:${here} → ${v}`);
            process.exit(1);
          }
          leaves += 1;
          if (screen.length < 8) screen.push(`  ${file}:${here} → ${renderSample(v)}`);
        } else {
          walkAssert(v, here);
        }
      }
    };
    walkAssert(pseudo, "");
  }
  // Control: a raw (un-keyed) EN string must NOT read as pseudo — this is the
  // exact signal a reviewer sees when a hardcoded string leaks onto a screen.
  if (isPseudo("Checkout")) {
    console.error("✖ pseudo smoke broken — raw EN string classified as pseudo");
    process.exit(1);
  }
  console.log(
    `✔ pseudo-locale smoke OK — en-XA bracketed ${leaves} strings across ${files.length} namespaces`,
  );
  console.log("  sample rendered screen (every line wrapped in [!! … !!]):");
  for (const line of screen) console.log(line);
  console.log('  control: raw "Checkout" is NOT pseudo →', isPseudo("Checkout"));
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

function collectFiles(scanDirs, allowFixtures = false) {
  const files = [];
  for (const d of scanDirs) files.push(...walk(join(ROOT, d), [".tsx", ".jsx"], [], allowFixtures));
  return files;
}

function collectMoneyScanFiles() {
  // formatK-bypass runs repo-wide (ts + tsx) across apps + services + packages.
  const files = [];
  for (const d of ["apps", "services", "packages"]) {
    for (const f of walk(join(ROOT, d), [".ts", ".tsx"])) {
      const rel = relative(ROOT, f);
      if (isIgnored(rel)) continue;
      files.push(f);
    }
  }
  return files;
}

function run({ scanDirs, fixtureMode }) {
  const { defined } = loadDefinedKeys();
  const all = [];
  const usedFull = new Set();

  const jsxFiles = collectFiles(scanDirs, fixtureMode);
  for (const file of jsxFiles) {
    const src = readFileSync(file, "utf8");
    all.push(...scanHardcoded(file, src));
    const mk = scanMissingKeys(file, src, defined);
    all.push(...mk.violations);
    for (const k of mk.usedFull) usedFull.add(k);
  }

  const moneyFiles = fixtureMode ? jsxFiles : collectMoneyScanFiles();
  for (const file of moneyFiles) {
    const src = readFileSync(file, "utf8");
    all.push(...scanFormatKBypass(file, src));
  }

  return { violations: all, defined, usedFull };
}

function report(violations) {
  const byKind = { "hardcoded-string": [], "missing-key": [], "formatk-bypass": [] };
  for (const v of violations) (byKind[v.kind] ??= []).push(v);
  for (const [kind, list] of Object.entries(byKind)) {
    if (!list.length) continue;
    console.error(`\n✖ ${kind} (${list.length}):`);
    for (const v of list.slice(0, 100)) {
      console.error(`  ${v.rel}:${v.line}  ${v.detail}`);
    }
  }
}

function selfTest() {
  const fixtureDir = "scripts/ci/__fixtures__/i18n";
  const { violations } = run({ scanDirs: [fixtureDir], fixtureMode: true });
  const kinds = new Set(violations.map((v) => v.kind));
  const required = ["hardcoded-string", "missing-key", "formatk-bypass"];
  const missing = required.filter((k) => !kinds.has(k));
  if (missing.length) {
    console.error(`✖ self-test FAILED — detectors with no teeth: ${missing.join(", ")}`);
    report(violations);
    process.exit(1);
  }
  console.log("✔ self-test OK — fixture caught:", required.join(", "));
  console.log(`  (${violations.length} seeded violations detected across the 3 checks)`);
  process.exit(0);
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.includes("--self-test")) return selfTest();
  if (argv.includes("--pseudo-smoke")) return pseudoSmoke();

  const pathsIdx = argv.indexOf("--paths");
  const explicit =
    pathsIdx !== -1 ? argv.slice(pathsIdx + 1).filter((a) => !a.startsWith("--")) : null;
  const fixtureMode = Boolean(explicit);
  const scanDirs = explicit ?? DEFAULT_SCAN_DIRS;

  const { violations, defined, usedFull } = run({ scanDirs, fixtureMode });

  if (!fixtureMode) {
    const unused = [...defined].filter((k) => !usedFull.has(k));
    // Defined-but-unused is advisory only (server-composed footer/legal/email
    // copy and ICU sub-parts are used indirectly). Never fails the build.
    console.log(
      `i18n sweep: ${defined.size} EN keys defined, ${usedFull.size} statically resolved as used`,
    );
    if (unused.length) console.log(`  (advisory: ${unused.length} keys not statically referenced)`);
  }

  if (violations.length) {
    report(violations);
    console.error(`\n✖ i18n sweep FAILED — ${violations.length} violation(s).`);
    process.exit(1);
  }
  console.log("✔ i18n sweep clean — no hardcoded strings, missing keys, or formatK bypasses.");
  process.exit(0);
}

main();

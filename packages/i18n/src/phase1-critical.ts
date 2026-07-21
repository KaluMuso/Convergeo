/**
 * CUST-I18N-01 Phase 1 — critical customer purchase-journey key prefixes.
 * Completeness gates assert bem/nya define these leaves and that values are
 * not accidental English copies (except the allowlist below).
 */

export const PHASE1_CRITICAL_LOCALES = ["bem", "nya"] as const;

export const PHASE1_CRITICAL_NAMESPACES = [
  "common",
  "nav",
  "catalog",
  "search",
  "checkout",
  "orders",
  "account",
  "marketing",
] as const;

export type Phase1Namespace = (typeof PHASE1_CRITICAL_NAMESPACES)[number];

/** Dotted prefixes (inclusive). A key matches if it equals a prefix or starts with `${prefix}.`. */
export const PHASE1_CRITICAL_PREFIXES: Record<Phase1Namespace, readonly string[]> = {
  common: ["app", "common", "theme", "greeting", "offline", "install"],
  nav: ["skipToContent", "shop", "marketing", "account", "auth"],
  catalog: [
    "home.meta",
    "home.serviceBar",
    "home.hero",
    "home.trust",
    "home.demo",
    "home.categories",
    "home.rails",
    "home.sellCta",
    "browseCategories",
    "plp.title",
    "plp.defaultCategory",
    "plp.breadcrumbAria",
    "plp.results",
    "plp.emptyTitle",
    "plp.emptyBody",
    "plp.unavailableTitle",
    "plp.unavailableBody",
    "plp.card",
    "plp.loadMore",
    "plp.loading",
    "pdp",
    "returnableBadge",
  ],
  search: [
    "title",
    "placeholder",
    "submit",
    "recent",
    "tabs",
    "noResults",
    "unavailable",
    "invalid",
    "suggestionTerms",
    "suggestions",
    "categories",
    "askVergeo",
    "results",
    "input",
    "pagination",
    "result",
  ],
  checkout: [
    "cart",
    "checkout.pageTitle",
    "checkout.stepAnnouncement",
    "checkout.doneIndicator",
    "checkout.steps",
    "checkout.payment",
    "checkout.review",
    "checkout.pending",
    "checkout.ussd",
    "checkout.card",
    "checkout.emptyCart",
    "checkout.error",
    "checkout.loading",
    "checkout.stockUnavailable",
    "checkout.reservationExpired",
  ],
  orders: [
    "title",
    "empty",
    "list",
    "detail.title",
    "detail.back",
    "detail.orderId",
    "detail.vendor",
    "detail.total",
    "status",
    "timeline",
    "escrow",
    "errors",
  ],
  account: ["title", "nav", "locales", "common"],
  marketing: ["notFound", "error"],
};

/**
 * Values that may legitimately match English (brand, network names, symbols, codes).
 * Compared after trim; case-sensitive for brand tokens.
 */
export const PHASE1_ENGLISH_ALLOWLIST = new Set([
  "Vergeo5",
  "MTN",
  "Airtel",
  "Zamtel",
  "Lenco",
  "WhatsApp",
  "SMS",
  "PIN",
  "QR",
  "COD",
  "USSD",
  "MoMo",
  "Offline",
  "404",
  "500",
  "✓",
  "-",
  "+",
  "K",
  // Locale endonyms / place names that stay as-is in overlays
  "English",
  "Français",
  "中文",
  "Bemba",
  "Nyanja",
  "Zambia",
  "Lusaka",
]);

export function keyMatchesPhase1Prefix(key: string, prefixes: readonly string[]): boolean {
  return prefixes.some((prefix) => key === prefix || key.startsWith(`${prefix}.`));
}

export function extractIcuPlaceholders(template: string): string[] {
  const found = new Set<string>();
  for (const match of template.matchAll(/\{(\w+)(?:,[^}]*)?\}/g)) {
    const name = match[1];
    if (name) {
      found.add(name);
    }
  }
  return [...found].sort();
}

/** True when a translated value is still effectively English and not allowlisted. */
export function isUnexpectedEnglishFallback(enValue: string, localeValue: string): boolean {
  const en = enValue.trim();
  const loc = localeValue.trim();
  if (loc.length === 0) {
    return true;
  }
  if (PHASE1_ENGLISH_ALLOWLIST.has(loc)) {
    return false;
  }
  // Identical ICU-only / punctuation-only strings are OK when EN is also short tokens.
  if (en === loc) {
    // Allow identical when the English string is only placeholders/symbols/brand tokens.
    const withoutPlaceholders = en.replace(/\{[^}]+\}/g, "").trim();
    if (withoutPlaceholders.length === 0) {
      return false;
    }
    if (PHASE1_ENGLISH_ALLOWLIST.has(withoutPlaceholders)) {
      return false;
    }
    // Pure punctuation / placeholder wrappers e.g. "×{qty}", "({count})", "{a} ({b})"
    if (/^[×xX\s(){}\[\]0-9#.,:_/-]+$/.test(withoutPlaceholders)) {
      return false;
    }
    if (/^[×xX\s{}0-9#.,:_-]+$/.test(en)) {
      return false;
    }
    return true;
  }
  return false;
}

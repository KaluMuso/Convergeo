/**
 * Page template keys (plan §F.5): a stable, slug-free name for "which kind of page".
 * Never a URL, slug, id or query string — only these registered keys leave the browser.
 */

import type { ReferrerKind } from "./envelope";

const LOCALE_RE = /^\/(en|bem|nya|fr|zh)(?=\/|$)/;

/** First path segment → page key. Unlisted segments map to "other". */
const SEGMENT_KEYS: Record<string, string> = {
  p: "pdp",
  l: "listing",
  c: "plp",
  s: "service",
  v: "storefront",
  e: "event",
  search: "search",
  cart: "cart",
  checkout: "checkout",
  account: "account",
  wishlist: "wishlist",
  compare: "compare",
  categories: "categories",
  services: "services",
  events: "events",
  supplies: "supplies",
  directory: "directory",
  calendar: "calendar",
  ask: "ask",
  clips: "clips",
  help: "help",
  legal: "legal",
  privacy: "legal",
  terms: "legal",
  about: "about",
  contact: "contact",
  sell: "sell",
  beta: "beta",
  login: "auth",
  signup: "auth",
  otp: "auth",
  welcome: "auth",
  "reset-password": "auth",
  offline: "offline",
};

export function pageKeyFromPath(pathname: string | null | undefined): string {
  if (!pathname) {
    return "other";
  }
  const path = pathname.split(/[?#]/)[0]!.replace(LOCALE_RE, "");
  const segment = path.split("/").filter(Boolean)[0];
  if (segment === undefined) {
    return "home";
  }
  return SEGMENT_KEYS[segment] ?? "other";
}

const SEARCH_HOSTS = /(^|\.)(google|bing|duckduckgo|yahoo|yandex|baidu|ecosia)\./;
const SOCIAL_HOSTS =
  /(^|\.)(facebook|fb|instagram|whatsapp|wa\.me|t\.co|twitter|x\.com|tiktok|linkedin|youtube|telegram)/;

/** Coarse referrer class — the raw referrer is never sent (plan §R-B). */
export function referrerKind(referrer: string, ownHost: string): ReferrerKind {
  if (!referrer) {
    return "direct";
  }
  let host: string;
  try {
    host = new URL(referrer).hostname.toLowerCase();
  } catch {
    return "other";
  }
  if (host === ownHost.toLowerCase()) {
    return "internal";
  }
  if (SEARCH_HOSTS.test(host)) {
    return "search";
  }
  if (SOCIAL_HOSTS.test(host)) {
    return "social";
  }
  return "other";
}

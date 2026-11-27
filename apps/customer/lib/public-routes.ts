import { LOCALES } from "@vergeo/i18n";

/**
 * Customer routes that render identically for everyone and never need the
 * server-verified session in middleware (so they may use offline JWT
 * verification and stay cacheable). Allowlist on purpose: anything not listed
 * (account, checkout, payment, orders, wishlist, cart, ask, auth, API ...)
 * keeps the full server `getUser()` check.
 */
const PUBLIC_SEGMENTS = new Set([
  "",
  "p",
  "c",
  "search",
  "e",
  "s",
  "v",
  "l",
  "events",
  "services",
  "vendors",
  "deals",
  "categories",
  "compare",
  "browse",
  "calendar",
  "help",
  "about",
  "contact",
  "legal",
  "privacy",
  "terms",
  "sell",
  "offline",
  "clips",
]);

export function isPublicCustomerRoute(pathname: string, method = "GET"): boolean {
  if (method !== "GET" && method !== "HEAD") return false;
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length === 0) return false;
  if (!(LOCALES as readonly string[]).includes(parts[0] as string)) return false;
  return PUBLIC_SEGMENTS.has(parts[1] ?? "");
}

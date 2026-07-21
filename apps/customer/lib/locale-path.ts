import { LOCALES } from "@vergeo/i18n";

/**
 * Replaces the locale prefix in a pathname while preserving the rest of the path
 * and any query string on the current URL (caller appends search separately).
 */
export function swapLocaleInPath(pathname: string, nextLocale: string): string {
  const normalized = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const segments = normalized.split("/").filter(Boolean);

  if (segments.length === 0) {
    return `/${nextLocale}`;
  }

  const [first, ...rest] = segments;
  if (first !== undefined && (LOCALES as readonly string[]).includes(first)) {
    return `/${[nextLocale, ...rest].join("/")}`;
  }

  return `/${nextLocale}${normalized}`;
}

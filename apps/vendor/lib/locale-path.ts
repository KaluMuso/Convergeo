import { LOCALES } from "@vergeo/i18n";

/** Replaces the locale prefix of a pathname, keeping the rest of the path. */
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

/** Masks a payout number for display: +260 97• •••• 123 style, last 3 digits only. */
export function maskMsisdn(msisdn: string): string {
  const digits = msisdn.replace(/\D/g, "");
  if (digits.length <= 3) {
    return msisdn;
  }
  return `${"•".repeat(Math.max(digits.length - 3, 0))}${digits.slice(-3)}`;
}

/**
 * Same-origin, locale-prefixed post-auth path sanitizer.
 *
 * Rejects open redirects (`https://evil`, `//evil`, `javascript:`, backslash
 * tricks, double-encoded external URLs) and cross-locale jumps. Callers must
 * still supply a portal-local fallback such as `/${locale}`.
 */

const UNSAFE_SCHEME = /^[a-z][a-z0-9+.-]*:/i;

function decodeOnce(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

function fullyDecode(value: string): string | null {
  let current = value;
  for (let i = 0; i < 3; i += 1) {
    const next = decodeOnce(current);
    if (next === null) {
      return null;
    }
    if (next === current) {
      return current;
    }
    current = next;
  }
  return current;
}

function isLocalePrefixedPath(path: string, locale: string): boolean {
  const withoutQuery = path.split("?")[0]?.split("#")[0] ?? "";
  return withoutQuery === `/${locale}` || withoutQuery.startsWith(`/${locale}/`);
}

export function sanitizeNextPath(
  locale: string,
  nextParam: string | null | undefined,
  fallbackPath: string,
): string {
  if (!nextParam) {
    return fallbackPath;
  }

  const decoded = fullyDecode(nextParam.trim());
  if (decoded === null) {
    return fallbackPath;
  }

  const candidate = decoded.trim();
  if (!candidate.startsWith("/")) {
    return fallbackPath;
  }
  if (candidate.startsWith("//")) {
    return fallbackPath;
  }
  if (candidate.includes("\\") || candidate.includes("\0")) {
    return fallbackPath;
  }
  if (candidate.includes("://") || UNSAFE_SCHEME.test(candidate.slice(1))) {
    return fallbackPath;
  }
  if (/%2f/i.test(nextParam) && /\/\//.test(candidate)) {
    return fallbackPath;
  }
  if (/%5c/i.test(nextParam)) {
    return fallbackPath;
  }
  if (candidate.includes("..")) {
    return fallbackPath;
  }
  if (!isLocalePrefixedPath(candidate, locale)) {
    return fallbackPath;
  }

  return candidate;
}

export function defaultPortalHomePath(locale: string): string {
  return `/${locale}`;
}

export function vendorOnboardingPath(locale: string): string {
  return `/${locale}/onboarding`;
}

export function adminPermissionDeniedPath(locale: string): string {
  return `/${locale}/permission-denied`;
}

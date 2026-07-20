import {
  CSP_NONCE_PLACEHOLDER,
  applyReportOnlyCspNonce,
  createLoginRedirect,
  getLocaleFromPath,
  mergeSessionCookies,
  shouldRedirectToLogin,
  updateSession,
} from "@vergeo/auth/middleware";
import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { type NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
});

const NONCE = `'nonce-${CSP_NONCE_PLACEHOLDER}'`;
const CLOUDINARY = "https://res.cloudinary.com";
const SUPABASE = "https://*.supabase.co";
const SUPABASE_WS = "wss://*.supabase.co";
const GA4_SCRIPT = "https://*.googletagmanager.com";
const GA4_CONNECT =
  "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com";
const GA4_IMG = "https://*.google-analytics.com https://*.googletagmanager.com";
const SENTRY_INGEST =
  "https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io";

const REPORT_ONLY_CSP = [
  "default-src 'self'",
  `script-src 'self' 'strict-dynamic' ${NONCE} https: ${GA4_SCRIPT}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${CLOUDINARY} ${GA4_IMG}`,
  "font-src 'self' data:",
  `connect-src 'self' ${SUPABASE} ${SUPABASE_WS} ${GA4_CONNECT} ${SENTRY_INGEST}`,
  "frame-src 'self'",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

export default async function middleware(request: NextRequest) {
  const session = await updateSession(request);
  const locale = getLocaleFromPath(request.nextUrl.pathname, LOCALES, DEFAULT_LOCALE);

  if (
    shouldRedirectToLogin("vendor", request.nextUrl.pathname, LOCALES, session.user, session.roles)
  ) {
    return applyReportOnlyCspNonce(
      request,
      createLoginRedirect(request, locale, session.response),
      REPORT_ONLY_CSP,
    );
  }

  const localeResponse = intlMiddleware(request);
  return applyReportOnlyCspNonce(
    request,
    mergeSessionCookies(session.response, localeResponse),
    REPORT_ONLY_CSP,
  );
}

export const config = {
  matcher: ["/", "/(en|bem|nya|fr|zh)/:path*"],
};

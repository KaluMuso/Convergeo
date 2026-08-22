import {
  CSP_NONCE_PLACEHOLDER,
  appendCspReporting,
  applyReportOnlyCspNonce,
  createPortalRedirect,
  getLocaleFromPath,
  handleCspReportRequest,
  isCspReportRequest,
  isHealthCheckPath,
  mergeSessionCookies,
  resolveGatedRedirect,
  updateSession,
} from "@vergeo/auth/middleware";
import { buildConnectSrc, CSP_ORIGINS } from "@vergeo/config/security-headers";
import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { type NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
});

const NONCE = `'nonce-${CSP_NONCE_PLACEHOLDER}'`;

const connectSrc = buildConnectSrc(
  process.env,
  `${CSP_ORIGINS.ga4Connect} ${CSP_ORIGINS.sentryIngest}`,
);

const REPORT_ONLY_CSP = appendCspReporting(
  [
    "default-src 'self'",
    `script-src 'self' 'strict-dynamic' ${NONCE} https: ${CSP_ORIGINS.ga4Script}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${CSP_ORIGINS.cloudinary} ${CSP_ORIGINS.ga4Img}`,
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    "frame-src 'self'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ].join("; "),
);

export default async function middleware(request: NextRequest) {
  if (isCspReportRequest(request)) {
    return handleCspReportRequest(request);
  }

  const session = await updateSession(request);
  const locale = getLocaleFromPath(request.nextUrl.pathname, LOCALES, DEFAULT_LOCALE);
  // /health carries only non-secret status/config facts (see route.ts) — it
  // must stay reachable unauthenticated, like any deployment health check.
  const gate = isHealthCheckPath(request.nextUrl.pathname, LOCALES)
    ? null
    : resolveGatedRedirect(
        "vendor",
        request.nextUrl.pathname,
        LOCALES,
        session.user,
        session.roles,
      );

  if (gate) {
    return applyReportOnlyCspNonce(
      request,
      createPortalRedirect(gate, request, locale, session.response),
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
  matcher: ["/api/csp-report", "/", "/(en|bem|nya|fr|zh)/:path*"],
};

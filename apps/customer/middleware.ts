import {
  CSP_NONCE_PLACEHOLDER,
  appendCspReporting,
  applyReportOnlyCspNonce,
  handleCspReportRequest,
  isCspReportRequest,
  mergeSessionCookies,
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

function buildReportOnlyCsp(lenco: boolean): string {
  const scriptExtra = lenco ? ` ${CSP_ORIGINS.lencoWidget}` : "";
  const frameExtra = lenco ? ` ${CSP_ORIGINS.lencoWidget}` : "";
  const connectExtra = lenco ? ` ${CSP_ORIGINS.lencoWidget} ${CSP_ORIGINS.lencoApi}` : "";
  const connectSrc = buildConnectSrc(
    process.env,
    `${CSP_ORIGINS.ga4Connect} ${CSP_ORIGINS.sentryIngest}${connectExtra}`,
  );
  // Omit upgrade-insecure-requests from report-only — browsers ignore it there and
  // log a console warning. Enforced CSP (next.config) still upgrades in production.
  const base = [
    "default-src 'self'",
    `script-src 'self' 'strict-dynamic' ${NONCE} https: ${CSP_ORIGINS.ga4Script}${scriptExtra}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${CSP_ORIGINS.cloudinary} ${CSP_ORIGINS.ga4Img}`,
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    `frame-src 'self'${frameExtra}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    `form-action 'self'${lenco ? ` ${CSP_ORIGINS.lencoWidget}` : ""}`,
  ].join("; ");
  return appendCspReporting(base);
}

export function isCheckoutCardRoute(pathname: string): boolean {
  const [locale, checkout, card, paymentId, ...rest] = pathname.split("/").filter(Boolean);
  return (
    rest.length === 0 &&
    typeof paymentId === "string" &&
    paymentId.length > 0 &&
    LOCALES.includes(locale as (typeof LOCALES)[number]) &&
    checkout === "checkout" &&
    card === "card"
  );
}

export default async function middleware(request: NextRequest) {
  if (isCspReportRequest(request)) {
    return handleCspReportRequest(request);
  }

  const session = await updateSession(request);
  const localeResponse = intlMiddleware(request);
  const response = mergeSessionCookies(session.response, localeResponse);
  return applyReportOnlyCspNonce(
    request,
    response,
    buildReportOnlyCsp(isCheckoutCardRoute(request.nextUrl.pathname)),
  );
}

export const config = {
  matcher: ["/api/csp-report", "/", "/(en|bem|nya|fr|zh)/:path*"],
};

import {
  CSP_NONCE_PLACEHOLDER,
  applyReportOnlyCspNonce,
  mergeSessionCookies,
  updateSession,
} from "@vergeo/auth/middleware";
import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { type NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

const NONCE = `'nonce-${CSP_NONCE_PLACEHOLDER}'`;
const CLOUDINARY = "https://res.cloudinary.com";
const SUPABASE = "https://*.supabase.co";
const SUPABASE_WS = "wss://*.supabase.co";
const GA4_SCRIPT = "https://*.googletagmanager.com";
const GA4_CONNECT =
  "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com";
const GA4_IMG = "https://*.google-analytics.com https://*.googletagmanager.com";
const LENCO_WIDGET = "https://pay.lenco.co https://pay.sandbox.lenco.co";
const LENCO_API = "https://api.lenco.co https://api.sandbox.lenco.co";
const SENTRY_INGEST =
  "https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://*.ingest.de.sentry.io";

const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
});

function buildReportOnlyCsp(lenco: boolean): string {
  const scriptExtra = lenco ? ` ${LENCO_WIDGET}` : "";
  const frameExtra = lenco ? ` ${LENCO_WIDGET}` : "";
  const connectExtra = lenco ? ` ${LENCO_WIDGET} ${LENCO_API}` : "";
  return [
    "default-src 'self'",
    `script-src 'self' 'strict-dynamic' ${NONCE} https: ${GA4_SCRIPT}${scriptExtra}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${CLOUDINARY} ${GA4_IMG}`,
    "font-src 'self' data:",
    `connect-src 'self' ${SUPABASE} ${SUPABASE_WS} ${GA4_CONNECT} ${SENTRY_INGEST}${connectExtra}`,
    `frame-src 'self'${frameExtra}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    `form-action 'self'${lenco ? ` ${LENCO_WIDGET}` : ""}`,
    "upgrade-insecure-requests",
  ].join("; ");
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
  matcher: ["/", "/(en|bem|nya|fr|zh)/:path*"],
};

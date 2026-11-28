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
import { buildConnectSrc, CSP_ORIGINS, cspSha256Source } from "@vergeo/config/security-headers";
import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { THEME_SCRIPT } from "@vergeo/ui/src/theme-script";
import { type NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";

import { isVendorAuthSetupPath } from "./lib/password-recovery-path";

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

// The pre-paint theme bootstrap (<ThemeScript/> in the root layout) is a static
// inline script with no nonce, so it is allowed by its sha256 hash, as on the
// customer origin. Without it every page reported an inline-script violation.
export function buildReportOnlyCsp(inlineScriptHashes: string[] = []): string {
  const hashes = inlineScriptHashes.length > 0 ? ` ${inlineScriptHashes.join(" ")}` : "";
  return appendCspReporting(
    [
      "default-src 'self'",
      `script-src 'self' 'strict-dynamic' ${NONCE}${hashes} https: ${CSP_ORIGINS.ga4Script}`,
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
      // No upgrade-insecure-requests here: browsers ignore it in report-only and log
      // a console warning. The enforced CSP in next.config.ts still upgrades.
    ].join("; "),
  );
}

let reportOnlyCspCache: Promise<string> | undefined;
function getReportOnlyCsp(): Promise<string> {
  reportOnlyCspCache ??= cspSha256Source(THEME_SCRIPT).then((hash) => buildReportOnlyCsp([hash]));
  return reportOnlyCspCache;
}

export default async function middleware(request: NextRequest) {
  if (isCspReportRequest(request)) {
    return handleCspReportRequest(request);
  }

  const reportOnlyCsp = await getReportOnlyCsp();

  const session = await updateSession(request);
  const locale = getLocaleFromPath(request.nextUrl.pathname, LOCALES, DEFAULT_LOCALE);
  // /health carries only non-secret status/config facts (see route.ts) — it
  // must stay reachable unauthenticated, like any deployment health check.
  const gate =
    isHealthCheckPath(request.nextUrl.pathname, LOCALES) ||
    isVendorAuthSetupPath(request.nextUrl.pathname)
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
      reportOnlyCsp,
    );
  }

  const localeResponse = intlMiddleware(request);
  return applyReportOnlyCspNonce(
    request,
    mergeSessionCookies(session.response, localeResponse),
    reportOnlyCsp,
  );
}

export const config = {
  // See apps/customer/middleware.ts for the full rationale: a locale-less
  // path (e.g. `/onboarding`, `/sw.js`) previously skipped both the gate
  // check and next-intl's redirect, landing on `/[locale]` with an invalid
  // locale value and throwing when any interpolated message tried to format.
  matcher: ["/api/csp-report", "/((?!api|_next|_vercel|.*\\..*).*)"],
};

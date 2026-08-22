import {
  CSP_NONCE_PLACEHOLDER,
  appendCspReporting,
  applyReportOnlyCspNonce,
  createPortalRedirect,
  getLocaleFromPath,
  handleCspReportRequest,
  isAdminBypassActive,
  isCspReportRequest,
  isHealthCheckPath,
  mergeSessionCookies,
  resolveGatedRedirect,
  updateSession,
} from "@vergeo/auth/middleware";
import { buildConnectSrc, CSP_ORIGINS } from "@vergeo/config/security-headers";
import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
import { type NextRequest, NextResponse } from "next/server";
import createMiddleware from "next-intl/middleware";

import { verifyCfAccessAssertion } from "./lib/cf-access";

const CF_ACCESS_HEADER = "cf-access-jwt-assertion";

const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "always",
});

const NONCE = `'nonce-${CSP_NONCE_PLACEHOLDER}'`;

const connectSrc = buildConnectSrc(process.env, CSP_ORIGINS.sentryIngest);

const REPORT_ONLY_CSP = appendCspReporting(
  [
    "default-src 'self'",
    `script-src 'self' 'strict-dynamic' ${NONCE}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${CSP_ORIGINS.cloudinary}`,
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    "frame-src 'none'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ].join("; "),
);

export function isProductionCfAccessRequired(): boolean {
  return process.env.NODE_ENV === "production" && !isAdminBypassActive();
}

/**
 * Staging/Preview-only, `/health`-only exception: lets the deploy-staging
 * verifier prove the deployed admin build's effective API wiring
 * (`GET /{locale}/health` -> {status, app, env, buildId, apiHost}, never
 * session/user/admin data — see route.ts) without a Cloudflare Access
 * assertion.
 *
 * Requires TWO independent, non-request-controllable signals to agree —
 * neither is a request header, cookie, or query param a caller could set,
 * so this cannot be triggered against any deployment by an external
 * request:
 *
 *   A. `VERCEL_ENV === "preview"` — Vercel's own system signal for which
 *      kind of deployment this actually is. `NODE_ENV` cannot substitute
 *      for this: Next.js sets `NODE_ENV=production` for the built server
 *      bundle on every Vercel deployment, Production and Preview alike, so
 *      it cannot distinguish them.
 *   B. `NEXT_PUBLIC_DEPLOYMENT_PLANE` is `staging` or `preview` — the
 *      application-level plane, baked in by the Vercel project's own
 *      environment configuration.
 *
 * A misconfigured `NEXT_PUBLIC_DEPLOYMENT_PLANE` alone (e.g. accidentally
 * left as `staging` on a Production deployment) cannot open this exception:
 * `VERCEL_ENV` on Production is `"production"`, so signal A still fails
 * closed regardless of B.
 *
 * On the `production` plane this is always false, so CF Access (and the
 * admin role gate below) keep guarding `/health` exactly as before: this
 * function changes nothing about production admin's security model. It
 * also never touches `isAdminBypassActive()` — that flag's own scope is
 * unrelated and unaffected by this narrower, path-scoped exception.
 */
export function isStagingHealthCheckException(request: NextRequest): boolean {
  const isPreviewDeployment = process.env.VERCEL_ENV === "preview";
  if (!isPreviewDeployment) {
    return false;
  }

  const plane = process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE;
  const isStagingPlane = plane === "staging" || plane === "preview";
  if (!isStagingPlane) {
    return false;
  }

  return isHealthCheckPath(request.nextUrl.pathname, LOCALES);
}

export function hasCfAccessJwtAssertion(request: NextRequest): boolean {
  const assertion = request.headers.get(CF_ACCESS_HEADER);
  return typeof assertion === "string" && assertion.trim().length > 0;
}

export function createCfAccessForbiddenResponse(): NextResponse {
  return new NextResponse("Forbidden — Cloudflare Access required", { status: 403 });
}

export default async function middleware(request: NextRequest) {
  if (isCspReportRequest(request)) {
    return handleCspReportRequest(request);
  }

  const session = await updateSession(request);
  const locale = getLocaleFromPath(request.nextUrl.pathname, LOCALES, DEFAULT_LOCALE);

  const adminBypass = isAdminBypassActive();
  const healthCheckException = isStagingHealthCheckException(request);

  if (isProductionCfAccessRequired() && !healthCheckException) {
    // Cryptographically verify the Cloudflare Access assertion: signature against the
    // team JWKS (RS256) + expected audience + issuer + expiry. Fails closed — absent,
    // malformed, unsigned, wrong-key, wrong-audience, expired, or an unconfigured
    // verifier all return 403 before any handler runs. Authoritative admin RBAC still
    // happens in the API against `user_roles`, never from these claims alone.
    const assertion = request.headers.get(CF_ACCESS_HEADER);
    const cfAccess = await verifyCfAccessAssertion(assertion);
    if (!cfAccess.ok) {
      return applyReportOnlyCspNonce(request, createCfAccessForbiddenResponse(), REPORT_ONLY_CSP);
    }
  }

  const gate = healthCheckException
    ? null
    : resolveGatedRedirect(
        "admin",
        request.nextUrl.pathname,
        LOCALES,
        session.user,
        session.roles,
        {
          adminBypass,
        },
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

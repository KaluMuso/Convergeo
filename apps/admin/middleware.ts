import {
  createLoginRedirect,
  getLocaleFromPath,
  isAdminBypassActive,
  mergeSessionCookies,
  shouldRedirectToLogin,
  updateSession,
} from "@vergeo/auth/middleware";
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

export function isProductionCfAccessRequired(): boolean {
  return process.env.NODE_ENV === "production" && !isAdminBypassActive();
}

export function hasCfAccessJwtAssertion(request: NextRequest): boolean {
  const assertion = request.headers.get(CF_ACCESS_HEADER);
  return typeof assertion === "string" && assertion.trim().length > 0;
}

export function createCfAccessForbiddenResponse(): NextResponse {
  return new NextResponse("Forbidden — Cloudflare Access required", { status: 403 });
}

export default async function middleware(request: NextRequest) {
  const session = await updateSession(request);
  const locale = getLocaleFromPath(request.nextUrl.pathname, LOCALES, DEFAULT_LOCALE);

  const adminBypass = isAdminBypassActive();

  if (isProductionCfAccessRequired()) {
    // Cryptographically verify the Cloudflare Access assertion: signature against the
    // team JWKS (RS256) + expected audience + issuer + expiry. Fails closed — absent,
    // malformed, unsigned, wrong-key, wrong-audience, expired, or an unconfigured
    // verifier all return 403 before any handler runs. Authoritative admin RBAC still
    // happens in the API against `user_roles`, never from these claims alone.
    const assertion = request.headers.get(CF_ACCESS_HEADER);
    const cfAccess = await verifyCfAccessAssertion(assertion);
    if (!cfAccess.ok) {
      return createCfAccessForbiddenResponse();
    }
  }

  if (
    shouldRedirectToLogin("admin", request.nextUrl.pathname, LOCALES, session.user, session.roles, {
      adminBypass,
    })
  ) {
    return createLoginRedirect(request, locale, session.response);
  }

  const localeResponse = intlMiddleware(request);
  return mergeSessionCookies(session.response, localeResponse);
}

export const config = {
  matcher: ["/", "/(en|bem|nya|fr|zh)/:path*"],
};

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

/**
 * Validates the Cloudflare Access JWT assertion header.
 * TODO(M13+): verify signature against the Cloudflare Access JWKS for the team domain.
 */
export function isCfAccessJwtAssertionPresent(assertion: string | null): boolean {
  if (!assertion || !assertion.trim()) {
    return false;
  }

  const parts = assertion.trim().split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

export function createCfAccessForbiddenResponse(): NextResponse {
  return new NextResponse("Forbidden — Cloudflare Access required", { status: 403 });
}

export default async function middleware(request: NextRequest) {
  const session = await updateSession(request);
  const locale = getLocaleFromPath(request.nextUrl.pathname, LOCALES, DEFAULT_LOCALE);

  const adminBypass = isAdminBypassActive();

  if (isProductionCfAccessRequired()) {
    const assertion = request.headers.get(CF_ACCESS_HEADER);
    if (!isCfAccessJwtAssertionPresent(assertion)) {
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
  matcher: ["/", "/(en|bem|nya|fr)/:path*"],
};

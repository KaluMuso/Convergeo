import { createServerClient } from "@supabase/ssr";
import type { SetAllCookies } from "@supabase/ssr";
import type { User } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

import { getSupabaseAnonKey, getSupabaseUrl } from "./env";
import { getRolesFromUser, hasRole, type AppRole } from "./roles";

export type AuthGate = "none" | "vendor" | "admin";

export const CSP_NONCE_HEADER = "x-nonce";
export const CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only";
export const CSP_NONCE_PLACEHOLDER = "{{CSP_NONCE}}";

const MIDDLEWARE_OVERRIDE_HEADER = "x-middleware-override-headers";

export function createCspNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function substituteCspNonce(policy: string, nonce: string): string {
  return policy.replaceAll(CSP_NONCE_PLACEHOLDER, nonce);
}

function copyMiddlewareRequestHeaders(source: NextResponse, target: NextResponse): void {
  const sourceKeys = source.headers.get(MIDDLEWARE_OVERRIDE_HEADER);
  if (!sourceKeys) {
    return;
  }

  const overrideKeys = new Set(
    (target.headers.get(MIDDLEWARE_OVERRIDE_HEADER) ?? "")
      .split(",")
      .map((key) => key.trim())
      .filter(Boolean),
  );

  for (const key of sourceKeys.split(",")) {
    const normalizedKey = key.trim();
    if (!normalizedKey) {
      continue;
    }

    const middlewareHeader = `x-middleware-request-${normalizedKey}`;
    const value = source.headers.get(middlewareHeader);
    if (value !== null) {
      target.headers.set(middlewareHeader, value);
      overrideKeys.add(normalizedKey);
    }
  }

  if (overrideKeys.size > 0) {
    target.headers.set(MIDDLEWARE_OVERRIDE_HEADER, [...overrideKeys].join(","));
  }
}

export function applyReportOnlyCspNonce(
  request: NextRequest,
  response: NextResponse,
  reportOnlyPolicy: string,
  nonce = createCspNonce(),
): NextResponse {
  const csp = substituteCspNonce(reportOnlyPolicy, nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(CSP_NONCE_HEADER, nonce);
  requestHeaders.set(CSP_REPORT_ONLY_HEADER, csp);

  const requestOverride = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
  copyMiddlewareRequestHeaders(requestOverride, response);
  response.headers.set(CSP_REPORT_ONLY_HEADER, csp);
  return response;
}

export type UpdateSessionResult = {
  response: NextResponse;
  user: User | null;
  roles: AppRole[];
};

export function getLocaleFromPath(
  pathname: string,
  locales: readonly string[],
  defaultLocale: string,
): string {
  const segments = pathname.split("/").filter(Boolean);
  const candidate = segments[0];
  if (candidate && locales.includes(candidate)) {
    return candidate;
  }
  return defaultLocale;
}

export function isAuthExemptPath(pathname: string, locales: readonly string[]): boolean {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length < 2) {
    return false;
  }

  const locale = segments[0];
  if (!locale || !locales.includes(locale)) {
    return false;
  }

  return segments[1] === "login";
}

/**
 * Invite/concierge seller onboarding (VENDOR-BETA-01): authenticated customers
 * may reach `/onboarding` and `/onboarding/status` without already holding the
 * `vendor` role. Privileged vendor routes stay role-gated.
 */
export function isVendorOnboardingPath(pathname: string, locales: readonly string[]): boolean {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length < 2) {
    return false;
  }

  const locale = segments[0];
  if (!locale || !locales.includes(locale)) {
    return false;
  }

  return segments[1] === "onboarding";
}

export function shouldRedirectToLogin(
  gate: AuthGate,
  pathname: string,
  locales: readonly string[],
  user: User | null,
  roles: readonly string[],
  options?: { adminBypass?: boolean },
): boolean {
  if (gate === "none" || isAuthExemptPath(pathname, locales)) {
    return false;
  }

  if (gate === "admin" && options?.adminBypass) {
    return false;
  }

  if (!user) {
    return true;
  }

  if (gate === "vendor") {
    // Authenticated invitees can complete onboarding before admin grants vendor.
    if (isVendorOnboardingPath(pathname, locales)) {
      return false;
    }
    return !hasRole(roles, "vendor");
  }

  if (gate === "admin") {
    return !hasRole(roles, "admin");
  }

  return false;
}

export function createLoginRedirect(
  request: NextRequest,
  locale: string,
  sessionResponse: NextResponse,
): NextResponse {
  const loginUrl = new URL(`/${locale}/login`, request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  const redirect = NextResponse.redirect(loginUrl);

  sessionResponse.cookies.getAll().forEach((cookie) => {
    redirect.cookies.set(cookie);
  });

  return redirect;
}

export function mergeSessionCookies(source: NextResponse, target: NextResponse): NextResponse {
  source.cookies.getAll().forEach((cookie) => {
    target.cookies.set(cookie);
  });
  return target;
}

export function isAdminBypassActive(): boolean {
  return process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_ADMIN_BYPASS === "true";
}

export async function updateSession(request: NextRequest): Promise<UpdateSessionResult> {
  let response = NextResponse.next({
    request,
  });

  const supabase = createServerClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        response = NextResponse.next({
          request,
        });
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  return {
    response,
    user,
    roles: getRolesFromUser(user),
  };
}

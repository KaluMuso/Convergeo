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
export const CSP_REPORT_PATH = "/api/csp-report";
export const CSP_REPORT_GROUP = "csp-endpoint";
export const CSP_REPORTING_ENDPOINTS_HEADER = "Reporting-Endpoints";

const MIDDLEWARE_OVERRIDE_HEADER = "x-middleware-override-headers";

export function createCspNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function substituteCspNonce(policy: string, nonce: string): string {
  return policy.replaceAll(CSP_NONCE_PLACEHOLDER, nonce);
}

type EnvBag = Record<string, string | undefined>;

/** Same-origin sink by default; override with CSP_REPORT_URI for a central collector. */
export function resolveCspReportUri(env: EnvBag = process.env as EnvBag): string {
  const configured = env.CSP_REPORT_URI?.trim();
  if (configured) {
    return configured;
  }
  return CSP_REPORT_PATH;
}

export function appendCspReporting(
  policy: string,
  reportUri: string = resolveCspReportUri(),
): string {
  if (policy.includes("report-uri") || policy.includes("report-to")) {
    return policy;
  }
  return `${policy}; report-uri ${reportUri}; report-to ${CSP_REPORT_GROUP}`;
}

export function buildReportingEndpointsHeader(reportUri: string = resolveCspReportUri()): string {
  return `${CSP_REPORT_GROUP}="${reportUri}"`;
}

export function isCspReportRequest(
  request: NextRequest,
  reportUri: string = resolveCspReportUri(),
): boolean {
  if (request.method !== "POST") {
    return false;
  }
  const { pathname } = request.nextUrl;
  if (pathname === CSP_REPORT_PATH || pathname === reportUri) {
    return true;
  }
  try {
    const configured = new URL(reportUri, request.nextUrl.origin);
    return configured.pathname === pathname;
  } catch {
    return false;
  }
}

function summarizeCspReportBody(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return "";
  }
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    const report =
      (parsed["csp-report"] as Record<string, unknown> | undefined) ??
      (Array.isArray(parsed.body) ? (parsed.body[0] as Record<string, unknown>) : undefined) ??
      parsed;
    return JSON.stringify({
      blocked: report["blocked-uri"] ?? report.blockedURL ?? null,
      violated: report["violated-directive"] ?? report.effectiveDirective ?? null,
      source: report["source-file"] ?? report.sourceFile ?? null,
      disposition: report.disposition ?? null,
    });
  } catch {
    return trimmed.slice(0, 2048);
  }
}

/** Accept CSP violation reports (report-uri / Reporting API) and log a redacted summary. */
export async function handleCspReportRequest(request: NextRequest): Promise<NextResponse> {
  try {
    const raw = await request.text();
    const summary = summarizeCspReportBody(raw);
    if (summary) {
      console.info("[csp-report]", summary);
    }
  } catch {
    // Browsers may POST empty bodies on some report types — still return 204.
  }
  return new NextResponse(null, { status: 204 });
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
  const reportUri = resolveCspReportUri();
  const csp = appendCspReporting(substituteCspNonce(reportOnlyPolicy, nonce), reportUri);
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
  response.headers.set(CSP_REPORTING_ENDPOINTS_HEADER, buildReportingEndpointsHeader(reportUri));
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

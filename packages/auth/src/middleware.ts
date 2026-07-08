import { createServerClient } from "@supabase/ssr";
import type { SetAllCookies } from "@supabase/ssr";
import type { User } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

import { getSupabaseAnonKey, getSupabaseUrl } from "./env";
import { getRolesFromUser, hasRole, type AppRole } from "./roles";

export type AuthGate = "none" | "vendor" | "admin";

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

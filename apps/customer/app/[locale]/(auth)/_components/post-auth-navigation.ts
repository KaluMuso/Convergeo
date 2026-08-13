"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";

import { createAccountApiClient } from "../../account/_components/account-api";

import {
  isOnboardingComplete,
  resolveCustomerPostAuthPath,
  resolvePostAuthPath,
} from "./auth-utils";

import type { AuthPortal } from "@vergeo/auth/portal";

type AuthRouter = {
  push: (path: string) => void;
  refresh: () => void;
};

export type NavigateAfterPortalAuthArgs = {
  router: AuthRouter;
  locale: string;
  portal: AuthPortal;
  nextParam?: string | null;
  fallbackPath: string;
};

/**
 * Portal-aware post-auth navigation.
 *
 * Customer may call `/account/preferences` to decide welcome vs destination.
 * Vendor and Admin must never inherit that Customer onboarding path: they
 * navigate to a sanitized same-origin destination. Authorization (vendor
 * ownership / admin role) remains the middleware + API layer's job.
 */
export async function navigateAfterPortalAuth({
  router,
  locale,
  portal,
  nextParam,
  fallbackPath,
}: NavigateAfterPortalAuthArgs): Promise<void> {
  const fallback = resolvePostAuthPath(locale, nextParam, fallbackPath);

  if (portal !== "customer") {
    router.push(fallback);
    router.refresh();
    return;
  }

  try {
    const supabase = await getBrowserClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.access_token) {
      router.push(fallback);
      router.refresh();
      return;
    }

    const api = createAccountApiClient(() => session.access_token);
    const preferences = await api.getPreferences();
    const destination = resolveCustomerPostAuthPath(
      locale,
      nextParam,
      fallbackPath,
      isOnboardingComplete(preferences.onboarding),
    );
    router.push(destination);
  } catch {
    router.push(fallback);
  }

  router.refresh();
}

/** @deprecated Use navigateAfterPortalAuth with portal: "customer" */
export async function navigateAfterCustomerAuth(
  args: Omit<NavigateAfterPortalAuthArgs, "portal">,
): Promise<void> {
  return navigateAfterPortalAuth({ ...args, portal: "customer" });
}

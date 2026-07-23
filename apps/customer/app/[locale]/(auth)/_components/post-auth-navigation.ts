"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";

import { createAccountApiClient } from "../../account/_components/account-api";

import {
  isOnboardingComplete,
  resolveCustomerPostAuthPath,
  resolvePostAuthPath,
} from "./auth-utils";

type AuthRouter = {
  push: (path: string) => void;
  refresh: () => void;
};

export async function navigateAfterCustomerAuth({
  router,
  locale,
  nextParam,
  fallbackPath,
}: {
  router: AuthRouter;
  locale: string;
  nextParam?: string | null;
  fallbackPath: string;
}): Promise<void> {
  const fallback = resolvePostAuthPath(locale, nextParam, fallbackPath);

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

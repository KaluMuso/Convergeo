"use client";

import type { Session, User } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

import { getBrowserClient } from "./browser-client-lazy";

export type UseSessionResult = {
  session: Session | null;
  user: User | null;
  loading: boolean;
};

declare global {
  interface Window {
    /** Set by Playwright payment fixtures when NEXT_PUBLIC_E2E_MOCK_SESSION=1. */
    __VERGEO_E2E_SESSION__?: Session;
  }
}

export function useSession(): UseSessionResult {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;

    // Deterministic E2E buyer session (CI payment-mock mode only). Never active
    // unless NEXT_PUBLIC_E2E_MOCK_SESSION=1 is compiled into the client bundle.
    // Allow Playwright-injected sessions in development, or when the explicit
    // NEXT_PUBLIC_E2E_MOCK_SESSION=1 flag is compiled into the client (staging
    // honesty specs). Never honour the injection in production builds without
    // that flag.
    const e2eMockAllowed =
      process.env.NEXT_PUBLIC_E2E_MOCK_SESSION === "1" || process.env.NODE_ENV === "development";
    if (e2eMockAllowed) {
      const injected = window.__VERGEO_E2E_SESSION__;
      if (injected?.access_token) {
        setSession(injected);
        setLoading(false);
        return () => {
          active = false;
        };
      }
    }

    // Load the Supabase browser client lazily so @supabase/ssr + supabase-js do
    // NOT land in the first-load JS of every route that reads the session — the
    // heavy client is fetched as a separate chunk after hydration. `session` stays
    // null and `loading` stays true until it resolves, which every consumer already
    // handles.
    void getBrowserClient().then((supabase) => {
      if (!active) {
        return;
      }

      void supabase.auth.getSession().then(({ data }) => {
        if (!active) {
          return;
        }
        setSession(data.session);
        setLoading(false);
      });

      const {
        data: { subscription },
      } = supabase.auth.onAuthStateChange((_event, nextSession) => {
        setSession(nextSession);
        setLoading(false);
      });
      unsubscribe = () => subscription.unsubscribe();
    });

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  return {
    session,
    user: session?.user ?? null,
    loading,
  };
}

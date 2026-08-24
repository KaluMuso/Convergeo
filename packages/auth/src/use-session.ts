"use client";

import type { Session, User } from "@supabase/supabase-js";
import { isE2EMockSessionAllowed } from "@vergeo/config/api-base-url";
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

    // Deterministic E2E buyer session (CI payment-mock mode / staging honesty
    // specs only). Fails closed on every axis — see
    // @vergeo/config's isE2EMockSessionAllowed for the full contract: the
    // explicit NEXT_PUBLIC_E2E_MOCK_SESSION=1 flag is never sufficient alone,
    // it must be paired with the immutable NEXT_PUBLIC_DEPLOYMENT_PLANE=staging
    // build marker, so an accidental flag on a Production build still denies
    // the mock. `next dev` remains the one unconditional exception.
    if (isE2EMockSessionAllowed()) {
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

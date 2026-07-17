"use client";

import type { Session, User } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

import { getBrowserClient } from "./browser-client-lazy";

export type UseSessionResult = {
  session: Session | null;
  user: User | null;
  loading: boolean;
};

export function useSession(): UseSessionResult {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;

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

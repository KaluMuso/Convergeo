"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { useEffect, useSyncExternalStore } from "react";

import { AuthTransition, type CartMergeResolution, type CustomerSession } from "./auth-transition";
import { mergeGuestCartIntoAccount } from "./cart-merge";

async function mergeCustomerCart(
  session: CustomerSession,
  resolution?: CartMergeResolution,
): Promise<void> {
  await mergeGuestCartIntoAccount(session.access_token, resolution);
}

export const customerAuth = new AuthTransition(mergeCustomerCart);

let initialization: Promise<void> | undefined;

export function initializeCustomerSession(): Promise<void> {
  const mockSession = (window as Window & { __VERGEO_E2E_SESSION__?: CustomerSession })
    .__VERGEO_E2E_SESSION__;
  const mockSessionAllowed =
    process.env.NODE_ENV === "development" ||
    (process.env.NEXT_PUBLIC_E2E_MOCK_SESSION === "1" &&
      process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE === "staging");

  if (!initialization && mockSessionAllowed && mockSession?.access_token) {
    void customerAuth.observe(mockSession).catch(() => undefined);
    initialization = Promise.resolve();
  }

  if (!initialization) {
    initialization = getBrowserClient()
      .then(async (client) => {
        let authEvents = 0;
        const {
          data: { subscription },
        } = client.auth.onAuthStateChange((_event, session) => {
          authEvents += 1;
          void customerAuth.observe(session).catch(() => undefined);
        });

        const beforeGetSession = authEvents;
        try {
          const { data, error } = await client.auth.getSession();
          if (error) throw error;
          if (authEvents === beforeGetSession) {
            void customerAuth.observe(data.session).catch(() => undefined);
          }
        } catch (error) {
          subscription.unsubscribe();
          throw error;
        }
      })
      .catch((error: unknown) => {
        initialization = undefined;
        customerAuth.failInitialization(error);
        throw error;
      });
  }

  return initialization;
}

export async function reconcileCustomerSession(
  session: CustomerSession,
  retry = false,
): Promise<CustomerSession | null> {
  await initializeCustomerSession();
  await customerAuth.observe(session, { retry });
  return customerAuth.ready();
}

export async function getReadyCustomerSession(
  retry = false,
  resolution?: CartMergeResolution,
): Promise<CustomerSession | null> {
  await initializeCustomerSession();
  return customerAuth.ready(retry, resolution);
}

const serverState = { session: null, loading: true, error: null, generation: 0 };

export function useSession() {
  const state = useSyncExternalStore(
    customerAuth.subscribe,
    customerAuth.snapshot,
    () => serverState,
  );

  useEffect(() => {
    void initializeCustomerSession().catch(() => undefined);
  }, []);

  return {
    ...state,
    user: state.session?.user ?? null,
    retry: (resolution?: CartMergeResolution) => getReadyCustomerSession(true, resolution),
  };
}

export type { CartMergeResolution, CustomerSession } from "./auth-transition";

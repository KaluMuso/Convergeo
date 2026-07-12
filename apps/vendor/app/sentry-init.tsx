"use client";

import { useEffect } from "react";

import { initClientSentry } from "../sentry.client.config";

/**
 * Lazy Sentry loader (M16-P06). Renders nothing. After hydration it dynamically
 * `import()`s `@sentry/nextjs` — landing the SDK in an ASYNC chunk, never in first-load
 * JS — and only when `NEXT_PUBLIC_SENTRY_DSN` is set (dev/CI and DSN-less deploys pay
 * zero bytes and make zero network calls).
 */
export function SentryInit() {
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return;
    void import("@sentry/nextjs").then((Sentry) => {
      initClientSentry(Sentry);
    });
  }, []);
  return null;
}

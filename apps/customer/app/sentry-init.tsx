"use client";

import { useEffect } from "react";

import { initClientSentry } from "../sentry.client.config";

/**
 * Lazy Sentry loader (M16-P06). Renders nothing. After hydration it dynamically
 * `import()`s `@sentry/nextjs` — landing the SDK in an ASYNC chunk, never in a route's
 * first-load JS manifest — and only when `NEXT_PUBLIC_SENTRY_DSN` is set (so dev/CI and
 * DSN-less deploys pay zero bytes and make zero network calls). Keeps customer routes
 * within the ≤150 KB gz budget (CLAUDE.md #7).
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

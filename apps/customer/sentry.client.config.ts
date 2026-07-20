/**
 * Sentry browser init — customer app (M16-P06 / Prompt 9).
 *
 * SDK-free at load time (`import type` only). Heavy `@sentry/nextjs` is passed in by
 * the lazy loader (`app/sentry-init.tsx`) after hydration so it stays off first-load JS
 * (CLAUDE.md #7: ≤150 KB gz). Scrubbing lives in `@vergeo/observability`.
 */
import type * as SentryType from "@sentry/nextjs";
import { resolveEnvironment, resolveReleaseSha, scrub } from "@vergeo/observability";

/**
 * Initialise the browser SDK with the dynamically-imported Sentry module. Called by
 * the lazy loader only when `NEXT_PUBLIC_SENTRY_DSN` is present.
 */
export function initClientSentry(Sentry: typeof SentryType): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  const release = resolveReleaseSha();
  const environment = resolveEnvironment();

  Sentry.init({
    dsn,
    environment,
    release,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    maxBreadcrumbs: 50,
    integrations: (defaults) =>
      defaults.filter((i) => !/(BrowserTracing|Replay|Feedback)/.test(i.name)),
    initialScope: {
      tags: {
        application: "customer",
        ...(release ? { release_sha: release } : {}),
      },
    },
    beforeSend: (event) => scrub(event) as typeof event,
    beforeBreadcrumb: (crumb) => scrub(crumb) as typeof crumb,
  });
}

export { scrub } from "@vergeo/observability";

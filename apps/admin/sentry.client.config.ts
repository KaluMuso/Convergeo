/**
 * Sentry browser init — admin app (STRICTEST).
 * Lazy-loaded via `app/sentry-init.tsx`. Drops console/http breadcrumbs.
 */
import type * as SentryType from "@sentry/nextjs";
import { resolveEnvironment, resolveReleaseSha, scrub } from "@vergeo/observability";

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
    maxBreadcrumbs: 20,
    integrations: (defaults) =>
      defaults.filter((i) => !/(BrowserTracing|Replay|Feedback)/.test(i.name)),
    initialScope: {
      tags: {
        application: "admin",
        ...(release ? { release_sha: release } : {}),
      },
    },
    beforeSend: (event) => scrub(event) as typeof event,
    beforeBreadcrumb: (crumb) => {
      if (crumb.category === "console" || crumb.category === "xhr" || crumb.category === "fetch") {
        return null;
      }
      return scrub(crumb) as typeof crumb;
    },
  });
}

export { scrub } from "@vergeo/observability";

/** Server Sentry bootstrap for admin (see customer/instrumentation.ts). */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  const Sentry = await import("@sentry/nextjs");
  const { resolveEnvironment, resolveReleaseSha, scrub } = await import("@vergeo/observability");
  const release = resolveReleaseSha();

  Sentry.init({
    dsn,
    environment: resolveEnvironment(),
    release,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    maxBreadcrumbs: 20,
    initialScope: {
      tags: {
        application: "admin",
        runtime: "nodejs",
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

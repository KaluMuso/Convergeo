/** Server Sentry bootstrap for vendor (see customer/instrumentation.ts). */
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
    initialScope: {
      tags: {
        application: "vendor",
        runtime: "nodejs",
        ...(release ? { release_sha: release } : {}),
      },
    },
    beforeSend: (event) => scrub(event) as typeof event,
    beforeBreadcrumb: (crumb) => scrub(crumb) as typeof crumb,
  });
}

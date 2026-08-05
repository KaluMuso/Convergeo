import { scrubText } from "./scrub";

export type ClientErrorBoundary = "route" | "global";

export type ClientErrorApplication = "customer" | "vendor" | "admin";

export type ClientErrorPayload = {
  message: string;
  digest?: string;
  stack?: string;
  boundary: ClientErrorBoundary;
  application: ClientErrorApplication;
  locale?: string;
  url?: string;
  userAgent?: string;
};

export type ReportClientErrorOptions = {
  apiBaseUrl?: string;
  locale?: string;
};

function sanitizePayload(
  error: Error & { digest?: string },
  input: ClientErrorPayload,
): ClientErrorPayload {
  const message = scrubText(error.message || input.message).slice(0, 500);
  const stack = error.stack ? scrubText(error.stack).slice(0, 8_000) : undefined;

  return {
    ...input,
    message,
    digest: input.digest?.slice(0, 128),
    stack,
    locale: input.locale?.slice(0, 8),
    url: input.url?.slice(0, 2_000),
    userAgent: input.userAgent?.slice(0, 500),
  };
}

async function captureWithSentry(
  error: Error & { digest?: string },
  payload: ClientErrorPayload,
): Promise<boolean> {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();
  if (!dsn) {
    return false;
  }

  try {
    const Sentry = await import("@sentry/nextjs");
    Sentry.captureException(error, {
      tags: {
        boundary: payload.boundary,
        application: payload.application,
      },
      extra: {
        digest: payload.digest,
        locale: payload.locale,
      },
    });
    return true;
  } catch {
    return false;
  }
}

function postToTelemetryApi(apiBaseUrl: string, payload: ClientErrorPayload): void {
  const endpoint = `${apiBaseUrl.replace(/\/$/, "")}/telemetry/frontend-errors`;
  const body = JSON.stringify(payload);

  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const sent = navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
      if (sent) {
        return;
      }
    }
  } catch {
    // Fall through to fetch.
  }

  void fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

/** Fire-and-forget client error reporting: Sentry when configured, else API beacon. */
export async function reportClientError(
  error: Error & { digest?: string },
  payload: ClientErrorPayload,
  options: ReportClientErrorOptions = {},
): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }

  const sanitized = sanitizePayload(error, {
    ...payload,
    locale: options.locale ?? payload.locale,
    url: payload.url ?? window.location.href,
    userAgent: payload.userAgent ?? navigator.userAgent,
  });

  const sentToSentry = await captureWithSentry(error, sanitized);
  if (sentToSentry) {
    return;
  }

  const apiBaseUrl = options.apiBaseUrl?.trim();
  if (!apiBaseUrl) {
    return;
  }

  postToTelemetryApi(apiBaseUrl, sanitized);
}

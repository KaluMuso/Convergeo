import { ApiError } from "@vergeo/config";

/**
 * Failures worth one silent retry: the request most likely never reached a handler
 * (network drop, cold API) or carried a token that expired between the click and the
 * request. Moderation decisions are idempotent on the server, so repeating one is safe.
 */
export function isTransientDecisionFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }
  return (
    error.code === "network_error" ||
    error.status === 0 ||
    error.status === 401 ||
    error.status === 408 ||
    error.status === 425 ||
    error.status === 429 ||
    error.status >= 502
  );
}

export type DecisionRetryOptions = {
  /** Called before the retry, e.g. to force a session/token refresh. Errors are ignored. */
  beforeRetry?: () => Promise<void> | void;
  /** Wait before retrying, in ms. */
  delayMs?: number;
};

/** Runs `action`; on a transient failure waits, refreshes, and tries exactly once more. */
export async function withDecisionRetry<T>(
  action: () => Promise<T>,
  options: DecisionRetryOptions = {},
): Promise<T> {
  try {
    return await action();
  } catch (error) {
    if (!isTransientDecisionFailure(error)) {
      throw error;
    }
    try {
      await options.beforeRetry?.();
    } catch {
      // A failed refresh must not mask the retry; the retry reports its own error.
    }
    const delay = options.delayMs ?? 400;
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    return action();
  }
}

/** Reference to quote to support: the API request id when the failure carried one. */
export function decisionFailureReference(error: unknown): string | null {
  if (error instanceof ApiError && error.requestId && error.requestId !== "unknown") {
    return error.requestId;
  }
  return null;
}

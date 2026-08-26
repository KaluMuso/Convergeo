/**
 * Small resilient JSON fetch for discovery SSR paths (home rails, category/PLP
 * listings, popular searches, clips feed/detail — see the callsite audit in
 * PR-E's description). One automatic retry on network failure, internal
 * per-attempt timeout, or 5xx; 4xx and caller cancellation never retry; no
 * silent success.
 */

/**
 * Per-attempt timeout, evidence-based (not old PR #658's un-justified 4000ms):
 * these are server-side SSR fetches from Vercel to the FastAPI backend, and
 * contribute directly to TTFB inside the CLAUDE.md LCP budget (≤2.5s,
 * Fast-3G/360px) — a single attempt must never come close to consuming that
 * whole budget on its own. D22 (docs/plan/00-decisions.md) targets Postgres
 * FTS at ≤150ms p95, so a healthy backend response is expected in the tens-
 * to-low-hundreds-of-milliseconds range; 2000ms leaves generous headroom
 * over that for real tail latency while keeping the worst case (one retry:
 * ~2*timeoutMs + retryDelayMs ≈ 4.25s) well under double the old blind
 * 4000ms-per-attempt choice, so a degraded backend fails fast enough for a
 * callsite's try/catch to fall back to its empty state instead of hanging.
 */
export const DEFAULT_FETCH_TIMEOUT_MS = 2_000;

export type FetchJsonOptions = RequestInit & {
  retries?: number;
  retryDelayMs?: number;
  /** Bounded timeout for EACH attempt (not the retries combined). 0 disables it. */
  timeoutMs?: number;
  /** Next.js fetch cache hint (SSR discovery paths). */
  next?: { revalidate?: number | false; tags?: string[] };
};

/**
 * Carries the HTTP status explicitly so retry classification never depends on
 * parsing `error.message` (old PR #658 matched `/^HTTP 4\d\d /` against the
 * message — fragile, and English-locale-coupled).
 */
export class FetchHttpError extends Error {
  readonly status: number;

  constructor(status: number, url: string) {
    super(`HTTP ${status} for ${url}`);
    this.name = "FetchHttpError";
    this.status = status;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * Duck-typed, not `instanceof Error`: an abort reason can be a `DOMException`
 * constructed in a different realm than this module's ambient `Error` (e.g.
 * a runtime's own AbortController/fetch implementation) — `instanceof`
 * across realms is unreliable even though `.message`/`.name` are present.
 */
function looksLikeError(value: unknown): value is Error {
  return (
    typeof value === "object" && value !== null && typeof (value as Error).message === "string"
  );
}

export async function fetchJson<T>(url: string, options: FetchJsonOptions = {}): Promise<T> {
  const {
    retries = 1,
    retryDelayMs = 250,
    timeoutMs = DEFAULT_FETCH_TIMEOUT_MS,
    signal: callerSignal,
    ...init
  } = options;

  let attempt = 0;
  let lastError: unknown;

  while (attempt <= retries) {
    // Fresh per-attempt timeout controller — a timeout budget covering ALL
    // retries combined would let one slow attempt eat the next attempt's
    // allowance; each attempt gets its own full `timeoutMs`.
    const timeoutController = timeoutMs > 0 ? new AbortController() : null;
    const timeoutHandle =
      timeoutController === null
        ? null
        : setTimeout(
            () => timeoutController.abort(new DOMException("Attempt timed out", "TimeoutError")),
            timeoutMs,
          );
    // AbortSignal.any composes fresh per attempt — no listener accumulation
    // across retries, and nothing to manually remove on cleanup.
    const signals = [callerSignal, timeoutController?.signal].filter(
      (signal): signal is AbortSignal => signal != null,
    );
    const attemptSignal = signals.length > 0 ? AbortSignal.any(signals) : undefined;

    try {
      const response = await fetch(url, {
        ...init,
        signal: attemptSignal,
        headers: {
          Accept: "application/json",
          ...(init.headers ?? {}),
        },
      });

      if (!response.ok) {
        if (response.status >= 500 && attempt < retries) {
          attempt += 1;
          await sleep(retryDelayMs * attempt);
          continue;
        }
        // 4xx, or 5xx with no retry budget left — thrown here, never inside
        // a branch the surrounding catch treats as retryable.
        throw new FetchHttpError(response.status, url);
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof FetchHttpError) {
        // Deterministic HTTP error — never retry, regardless of budget.
        throw error;
      }
      if (callerSignal?.aborted) {
        // Explicit caller cancellation — propagate promptly, never retry.
        // Distinct from an internal per-attempt timeout, which HAS NOT
        // aborted the caller's own signal and so falls through to retry.
        throw error;
      }
      lastError = error;
      if (attempt >= retries) {
        break;
      }
      attempt += 1;
      await sleep(retryDelayMs * attempt);
    } finally {
      if (timeoutHandle !== null) {
        clearTimeout(timeoutHandle);
      }
    }
  }

  throw looksLikeError(lastError) ? lastError : new Error(`Failed to fetch ${url}`);
}

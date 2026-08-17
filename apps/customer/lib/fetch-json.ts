/**
 * Small resilient JSON fetch for discovery SSR/client paths.
 * One automatic retry on network failure, abort/timeout, or 5xx; no silent success.
 */

export const DEFAULT_FETCH_TIMEOUT_MS = 4_000;

export type FetchJsonOptions = RequestInit & {
  retries?: number;
  retryDelayMs?: number;
  /** Bounded timeout for each attempt. 0 disables the timeout. */
  timeoutMs?: number;
  /** Next.js fetch cache hint (SSR discovery paths). */
  next?: { revalidate?: number | false; tags?: string[] };
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function mergeAbortSignals(signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const active = signals.filter((signal): signal is AbortSignal => signal !== undefined);
  if (active.length === 0) {
    return undefined;
  }
  if (active.length === 1) {
    return active[0];
  }
  if (typeof AbortSignal.any === "function") {
    return AbortSignal.any(active);
  }
  const controller = new AbortController();
  for (const signal of active) {
    if (signal.aborted) {
      controller.abort(signal.reason);
      return controller.signal;
    }
    signal.addEventListener("abort", () => controller.abort(signal.reason), { once: true });
  }
  return controller.signal;
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
    const timeoutController = timeoutMs > 0 ? new AbortController() : null;
    const timeoutHandle =
      timeoutController === null ? null : setTimeout(() => timeoutController.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        ...init,
        signal: mergeAbortSignals([callerSignal, timeoutController?.signal]),
        headers: {
          Accept: "application/json",
          ...(init.headers ?? {}),
        },
      });
      if (response.status >= 500 && attempt < retries) {
        attempt += 1;
        await sleep(retryDelayMs * attempt);
        continue;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status} for ${url}`);
      }
      return (await response.json()) as T;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : "";
      const isClientHttp = /^HTTP 4\d\d /.test(message);
      if (isClientHttp || attempt >= retries) {
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

  throw lastError instanceof Error ? lastError : new Error(`Failed to fetch ${url}`);
}

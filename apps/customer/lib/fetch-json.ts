/**
 * Small resilient JSON fetch for discovery SSR/client paths.
 * One automatic retry on network failure or 5xx; no silent success.
 */

export type FetchJsonOptions = RequestInit & {
  retries?: number;
  retryDelayMs?: number;
  /** Next.js fetch cache hint (SSR discovery paths). */
  next?: { revalidate?: number | false; tags?: string[] };
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export async function fetchJson<T>(url: string, options: FetchJsonOptions = {}): Promise<T> {
  const { retries = 1, retryDelayMs = 250, ...init } = options;
  let attempt = 0;
  let lastError: unknown;

  while (attempt <= retries) {
    try {
      const response = await fetch(url, {
        ...init,
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
      if (attempt >= retries) {
        break;
      }
      attempt += 1;
      await sleep(retryDelayMs * attempt);
    }
  }

  throw lastError instanceof Error ? lastError : new Error(`Failed to fetch ${url}`);
}

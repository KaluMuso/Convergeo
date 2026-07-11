/**
 * Best-effort in-memory fixed-window rate limiter for the contact route.
 * Per-instance only (serverless instances do not share state), so it is a
 * first line of defence against bursts — not a distributed guarantee.
 */

export type RateLimitResult = { allowed: boolean; remaining: number; resetAt: number };

type Bucket = { count: number; resetAt: number };

const buckets = new Map<string, Bucket>();

export const DEFAULT_LIMIT = 3;
export const DEFAULT_WINDOW_MS = 60_000;

export function checkRateLimit(
  key: string,
  limit: number = DEFAULT_LIMIT,
  windowMs: number = DEFAULT_WINDOW_MS,
  now: number = Date.now(),
): RateLimitResult {
  const existing = buckets.get(key);

  if (!existing || existing.resetAt <= now) {
    const resetAt = now + windowMs;
    buckets.set(key, { count: 1, resetAt });
    return { allowed: true, remaining: limit - 1, resetAt };
  }

  if (existing.count >= limit) {
    return { allowed: false, remaining: 0, resetAt: existing.resetAt };
  }

  existing.count += 1;
  return { allowed: true, remaining: limit - existing.count, resetAt: existing.resetAt };
}

/** Test helper — clears all buckets. */
export function resetRateLimits(): void {
  buckets.clear();
}

import { getApiBaseUrl } from "./api-base-url";

/**
 * Busy mode (admin → Config → Busy mode) from `GET /public/config/busy-mode`.
 * The API caches the level for 30 s. Every failure means "nothing paused" so a flaky
 * config call can never hide features, and cart/checkout/payments never read this.
 */
export type BusyMode = {
  level: number;
  pausedFeatures: readonly string[];
};

export const NORMAL_BUSY_MODE: BusyMode = { level: 0, pausedFeatures: [] };

export function parseBusyMode(payload: unknown): BusyMode {
  if (typeof payload !== "object" || payload === null) {
    return NORMAL_BUSY_MODE;
  }
  const record = payload as Record<string, unknown>;
  const level = record.level;
  if (
    typeof level !== "number" ||
    !Number.isInteger(level) ||
    level < 0 ||
    level > 4
  ) {
    return NORMAL_BUSY_MODE;
  }
  const features = Array.isArray(record.paused_features)
    ? record.paused_features.filter((f): f is string => typeof f === "string")
    : [];
  return { level, pausedFeatures: features };
}

export function isPaused(mode: BusyMode, feature: string): boolean {
  return mode.pausedFeatures.includes(feature);
}

const CLIENT_TTL_MS = 30_000;
let clientCache: { at: number; pending: Promise<BusyMode> } | null = null;

/** Browser-side fetch, memoised for 30 s. Never throws. */
export function fetchBusyModeClient(): Promise<BusyMode> {
  const now = Date.now();
  if (clientCache && now - clientCache.at < CLIENT_TTL_MS) {
    return clientCache.pending;
  }
  const base = getApiBaseUrl();
  if (!base) {
    return Promise.resolve(NORMAL_BUSY_MODE);
  }
  const pending = fetch(`${base.replace(/\/$/, "")}/public/config/busy-mode`)
    .then(async (response) =>
      response.ok ? parseBusyMode(await response.json()) : NORMAL_BUSY_MODE,
    )
    .catch(() => NORMAL_BUSY_MODE);
  clientCache = { at: now, pending };
  return pending;
}

export function resetBusyModeCacheForTests(): void {
  clientCache = null;
}

import { absoluteApiUrl, getApiBaseUrl } from "./api-base-url";

/**
 * Read-only storefront display thresholds from `GET /public/config/storefront`
 * (platform_config on the API). Any field is `null` when the API is unreachable or
 * returns an invalid value — callers must hide the dependent UI rather than invent a
 * number, so the storefront never advertises a threshold the API does not enforce.
 */
export type StorefrontConfig = {
  freeDeliveryThresholdNgwee: number | null;
  lowStockThreshold: number | null;
};

export const EMPTY_STOREFRONT_CONFIG: StorefrontConfig = {
  freeDeliveryThresholdNgwee: null,
  lowStockThreshold: null,
};

function nonNegativeInt(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function parseStorefrontConfig(payload: unknown): StorefrontConfig {
  if (typeof payload !== "object" || payload === null) {
    return EMPTY_STOREFRONT_CONFIG;
  }
  const record = payload as Record<string, unknown>;
  const threshold = nonNegativeInt(record.free_delivery_threshold_ngwee);
  return {
    // 0 would divide by zero in the progress bar and means "no threshold".
    freeDeliveryThresholdNgwee: threshold !== null && threshold > 0 ? threshold : null,
    lowStockThreshold: nonNegativeInt(record.low_stock_threshold),
  };
}

/** Server-side fetch (ISR-friendly). Never throws. */
export async function fetchStorefrontConfig(): Promise<StorefrontConfig> {
  const url = absoluteApiUrl("/public/config/storefront");
  if (!url) {
    return EMPTY_STOREFRONT_CONFIG;
  }
  try {
    const response = await fetch(url, { next: { revalidate: 60 } });
    if (!response.ok) {
      return EMPTY_STOREFRONT_CONFIG;
    }
    return parseStorefrontConfig(await response.json());
  } catch {
    return EMPTY_STOREFRONT_CONFIG;
  }
}

let clientCache: Promise<StorefrontConfig> | null = null;

/** Browser-side fetch, memoised per page load. Never throws. */
export function fetchStorefrontConfigClient(): Promise<StorefrontConfig> {
  if (clientCache) {
    return clientCache;
  }
  const base = getApiBaseUrl();
  if (!base) {
    return Promise.resolve(EMPTY_STOREFRONT_CONFIG);
  }
  const pending = fetch(`${base.replace(/\/$/, "")}/public/config/storefront`)
    .then(async (response) =>
      response.ok ? parseStorefrontConfig(await response.json()) : EMPTY_STOREFRONT_CONFIG,
    )
    .catch(() => EMPTY_STOREFRONT_CONFIG)
    .then((config) => {
      if (config === EMPTY_STOREFRONT_CONFIG) {
        clientCache = null; // retry on next mount after a failure
      }
      return config;
    });
  clientCache = pending;
  return pending;
}

export function resetStorefrontConfigCacheForTests(): void {
  clientCache = null;
}

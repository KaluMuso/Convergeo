/** Shared GA4 globals shape. GA4 exposes `gtag()` + the `dataLayer` push queue. */
export type GtagFn = (...args: unknown[]) => void;

export type GtagWindow = Window &
  typeof globalThis & {
    gtag?: GtagFn;
    dataLayer?: unknown[];
  };

"use client";

import { useEffect } from "react";

export const DEFAULT_SW_URL = "/sw.js";

type ProbeFetch = typeof fetch;

/**
 * Only register when the intended worker artifact is actually served.
 * Avoids console 404 noise when a deploy omitted `public/sw.js`.
 */
export async function shouldRegisterServiceWorker(
  swUrl: string = DEFAULT_SW_URL,
  fetchImpl: ProbeFetch = fetch,
): Promise<boolean> {
  try {
    let response = await fetchImpl(swUrl, {
      method: "HEAD",
      cache: "no-store",
      credentials: "omit",
    });
    if (response.status === 405 || response.status === 501) {
      response = await fetchImpl(swUrl, {
        method: "GET",
        cache: "no-store",
        credentials: "omit",
      });
    }
    if (!response.ok) {
      return false;
    }
    const contentType = (response.headers.get("content-type") ?? "").toLowerCase();
    if (
      contentType.length > 0 &&
      !contentType.includes("javascript") &&
      !contentType.includes("ecmascript")
    ) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

type SerwistWindow = Window & {
  serwist?: {
    register: () => Promise<unknown>;
  };
};

export async function registerServiceWorkerIfAvailable(
  swUrl: string = DEFAULT_SW_URL,
  options?: {
    fetchImpl?: ProbeFetch;
    registerImpl?: (url: string) => Promise<unknown>;
    serwistRegister?: () => Promise<unknown>;
  },
): Promise<"registered" | "skipped"> {
  const available = await shouldRegisterServiceWorker(swUrl, options?.fetchImpl ?? fetch);
  if (!available) {
    return "skipped";
  }

  if (options?.serwistRegister) {
    await options.serwistRegister();
    return "registered";
  }

  if (options?.registerImpl) {
    await options.registerImpl(swUrl);
    return "registered";
  }

  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return "skipped";
  }

  const serwist = (window as SerwistWindow).serwist;
  if (serwist?.register) {
    await serwist.register();
    return "registered";
  }

  await navigator.serviceWorker.register(swUrl, { scope: "/" });
  return "registered";
}

/** Client gate for PWA registration. Pair with `@serwist/next` `register: false`. */
export function ServiceWorkerRegister({ swUrl = DEFAULT_SW_URL }: { swUrl?: string }) {
  useEffect(() => {
    void registerServiceWorkerIfAvailable(swUrl);
  }, [swUrl]);

  return null;
}

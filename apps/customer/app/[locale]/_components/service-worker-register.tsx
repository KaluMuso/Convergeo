"use client";

import { useEffect } from "react";

export const DEFAULT_SW_URL = "/sw.js";

type ProbeFetch = typeof fetch;

/**
 * Only register when the intended worker artifact is actually served.
 * Avoids console 404 noise when a deploy omitted `public/sw.js`.
 * Does not ship a fake/no-op worker.
 */
export async function shouldRegisterServiceWorker(
  swUrl: string = DEFAULT_SW_URL,
  fetchImpl: ProbeFetch = fetch,
): Promise<boolean> {
  try {
    // Prefer HEAD to avoid downloading the worker body on every navigation.
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
    // Accept JS workers; also allow empty content-type (some CDNs omit it).
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

/**
 * Client gate for PWA registration. Mount once at the locale root.
 * Pair with `@serwist/next` `register: false` so we never auto-register a 404.
 */
export function ServiceWorkerRegister({ swUrl = DEFAULT_SW_URL }: { swUrl?: string }) {
  useEffect(() => {
    void registerServiceWorkerIfAvailable(swUrl);
  }, [swUrl]);

  return null;
}

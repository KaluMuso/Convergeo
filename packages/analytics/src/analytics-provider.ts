"use client";

/**
 * Consent-aware GA4 mount for the customer app. SSR-safe and layout-shift-free:
 * it renders nothing (returns null) and does all its work in an effect, so there
 * is no CLS and the GA4 script is loaded deferred/async after hydration.
 *
 * The GA4 script is injected ONLY when consent is granted AND a measurement id is
 * present. Consent refusal disables GA4 only — anonymized server beacons keep
 * flowing via `track`. The measurement id comes from
 * `NEXT_PUBLIC_GA4_MEASUREMENT_ID` (never hardcoded) or an explicit prop.
 */

import { useEffect } from "react";

import { hasAnalyticsConsent } from "./consent";
import type { GtagWindow } from "./gtag";
import { flush } from "./track";

const GA4_SCRIPT_ID = "vg-ga4-src";

export interface AnalyticsProviderProps {
  /** GA4 measurement id; falls back to NEXT_PUBLIC_GA4_MEASUREMENT_ID. */
  measurementId?: string;
}

function loadGa4(measurementId: string): void {
  if (document.getElementById(GA4_SCRIPT_ID)) {
    return;
  }
  const w = window as GtagWindow;
  const dataLayer: unknown[] = w.dataLayer ?? [];
  w.dataLayer = dataLayer;
  if (typeof w.gtag !== "function") {
    w.gtag = (...args: unknown[]) => {
      dataLayer.push(args);
    };
  }
  w.gtag("js", new Date());
  // anonymize_ip keeps the mirror DPA-friendly; the server log is already anonymized.
  w.gtag("config", measurementId, { anonymize_ip: true, send_page_view: true });

  const script = document.createElement("script");
  script.id = GA4_SCRIPT_ID;
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.appendChild(script);
}

export function AnalyticsProvider({ measurementId }: AnalyticsProviderProps): null {
  useEffect(() => {
    const id = measurementId ?? process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID;

    // GA4 mirror: consent-gated. Server beacons flow regardless via track().
    if (id && hasAnalyticsConsent()) {
      loadGa4(id);
    }

    // Data-frugal: flush the batched beacon queue when the tab is hidden/unloaded.
    const flushOnHide = (): void => {
      flush();
    };
    document.addEventListener("visibilitychange", flushOnHide);
    window.addEventListener("pagehide", flushOnHide);
    return () => {
      document.removeEventListener("visibilitychange", flushOnHide);
      window.removeEventListener("pagehide", flushOnHide);
    };
  }, [measurementId]);

  return null;
}

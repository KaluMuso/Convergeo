"use client";

import { useEffect, useState } from "react";

import { dashboardApi } from "./api";

const STORAGE_KEY = "vg_admin_analytics_enabled";

/**
 * Convergeo Intelligence 1B-05: reveal the Analytics nav entry only when the API says the
 * `analytics_v2_rollups` flag is ON. One status read per browser session (cached in
 * sessionStorage); any failure keeps the entry hidden, so with the flag off the admin
 * navigation is unchanged.
 */
export function useAnalyticsNavEnabled(active: boolean): boolean {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    if (!active) {
      return;
    }
    try {
      const cached = window.sessionStorage.getItem(STORAGE_KEY);
      if (cached !== null) {
        setEnabled(cached === "1");
        return;
      }
    } catch {
      // Storage unavailable (private mode): fall through to a single read.
    }
    let cancelled = false;
    void dashboardApi
      .request<{ enabled: boolean }>("/admin/analytics/status")
      .then((status) => {
        if (cancelled) {
          return;
        }
        setEnabled(status.enabled === true);
        try {
          window.sessionStorage.setItem(STORAGE_KEY, status.enabled === true ? "1" : "0");
        } catch {
          // Best effort only.
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [active]);

  return enabled;
}

"use client";

import { useEffect, useState } from "react";

type ConnectionLike = { saveData?: boolean };

function readSaveData(): boolean {
  if (typeof navigator === "undefined") {
    return false;
  }
  const conn = (navigator as Navigator & { connection?: ConnectionLike }).connection;
  return Boolean(conn?.saveData);
}

/**
 * True when the user has asked the browser to conserve data — either the
 * Network Information `Save-Data` flag (Chrome / Android "Data Saver") or the
 * `prefers-reduced-data: reduce` media query. Reactive to media-query changes.
 *
 * Client-only: returns `false` during SSR / first paint, then resolves on mount.
 * Callers gate bandwidth-hungry enhancements behind it (carousel autoplay,
 * IntersectionObserver auto-pagination, eager media) — data-cost frugality for
 * 3G-first Zambia. Single source of truth so every surface reads the same signal.
 */
export function usePrefersReducedData(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const saveData = readSaveData();
    if (typeof window.matchMedia !== "function") {
      setReduced(saveData);
      return;
    }

    const mq = window.matchMedia("(prefers-reduced-data: reduce)");
    const update = () => setReduced(mq.matches || saveData);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}

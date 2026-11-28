"use client";

import { useEffect, useState } from "react";

import {
  fetchBusyModeClient,
  NORMAL_BUSY_MODE,
  type BusyMode,
} from "./busy-mode";

/**
 * Current busy mode. Starts as "normal" (`ready: false`) so the first paint never
 * hides anything; callers that would fire extra API calls wait for `ready`.
 */
export function useBusyMode(): BusyMode & { ready: boolean } {
  const [mode, setMode] = useState<BusyMode & { ready: boolean }>({
    ...NORMAL_BUSY_MODE,
    ready: false,
  });
  useEffect(() => {
    let active = true;
    void fetchBusyModeClient().then((next) => {
      if (active) setMode({ ...next, ready: true });
    });
    return () => {
      active = false;
    };
  }, []);
  return mode;
}

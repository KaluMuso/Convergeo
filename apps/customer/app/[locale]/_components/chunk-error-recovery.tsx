"use client";

import { useEffect } from "react";

import { reloadOnceForChunkError } from "../../../lib/chunk-reload";

/**
 * Lazy panels (Ask Vergeo, mini-cart, gallery zoom) load chunks on demand,
 * outside any route error boundary. When such a load fails because a new
 * deploy replaced the build, recover with one guarded hard reload.
 */
export function ChunkErrorRecovery() {
  useEffect(() => {
    const onRejection = (event: PromiseRejectionEvent) => {
      reloadOnceForChunkError(event.reason);
    };
    const onError = (event: ErrorEvent) => {
      reloadOnceForChunkError(event.error ?? event.message);
    };
    window.addEventListener("unhandledrejection", onRejection);
    window.addEventListener("error", onError);
    return () => {
      window.removeEventListener("unhandledrejection", onRejection);
      window.removeEventListener("error", onError);
    };
  }, []);
  return null;
}

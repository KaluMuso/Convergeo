"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { recordAdEvent } from "./ad-events";

/** Counts one impression when ≥50% visible and a click on activation. */
export function AdTracker({ placementId, children }: { placementId: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          recordAdEvent(placementId, "impression");
          observer.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [placementId]);

  return (
    <div ref={ref} onClickCapture={() => recordAdEvent(placementId, "click")}>
      {children}
    </div>
  );
}

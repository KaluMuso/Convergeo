"use client";

import { useCallback, useEffect, useState } from "react";

const DEFAULT_THRESHOLD_PX = 480;

type BackToTopProps = {
  label: string;
  thresholdPx?: number;
};

/**
 * Fixed return-to-top control for long browse surfaces (PLP, search).
 * Sits above the shop bottom nav + safe area.
 */
export function BackToTop({ label, thresholdPx = DEFAULT_THRESHOLD_PX }: BackToTopProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setVisible(window.scrollY > thresholdPx);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [thresholdPx]);

  const scrollToTop = useCallback(() => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
  }, []);

  if (!visible) {
    return null;
  }

  return (
    <button
      type="button"
      onClick={scrollToTop}
      aria-label={label}
      data-testid="back-to-top"
      className="tap fixed right-4 z-40 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border bg-surface text-text shadow-2 transition-opacity duration-fast ease-std motion-reduce:transition-none focus-visible:outline-none focus-visible:shadow-focusRing lg:right-6"
      style={{ bottom: "calc(3.75rem + env(safe-area-inset-bottom, 0px))" }}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-5 w-5"
        aria-hidden
      >
        <path d="m6 15 6-6 6 6" />
      </svg>
    </button>
  );
}

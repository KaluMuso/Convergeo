"use client";

import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useEffect, useState, type RefObject } from "react";

export const EVENT_TICKET_PICKER_ID = "event-ticket-picker";

export type EventStickyCtaLabels = {
  ariaLabel: string;
  cta: string;
  free: string;
  soldOut: string;
};

export type EventStickyCtaProps = {
  priceLine: string;
  isSoldOut: boolean;
  isFree: boolean;
  observeRef: RefObject<HTMLElement | null>;
  labels: EventStickyCtaLabels;
};

export function EventStickyCta({
  priceLine,
  isSoldOut,
  isFree,
  observeRef,
  labels,
}: EventStickyCtaProps) {
  const [out, setOut] = useState(false);
  useEffect(() => {
    const el = observeRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([entry]) => setOut(!entry?.isIntersecting), {
      threshold: 0.1,
      rootMargin: "0px 0px -72px 0px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, [observeRef]);
  if (!out || isSoldOut) return null;
  return (
    <aside
      data-testid="event-sticky-cta"
      aria-label={labels.ariaLabel}
      className="fixed inset-x-0 z-40 border-t border-border bg-surface/95 p-3 lg:hidden"
      style={{ bottom: "calc(3.5rem + env(safe-area-inset-bottom, 0px))" }}
    >
      <div className="mx-auto flex max-w-[1400px] items-center gap-3">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-text">
          {isFree ? labels.free : priceLine}
        </p>
        <LinkButton
          href={`#${EVENT_TICKET_PICKER_ID}`}
          variant="primary"
          className="min-h-11 rounded-md px-4 text-sm font-semibold"
          LinkComponent={Link}
        >
          {labels.cta}
        </LinkButton>
      </div>
    </aside>
  );
}

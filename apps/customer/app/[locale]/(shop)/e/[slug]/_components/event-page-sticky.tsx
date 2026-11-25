"use client";
import { useEffect, useRef } from "react";
import {
  EVENT_TICKET_PICKER_ID,
  EventStickyCta,
  type EventStickyCtaProps,
} from "./event-sticky-cta";
export function EventPageSticky(props: Omit<EventStickyCtaProps, "observeRef">) {
  const observeRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    observeRef.current = document.getElementById(EVENT_TICKET_PICKER_ID);
  }, []);
  return <EventStickyCta {...props} observeRef={observeRef} />;
}

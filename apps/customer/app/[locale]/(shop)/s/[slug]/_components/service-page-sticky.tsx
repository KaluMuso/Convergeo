"use client";

import { useEffect, useRef } from "react";

import {
  ServiceStickyCta,
  type ServiceStickyCtaLabels,
  type ServiceStickyCtaProps,
  type ServiceStickyKind,
} from "./service-sticky-cta";

import type { RequestQuoteLabels } from "../../../_components/pdp/request-quote-button";

export type ServicePageStickyProps = Omit<ServiceStickyCtaProps, "observeRef" | "labels"> & {
  labels: ServiceStickyCtaLabels;
  kind: ServiceStickyKind;
  quoteLabels: RequestQuoteLabels;
};

const SIDEBAR_ID = "service-sidebar-cta";

export function ServicePageSticky(props: ServicePageStickyProps) {
  const observeRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    observeRef.current = document.getElementById(SIDEBAR_ID);
  }, []);

  return <ServiceStickyCta {...props} observeRef={observeRef} />;
}

export { SIDEBAR_ID as SERVICE_SIDEBAR_CTA_ID };

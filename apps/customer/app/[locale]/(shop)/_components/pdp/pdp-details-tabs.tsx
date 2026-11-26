"use client";

import { Tabs, type TabItem } from "@vergeo/ui/src/tabs";
import { useEffect, useState, type ReactNode } from "react";

const REVIEWS_HASHES = new Set(["#pdp-reviews", "#reviews"]);

export type PdpDetailsTabsLabels = {
  ariaLabel: string;
  overview: string;
  specs: string;
  reviews: string;
};

type PdpDetailsTabsProps = {
  labels: PdpDetailsTabsLabels;
  hasOverview: boolean;
  overviewPanel: ReactNode;
  specsPanel: ReactNode;
  reviewsPanel: ReactNode;
};

export function PdpDetailsTabs({
  labels,
  hasOverview,
  overviewPanel,
  specsPanel,
  reviewsPanel,
}: PdpDetailsTabsProps) {
  const items: TabItem[] = [];
  const [active, setActive] = useState(hasOverview ? "overview" : "specs");

  useEffect(() => {
    const openFromHash = () => {
      if (!REVIEWS_HASHES.has(window.location.hash)) {
        return;
      }
      setActive("reviews");
      requestAnimationFrame(() => {
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        document
          .getElementById("pdp-reviews")
          ?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      });
    };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, []);

  if (hasOverview) {
    items.push({
      key: "overview",
      label: labels.overview,
      panel: <section id="pdp-about">{overviewPanel}</section>,
    });
  }

  items.push(
    {
      key: "specs",
      label: labels.specs,
      panel: <section id="pdp-specs">{specsPanel}</section>,
    },
    {
      key: "reviews",
      label: labels.reviews,
      panel: <section id="pdp-reviews">{reviewsPanel}</section>,
    },
  );

  return (
    <Tabs
      ariaLabel={labels.ariaLabel}
      value={active}
      onValueChange={setActive}
      mountInactivePanels
      items={items}
      panelClassName="pt-4"
    />
  );
}

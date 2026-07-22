"use client";

import { Tabs, type TabItem } from "@vergeo/ui/src/tabs";
import type { ReactNode } from "react";

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

  if (hasOverview) {
    items.push({
      key: "overview",
      label: labels.overview,
      panel: overviewPanel,
    });
  }

  items.push(
    {
      key: "specs",
      label: labels.specs,
      panel: specsPanel,
    },
    {
      key: "reviews",
      label: labels.reviews,
      panel: reviewsPanel,
    },
  );

  return (
    <Tabs
      ariaLabel={labels.ariaLabel}
      defaultValue={hasOverview ? "overview" : "specs"}
      mountInactivePanels
      items={items}
      panelClassName="pt-4"
    />
  );
}

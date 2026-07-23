"use client";

import { useState } from "react";

import {
  Comparison,
  type ComparisonLabels,
  type ComparisonListing,
} from "../../_components/pdp/comparison";

import type { LogisticsPillLabels } from "../../_components/plp/logistics-pills";

type CompareResultsProps = {
  listings: ComparisonListing[];
  labels: ComparisonLabels;
  logisticsPillLabels: Pick<LogisticsPillLabels, "delivery" | "pickup">;
};

export function CompareResults({ listings, labels, logisticsPillLabels }: CompareResultsProps) {
  const [selectedListingId, setSelectedListingId] = useState<string | null>(
    () => listings[0]?.id ?? null,
  );

  return (
    <Comparison
      listings={listings}
      selectedListingId={selectedListingId}
      labels={labels}
      logisticsPillLabels={logisticsPillLabels}
      onSelect={setSelectedListingId}
    />
  );
}

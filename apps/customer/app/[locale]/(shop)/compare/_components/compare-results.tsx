"use client";

import { useState } from "react";

import {
  Comparison,
  type ComparisonLabels,
  type ComparisonListing,
} from "../../_components/pdp/comparison";

type CompareResultsProps = {
  listings: ComparisonListing[];
  labels: ComparisonLabels;
};

export function CompareResults({ listings, labels }: CompareResultsProps) {
  const [selectedListingId, setSelectedListingId] = useState<string | null>(
    () => listings[0]?.id ?? null,
  );

  return (
    <Comparison
      listings={listings}
      selectedListingId={selectedListingId}
      labels={labels}
      onSelect={setSelectedListingId}
    />
  );
}

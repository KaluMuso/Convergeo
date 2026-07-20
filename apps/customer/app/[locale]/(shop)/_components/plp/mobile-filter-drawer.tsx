"use client";

import { Button } from "@vergeo/ui/src/button";
import { Modal } from "@vergeo/ui/src/modal";
import { useState } from "react";

import { FacetPanel, type FacetCounts, type FacetPanelLabels } from "./facet-panel";
import { hasActivePlpFilters, type PlpFilterState } from "./plp-filters";

type MobileFilterDrawerProps = {
  labels: FacetPanelLabels & {
    openFilters: string;
    filtersActive: string;
  };
  facets: FacetCounts;
  initialState: PlpFilterState;
};

/**
 * Mobile-only filter entry — opens FacetPanel in a modal (desktop uses the sticky sidebar).
 */
export function MobileFilterDrawer({ labels, facets, initialState }: MobileFilterDrawerProps) {
  const [open, setOpen] = useState(false);
  const active = hasActivePlpFilters(initialState);

  return (
    <div className="lg:hidden" data-testid="plp-mobile-filters">
      <Button
        type="button"
        variant="secondary"
        size="md"
        className="w-full"
        loading={false}
        loadingLabel={labels.openFilters}
        aria-expanded={open}
        data-testid="plp-open-filters"
        onClick={() => setOpen(true)}
      >
        {active ? labels.filtersActive : labels.openFilters}
      </Button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={labels.heading}
        data-testid="plp-filter-drawer"
        className="max-h-[85dvh] w-[min(100%,24rem)] overflow-y-auto"
      >
        <FacetPanel
          labels={labels}
          facets={facets}
          initialState={initialState}
          className="border-0 p-0 shadow-none"
          onApplied={() => setOpen(false)}
        />
      </Modal>
    </div>
  );
}

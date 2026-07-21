"use client";

import { Button } from "@vergeo/ui/src/button";
import { Modal } from "@vergeo/ui/src/modal";
import { useState } from "react";

import {
  SearchFilterPanel,
  type SearchCategoryOption,
  type SearchFilterPanelLabels,
} from "./search-filter-panel";
import { hasActiveSearchFilters, type SearchFilterState } from "./search-filters";

type SearchMobileFilterDrawerProps = {
  labels: SearchFilterPanelLabels & {
    openFilters: string;
    filtersActive: string;
  };
  categories: SearchCategoryOption[];
  initialState: SearchFilterState;
  categoryCounts?: Record<string, number>;
};

export function SearchMobileFilterDrawer({
  labels,
  categories,
  initialState,
  categoryCounts,
}: SearchMobileFilterDrawerProps) {
  const [open, setOpen] = useState(false);
  const active = hasActiveSearchFilters(initialState);

  return (
    <div className="lg:hidden" data-testid="search-mobile-filters">
      <Button
        type="button"
        variant="secondary"
        size="md"
        className="w-full"
        loading={false}
        loadingLabel={labels.openFilters}
        aria-expanded={open}
        data-testid="search-open-filters"
        onClick={() => setOpen(true)}
      >
        {active ? labels.filtersActive : labels.openFilters}
      </Button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={labels.heading}
        data-testid="search-filter-drawer"
        className="max-h-[85dvh] w-[min(100%,24rem)] overflow-y-auto"
      >
        <SearchFilterPanel
          labels={labels}
          categories={categories}
          initialState={initialState}
          categoryCounts={categoryCounts}
          className="border-0 p-0 shadow-none"
          onApplied={() => setOpen(false)}
        />
      </Modal>
    </div>
  );
}

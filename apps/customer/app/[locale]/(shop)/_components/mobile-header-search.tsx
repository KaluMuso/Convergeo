"use client";

import { IconSearch } from "@vergeo/ui/src/icons";
import { BottomSheet } from "@vergeo/ui/src/bottom-sheet";
import { useState } from "react";

import { SearchInput, type SearchInputLabels } from "./search/search-input";

type MobileHeaderSearchProps = {
  locale: string;
  labels: SearchInputLabels;
  sheetTitle: string;
  triggerLabel: string;
};

/**
 * Mobile/tablet header search affordance — opens a bottom sheet with the
 * shared SearchInput (suggestions, recent-on-focus, deep-links).
 */
export function MobileHeaderSearch({
  locale,
  labels,
  sheetTitle,
  triggerLabel,
}: MobileHeaderSearchProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-11 w-full max-w-md items-center gap-2 rounded-pill border border-border bg-surface px-4 text-sm text-text-3 transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
        aria-label={triggerLabel}
        data-testid="mobile-header-search-trigger"
      >
        <IconSearch className="text-text-2" aria-hidden />
        <span className="truncate">{labels.placeholder}</span>
      </button>

      <BottomSheet
        open={open}
        onClose={() => setOpen(false)}
        title={sheetTitle}
        snapHeight="auto"
        data-testid="mobile-header-search-sheet"
      >
        <div className="px-4 pb-6 pt-2">
          <SearchInput locale={locale} labels={labels} autoFocus />
        </div>
      </BottomSheet>
    </>
  );
}

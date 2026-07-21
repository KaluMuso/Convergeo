"use client";

import { SearchInput, type SearchInputLabels } from "./search/search-input";

type DesktopHeaderSearchProps = {
  locale: string;
  labels: SearchInputLabels;
};

/**
 * Desktop sticky header search with live suggestions (audit §4.2 / F04).
 * Wraps the shared SearchInput in compact header chrome.
 */
export function DesktopHeaderSearch({ locale, labels }: DesktopHeaderSearchProps) {
  return (
    <SearchInput
      locale={locale}
      labels={labels}
      compact
      inputClassName="h-11 border-primary/30 bg-bg shadow-1"
    />
  );
}

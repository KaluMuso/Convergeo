"use client";

import { SearchInput, type SearchInputLabels } from "./search/search-input";

type DesktopHeaderSearchProps = {
  locale: string;
  labels: SearchInputLabels;
  askLabel?: string;
};

/**
 * Desktop sticky header search with live suggestions (audit §4.2 / F04).
 * Wraps the shared SearchInput in compact header chrome.
 */
export function DesktopHeaderSearch({ locale, labels, askLabel }: DesktopHeaderSearchProps) {
  return (
    <SearchInput
      locale={locale}
      labels={labels}
      compact
      askLabel={askLabel}
      inputClassName="h-11 rounded-pill border-border bg-bg/80 pl-5 focus:border-primary focus:bg-surface"
    />
  );
}

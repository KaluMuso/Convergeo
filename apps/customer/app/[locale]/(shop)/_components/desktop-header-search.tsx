"use client";

import { usePathname } from "next/navigation";

import { SearchInput, type SearchInputLabels } from "./search/search-input";

/** In-page search on `/{locale}/search` — hide header field to avoid duplicates. */
function isLocaleSearchPath(pathname: string | null): boolean {
  if (!pathname) return false;
  const segments = pathname.split("/").filter(Boolean);
  return segments.at(-1) === "search";
}

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
  const pathname = usePathname();
  if (isLocaleSearchPath(pathname)) {
    return null;
  }

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

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

export const RECENT_SEARCHES_KEY = "vergeo5.recentSearches";
const MAX_RECENT = 8;

export function readRecentSearches(): string[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(RECENT_SEARCHES_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(
      (item): item is string => typeof item === "string" && item.trim().length > 0,
    );
  } catch {
    return [];
  }
}

export function writeRecentSearches(terms: string[]): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(terms.slice(0, MAX_RECENT)));
}

export function addRecentSearch(term: string): string[] {
  const trimmed = term.trim();
  if (!trimmed) {
    return readRecentSearches();
  }

  const next = [
    trimmed,
    ...readRecentSearches().filter((item) => item.toLowerCase() !== trimmed.toLowerCase()),
  ];
  writeRecentSearches(next);
  return next.slice(0, MAX_RECENT);
}

export function clearRecentSearches(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(RECENT_SEARCHES_KEY);
}

export type RecentSearchesLabels = {
  title: string;
  clear: string;
  remove: string;
};

export type RecentSearchesProps = {
  locale: string;
  labels: RecentSearchesLabels;
  query?: string;
  className?: string;
};

export function RecentSearches({ locale, labels, query, className }: RecentSearchesProps) {
  const [items, setItems] = useState<string[]>([]);

  useEffect(() => {
    setItems(readRecentSearches());
  }, []);

  useEffect(() => {
    if (!query?.trim()) {
      return;
    }
    setItems(addRecentSearch(query));
  }, [query]);

  const handleClear = useCallback(() => {
    clearRecentSearches();
    setItems([]);
  }, []);

  if (items.length === 0) {
    return null;
  }

  return (
    <section className={className} aria-label={labels.title}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text">{labels.title}</h2>
        <button
          type="button"
          onClick={handleClear}
          className="min-h-11 shrink-0 px-2 text-sm text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {labels.clear}
        </button>
      </div>
      <ul className="flex flex-wrap gap-2">
        {items.map((term) => (
          <li key={term}>
            <Link
              href={`/${locale}/search?q=${encodeURIComponent(term)}`}
              className="inline-flex min-h-11 items-center rounded-pill border border-border bg-surface px-3 text-sm text-text hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {term}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

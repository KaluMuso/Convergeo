/**
 * Shared search kind constants — must NOT live in a `"use client"` module.
 *
 * CUST-SEARCH-01 / digest `3273208722`: the Server Component search page was
 * spreading `SEARCH_KINDS` imported from `results-tabs.tsx` (`"use client"`).
 * Client-module values are not iterable on the server → TypeError crash.
 */

export type SearchKind = "products" | "services" | "events" | "vendors";

export type SearchKindFilter = SearchKind | "all";

/** Consumer search kinds (supplies intentionally excluded — B2B /supplies surface). */
export const SEARCH_KINDS: readonly SearchKind[] = [
  "products",
  "services",
  "events",
  "vendors",
] as const;

/** Kinds used for tab-count fan-out on the server (includes "all"). */
export function searchTabKinds(): SearchKindFilter[] {
  return ["all", ...SEARCH_KINDS];
}

export function isSearchKind(value: string): value is SearchKind {
  return (SEARCH_KINDS as readonly string[]).includes(value);
}

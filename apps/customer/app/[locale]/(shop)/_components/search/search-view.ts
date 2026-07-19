import { isSearchKind, type SearchKind, type SearchKindFilter } from "./search-kinds";

import type { SearchResponse, TabCounts } from "./results-tabs";

/** Soft upper bound — keeps URL/API payloads sane without redesigning search. */
export const MAX_SEARCH_QUERY_LENGTH = 200;

export type NormalizedSearchQuery =
  { status: "empty" } | { status: "invalid"; reason: "too_long" } | { status: "ok"; query: string };

export function normalizeSearchQuery(raw: string | undefined): NormalizedSearchQuery {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) {
    return { status: "empty" };
  }
  if (trimmed.length > MAX_SEARCH_QUERY_LENGTH) {
    return { status: "invalid", reason: "too_long" };
  }
  return { status: "ok", query: trimmed };
}

export function parseSearchKind(value: string | undefined): SearchKindFilter {
  if (!value) {
    return "all";
  }
  if (isSearchKind(value)) {
    return value;
  }
  return "all";
}

export function parseSearchPage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export type SearchPageView =
  | { status: "idle" }
  | { status: "invalid"; reason: "too_long" }
  | { status: "unavailable"; query: string }
  | { status: "zero"; query: string; response: SearchResponse }
  | {
      status: "results";
      query: string;
      response: SearchResponse;
      tabCounts: TabCounts;
      kind: SearchKindFilter;
    };

/**
 * Map fetch outcomes to UI states.
 * Failed API (null response after a query) must never collapse to zero-results.
 */
export function resolveSearchPageView(args: {
  normalized: NormalizedSearchQuery;
  kind: SearchKindFilter;
  searchResponse: SearchResponse | null;
  tabCounts: TabCounts | null;
}): SearchPageView {
  if (args.normalized.status === "empty") {
    return { status: "idle" };
  }
  if (args.normalized.status === "invalid") {
    return { status: "invalid", reason: args.normalized.reason };
  }

  const query = args.normalized.query;
  if (args.searchResponse === null) {
    return { status: "unavailable", query };
  }
  if (args.searchResponse.total === 0) {
    return { status: "zero", query, response: args.searchResponse };
  }
  if (!args.tabCounts) {
    return { status: "unavailable", query };
  }
  return {
    status: "results",
    query,
    response: args.searchResponse,
    tabCounts: args.tabCounts,
    kind: args.kind,
  };
}

export type { SearchKind, SearchKindFilter };

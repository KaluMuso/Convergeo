import type { RfqThread } from "../../../../../lib/rfq-api";

export type ListingQuoteDisplayStatus =
  "pending" | "quoted" | "quoted_expired" | "accepted" | "rejected" | "error";

export function isQuoteExpired(thread: RfqThread): boolean {
  if (thread.status !== "quoted" || !thread.quote_valid_until) {
    return false;
  }
  const validUntil = new Date(thread.quote_valid_until);
  return Number.isFinite(validUntil.getTime()) && validUntil.getTime() <= Date.now();
}

export function listingQuoteDisplayStatus(thread: RfqThread | null): ListingQuoteDisplayStatus {
  if (thread === null) {
    return "error";
  }
  if (thread.status === "pending") {
    return "pending";
  }
  if (thread.status === "quoted") {
    return isQuoteExpired(thread) ? "quoted_expired" : "quoted";
  }
  if (thread.status === "accepted") {
    return "accepted";
  }
  if (thread.status === "rejected") {
    return "rejected";
  }
  return "error";
}

export function canAcceptListingQuote(thread: RfqThread): boolean {
  return listingQuoteDisplayStatus(thread) === "quoted";
}

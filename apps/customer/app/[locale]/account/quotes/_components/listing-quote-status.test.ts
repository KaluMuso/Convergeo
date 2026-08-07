import { describe, expect, it } from "vitest";

import {
  canAcceptListingQuote,
  isQuoteExpired,
  listingQuoteDisplayStatus,
} from "./listing-quote-status";

import type { RfqThread } from "../../../../../lib/rfq-api";

function thread(partial: Partial<RfqThread> & Pick<RfqThread, "status">): RfqThread {
  return {
    id: "thread-1",
    customer_id: "cust-1",
    vendor_id: "vendor-1",
    listing_id: "listing-1",
    service_id: null,
    requested_details: "Need 10 units",
    status: partial.status,
    quote_price_ngwee: partial.quote_price_ngwee ?? null,
    quote_valid_until: partial.quote_valid_until ?? null,
    quoted_at: partial.quoted_at ?? null,
    last_message_at: partial.last_message_at ?? null,
    created_at: partial.created_at ?? "2026-01-01T00:00:00Z",
  };
}

describe("listingQuoteDisplayStatus", () => {
  it("maps pending", () => {
    expect(listingQuoteDisplayStatus(thread({ status: "pending" }))).toBe("pending");
  });

  it("maps quoted", () => {
    expect(
      listingQuoteDisplayStatus(
        thread({
          status: "quoted",
          quote_price_ngwee: 100_000,
          quote_valid_until: "2099-01-01T00:00:00Z",
        }),
      ),
    ).toBe("quoted");
  });

  it("maps quoted expired", () => {
    expect(
      listingQuoteDisplayStatus(
        thread({
          status: "quoted",
          quote_valid_until: "2020-01-01T00:00:00Z",
        }),
      ),
    ).toBe("quoted_expired");
  });

  it("can accept only active quoted", () => {
    expect(
      canAcceptListingQuote(
        thread({
          status: "quoted",
          quote_valid_until: "2099-01-01T00:00:00Z",
        }),
      ),
    ).toBe(true);
    expect(canAcceptListingQuote(thread({ status: "accepted" }))).toBe(false);
  });

  it("detects expiry", () => {
    expect(
      isQuoteExpired(
        thread({
          status: "quoted",
          quote_valid_until: "2020-01-01T00:00:00Z",
        }),
      ),
    ).toBe(true);
  });
});

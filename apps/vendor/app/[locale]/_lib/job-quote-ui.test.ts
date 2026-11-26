import { describe, expect, it } from "vitest";

import { canOpenJobQuoteForm, showJobQuoteSummary } from "./job-quote-ui";

describe("job quote UI helpers", () => {
  it("blocks resubmit when a quote is submitted or accepted", () => {
    expect(canOpenJobQuoteForm({ status: "submitted" })).toBe(false);
    expect(canOpenJobQuoteForm({ status: "accepted" })).toBe(false);
  });

  it("allows a new quote after decline or expiry", () => {
    expect(canOpenJobQuoteForm({ status: "declined" })).toBe(true);
    expect(canOpenJobQuoteForm({ status: "expired" })).toBe(true);
    expect(canOpenJobQuoteForm(null)).toBe(true);
  });

  it("shows summary whenever a quote exists", () => {
    expect(showJobQuoteSummary({ status: "accepted" })).toBe(true);
    expect(showJobQuoteSummary(null)).toBe(false);
  });
});

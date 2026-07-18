import { describe, expect, it } from "vitest";

import { summarizeOrderLedger } from "./ledger-summary";

describe("summarizeOrderLedger", () => {
  it("returns empty summary without inventing balances", () => {
    expect(summarizeOrderLedger([])).toEqual({
      transactionCount: 0,
      postingCount: 0,
      absolutePostingNgwee: 0,
      kinds: [],
    });
  });

  it("aggregates kinds and absolute posting amounts from live rows only", () => {
    const summary = summarizeOrderLedger([
      {
        id: "t1",
        kind: "ESCROW_HOLD",
        created_at: "2026-07-18T00:00:00Z",
        postings: [
          { id: "p1", account_id: "escrow", amount_ngwee: 5000 },
          { id: "p2", account_id: "cash", amount_ngwee: -5000 },
        ],
      },
      {
        id: "t2",
        kind: "ESCROW_RELEASE",
        created_at: "2026-07-18T01:00:00Z",
        postings: [{ id: "p3", account_id: "escrow", amount_ngwee: -2000 }],
      },
    ]);

    expect(summary.transactionCount).toBe(2);
    expect(summary.postingCount).toBe(3);
    expect(summary.absolutePostingNgwee).toBe(12000);
    expect(summary.kinds).toEqual(["ESCROW_HOLD", "ESCROW_RELEASE"]);
  });
});

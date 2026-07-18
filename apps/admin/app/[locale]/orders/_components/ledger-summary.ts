import type { LedgerTransaction } from "./api";

export type OrderLedgerSummary = {
  transactionCount: number;
  postingCount: number;
  /** Sum of absolute posting amounts — informational only, not a fabricated balance. */
  absolutePostingNgwee: number;
  kinds: string[];
};

/**
 * Read-only summary derived from order ledger rows returned by GET /admin/orders/{id}.
 * Does not invent escrow held/released balances when the API does not expose them.
 */
export function summarizeOrderLedger(ledger: LedgerTransaction[]): OrderLedgerSummary {
  const kinds = new Set<string>();
  let postingCount = 0;
  let absolutePostingNgwee = 0;

  for (const txn of ledger) {
    kinds.add(txn.kind);
    for (const posting of txn.postings) {
      postingCount += 1;
      absolutePostingNgwee += Math.abs(posting.amount_ngwee);
    }
  }

  return {
    transactionCount: ledger.length,
    postingCount,
    absolutePostingNgwee,
    kinds: [...kinds].sort(),
  };
}

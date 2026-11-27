/** Shared 8-character order reference shown to sellers (matches returns, disputes, scan). */
export function formatOrderCode(orderId: string): string {
  const trimmed = orderId.trim();
  if (trimmed.length === 0) {
    return "";
  }
  return trimmed.replace(/-/g, "").slice(0, 8).toUpperCase();
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isFullOrderUuid(value: string): boolean {
  return UUID_RE.test(value.trim());
}

/** Normalize seller-entered order code: full UUID or 8-char prefix from the buyer. */
export function normalizeOrderLookupInput(value: string): string {
  return value.trim().replace(/\s+/g, "");
}

export type OrderIdCandidate = { id: string };

/**
 * Map short code or UUID to a single order id from the vendor's pickup-ready list.
 * Returns null when nothing matches or more than one order shares the prefix.
 */
export function resolveOrderIdFromInput(
  rawInput: string,
  candidates: OrderIdCandidate[],
): string | null {
  const input = normalizeOrderLookupInput(rawInput);
  if (!input) {
    return null;
  }
  if (isFullOrderUuid(input)) {
    return input.toLowerCase();
  }
  const compact = input.replace(/[^0-9a-f]/gi, "");
  if (compact.length < 8) {
    return null;
  }
  const short = compact.slice(0, 8).toLowerCase();
  const matches = candidates.filter((row) => {
    const rowCompact = row.id.replace(/-/g, "").toLowerCase();
    return rowCompact.startsWith(short) || formatOrderCode(row.id).toLowerCase() === short;
  });
  if (matches.length === 1) {
    return matches[0]?.id ?? null;
  }
  return null;
}

export function hasApprovedLiveListing(
  rows: Array<{ status: string; product_status?: string | null }>,
): boolean {
  return rows.some(
    (row) =>
      row.status === "active" &&
      row.product_status !== "pending_moderation" &&
      row.product_status !== "rejected",
  );
}

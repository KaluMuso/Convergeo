/**
 * Buyer pass-through platform fee. The rate (`platform_fee_bps`) comes from the events
 * API — the same constant the ticket purchase charges with — so the UI never
 * re-hard-codes it. Integer maths only (ngwee), floor-rounded like the server
 * (`(line_total * bps) // 10_000`).
 */
export function parsePlatformFeeBps(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= 10_000
    ? value
    : null;
}

export function buyerPlatformFeeNgwee(lineTotalNgwee: number, feeBps: number): number {
  if (lineTotalNgwee <= 0 || feeBps <= 0) {
    return 0;
  }
  return Math.floor((lineTotalNgwee * feeBps) / 10_000);
}

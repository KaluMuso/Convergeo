/**
 * M17-P08 — cost display helpers.
 *
 * Money arrives as integer micro-USD and is formatted for display here and
 * nowhere else. Doing the division at the render site is how one screen ends up
 * saying $1.50 while another says $1.5 for the same number.
 */

const MICROS_PER_USD = 1_000_000;

export function formatUsdMicros(micros: number): string {
  if (!Number.isFinite(micros) || micros < 0) {
    return "$0.00";
  }
  return `$${(micros / MICROS_PER_USD).toFixed(2)}`;
}

/** Whole-percent share of the cap consumed. A cap of 0 means "unbounded". */
export function spendPercent(spendMicros: number, capMicros: number): number {
  if (capMicros <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((spendMicros / capMicros) * 100));
}

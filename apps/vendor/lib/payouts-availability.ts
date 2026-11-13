/**
 * Whether the vendor Payouts screen shows live balances and payout history.
 *
 * Payout execution is disabled server-side by default (`PAYOUTS_ENABLED`, see
 * services/api/app/services/payouts/gate.py) and stays off for the Nov 2026
 * pilot. Until it is switched on, the vendor app must not show balances or
 * controls that imply money can be paid out — it explains the pilot instead.
 *
 * Fail closed: only an explicit `NEXT_PUBLIC_VENDOR_PAYOUTS_ENABLED=true` (or
 * `1`) at build time turns the live screen on. The literal env access is kept
 * so Next.js can inline it.
 */
export function isVendorPayoutsEnabled(
  raw: string | undefined = process.env.NEXT_PUBLIC_VENDOR_PAYOUTS_ENABLED,
): boolean {
  const value = raw?.trim().toLowerCase();
  return value === "true" || value === "1";
}

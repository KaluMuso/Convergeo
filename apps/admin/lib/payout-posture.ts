/**
 * Payout/refund posture for the console. The API kill switch (PAYOUTS_ENABLED,
 * default OFF) is a server env var that no admin endpoint exposes, so the
 * console mirrors it with NEXT_PUBLIC_VERGEO_PAYOUTS_ENABLED and FAILS CLOSED:
 * unless that is explicitly truthy, buttons that would send a customer refund
 * are not rendered. Set both together when payouts are switched on.
 */
const TRUTHY = new Set(["1", "true", "yes", "on"]);

export function parsePayoutsEnabled(raw: string | undefined | null): boolean {
  return TRUTHY.has((raw ?? "").trim().toLowerCase());
}

export function payoutsEnabled(): boolean {
  return parsePayoutsEnabled(process.env.NEXT_PUBLIC_VERGEO_PAYOUTS_ENABLED);
}

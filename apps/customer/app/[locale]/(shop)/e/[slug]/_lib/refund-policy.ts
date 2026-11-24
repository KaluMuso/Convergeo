/** Organiser-selected refund policy keys stored on `events.refund_policy_key`. */
export const EVENT_REFUND_POLICY_KEYS = ["platform_standard", "no_refunds", "flexible"] as const;

export type EventRefundPolicyKey = (typeof EVENT_REFUND_POLICY_KEYS)[number];

export function isKnownRefundPolicyKey(key: string): key is EventRefundPolicyKey {
  return (EVENT_REFUND_POLICY_KEYS as readonly string[]).includes(key);
}

/** i18n suffix under `events.detail.refund.{suffix}`. */
export function refundPolicyMessageKey(key: string | null | undefined): string {
  if (!key || !key.trim()) {
    return "unknown";
  }
  return isKnownRefundPolicyKey(key) ? key : "unknown";
}

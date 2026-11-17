import { ApiError, createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type PointsReason =
  | "order_completed"
  | "review"
  | "reversal"
  | "redeem"
  | "expire"
  | "admin_adjust";

export type PointsEntry = {
  id: string;
  points: number;
  reason: PointsReason;
  order_id: string | null;
  created_at: string;
};

export type PointsSummary = {
  enabled: boolean;
  balance: number;
  lifetime_earned: number;
  next_coupon_threshold: number;
  points_to_next: number;
  redeem_available: boolean;
  history: PointsEntry[];
};

/** `null` when the `loyalty_points` flag is off (API answers 404). */
export async function fetchPoints(accessToken: string): Promise<PointsSummary | null> {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => accessToken });
  try {
    return await client.request<PointsSummary>("/me/points");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Whole-percent progress toward the next coupon threshold, clamped to 0–100. */
export function progressPercent(balance: number, threshold: number): number {
  if (threshold <= 0) return 0;
  return Math.max(0, Math.min(100, Math.floor((balance * 100) / threshold)));
}

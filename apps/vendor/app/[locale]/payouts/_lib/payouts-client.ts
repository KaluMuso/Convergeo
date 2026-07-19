import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

export type PayoutBalances = {
  escrow_held_ngwee: number;
  released_available_ngwee: number;
  paid_out_ngwee: number;
  payouts_blocked: boolean;
  payout_hold_until: string | null;
  payout_msisdn: string | null;
  payout_rail: string | null;
};

export type PayoutHistoryItem = {
  id: string;
  amount_ngwee: number;
  rail: string;
  status: string;
  lenco_reference: string;
  created_at: string;
};

export type PayoutMethodChangePayload = {
  payout_msisdn: string;
  payout_rail: "mtn" | "airtel" | "zamtel";
  otp: string;
};

export type PayoutMethodChangeResult = {
  payout_msisdn: string;
  payout_rail: string;
  payout_hold_until: string;
  resolved_name: string | null;
  match_score: number;
  matched: boolean;
};

export function createPayoutsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    getBalances(): Promise<PayoutBalances> {
      return client.request<PayoutBalances>("/vendor/payouts");
    },

    getHistory(): Promise<{ items: PayoutHistoryItem[] }> {
      return client.request<{ items: PayoutHistoryItem[] }>("/vendor/payouts/history");
    },

    async downloadStatement(month: string): Promise<Blob> {
      const baseUrl = getApiBaseUrl().replace(/\/$/, "");
      const token = await getToken();
      const response = await fetch(
        `${baseUrl}/vendor/payouts/statement?month=${encodeURIComponent(month)}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      if (!response.ok) {
        throw new Error("statement_download_failed");
      }
      return response.blob();
    },

    changeMethod(payload: PayoutMethodChangePayload): Promise<PayoutMethodChangeResult> {
      return client.request<PayoutMethodChangeResult>("/vendor/payouts/method", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
  };
}

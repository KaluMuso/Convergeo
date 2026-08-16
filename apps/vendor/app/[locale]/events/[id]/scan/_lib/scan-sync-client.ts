import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

import type { BatchScanResult, BatchSubmitScan, ScanSyncResponse } from "./offline-store";

type BatchVerifyResponse = {
  results: BatchScanResult[];
};

export function createScanSyncClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });

  return {
    /** GET /events/{eventId}/instances/{instanceId}/scan-sync -- window sigs only, never the secret. */
    getScanSync(eventId: string, instanceId: string): Promise<ScanSyncResponse> {
      return client.request<ScanSyncResponse>(
        `/events/${eventId}/instances/${instanceId}/scan-sync`,
      );
    },

    /**
     * POST /tickets/verify/batch -- the same merged endpoint the online
     * verify flow uses. Reused verbatim to reconcile the offline queue so
     * first-scan-wins resolution always happens server-side.
     */
    async verifyBatch(
      eventId: string,
      instanceId: string,
      scans: BatchSubmitScan[],
    ): Promise<BatchScanResult[]> {
      const response = await client.request<BatchVerifyResponse>("/tickets/verify/batch", {
        method: "POST",
        body: JSON.stringify({ event_id: eventId, instance_id: instanceId, scans }),
      });
      return response.results;
    },

    overrideCheckIn(body: {
      ticket_id: string;
      event_id: string;
      instance_id: string;
      reason: string;
    }): Promise<{ ticket_id: string; to_status: string }> {
      return client.request<{ ticket_id: string; to_status: string }>("/tickets/verify/override", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  };
}

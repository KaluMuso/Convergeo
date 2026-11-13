import { createApiClient } from "@vergeo/config";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

import type { BatchScanResult, BatchSubmitScan, ScanSyncResponse } from "./offline-store";

type BatchVerifyResponse = {
  results: BatchScanResult[];
};

/** Mirrors `VerifyTicketResponse` in services/api/app/routers/ticket_verify.py. */
export type VerifyTicketResponse = {
  ticket_id: string;
  from_status: string;
  to_status: string;
  checked_in_at: string;
  event_id: string;
  instance_id: string;
  holder_name: string | null;
  ticket_type_name: string;
  event_title?: string;
  id_check_required?: boolean;
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

    /**
     * POST /tickets/verify -- the single-ticket manual (PIN) fallback.
     *
     * The PIN is never checkable on the device: `scan-sync` ships
     * `pin_hash_present` but never the hash, so this always round-trips to the
     * server, which re-runs the full SCAN_ROLES authorization check and the
     * atomic single-use `issued -> checked_in` claim.
     */
    verifyManualPin(body: {
      ticket_id: string;
      event_id: string;
      instance_id: string | null;
      pin: string;
    }): Promise<VerifyTicketResponse> {
      return client.request<VerifyTicketResponse>("/tickets/verify", {
        method: "POST",
        body: JSON.stringify({
          ticket_id: body.ticket_id,
          event_id: body.event_id,
          ...(body.instance_id ? { instance_id: body.instance_id } : {}),
          pin: body.pin,
        }),
      });
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

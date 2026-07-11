import { describe, expect, it } from "vitest";

import {
  buildSyncedTicketCache,
  createMemoryBackend,
  OfflineScanStore,
  parseScanCode,
  reconcilePendingWithResults,
  validateOfflineScan,
  type BatchScanResult,
  type BatchSubmitScan,
  type PendingScan,
  type ScanSyncResponse,
} from "./offline-store";

const HORIZON_START = 1_000_000;
const HORIZON_END = 1_000_010; // 11 windows, indices 0..10
const WINDOW_MS = 60_000;

function windowToMs(window: number): number {
  return window * WINDOW_MS;
}

function fixtureSync(overrides: Partial<ScanSyncResponse> = {}): ScanSyncResponse {
  const windowSigs = Array.from(
    { length: HORIZON_END - HORIZON_START + 1 },
    (_, i) => `sig-${HORIZON_START + i}`,
  );
  return {
    event_id: "event-1",
    instance_id: "instance-1",
    starts_at: "2026-08-01T18:00:00Z",
    window_seconds: 60,
    horizon_start_window: HORIZON_START,
    horizon_end_window: HORIZON_END,
    tickets: [{ ticket_id: "ticket-a", window_sigs: windowSigs, pin_hash_present: true }],
    ...overrides,
  };
}

function codeFor(ticketId: string, window: number, sig: string): string {
  return `${ticketId}:${window}:${sig}`;
}

describe("parseScanCode", () => {
  it("parses the ticketId:window:sig shape build_qr_code emits", () => {
    expect(parseScanCode("ticket-a:1000000:sig-1000000")).toEqual({
      ticketId: "ticket-a",
      window: 1_000_000,
      sig: "sig-1000000",
    });
  });

  it("trims surrounding whitespace", () => {
    expect(parseScanCode("  ticket-a:1000000:sig-1000000  ")).toEqual({
      ticketId: "ticket-a",
      window: 1_000_000,
      sig: "sig-1000000",
    });
  });

  it.each([["not-a-code"], ["a:b"], ["a:b:c:d"], ["a::sig"], ["a:notanumber:sig"], [":1:sig"]])(
    "rejects malformed code %s",
    (raw) => {
      expect(parseScanCode(raw)).toBeNull();
    },
  );
});

describe("validateOfflineScan", () => {
  const payload = fixtureSync();
  const cache = buildSyncedTicketCache(payload);

  it("accepts a scan whose sig matches the cached window exactly", () => {
    const nowMs = windowToMs(1_000_005);
    const result = validateOfflineScan(
      cache,
      { ticketId: "ticket-a", window: 1_000_005, sig: "sig-1000005" },
      nowMs,
    );
    expect(result.outcome).toBe("valid");
  });

  it("rejects an unknown ticket id", () => {
    const nowMs = windowToMs(1_000_005);
    const result = validateOfflineScan(
      cache,
      { ticketId: "ticket-z", window: 1_000_005, sig: "sig-1000005" },
      nowMs,
    );
    expect(result.outcome).toBe("unknown_ticket");
  });

  it("rejects a window more than +/-1 away from the device clock (stale)", () => {
    const nowMs = windowToMs(1_000_005);
    const result = validateOfflineScan(
      cache,
      { ticketId: "ticket-a", window: 1_000_002, sig: "sig-1000002" },
      nowMs,
    );
    expect(result.outcome).toBe("stale_window");
  });

  it("rejects a window inside the freshness tolerance but outside the synced horizon", () => {
    // 1_000_011 is one past HORIZON_END -- not in the cached array.
    const nowMs = windowToMs(1_000_011);
    const result = validateOfflineScan(
      cache,
      { ticketId: "ticket-a", window: 1_000_011, sig: "whatever" },
      nowMs,
    );
    expect(result.outcome).toBe("not_synced");
  });

  it("rejects a sig that does not match the cached sig for that window", () => {
    const nowMs = windowToMs(1_000_005);
    const result = validateOfflineScan(
      cache,
      { ticketId: "ticket-a", window: 1_000_005, sig: "forged-sig" },
      nowMs,
    );
    expect(result.outcome).toBe("invalid_sig");
  });

  it("still validates when the scanning device's clock is skewed by up to 60s (+/-1 window)", () => {
    const trueWindow = 1_000_005;
    const scan = { ticketId: "ticket-a", window: trueWindow, sig: `sig-${trueWindow}` };

    // Device clock 60s fast.
    const fastResult = validateOfflineScan(cache, scan, windowToMs(trueWindow + 1));
    expect(fastResult.outcome).toBe("valid");

    // Device clock 60s slow.
    const slowResult = validateOfflineScan(cache, scan, windowToMs(trueWindow - 1));
    expect(slowResult.outcome).toBe("valid");

    // Device clock 120s off -- outside tolerance, must fail.
    const tooSkewedResult = validateOfflineScan(cache, scan, windowToMs(trueWindow + 2));
    expect(tooSkewedResult.outcome).toBe("stale_window");
  });
});

describe("reconcilePendingWithResults", () => {
  it("maps checked_in / already_checked_in / duplicate / rejected onto local statuses", () => {
    const pending: PendingScan[] = [
      {
        id: "1",
        ticketId: "a",
        window: 1,
        sig: "s",
        code: "a:1:s",
        scannedAt: "t1",
        status: "pending",
      },
      {
        id: "2",
        ticketId: "b",
        window: 1,
        sig: "s",
        code: "b:1:s",
        scannedAt: "t2",
        status: "pending",
      },
      {
        id: "3",
        ticketId: "c",
        window: 1,
        sig: "s",
        code: "c:1:s",
        scannedAt: "t3",
        status: "pending",
      },
      {
        id: "4",
        ticketId: "d",
        window: 1,
        sig: "s",
        code: "d:1:s",
        scannedAt: "t4",
        status: "pending",
      },
    ];
    const results: BatchScanResult[] = [
      { ticket_id: "a", scanned_at: "t1", outcome: "checked_in" },
      { ticket_id: "b", scanned_at: "t2", outcome: "already_checked_in", error_code: null },
      {
        ticket_id: "c",
        scanned_at: "t3",
        outcome: "duplicate",
        error_code: "ticket_duplicate_scan",
      },
      { ticket_id: "d", scanned_at: "t4", outcome: "rejected", error_code: "ticket_qr_stale" },
    ];

    const reconciled = reconcilePendingWithResults(pending, results);
    expect(reconciled.map((r) => r.status)).toEqual(["synced", "conflict", "conflict", "rejected"]);
    expect(reconciled[3]?.errorCode).toBe("ticket_qr_stale");
  });
});

describe("OfflineScanStore offline validate/queue/sync cycle", () => {
  it("enqueues a valid offline scan and rejects an invalid one", async () => {
    const store = new OfflineScanStore(createMemoryBackend());
    await store.hydrate();
    await store.syncFromServer(fixtureSync());

    const nowMs = windowToMs(1_000_005);
    const validCode = codeFor("ticket-a", 1_000_005, "sig-1000005");
    const accepted = await store.enqueueScan(validCode, nowMs);
    expect(accepted).toEqual({
      accepted: true,
      scan: expect.objectContaining({ ticketId: "ticket-a", status: "pending" }),
    });
    expect(store.pendingCount).toBe(1);

    const forgedCode = codeFor("ticket-a", 1_000_005, "forged");
    const rejected = await store.enqueueScan(forgedCode, nowMs);
    expect(rejected).toEqual({ accepted: false, outcome: "invalid_sig" });
    // The rejected scan must not be queued.
    expect(store.pendingCount).toBe(1);
  });

  it("reconciles a queued scan against the injected batch-verify submit function", async () => {
    const store = new OfflineScanStore(createMemoryBackend());
    await store.hydrate();
    await store.syncFromServer(fixtureSync());

    const nowMs = windowToMs(1_000_005);
    await store.enqueueScan(codeFor("ticket-a", 1_000_005, "sig-1000005"), nowMs);
    expect(store.pendingCount).toBe(1);

    const submit = async (scans: BatchSubmitScan[]): Promise<BatchScanResult[]> =>
      scans.map((scan) => ({
        ticket_id: scan.ticket_id,
        scanned_at: scan.scanned_at,
        outcome: "checked_in" as const,
        from_status: "issued",
      }));

    const summary = await store.reconcile(submit);
    expect(summary).toEqual({ synced: 1, conflict: 0, rejected: 0 });
    expect(store.pendingCount).toBe(0);
    expect(store.syncedCount).toBe(1);
    expect(store.queueSnapshot[0]?.status).toBe("synced");
  });

  it("persists the synced cache and pending queue across a reload (same backend, new store instance)", async () => {
    const backend = createMemoryBackend();
    const before = new OfflineScanStore(backend);
    await before.hydrate();
    await before.syncFromServer(fixtureSync());
    const nowMs = windowToMs(1_000_005);
    await before.enqueueScan(codeFor("ticket-a", 1_000_005, "sig-1000005"), nowMs);

    // Simulate an app restart: a fresh store instance over the same
    // persisted backend must see the same synced data + pending queue.
    const after = new OfflineScanStore(backend);
    await after.hydrate();
    expect(after.lastSync?.event_id).toBe("event-1");
    expect(after.pendingCount).toBe(1);
    expect(after.queueSnapshot[0]?.ticketId).toBe("ticket-a");
  });
});

describe("first-scan-wins across two devices", () => {
  function createFakeServer() {
    const ticketStatus = new Map<string, "issued" | "checked_in">();
    return {
      async verifyBatch(scans: BatchSubmitScan[]): Promise<BatchScanResult[]> {
        return scans.map((scan) => {
          const status = ticketStatus.get(scan.ticket_id) ?? "issued";
          if (status === "checked_in") {
            return {
              ticket_id: scan.ticket_id,
              scanned_at: scan.scanned_at,
              outcome: "already_checked_in" as const,
              from_status: "checked_in",
            };
          }
          ticketStatus.set(scan.ticket_id, "checked_in");
          return {
            ticket_id: scan.ticket_id,
            scanned_at: scan.scanned_at,
            outcome: "checked_in" as const,
            from_status: "issued",
          };
        });
      },
    };
  }

  it("checks in on the first device's reconcile and flags the second device's as a conflict", async () => {
    const payload = fixtureSync();
    const nowMs = windowToMs(1_000_005);
    const code = codeFor("ticket-a", 1_000_005, "sig-1000005");
    const server = createFakeServer();

    const deviceA = new OfflineScanStore(createMemoryBackend());
    await deviceA.hydrate();
    await deviceA.syncFromServer(payload);
    await deviceA.enqueueScan(code, nowMs);

    const deviceB = new OfflineScanStore(createMemoryBackend());
    await deviceB.hydrate();
    await deviceB.syncFromServer(payload);
    await deviceB.enqueueScan(code, nowMs + 5_000);

    // Device A reconciles first (e.g. it regained connectivity first).
    const summaryA = await deviceA.reconcile((scans) => server.verifyBatch(scans));
    expect(summaryA).toEqual({ synced: 1, conflict: 0, rejected: 0 });
    expect(deviceA.queueSnapshot[0]?.status).toBe("synced");

    // Device B reconciles against the now-updated shared server state.
    const summaryB = await deviceB.reconcile((scans) => server.verifyBatch(scans));
    expect(summaryB).toEqual({ synced: 0, conflict: 1, rejected: 0 });
    expect(deviceB.queueSnapshot[0]?.status).toBe("conflict");
  });
});

/**
 * Offline-first cache + pending check-in queue for the organiser scanner.
 *
 * Design: the noisy, hard-to-unit-test bit (IndexedDB) is isolated behind a
 * tiny `OfflineScanBackend` interface with two implementations -- a real
 * IndexedDB-backed one for the browser, and an in-memory one for tests/SSR.
 * All the actual logic (window-sig parity check, +/-1 skew tolerance,
 * first-scan-wins reconcile) lives in plain, backend-agnostic functions so it
 * can be exercised directly in vitest without a DOM IndexedDB polyfill.
 *
 * The window-sig math here must stay byte-for-byte compatible with
 * `services/api/app/routers/ticket_verify.py` (current_window / window_sig /
 * +/-1 tolerance) -- this module never computes a sig itself, it only
 * compares a scanned sig against the ones the server already derived and
 * shipped down via `/events/{id}/instances/{id}/scan-sync`.
 */

// ---------------------------------------------------------------------------
// Wire types (mirror services/api/app/routers/ticket_scan_sync.py + ticket_verify.py)
// ---------------------------------------------------------------------------

export type ScanSyncTicket = {
  ticket_id: string;
  window_sigs: string[];
  pin_hash_present: boolean;
};

export type ScanSyncResponse = {
  event_id: string;
  instance_id: string;
  starts_at: string;
  window_seconds: number;
  horizon_start_window: number;
  horizon_end_window: number;
  tickets: ScanSyncTicket[];
};

export type BatchOutcome = "checked_in" | "duplicate" | "rejected" | "already_checked_in";

export type BatchScanResult = {
  ticket_id: string;
  scanned_at: string;
  outcome: BatchOutcome;
  from_status?: string | null;
  checked_in_at?: string | null;
  error_code?: string | null;
};

export type BatchSubmitScan = {
  ticket_id: string;
  code: string;
  scanned_at: string;
};

// ---------------------------------------------------------------------------
// Local (device) types
// ---------------------------------------------------------------------------

export type SyncedTicketCacheEntry = {
  windowSigs: string[];
  horizonStartWindow: number;
  pinHashPresent: boolean;
};

export type SyncedTicketCache = Map<string, SyncedTicketCacheEntry>;

export type ParsedScanCode = {
  ticketId: string;
  window: number;
  sig: string;
};

export type OfflineValidationOutcome =
  "valid" | "unknown_ticket" | "stale_window" | "not_synced" | "invalid_sig";

export type OfflineValidation = { outcome: OfflineValidationOutcome };

export type PendingScanStatus = "pending" | "synced" | "conflict" | "rejected";

export type PendingScan = {
  id: string;
  ticketId: string;
  window: number;
  sig: string;
  code: string;
  scannedAt: string;
  status: PendingScanStatus;
  errorCode?: string;
};

// Matches ticket_verify._WINDOW_TOLERANCE (+/-1 window == +/-60s at 60s windows).
const WINDOW_TOLERANCE = 1;

// ---------------------------------------------------------------------------
// Pure functions -- unit-testable without any storage backend
// ---------------------------------------------------------------------------

export function buildSyncedTicketCache(payload: ScanSyncResponse): SyncedTicketCache {
  const cache: SyncedTicketCache = new Map();
  for (const ticket of payload.tickets) {
    cache.set(ticket.ticket_id, {
      windowSigs: ticket.window_sigs,
      horizonStartWindow: payload.horizon_start_window,
      pinHashPresent: ticket.pin_hash_present,
    });
  }
  return cache;
}

/** Parses `${ticketId}:${window}:${sig}` -- the exact shape build_qr_code emits. */
export function parseScanCode(raw: string): ParsedScanCode | null {
  const cleaned = raw.trim();
  const parts = cleaned.split(":");
  if (parts.length !== 3) {
    return null;
  }
  const ticketId = parts[0];
  const windowRaw = parts[1];
  const sig = parts[2];
  if (!ticketId || !windowRaw || !sig) {
    return null;
  }
  if (!/^-?\d+$/.test(windowRaw)) {
    return null;
  }
  const window = Number.parseInt(windowRaw, 10);
  return { ticketId, window, sig };
}

export function currentWindow(nowMs: number = Date.now()): number {
  return Math.floor(nowMs / 1000 / 60);
}

/**
 * Validates a scanned {ticketId, window, sig} against the synced cache.
 *
 * Two checks, mirroring the server exactly:
 *  1. Freshness: the code's embedded window must be within +/-1 window of
 *     this device's own clock (tolerates up to ~60s of device clock skew).
 *  2. Authenticity: the sig must match the cached sig for that exact window
 *     (the cached sig was itself HMAC'd server-side from the real qr_secret,
 *     so a match here is equivalent to the server's assert_window_sig check).
 */
export function validateOfflineScan(
  cache: SyncedTicketCache,
  scan: ParsedScanCode,
  nowMs: number = Date.now(),
): OfflineValidation {
  const deviceNowWindow = currentWindow(nowMs);
  if (Math.abs(scan.window - deviceNowWindow) > WINDOW_TOLERANCE) {
    return { outcome: "stale_window" };
  }

  const entry = cache.get(scan.ticketId);
  if (!entry) {
    return { outcome: "unknown_ticket" };
  }

  const index = scan.window - entry.horizonStartWindow;
  if (index < 0 || index >= entry.windowSigs.length) {
    return { outcome: "not_synced" };
  }

  if (entry.windowSigs[index] !== scan.sig) {
    return { outcome: "invalid_sig" };
  }

  return { outcome: "valid" };
}

/**
 * Applies server reconcile results back onto the (index-aligned) pending
 * subset that was submitted. `verify_batch_scans` preserves request order in
 * its response, so zipping by index is safe and avoids needing a secondary
 * key. First-scan-wins: only one queued scan per ticket can land
 * outcome "checked_in"; any other queued scan of the same ticket becomes a
 * "conflict" (duplicate), regardless of which device queued it first.
 */
export function reconcilePendingWithResults(
  submitted: PendingScan[],
  results: BatchScanResult[],
): PendingScan[] {
  return submitted.map((pending, index) => {
    const result = results[index];
    if (!result) {
      return pending;
    }
    if (result.outcome === "checked_in") {
      return { ...pending, status: "synced" as const, errorCode: undefined };
    }
    if (result.outcome === "already_checked_in" || result.outcome === "duplicate") {
      return { ...pending, status: "conflict" as const, errorCode: result.error_code ?? undefined };
    }
    return { ...pending, status: "rejected" as const, errorCode: result.error_code ?? undefined };
  });
}

function makeLocalId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---------------------------------------------------------------------------
// Storage backend abstraction
// ---------------------------------------------------------------------------

export interface OfflineScanBackend {
  loadSync(): Promise<ScanSyncResponse | null>;
  saveSync(payload: ScanSyncResponse): Promise<void>;
  loadQueue(): Promise<PendingScan[]>;
  saveQueue(queue: PendingScan[]): Promise<void>;
}

/** In-memory backend -- used by tests and as a safe SSR/no-IndexedDB fallback. */
export function createMemoryBackend(): OfflineScanBackend {
  let sync: ScanSyncResponse | null = null;
  let queue: PendingScan[] = [];
  return {
    async loadSync() {
      return sync;
    },
    async saveSync(payload: ScanSyncResponse) {
      sync = payload;
    },
    async loadQueue() {
      return queue;
    },
    async saveQueue(next: PendingScan[]) {
      queue = next;
    },
  };
}

const DB_NAME = "vergeo5-vendor-scan-sync";
const DB_VERSION = 1;
const STORE_SYNC = "sync";
const STORE_QUEUE = "queue";
const RECORD_KEY = "latest";

function hasIndexedDb(): boolean {
  return typeof indexedDB !== "undefined";
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_SYNC)) {
        db.createObjectStore(STORE_SYNC);
      }
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        db.createObjectStore(STORE_QUEUE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function idbGet<T>(storeName: string): Promise<T | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readonly");
    const request = tx.objectStore(storeName).get(RECORD_KEY);
    request.onsuccess = () => resolve(request.result as T | undefined);
    request.onerror = () => reject(request.error);
  });
}

async function idbPut(storeName: string, value: unknown): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    tx.objectStore(storeName).put(value, RECORD_KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/** Real IndexedDB-backed persistence -- survives reload/app-restart while offline. */
export function createIndexedDbBackend(): OfflineScanBackend {
  return {
    async loadSync() {
      if (!hasIndexedDb()) {
        return null;
      }
      const value = await idbGet<ScanSyncResponse>(STORE_SYNC);
      return value ?? null;
    },
    async saveSync(payload: ScanSyncResponse) {
      if (!hasIndexedDb()) {
        return;
      }
      await idbPut(STORE_SYNC, payload);
    },
    async loadQueue() {
      if (!hasIndexedDb()) {
        return [];
      }
      const value = await idbGet<PendingScan[]>(STORE_QUEUE);
      return value ?? [];
    },
    async saveQueue(queue: PendingScan[]) {
      if (!hasIndexedDb()) {
        return;
      }
      await idbPut(STORE_QUEUE, queue);
    },
  };
}

// ---------------------------------------------------------------------------
// High-level store -- wires backend + pure functions + an in-memory read cache
// ---------------------------------------------------------------------------

export type EnqueueResult =
  { accepted: true; scan: PendingScan } | { accepted: false; outcome: OfflineValidationOutcome };

export class OfflineScanStore {
  private readonly backend: OfflineScanBackend;
  private sync: ScanSyncResponse | null = null;
  private cache: SyncedTicketCache = new Map();
  private queue: PendingScan[] = [];
  private hydrated = false;

  constructor(backend: OfflineScanBackend = createIndexedDbBackend()) {
    this.backend = backend;
  }

  async hydrate(): Promise<void> {
    this.sync = await this.backend.loadSync();
    this.cache = this.sync ? buildSyncedTicketCache(this.sync) : new Map();
    this.queue = await this.backend.loadQueue();
    this.hydrated = true;
  }

  private ensureHydrated(): void {
    if (!this.hydrated) {
      throw new Error("OfflineScanStore.hydrate() must be called before use");
    }
  }

  get lastSync(): ScanSyncResponse | null {
    return this.sync;
  }

  get queueSnapshot(): PendingScan[] {
    return this.queue.slice();
  }

  get pendingCount(): number {
    return this.queue.filter((item) => item.status === "pending").length;
  }

  get syncedCount(): number {
    return this.queue.filter((item) => item.status === "synced").length;
  }

  async syncFromServer(payload: ScanSyncResponse): Promise<void> {
    this.sync = payload;
    this.cache = buildSyncedTicketCache(payload);
    await this.backend.saveSync(payload);
  }

  /** Validates a raw scanned code against the cached horizon without queueing it. */
  validate(
    raw: string,
    nowMs: number = Date.now(),
  ): { parsed: ParsedScanCode | null; validation: OfflineValidation } {
    const parsed = parseScanCode(raw);
    if (!parsed) {
      return { parsed: null, validation: { outcome: "unknown_ticket" } };
    }
    return { parsed, validation: validateOfflineScan(this.cache, parsed, nowMs) };
  }

  /** Validates and, if valid, appends a pending check-in to the persisted queue. */
  async enqueueScan(raw: string, nowMs: number = Date.now()): Promise<EnqueueResult> {
    this.ensureHydrated();
    const { parsed, validation } = this.validate(raw, nowMs);
    if (!parsed || validation.outcome !== "valid") {
      return { accepted: false, outcome: validation.outcome };
    }

    const scan: PendingScan = {
      id: makeLocalId(),
      ticketId: parsed.ticketId,
      window: parsed.window,
      sig: parsed.sig,
      code: raw.trim(),
      scannedAt: new Date(nowMs).toISOString(),
      status: "pending",
    };
    this.queue = [...this.queue, scan];
    await this.backend.saveQueue(this.queue);
    return { accepted: true, scan };
  }

  /**
   * Submits every still-pending scan to the server (via the injected
   * `submit`, which callers wire to POST /tickets/verify/batch) and merges
   * the outcomes back onto the queue. Reuses the merged batch-verify
   * endpoint's first-scan-wins semantics -- this store never re-derives a
   * check-in decision itself once online.
   */
  async reconcile(
    submit: (scans: BatchSubmitScan[]) => Promise<BatchScanResult[]>,
  ): Promise<{ synced: number; conflict: number; rejected: number }> {
    this.ensureHydrated();
    const pending = this.queue.filter((item) => item.status === "pending");
    if (pending.length === 0) {
      return { synced: 0, conflict: 0, rejected: 0 };
    }

    const results = await submit(
      pending.map((item) => ({
        ticket_id: item.ticketId,
        code: item.code,
        scanned_at: item.scannedAt,
      })),
    );
    const reconciled = reconcilePendingWithResults(pending, results);

    const byId = new Map(reconciled.map((item) => [item.id, item]));
    this.queue = this.queue.map((item) => byId.get(item.id) ?? item);
    await this.backend.saveQueue(this.queue);

    let synced = 0;
    let conflict = 0;
    let rejected = 0;
    for (const item of reconciled) {
      if (item.status === "synced") synced += 1;
      else if (item.status === "conflict") conflict += 1;
      else if (item.status === "rejected") rejected += 1;
    }
    return { synced, conflict, rejected };
  }
}

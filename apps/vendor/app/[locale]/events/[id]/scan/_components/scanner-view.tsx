"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Select, Spinner } from "../../../../listings/new/_lib/ui";
// Reused, unmodified, from the order-pickup scanner feature.
import { useOnline } from "../../../../scan/_lib/use-online";
import { createEventsClient, type EventInstance } from "../../../_lib/events-client";
import {
  createIndexedDbBackend,
  OfflineScanStore,
  type OfflineValidationOutcome,
} from "../_lib/offline-store";
import { createScanSyncClient } from "../_lib/scan-sync-client";

import { CameraScanner } from "./camera-scanner";
import { OfflineBanner } from "./offline-banner";
import { RecentScans, type RecentScanItem, type RecentScanStatus } from "./recent-scans";
import { ScanCount } from "./scan-count";
import { ScanResultFlash, type ScanResultKind, type ScanResultState } from "./scan-result-flash";

type ScannerViewProps = {
  eventId: string;
};

function pickDefaultInstance(instances: EventInstance[]): EventInstance | null {
  if (instances.length === 0) {
    return null;
  }
  const now = Date.now();
  const upcoming = instances
    .filter((instance) => new Date(instance.starts_at).getTime() >= now - 12 * 60 * 60 * 1000)
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
  return upcoming[0] ?? instances[0] ?? null;
}

function outcomeToResultKind(outcome: OfflineValidationOutcome): ScanResultKind {
  switch (outcome) {
    case "unknown_ticket":
      return "unknown_ticket";
    case "stale_window":
      return "stale_window";
    case "not_synced":
      return "not_synced";
    case "invalid_sig":
      return "invalid_sig";
    default:
      return "invalid_format";
  }
}

export function ScannerView({ eventId }: ScannerViewProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const online = useOnline();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const eventsClient = useMemo(() => createEventsClient(getToken), [getToken]);
  const scanSyncClient = useMemo(() => createScanSyncClient(getToken), [getToken]);
  const store = useMemo(() => new OfflineScanStore(createIndexedDbBackend()), []);

  const [instances, setInstances] = useState<EventInstance[]>([]);
  const [instanceId, setInstanceId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingEvent, setLoadingEvent] = useState(true);
  const [storeReady, setStoreReady] = useState(false);

  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncedTicketCount, setSyncedTicketCount] = useState<number | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  const [cameraDenied, setCameraDenied] = useState(false);
  const [resultState, setResultState] = useState<ScanResultState>({ kind: "idle" });
  const [checkedInCount, setCheckedInCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [recent, setRecent] = useState<RecentScanItem[]>([]);
  const busyRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    void store.hydrate().then(() => {
      if (cancelled) return;
      setStoreReady(true);
      setPendingCount(store.pendingCount);
      setCheckedInCount(store.syncedCount);
    });
    return () => {
      cancelled = true;
    };
  }, [store]);

  useEffect(() => {
    if (sessionLoading || !session) {
      return;
    }
    let cancelled = false;
    setLoadingEvent(true);
    setLoadError(null);
    eventsClient
      .getEvent(eventId)
      .then(({ event }) => {
        if (cancelled) return;
        setInstances(event.instances);
        setInstanceId((current) => current ?? pickDefaultInstance(event.instances)?.id ?? null);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError(t("scan.eventCheckIn.errors.loadEventFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingEvent(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [eventId, eventsClient, session, sessionLoading, t]);

  const runSync = useCallback(async () => {
    if (!instanceId || !online) {
      return;
    }
    setSyncing(true);
    setSyncError(null);
    try {
      const payload = await scanSyncClient.getScanSync(eventId, instanceId);
      await store.syncFromServer(payload);
      setSyncedTicketCount(payload.tickets.length);
      setLastSyncedAt(new Date().toISOString());
    } catch {
      setSyncError(t("scan.eventCheckIn.sync.error"));
    } finally {
      setSyncing(false);
    }
  }, [eventId, instanceId, online, scanSyncClient, store, t]);

  // Only auto-sync once per instance selection -- subsequent syncs are
  // manual (button) to avoid burning mobile data mid check-in. `runSync`
  // is intentionally omitted from the deps array for that reason.
  useEffect(() => {
    if (storeReady && instanceId && online) {
      void runSync();
    }
  }, [storeReady, instanceId]);

  const attemptReconcile = useCallback(async () => {
    if (!online) {
      return;
    }
    try {
      const summary = await store.reconcile((scans) => scanSyncClient.verifyBatch(scans));
      if (summary.synced > 0 || summary.conflict > 0 || summary.rejected > 0) {
        setCheckedInCount(store.syncedCount);
        setPendingCount(store.pendingCount);
        setRecent((current) =>
          current.map((item) => {
            const match = store.queueSnapshot.find(
              (q) => q.ticketId === item.ticketId && q.scannedAt === item.scannedAt,
            );
            if (!match) return item;
            const status: RecentScanStatus =
              match.status === "synced"
                ? "checked_in"
                : match.status === "conflict"
                  ? "conflict"
                  : match.status === "rejected"
                    ? "rejected"
                    : "pending";
            return { ...item, status };
          }),
        );
      }
    } catch {
      // Reconcile failures just leave items pending; they retry next time
      // the device is online (e.g. next successful scan or manual sync).
    }
  }, [online, scanSyncClient, store]);

  // Fires once when connectivity is (re)gained -- `attemptReconcile` is
  // intentionally omitted from the deps array since it is deliberately not
  // meant to re-run on every render (only on online/storeReady transitions).
  useEffect(() => {
    if (online && storeReady && store.pendingCount > 0) {
      void attemptReconcile();
    }
  }, [online, storeReady]);

  const handleCodeDetected = useCallback(
    (raw: string) => {
      if (busyRef.current || !storeReady) {
        return;
      }
      busyRef.current = true;
      void (async () => {
        try {
          const { parsed, validation } = store.validate(raw);
          if (!parsed) {
            setResultState({ kind: "invalid_format", ticketId: null });
            return;
          }
          if (validation.outcome !== "valid") {
            setResultState({
              kind: outcomeToResultKind(validation.outcome),
              ticketId: parsed.ticketId,
            });
            return;
          }

          const enqueued = await store.enqueueScan(raw);
          if (!enqueued.accepted) {
            setResultState({
              kind: outcomeToResultKind(enqueued.outcome),
              ticketId: parsed.ticketId,
            });
            return;
          }

          setPendingCount(store.pendingCount);
          setRecent((current) =>
            [
              {
                ticketId: parsed.ticketId,
                scannedAt: enqueued.scan.scannedAt,
                status: "pending" as RecentScanStatus,
              },
              ...current,
            ].slice(0, 12),
          );
          setResultState({ kind: online ? "valid" : "queued", ticketId: parsed.ticketId });

          if (online) {
            await attemptReconcile();
          }
        } finally {
          busyRef.current = false;
        }
      })();
    },
    [attemptReconcile, online, storeReady, store],
  );

  const handleCameraDenied = useCallback(() => setCameraDenied(true), []);
  const dismissResult = useCallback(() => setResultState({ kind: "idle" }), []);

  if (sessionLoading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "var(--sp-8)" }}>
        <Spinner label={t("scan.eventCheckIn.title")} />
      </div>
    );
  }

  if (!session) {
    return (
      <p style={{ color: "var(--text-2)", fontSize: "var(--fs-small)" }}>
        {t("scan.eventCheckIn.errors.unauthorized")}
      </p>
    );
  }

  if (loadingEvent) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "var(--sp-8)" }}>
        <Spinner label={t("scan.eventCheckIn.title")} />
      </div>
    );
  }

  if (loadError) {
    return (
      <p role="alert" style={{ color: "var(--danger)", fontSize: "var(--fs-small)" }}>
        {loadError}
      </p>
    );
  }

  if (instances.length === 0) {
    return (
      <p style={{ color: "var(--text-2)", fontSize: "var(--fs-small)" }}>
        {t("scan.eventCheckIn.errors.noInstances")}
      </p>
    );
  }

  const showScanner = resultState.kind === "idle";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <header>
        <p
          style={{
            margin: 0,
            fontSize: "var(--fs-small)",
            color: "var(--text-3)",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          {t("scan.eventCheckIn.eyebrow")}
        </p>
        <h1 style={{ margin: "var(--sp-1) 0", fontFamily: "var(--font-display)" }}>
          {t("scan.eventCheckIn.title")}
        </h1>
        <p style={{ margin: 0, color: "var(--text-2)", fontSize: "var(--fs-small)" }}>
          {t("scan.eventCheckIn.intro")}
        </p>
      </header>

      {instances.length > 1 ? (
        <label style={{ display: "flex", flexDirection: "column", gap: "var(--sp-1)" }}>
          <span style={{ fontSize: "var(--fs-small)", color: "var(--text-2)" }}>
            {t("scan.eventCheckIn.instanceLabel")}
          </span>
          <Select value={instanceId ?? ""} onChange={(event) => setInstanceId(event.target.value)}>
            {instances.map((instance) => (
              <option key={instance.id} value={instance.id}>
                {new Date(instance.starts_at).toLocaleString()}
              </option>
            ))}
          </Select>
        </label>
      ) : null}

      <ScanCount checkedInCount={checkedInCount} pendingCount={pendingCount} />

      {!online ? <OfflineBanner lastSyncedAt={lastSyncedAt} /> : null}

      {online ? (
        <button
          type="button"
          data-testid="event-scan-sync-button"
          onClick={() => void runSync()}
          disabled={syncing}
          style={{
            minHeight: "2.75rem",
            border: "1px solid var(--border)",
            borderRadius: "var(--r)",
            background: "var(--surface)",
            color: "var(--primary)",
            fontWeight: 600,
            cursor: syncing ? "default" : "pointer",
          }}
        >
          {syncing
            ? t("scan.eventCheckIn.sync.syncing")
            : syncedTicketCount !== null
              ? t("scan.eventCheckIn.sync.success", { count: syncedTicketCount })
              : t("scan.eventCheckIn.sync.button")}
        </button>
      ) : null}
      {syncError ? (
        <p role="alert" style={{ margin: 0, color: "var(--danger)", fontSize: "var(--fs-small)" }}>
          {syncError}
        </p>
      ) : null}

      {resultState.kind !== "idle" ? (
        <ScanResultFlash state={resultState} onDismiss={dismissResult} />
      ) : null}

      {showScanner ? (
        cameraDenied ? (
          <div
            data-testid="event-scan-camera-denied-notice"
            style={{
              borderRadius: "var(--r)",
              border: "1px dashed var(--border)",
              padding: "var(--sp-3)",
              fontSize: "var(--fs-small)",
              color: "var(--text-2)",
            }}
          >
            <p style={{ margin: 0, fontWeight: 600, color: "var(--text)" }}>
              {t("scan.eventCheckIn.camera.denied")}
            </p>
            <p style={{ margin: "var(--sp-1) 0 0" }}>{t("scan.eventCheckIn.camera.deniedBody")}</p>
          </div>
        ) : (
          <CameraScanner
            disabled={!storeReady}
            onCodeDetected={handleCodeDetected}
            onCameraDenied={handleCameraDenied}
          />
        )
      ) : null}

      <RecentScans items={recent} />
    </div>
  );
}

// Re-exported so tests can construct ApiError-driven failure scenarios without
// importing @vergeo/config directly in every test file.
export { ApiError };

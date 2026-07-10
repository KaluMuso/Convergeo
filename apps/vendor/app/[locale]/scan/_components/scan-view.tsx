"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useRef, useState } from "react";

import { Spinner } from "../../listings/new/_lib/ui";
import { playPickupSuccessHaptic } from "../_lib/haptics";
import { createPickupClient } from "../_lib/pickup-client";
import {
  appendRecentVerification,
  readRecentVerifications,
  type RecentVerification,
} from "../_lib/recent-verifications";
import { useOnline } from "../_lib/use-online";
import { classifyVerifyError } from "../_lib/verify-errors";

import { CameraScanner } from "./camera-scanner";
import { OfflineNotice } from "./offline-notice";
import { PinFallback } from "./pin-fallback";
import { RecentVerifications } from "./recent-verifications";
import { VerifyResult, type VerifyResultState } from "./verify-result";

export type ScanMode = "camera" | "pin";

type ScanViewProps = Record<string, never>;

export function ScanView(_props: ScanViewProps) {
  const t = useTranslations("vendor");
  const { session, loading } = useSession();
  const online = useOnline();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const client = useMemo(() => createPickupClient(getToken), [getToken]);

  const [scanMode, setScanMode] = useState<ScanMode>("camera");
  const [cameraDenied, setCameraDenied] = useState(false);
  const [resultState, setResultState] = useState<VerifyResultState>({ kind: "idle" });
  const [recent, setRecent] = useState<RecentVerification[]>(() => readRecentVerifications());
  const verifyingRef = useRef(false);

  const resetForAnotherScan = useCallback(() => {
    verifyingRef.current = false;
    setResultState({ kind: "idle" });
  }, []);

  const handleVerifySuccess = useCallback((orderId: string) => {
    playPickupSuccessHaptic();
    setRecent(appendRecentVerification(orderId));
    setResultState({ kind: "success", orderId });
    verifyingRef.current = false;
  }, []);

  const handleVerifyFailure = useCallback((error: unknown, source: "qr" | "pin") => {
    verifyingRef.current = false;
    if (error instanceof ApiError) {
      setResultState({
        kind: "error",
        errorKind: classifyVerifyError(error.code, source),
      });
      return;
    }
    setResultState({ kind: "error", errorKind: "generic" });
  }, []);

  const runVerify = useCallback(
    async (action: () => Promise<{ order_id: string }>, source: "qr" | "pin") => {
      if (!online) {
        setResultState({ kind: "error", errorKind: "offline" });
        return;
      }
      if (verifyingRef.current) {
        return;
      }
      verifyingRef.current = true;
      setResultState({ kind: "verifying" });
      try {
        const response = await action();
        handleVerifySuccess(response.order_id);
      } catch (error) {
        handleVerifyFailure(error, source);
      }
    },
    [handleVerifyFailure, handleVerifySuccess, online],
  );

  const handleQrDetected = useCallback(
    (token: string) => {
      void runVerify(() => client.verifyQr(token), "qr");
    },
    [client, runVerify],
  );

  const handlePinSubmit = useCallback(
    (orderId: string, pin: string) => {
      void runVerify(() => client.verifyPin(orderId, pin), "pin");
    },
    [client, runVerify],
  );

  const handleCameraDenied = useCallback(() => {
    setCameraDenied(true);
    setScanMode("pin");
  }, []);

  const showCamera = scanMode === "camera" && !cameraDenied;
  const showPin = scanMode === "pin" || cameraDenied;
  const isVerifying = resultState.kind === "verifying";
  const showScanner = resultState.kind === "idle" || resultState.kind === "verifying";

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "var(--sp-8)" }}>
        <Spinner label={t("scan.verifying")} />
      </div>
    );
  }

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
          {t("scan.eyebrow")}
        </p>
        <h1 style={{ margin: "var(--sp-1) 0", fontFamily: "var(--font-display)" }}>
          {t("scan.title")}
        </h1>
        <p style={{ margin: 0, color: "var(--text-2)", fontSize: "var(--fs-small)" }}>
          {t("scan.intro")}
        </p>
      </header>

      {!online ? <OfflineNotice /> : null}

      {resultState.kind !== "idle" && resultState.kind !== "verifying" ? (
        <VerifyResult
          state={resultState}
          onScanAnother={resetForAnotherScan}
          onRetry={resetForAnotherScan}
        />
      ) : null}

      {showScanner ? (
        <>
          {cameraDenied ? (
            <div
              data-testid="scan-camera-denied"
              style={{
                borderRadius: "var(--r)",
                border: "1px dashed var(--border)",
                padding: "var(--sp-3)",
                fontSize: "var(--fs-small)",
                color: "var(--text-2)",
              }}
            >
              <p style={{ margin: 0, fontWeight: 600, color: "var(--text)" }}>
                {t("scan.camera.denied")}
              </p>
              <p style={{ margin: "var(--sp-1) 0 0" }}>{t("scan.camera.deniedBody")}</p>
            </div>
          ) : null}

          {showCamera ? (
            <CameraScanner
              disabled={!online || isVerifying}
              onQrDetected={handleQrDetected}
              onCameraDenied={handleCameraDenied}
            />
          ) : null}

          {showPin ? (
            <PinFallback
              disabled={!online}
              isSubmitting={isVerifying}
              onSubmit={handlePinSubmit}
              onUseCamera={
                cameraDenied
                  ? undefined
                  : () => {
                      setScanMode("camera");
                    }
              }
              showCameraOption={!cameraDenied}
            />
          ) : (
            <button
              type="button"
              data-testid="scan-switch-pin"
              onClick={() => setScanMode("pin")}
              style={{
                minHeight: "2.75rem",
                border: "none",
                background: "transparent",
                color: "var(--primary)",
                fontWeight: 600,
                cursor: "pointer",
                textAlign: "left",
                padding: 0,
              }}
            >
              {t("scan.camera.usePin")}
            </button>
          )}
        </>
      ) : null}

      {isVerifying ? (
        <p
          data-testid="scan-verifying"
          style={{ margin: 0, textAlign: "center", color: "var(--text-2)" }}
        >
          {t("scan.verifying")}
        </p>
      ) : null}

      <RecentVerifications items={recent} />
    </div>
  );
}

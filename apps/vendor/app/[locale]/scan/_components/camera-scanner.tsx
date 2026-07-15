"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Spinner } from "../../listings/new/_lib/ui";
import { decodeQrFromImageData } from "../_lib/qr-decode";

export type CameraScannerMode = "loading" | "active" | "denied";

type CameraScannerProps = {
  disabled: boolean;
  onQrDetected: (token: string) => void;
  onCameraDenied: () => void;
};

export function CameraScanner({ disabled, onQrDetected, onCameraDenied }: CameraScannerProps) {
  const t = useTranslations("vendor");
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const frameRef = useRef<number | null>(null);
  const lastTokenRef = useRef<string | null>(null);
  const [mode, setMode] = useState<CameraScannerMode>("loading");

  const stopCamera = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop();
      }
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (disabled) {
      stopCamera();
      return;
    }

    let cancelled = false;

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMode("denied");
        onCameraDenied();
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
        if (cancelled) {
          for (const track of stream.getTracks()) {
            track.stop();
          }
          return;
        }

        streamRef.current = stream;
        const video = videoRef.current;
        if (!video) {
          return;
        }
        video.srcObject = stream;
        await video.play();
        setMode("active");

        const scanFrame = async () => {
          if (cancelled || disabled) {
            return;
          }
          const canvas = canvasRef.current;
          const videoEl = videoRef.current;
          if (!canvas || !videoEl || videoEl.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
            frameRef.current = requestAnimationFrame(scanFrame);
            return;
          }

          const width = videoEl.videoWidth;
          const height = videoEl.videoHeight;
          if (width > 0 && height > 0) {
            canvas.width = width;
            canvas.height = height;
            const context = canvas.getContext("2d", { willReadFrequently: true });
            if (context) {
              context.drawImage(videoEl, 0, 0, width, height);
              const imageData = context.getImageData(0, 0, width, height);
              const token = await decodeQrFromImageData(imageData);
              if (token && token !== lastTokenRef.current) {
                lastTokenRef.current = token;
                onQrDetected(token);
              }
            }
          }

          frameRef.current = requestAnimationFrame(scanFrame);
        };

        frameRef.current = requestAnimationFrame(scanFrame);
      } catch {
        if (!cancelled) {
          setMode("denied");
          onCameraDenied();
        }
      }
    }

    void startCamera();

    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [disabled, onCameraDenied, onQrDetected, stopCamera]);

  if (mode === "loading") {
    return (
      <div
        data-testid="scan-camera-loading"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "14rem",
          borderRadius: "var(--r)",
          background: "var(--bg-2)",
        }}
      >
        <Spinner label={t("scan.camera.loading")} />
      </div>
    );
  }

  if (mode === "denied") {
    return (
      <div
        data-testid="scan-camera-denied"
        style={{
          borderRadius: "var(--r)",
          border: "1px dashed var(--border)",
          padding: "var(--sp-4)",
          textAlign: "center",
        }}
      >
        <p style={{ margin: 0, fontWeight: 600 }}>{t("scan.camera.denied")}</p>
        <p
          style={{ margin: "var(--sp-2) 0 0", color: "var(--text-2)", fontSize: "var(--fs-small)" }}
        >
          {t("scan.camera.deniedBody")}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="scan-camera-active">
      <div
        style={{
          position: "relative",
          overflow: "hidden",
          borderRadius: "var(--r)",
          background: "#000",
          aspectRatio: "1",
          maxHeight: "18rem",
        }}
      >
        <video
          ref={videoRef}
          playsInline
          muted
          autoPlay
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
        <canvas ref={canvasRef} hidden />
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            inset: "12%",
            border: "2px solid color-mix(in srgb, var(--primary) 80%, white)",
            borderRadius: "var(--r)",
            boxShadow: "0 0 0 9999px color-mix(in srgb, black 35%, transparent)",
          }}
        />
      </div>
      <p
        style={{
          margin: "var(--sp-2) 0 0",
          fontSize: "var(--fs-small)",
          color: "var(--text-2)",
          textAlign: "center",
        }}
      >
        {t("scan.camera.hint")}
      </p>
    </div>
  );
}

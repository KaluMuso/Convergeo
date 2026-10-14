"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "../_lib/ui";

type DocCaptureProps = {
  label: string;
  helpText: string;
  captureLabel: string;
  retakeLabel: string;
  usePhotoLabel: string;
  onCapture: (file: File) => void;
  disabled?: boolean;
  facingMode?: "user" | "environment";
  existingPreviewUrl?: string | null;
};

export function DocCapture({
  label,
  helpText,
  captureLabel,
  retakeLabel,
  usePhotoLabel,
  onCapture,
  disabled = false,
  facingMode = "environment",
  existingPreviewUrl = null,
}: DocCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const attachedVideoRef = useRef<HTMLVideoElement | null>(null);
  const lifecycle = useRef({ mounted: false, generation: 0 });
  const pendingFileRef = useRef<File | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(existingPreviewUrl);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isCurrentCamera = useCallback(
    (generation: number) =>
      lifecycle.current.mounted && lifecycle.current.generation === generation,
    [],
  );

  const stopCamera = useCallback(() => {
    // Invalidate pending acquisition, playback and canvas callbacks before release.
    lifecycle.current.generation += 1;
    const stream = streamRef.current;
    streamRef.current = null;
    const video = attachedVideoRef.current;
    attachedVideoRef.current = null;
    if (video?.srcObject === stream) {
      video.srcObject = null;
    }
    stream?.getTracks().forEach((track) => track.stop());
    if (lifecycle.current.mounted) {
      setCameraActive(false);
    }
  }, []);

  useEffect(() => {
    lifecycle.current.mounted = true;
    return () => {
      lifecycle.current.mounted = false;
      pendingFileRef.current = null;
      stopCamera();
    };
  }, [stopCamera]);

  useEffect(() => {
    if (existingPreviewUrl) {
      setPreviewUrl(existingPreviewUrl);
    }
  }, [existingPreviewUrl]);

  const startCamera = useCallback(async () => {
    if (!lifecycle.current.mounted || disabled) {
      return;
    }
    setError(null);
    stopCamera();
    const generation = lifecycle.current.generation;
    pendingFileRef.current = null;

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Camera not available on this device.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      if (!isCurrentCamera(generation)) {
        // This stream was never owned by the mounted capture; release it directly.
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const video = videoRef.current;
      if (video) {
        attachedVideoRef.current = video;
        video.srcObject = stream;
        await video.play();
      }
      if (!isCurrentCamera(generation)) {
        // stopCamera already released an attached stream on replacement/unmount.
        return;
      }
      setCameraActive(true);
      setPreviewUrl(null);
      setPendingFile(null);
    } catch {
      if (!isCurrentCamera(generation)) {
        return;
      }
      stopCamera();
      setError("Could not access camera. Check permissions.");
    }
  }, [disabled, facingMode, isCurrentCamera, stopCamera]);

  const takePhoto = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const generation = lifecycle.current.generation;
    if (!video || !canvas || !streamRef.current || !isCurrentCamera(generation) || disabled) {
      return;
    }

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.drawImage(video, 0, 0, width, height);
    canvas.toBlob(
      (blob) => {
        if (!blob || !isCurrentCamera(generation)) {
          return;
        }
        const file = new File([blob], `capture-${Date.now()}.jpg`, { type: "image/jpeg" });
        pendingFileRef.current = file;
        setPendingFile(file);
        setPreviewUrl(URL.createObjectURL(blob));
        stopCamera();
      },
      "image/jpeg",
      0.85,
    );
  }, [disabled, isCurrentCamera, stopCamera]);

  const confirmPhoto = useCallback(() => {
    const file = pendingFileRef.current;
    if (file && lifecycle.current.mounted && !disabled) {
      // Consume synchronously so repeated confirmation cannot upload the same file.
      pendingFileRef.current = null;
      setPendingFile(null);
      onCapture(file);
    }
  }, [disabled, onCapture]);

  const retake = useCallback(() => {
    if (!lifecycle.current.mounted || disabled) {
      return;
    }
    pendingFileRef.current = null;
    setPendingFile(null);
    setPreviewUrl(null);
    void startCamera();
  }, [disabled, startCamera]);

  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="font-medium text-text">{label}</p>
        <p className="text-sm text-text-2">{helpText}</p>
      </div>

      <div className="relative aspect-[4/3] w-full overflow-hidden rounded border border-border bg-bg-2">
        {previewUrl ? (
          <img alt="" className="h-full w-full object-cover" src={previewUrl} />
        ) : (
          <video
            ref={videoRef}
            className="h-full w-full object-cover"
            muted
            playsInline
            aria-hidden={!cameraActive}
          />
        )}
        <canvas ref={canvasRef} className="hidden" />
      </div>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <div className="flex flex-col gap-2">
        {!cameraActive && !previewUrl ? (
          <Button
            type="button"
            className="w-full"
            disabled={disabled}
            loading={false}
            loadingLabel=""
            onClick={() => void startCamera()}
          >
            {captureLabel}
          </Button>
        ) : null}

        {cameraActive ? (
          <Button
            type="button"
            className="w-full"
            disabled={disabled}
            loading={false}
            loadingLabel=""
            onClick={takePhoto}
          >
            {captureLabel}
          </Button>
        ) : null}

        {previewUrl && pendingFile ? (
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              className="flex-1"
              disabled={disabled}
              loading={false}
              loadingLabel=""
              onClick={retake}
            >
              {retakeLabel}
            </Button>
            <Button
              type="button"
              className="flex-1"
              disabled={disabled}
              loading={false}
              loadingLabel=""
              onClick={confirmPhoto}
            >
              {usePhotoLabel}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

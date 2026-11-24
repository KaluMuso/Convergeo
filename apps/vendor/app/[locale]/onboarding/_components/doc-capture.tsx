"use client";

import { type ChangeEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { prepareKycImageFile, validateKycImageFile } from "../_lib/kyc-image";
import { Button } from "../_lib/ui";

type DocCaptureProps = {
  label: string;
  helpText: string;
  captureLabel: string;
  retakeLabel: string;
  usePhotoLabel: string;
  uploadInsteadLabel: string;
  cameraUnavailableLabel: string;
  cameraErrorLabel: string;
  invalidFileTypeLabel: string;
  fileTooLargeLabel: string;
  onCapture: (file: File) => void;
  disabled?: boolean;
  facingMode?: "user" | "environment";
  existingPreviewUrl?: string | null;
};

function useFinePointer(): boolean {
  const [fine, setFine] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const query = "(pointer: fine)";
    const media = window.matchMedia(query);
    const update = () => setFine(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return fine;
}

export function DocCapture({
  label,
  helpText,
  captureLabel,
  retakeLabel,
  usePhotoLabel,
  uploadInsteadLabel,
  cameraUnavailableLabel,
  cameraErrorLabel,
  invalidFileTypeLabel,
  fileTooLargeLabel,
  onCapture,
  disabled = false,
  facingMode = "environment",
  existingPreviewUrl = null,
}: DocCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const attachedVideoRef = useRef<HTMLVideoElement | null>(null);
  const lifecycle = useRef({ mounted: false, generation: 0 });
  const pendingFileRef = useRef<File | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(existingPreviewUrl);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preparingUpload, setPreparingUpload] = useState(false);
  const isFinePointer = useFinePointer();

  const captureFacing = facingMode === "user" ? "user" : "environment";
  const showUploadOption =
    !cameraActive && !previewUrl && !disabled && (isFinePointer || Boolean(error));

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

  // Layout effect: the capture button is tappable as soon as it commits, before
  // passive effects flush. A passive effect left a window where a tap was
  // silently ignored as "unmounted".
  useLayoutEffect(() => {
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
      setError(cameraUnavailableLabel);
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
      setError(cameraErrorLabel);
    }
  }, [cameraErrorLabel, cameraUnavailableLabel, disabled, facingMode, isCurrentCamera, stopCamera]);

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

  const validationMessage = useCallback(
    (problem: ReturnType<typeof validateKycImageFile>) => {
      if (problem === "invalid_type") {
        return invalidFileTypeLabel;
      }
      if (problem === "too_large") {
        return fileTooLargeLabel;
      }
      return null;
    },
    [fileTooLargeLabel, invalidFileTypeLabel],
  );

  const applyPreparedFile = useCallback(
    (generation: number, file: File) => {
      if (!isCurrentCamera(generation)) {
        return;
      }
      pendingFileRef.current = file;
      setPendingFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setError(null);
      stopCamera();
    },
    [isCurrentCamera, stopCamera],
  );

  const handleFilePicked = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const input = event.target;
      const raw = input.files?.[0];
      input.value = "";
      if (!raw || !lifecycle.current.mounted || disabled) {
        return;
      }

      const generation = lifecycle.current.generation;
      const upfront = validateKycImageFile(raw);
      if (upfront) {
        setError(validationMessage(upfront));
        return;
      }

      setPreparingUpload(true);
      try {
        const file = await prepareKycImageFile(raw);
        applyPreparedFile(generation, file);
      } catch (err) {
        if (!lifecycle.current.mounted) {
          return;
        }
        const code = err instanceof Error ? err.message : "";
        if (code === "too_large") {
          setError(fileTooLargeLabel);
        } else if (code === "invalid_type") {
          setError(invalidFileTypeLabel);
        }
      } finally {
        if (lifecycle.current.mounted) {
          setPreparingUpload(false);
        }
      }
    },
    [applyPreparedFile, disabled, fileTooLargeLabel, invalidFileTypeLabel, validationMessage],
  );

  const openFilePicker = useCallback(() => {
    if (!disabled && !preparingUpload) {
      fileInputRef.current?.click();
    }
  }, [disabled, preparingUpload]);

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

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture={captureFacing}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        disabled={disabled || preparingUpload}
        onChange={(event) => void handleFilePicked(event)}
      />

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <div className="flex flex-col gap-2">
        {!cameraActive && !previewUrl ? (
          <div className={showUploadOption ? "flex gap-2" : undefined}>
            <Button
              type="button"
              className={showUploadOption ? "min-w-0 flex-1" : "w-full"}
              disabled={disabled}
              loading={false}
              loadingLabel=""
              onClick={() => void startCamera()}
            >
              {captureLabel}
            </Button>
            {showUploadOption ? (
              <Button
                type="button"
                variant="secondary"
                className="min-w-0 flex-1"
                disabled={disabled || preparingUpload}
                loading={preparingUpload}
                loadingLabel=""
                onClick={openFilePicker}
              >
                {uploadInsteadLabel}
              </Button>
            ) : null}
          </div>
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

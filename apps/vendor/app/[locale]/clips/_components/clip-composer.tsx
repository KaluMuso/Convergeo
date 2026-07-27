"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useRef, useState } from "react";

import { createClipsClient, type SignedClipUpload } from "../_lib/clips-client";
import {
  MAX_CLIP_BYTES,
  readDuration,
  uploadToCloudinary,
  validateDuration,
  validateFile,
  type FileProblem,
} from "../_lib/upload";

/**
 * M17-P06 — record/select, compose, upload.
 *
 * The resilience shape is deliberate and mirrors the M12-P05 image manager:
 *
 * * the file is validated **before** a draft is created, so an over-limit file
 *   never costs a round trip or a signed slot;
 * * the signed params and the `File` handle are held in state, so **retry sends
 *   the same bytes to the same slot** — no second picker, no second draft, no
 *   phantom clip;
 * * an interrupted upload leaves the draft recoverable rather than orphaned: the
 *   clip stays in `draft` until Cloudinary's callback moves it on.
 *
 * Camera denial is handled as a **state, not a dead end** — the file picker is
 * always present, so "we can't reach your camera" is followed by something the
 * vendor can actually do.
 */

type Phase = "idle" | "creating" | "uploading" | "done" | "failed";

const PROBLEM_KEY: Record<FileProblem, string> = {
  not_video: "clips.errors.notVideo",
  too_large: "clips.errors.tooLarge",
  too_long: "clips.errors.tooLong",
};

function formatMb(bytes: number): string {
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export function ClipComposer() {
  const t = useTranslations("vendor");
  const { session } = useSession();
  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const clipsClient = useMemo(() => createClipsClient(getToken), [getToken]);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [caption, setCaption] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [percent, setPercent] = useState(0);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [errorValues, setErrorValues] = useState<Record<string, string>>({});
  const [cameraDenied, setCameraDenied] = useState(false);

  // Held across a failure so retry needs neither a new draft nor a new pick.
  const [signed, setSigned] = useState<SignedClipUpload | null>(null);

  const fail = useCallback((key: string, values: Record<string, string> = {}) => {
    setErrorKey(key);
    setErrorValues(values);
    setPhase("failed");
  }, []);

  const onSelect = useCallback(
    async (selected: File | null) => {
      setErrorKey(null);
      setSigned(null);
      setPercent(0);
      setPhase("idle");
      if (!selected) {
        setFile(null);
        return;
      }

      const problem = validateFile(selected);
      if (problem) {
        setFile(null);
        fail(PROBLEM_KEY[problem], { size: formatMb(selected.size) });
        return;
      }

      const seconds = await readDuration(selected);
      const durationProblem = validateDuration(seconds);
      if (durationProblem) {
        setFile(null);
        fail(PROBLEM_KEY[durationProblem], {});
        return;
      }

      setDuration(seconds === null ? null : Math.round(seconds));
      setFile(selected);
    },
    [fail],
  );

  const runUpload = useCallback(
    async (params: SignedClipUpload, blob: File) => {
      setPhase("uploading");
      setPercent(0);
      try {
        await uploadToCloudinary(params, blob, setPercent).promise;
        setPhase("done");
      } catch {
        // The draft survives. Retry reuses `signed` and `file`.
        fail("clips.errors.uploadFailed");
      }
    },
    [fail],
  );

  const onSubmit = useCallback(async () => {
    if (!file) {
      return;
    }
    setPhase("creating");
    setErrorKey(null);
    try {
      const params = await clipsClient.createDraft({
        caption: caption.trim() || null,
        file_size_bytes: file.size,
        duration_s: duration ?? undefined,
      });
      setSigned(params);
      await runUpload(params, file);
    } catch (error) {
      const code = (error as { code?: string })?.code ?? "";
      if (code === "clip_cap_exceeded") {
        fail("clips.errors.weeklyCap");
      } else if (code === "forbidden") {
        fail("clips.errors.notVerified");
      } else if (code === "rate_limited") {
        fail("clips.errors.rateLimited");
      } else {
        fail("clips.errors.uploadFailed");
      }
    }
  }, [caption, clipsClient, duration, fail, file, runUpload]);

  const onRetry = useCallback(() => {
    if (signed && file) {
      // Same slot, same bytes: nothing is re-encoded and nothing is re-picked.
      void runUpload(signed, file);
      return;
    }
    void onSubmit();
  }, [file, onSubmit, runUpload, signed]);

  return (
    <section className="flex flex-col gap-4 p-4">
      <h1 className="text-h2 font-semibold text-text">{t("clips.compose.title")}</h1>

      <div className="rounded-2 border border-border bg-bg-2 p-3 text-sm text-text">
        <h2 className="font-medium">{t("clips.limits.title")}</h2>
        <ul className="mt-2 list-disc pl-5 text-muted">
          <li>{t("clips.limits.duration")}</li>
          <li>{t("clips.limits.size")}</li>
          <li>{t("clips.limits.orientation")}</li>
        </ul>
        {/* Data honesty is the same principle as the customer size chip: tell
            people what this costs BEFORE they spend it. */}
        <p className="mt-2 text-muted" data-testid="clips-data-cost">
          {t("clips.limits.dataCost")}
        </p>
      </div>

      {cameraDenied ? (
        <div
          role="alert"
          data-testid="clips-camera-denied"
          className="rounded-2 border border-border bg-surface p-3"
        >
          <p className="text-sm font-medium text-text">{t("clips.camera.denied")}</p>
          <p className="mt-1 text-sm text-muted">{t("clips.camera.deniedBody")}</p>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            data-testid="clips-use-picker"
            className="tap mt-2 min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text"
          >
            {t("clips.camera.usePicker")}
          </button>
        </div>
      ) : null}

      <label className="flex flex-col gap-1 text-sm text-text" htmlFor="clip-file">
        {t("clips.compose.chooseFile")}
        <input
          id="clip-file"
          ref={fileInputRef}
          type="file"
          accept="video/*"
          data-testid="clips-file-input"
          className="min-h-11 rounded-2 border border-border bg-surface p-2"
          onChange={(event) => {
            void onSelect(event.target.files?.[0] ?? null);
          }}
        />
      </label>

      <button
        type="button"
        data-testid="clips-record-button"
        className="tap min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text"
        onClick={async () => {
          const media = navigator.mediaDevices;
          if (!media?.getUserMedia) {
            setCameraDenied(true);
            return;
          }
          try {
            const stream = await media.getUserMedia({ video: true });
            // Permission is the only thing we needed; release the camera at once
            // rather than holding it open behind a file picker.
            for (const track of stream.getTracks()) {
              track.stop();
            }
            setCameraDenied(false);
            fileInputRef.current?.click();
          } catch {
            setCameraDenied(true);
          }
        }}
      >
        {t("clips.compose.record")}
      </button>

      {file ? (
        <p className="text-sm text-muted" data-testid="clips-selected">
          {t("clips.compose.selected", { name: file.name, size: formatMb(file.size) })}
        </p>
      ) : null}

      <label className="flex flex-col gap-1 text-sm text-text" htmlFor="clip-caption">
        {t("clips.compose.captionLabel")}
        <textarea
          id="clip-caption"
          value={caption}
          maxLength={600}
          placeholder={t("clips.compose.captionPlaceholder")}
          data-testid="clips-caption"
          onChange={(event) => setCaption(event.target.value)}
          className="min-h-24 rounded-2 border border-border bg-surface p-2"
        />
      </label>

      {errorKey ? (
        <p role="alert" data-testid="clips-error-message" className="text-sm text-danger">
          {t(errorKey, errorValues)}
        </p>
      ) : null}

      {phase === "uploading" ? (
        <p role="status" data-testid="clips-progress" className="text-sm text-text">
          {t("clips.compose.uploading", { percent })}
        </p>
      ) : null}

      {phase === "done" ? (
        <p role="status" data-testid="clips-done" className="text-sm text-success">
          {t("clips.compose.done")}
        </p>
      ) : null}

      {phase === "failed" ? (
        <button
          type="button"
          onClick={onRetry}
          data-testid="clips-retry"
          className="tap min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text"
        >
          {t("clips.compose.retry")}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => void onSubmit()}
          disabled={!file || phase === "creating" || phase === "uploading"}
          data-testid="clips-submit"
          className="tap min-h-11 rounded-full bg-primary px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
        >
          {t("clips.compose.submit")}
        </button>
      )}

      <p className="sr-only" data-testid="clips-max-bytes">
        {MAX_CLIP_BYTES}
      </p>
    </section>
  );
}

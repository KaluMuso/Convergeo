"use client";

import { useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { Button } from "./button";
import { FormField } from "./form-field";
import { Select } from "./select";
import { Textarea } from "./textarea";

export type FeedbackCategory = "bug" | "idea" | "confusing" | "praise" | "other";

export type FeedbackInput = {
  category: FeedbackCategory;
  message: string;
  /** Optional canvas-encoded screenshot as a data:image/* URL. */
  screenshot?: string;
};

export type FeedbackSubmitResult = {
  ok: boolean;
  /** When true, the widget shows the rate-limit message instead of the generic error. */
  rateLimited?: boolean;
};

export type FeedbackWidgetLabels = {
  trigger: string;
  heading: string;
  close: string;
  categoryLabel: string;
  categoryBug: string;
  categoryIdea: string;
  categoryConfusing: string;
  categoryPraise: string;
  categoryOther: string;
  messageLabel: string;
  messagePlaceholder: string;
  screenshotLabel: string;
  requiredMarker: string;
  submit: string;
  submitting: string;
  success: string;
  errorGeneric: string;
  errorRateLimited: string;
  validation: { messageRequired: string };
};

export interface FeedbackWidgetProps {
  labels: FeedbackWidgetLabels;
  onSubmit: (input: FeedbackInput) => Promise<FeedbackSubmitResult>;
  /** Longest edge of the downscaled screenshot in px (keeps the data URL small). */
  maxScreenshotEdge?: number;
}

type Status = "idle" | "submitting" | "success" | "error";

const CATEGORY_ORDER: FeedbackCategory[] = ["bug", "idea", "confusing", "praise", "other"];

function categoryLabel(labels: FeedbackWidgetLabels, category: FeedbackCategory): string {
  switch (category) {
    case "bug":
      return labels.categoryBug;
    case "idea":
      return labels.categoryIdea;
    case "confusing":
      return labels.categoryConfusing;
    case "praise":
      return labels.categoryPraise;
    case "other":
      return labels.categoryOther;
  }
}

/**
 * Downscale an uploaded image through a <canvas> and return a compact JPEG data
 * URL. Runs entirely client-side — nothing is uploaded until the user submits.
 */
async function encodeScreenshot(file: File, maxEdge: number): Promise<string | null> {
  if (typeof document === "undefined" || !file.type.startsWith("image/")) {
    return null;
  }
  const bitmap = await new Promise<HTMLImageElement | null>((resolve) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    image.src = url;
  });
  if (!bitmap) {
    return null;
  }
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return null;
  }
  ctx.drawImage(bitmap, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.7);
}

export function FeedbackWidget({
  labels,
  onSubmit,
  maxScreenshotEdge = 1024,
}: FeedbackWidgetProps) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<FeedbackCategory>("bug");
  const [message, setMessage] = useState("");
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [messageError, setMessageError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function reset(): void {
    setCategory("bug");
    setMessage("");
    setScreenshot(null);
    setStatus("idle");
    setMessageError(null);
    setFormError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function close(): void {
    setOpen(false);
    reset();
  }

  async function onScreenshotChange(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    if (!file) {
      setScreenshot(null);
      return;
    }
    const encoded = await encodeScreenshot(file, maxScreenshotEdge);
    setScreenshot(encoded);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setFormError(null);

    const trimmed = message.trim();
    if (trimmed.length < 3) {
      setMessageError(labels.validation.messageRequired);
      return;
    }
    setMessageError(null);
    setStatus("submitting");

    try {
      const result = await onSubmit({
        category,
        message: trimmed,
        screenshot: screenshot ?? undefined,
      });
      if (result.ok) {
        setStatus("success");
        return;
      }
      setStatus("error");
      setFormError(result.rateLimited ? labels.errorRateLimited : labels.errorGeneric);
    } catch {
      setStatus("error");
      setFormError(labels.errorGeneric);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 end-4 z-50 inline-flex min-h-11 items-center gap-2 rounded-full bg-primary px-4 py-2 font-body text-sm font-medium text-surface shadow-lg focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        <span aria-hidden="true">💬</span>
        {labels.trigger}
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label={labels.heading}
      className="fixed bottom-4 end-4 z-50 w-[min(92vw,22rem)] rounded-lg border border-border bg-surface p-4 shadow-xl"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-h3 text-display-ink">{labels.heading}</h2>
        <button
          type="button"
          onClick={close}
          aria-label={labels.close}
          className="inline-flex size-11 min-h-11 min-w-11 items-center justify-center rounded text-text-2 hover:bg-bg-2 focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      {status === "success" ? (
        <p
          role="status"
          className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 font-body text-body text-text"
        >
          {labels.success}
        </p>
      ) : (
        <form className="flex flex-col gap-4" noValidate onSubmit={handleSubmit}>
          <FormField label={labels.categoryLabel}>
            <Select
              value={category}
              onChange={(event) => setCategory(event.target.value as FeedbackCategory)}
            >
              {CATEGORY_ORDER.map((value) => (
                <option key={value} value={value}>
                  {categoryLabel(labels, value)}
                </option>
              ))}
            </Select>
          </FormField>

          <FormField
            label={labels.messageLabel}
            required
            requiredMarker={labels.requiredMarker}
            errorMessage={messageError ?? undefined}
          >
            <Textarea
              name="message"
              rows={4}
              value={message}
              error={Boolean(messageError)}
              placeholder={labels.messagePlaceholder}
              onChange={(event) => setMessage(event.target.value)}
            />
          </FormField>

          <label className="flex flex-col gap-2 font-body text-sm font-medium text-text">
            {labels.screenshotLabel}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={onScreenshotChange}
              className="text-sm text-text-2 file:me-3 file:rounded file:border file:border-border file:bg-bg-2 file:px-3 file:py-2 file:text-sm file:text-text"
            />
          </label>

          {formError ? (
            <p role="alert" className="font-body text-sm text-danger">
              {formError}
            </p>
          ) : null}

          <Button type="submit" loading={status === "submitting"} loadingLabel={labels.submitting}>
            {labels.submit}
          </Button>
        </form>
      )}
    </div>
  );
}

"use client";

import { createBrowserClient } from "@vergeo/auth/browser-client";
import { useCallback, useId, useMemo, useState } from "react";

export type ReportReviewReason = {
  value: string;
  label: string;
};

export type ReportReviewLabels = {
  /** Text on the collapsed "Report" trigger button. */
  cta: string;
  /** Heading of the expanded report form. */
  heading: string;
  /** Label for the reason radio group. */
  reasonLegend: string;
  /** Submit button text. */
  submit: string;
  /** Cancel button text. */
  cancel: string;
  /** Shown after a successful report. */
  success: string;
  /** Shown when the user is not signed in. */
  signedOut: string;
  /** Generic failure message. */
  error: string;
  /** Available report reasons (i18n'd by the caller). */
  reasons: ReportReviewReason[];
};

type ReportReviewProps = {
  reviewId: string;
  labels: ReportReviewLabels;
};

type Status = "idle" | "submitting" | "done" | "error";

/**
 * Customer-facing "report this review" control. Inserts a row into the shared M13-P04 `flags`
 * queue (entity_type = "review") via the RLS-guarded reporter-insert policy — the same queue the
 * admin moderation surface reads. No bespoke reports table or endpoint.
 */
export function ReportReview({ reviewId, labels }: ReportReviewProps) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [reason, setReason] = useState<string>(labels.reasons[0]?.value ?? "");
  const [message, setMessage] = useState<string | undefined>();
  const groupId = useId();

  const reasons = useMemo(() => labels.reasons, [labels.reasons]);

  const submit = useCallback(async () => {
    if (!reason) {
      return;
    }
    setStatus("submitting");
    setMessage(undefined);
    try {
      const supabase = createBrowserClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (!user) {
        setStatus("error");
        setMessage(labels.signedOut);
        return;
      }
      const { error } = await supabase.from("flags").insert({
        entity_type: "review",
        entity_id: reviewId,
        reason,
        reporter_user_id: user.id,
      });
      if (error) {
        setStatus("error");
        setMessage(labels.error);
        return;
      }
      setStatus("done");
      setMessage(labels.success);
    } catch {
      setStatus("error");
      setMessage(labels.error);
    }
  }, [labels.error, labels.signedOut, labels.success, reason, reviewId]);

  if (status === "done") {
    return (
      <p className="text-xs text-text-2" role="status">
        {message}
      </p>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-11 items-center text-xs font-medium text-text-2 underline"
      >
        {labels.cta}
      </button>
    );
  }

  return (
    <form
      className="space-y-3 rounded border border-border bg-surface p-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-display-ink">{labels.heading}</legend>
        <p className="text-xs text-text-2">{labels.reasonLegend}</p>
        <div className="space-y-1">
          {reasons.map((option) => (
            <label key={option.value} className="flex min-h-11 items-center gap-2 text-sm">
              <input
                type="radio"
                name={groupId}
                value={option.value}
                checked={reason === option.value}
                onChange={() => setReason(option.value)}
                className="h-4 w-4"
              />
              <span className="text-display-ink">{option.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {status === "error" && message ? (
        <p className="text-xs text-error" role="alert">
          {message}
        </p>
      ) : null}

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={status === "submitting" || !reason}
          className="inline-flex min-h-11 items-center rounded bg-primary px-3 text-sm font-medium text-white disabled:opacity-50"
        >
          {labels.submit}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setStatus("idle");
            setMessage(undefined);
          }}
          className="inline-flex min-h-11 items-center px-3 text-sm font-medium text-text-2"
        >
          {labels.cancel}
        </button>
      </div>
    </form>
  );
}

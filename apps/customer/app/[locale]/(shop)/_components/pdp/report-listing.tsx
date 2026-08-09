"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { Modal } from "@vergeo/ui/src/modal";
import { useCallback, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

export type ReportListingReason = {
  value: string;
  label: string;
};

export type ReportListingLabels = {
  cta: string;
  heading: string;
  reasonLegend: string;
  detailLabel: string;
  detailPlaceholder: string;
  submit: string;
  cancel: string;
  success: string;
  signedOut: string;
  error: string;
  rateLimited: string;
  reasons: ReportListingReason[];
};

type ReportListingProps = {
  listingId: string;
  labels: ReportListingLabels;
};

type Status = "idle" | "submitting" | "done" | "error";

const REPORT_REASONS = new Set(["counterfeit", "prohibited", "scam", "misleading", "other"]);

/**
 * Customer "report this listing" control — posts to the authenticated API
 * (`POST /flags/report`) rather than inserting into Supabase client-side.
 */
export function ReportListing({ listingId, labels }: ReportListingProps) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [reason, setReason] = useState(labels.reasons[0]?.value ?? "");
  const [detail, setDetail] = useState("");
  const [message, setMessage] = useState<string | undefined>();

  const close = useCallback(() => {
    setOpen(false);
    setStatus("idle");
    setMessage(undefined);
    setDetail("");
  }, []);

  const submit = useCallback(async () => {
    if (!reason || !REPORT_REASONS.has(reason)) {
      return;
    }
    setStatus("submitting");
    setMessage(undefined);
    try {
      const supabase = await getBrowserClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;
      if (!token) {
        setStatus("error");
        setMessage(labels.signedOut);
        return;
      }

      const base = getApiBaseUrl().replace(/\/$/, "");
      if (!base) {
        setStatus("error");
        setMessage(labels.error);
        return;
      }

      const response = await fetch(`${base}/flags/report`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          listing_id: listingId,
          reason,
          detail: detail.trim() ? detail.trim().slice(0, 500) : null,
        }),
      });

      if (response.status === 401 || response.status === 403) {
        setStatus("error");
        setMessage(labels.signedOut);
        return;
      }
      if (response.status === 429) {
        setStatus("error");
        setMessage(labels.rateLimited);
        return;
      }
      if (!response.ok) {
        setStatus("error");
        setMessage(labels.error);
        return;
      }
      setStatus("done");
    } catch {
      setStatus("error");
      setMessage(labels.error);
    }
  }, [detail, labels.error, labels.rateLimited, labels.signedOut, listingId, reason]);

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        data-testid="pdp-report-listing-cta"
        loadingLabel={labels.submit}
        onClick={() => setOpen(true)}
      >
        {labels.cta}
      </Button>
      <Modal
        open={open}
        onClose={close}
        title={labels.heading}
        data-testid="pdp-report-listing-dialog"
        closeOnEscape={status !== "submitting"}
        closeOnScrimClick={status !== "submitting"}
      >
        {status === "done" ? (
          <p className="mt-3 text-sm text-text-2" role="status">
            {labels.success}
          </p>
        ) : (
          <form
            className="mt-3 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-text">{labels.reasonLegend}</legend>
              <ul className="space-y-2">
                {labels.reasons.map((entry) => (
                  <li key={entry.value}>
                    <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-text">
                      <input
                        type="radio"
                        name="report-listing-reason"
                        value={entry.value}
                        checked={reason === entry.value}
                        onChange={() => setReason(entry.value)}
                      />
                      {entry.label}
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
            <label className="block space-y-1 text-sm text-text">
              <span className="font-medium">{labels.detailLabel}</span>
              <textarea
                value={detail}
                onChange={(event) => setDetail(event.target.value)}
                maxLength={500}
                rows={3}
                placeholder={labels.detailPlaceholder}
                className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text"
              />
            </label>
            {message ? (
              <p className="text-sm text-danger" role="alert">
                {message}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                variant="primary"
                loading={status === "submitting"}
                loadingLabel={labels.submit}
              >
                {labels.submit}
              </Button>
              <Button
                type="button"
                variant="secondary"
                loadingLabel={labels.cancel}
                onClick={close}
                disabled={status === "submitting"}
              >
                {labels.cancel}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}

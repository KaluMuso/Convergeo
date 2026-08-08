"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { Modal } from "@vergeo/ui/src/modal";
import { useCallback, useState } from "react";

export type ReportListingReason = {
  value: string;
  label: string;
};

export type ReportListingLabels = {
  cta: string;
  heading: string;
  reasonLegend: string;
  submit: string;
  cancel: string;
  success: string;
  signedOut: string;
  error: string;
  reasons: ReportListingReason[];
};

type ReportListingProps = {
  listingId: string;
  labels: ReportListingLabels;
};

type Status = "idle" | "submitting" | "done" | "error";

/**
 * Customer "report this listing" control — inserts into the shared M13-P04 flags queue.
 */
export function ReportListing({ listingId, labels }: ReportListingProps) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [reason, setReason] = useState(labels.reasons[0]?.value ?? "");
  const [message, setMessage] = useState<string | undefined>();

  const close = useCallback(() => {
    setOpen(false);
    setStatus("idle");
    setMessage(undefined);
  }, []);

  const submit = useCallback(async () => {
    if (!reason) {
      return;
    }
    setStatus("submitting");
    setMessage(undefined);
    try {
      const supabase = await getBrowserClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (!user) {
        setStatus("error");
        setMessage(labels.signedOut);
        return;
      }
      const { error } = await supabase.from("flags").insert({
        entity_type: "listing",
        entity_id: listingId,
        reason,
        reporter_user_id: user.id,
      });
      if (error) {
        setStatus("error");
        setMessage(labels.error);
        return;
      }
      setStatus("done");
    } catch {
      setStatus("error");
      setMessage(labels.error);
    }
  }, [labels.error, labels.signedOut, listingId, reason]);

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        data-testid="pdp-report-listing-cta"
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
          <p className="mt-3 text-sm text-text-2">{labels.success}</p>
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
            {message ? <p className="text-sm text-danger">{message}</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="primary" loading={status === "submitting"}>
                {labels.submit}
              </Button>
              <Button
                type="button"
                variant="secondary"
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

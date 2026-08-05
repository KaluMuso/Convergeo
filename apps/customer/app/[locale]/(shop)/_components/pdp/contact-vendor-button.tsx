"use client";

import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Textarea } from "@vergeo/ui/src/textarea";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { useContactVendor } from "./use-contact-vendor";

export type ContactVendorLabels = {
  cta: string;
  dialogTitle: string;
  dialogHint: string;
  messageLabel: string;
  messagePlaceholder: string;
  submit: string;
  submitting: string;
  cancel: string;
  done: string;
  successTitle: string;
  successBody: string;
  successContinued: string;
  signInPrompt: string;
  signInCta: string;
  errors: {
    empty: string;
    tooLong: string;
    prohibited: string;
    rateLimited: string;
    ownListing: string;
    generic: string;
    signInRequired: string;
  };
};

export type ContactVendorButtonProps = {
  locale: string;
  listingId: string;
  vendorName: string;
  labels: ContactVendorLabels;
};

export function ContactVendorButton({
  locale,
  listingId,
  vendorName,
  labels,
}: ContactVendorButtonProps) {
  const dialogTitleId = useId();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const {
    sessionReady,
    isSignedIn,
    status,
    errorKey,
    reusedExistingThread,
    maxBodyChars,
    sendMessage,
    reset,
  } = useContactVendor();

  const loginHref = `/${locale}/login?next=${encodeURIComponent(pathname || `/${locale}`)}`;

  const close = useCallback(() => {
    setOpen(false);
    setMessage("");
    reset();
  }, [reset]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close, open]);

  const handleSubmit = async () => {
    const result = await sendMessage(listingId, message);
    if (result) {
      setMessage("");
    }
  };

  const errorMessage =
    errorKey && errorKey in labels.errors
      ? labels.errors[errorKey as keyof ContactVendorLabels["errors"]]
      : null;

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        data-testid="pdp-contact-vendor-cta"
        className="w-full sm:w-auto"
        loadingLabel={labels.submitting}
        onClick={() => {
          reset();
          setOpen(true);
        }}
      >
        {labels.cta}
      </Button>

      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
          role="presentation"
          data-testid="pdp-contact-vendor-dialog"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              close();
            }
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={dialogTitleId}
            className="w-full max-w-md rounded border border-border bg-bg p-4 shadow-lg"
            style={{ borderRadius: "var(--r)" }}
          >
            <h3 id={dialogTitleId} className="font-display text-lg font-semibold text-text">
              {labels.dialogTitle}
            </h3>
            <p className="mt-1 text-sm text-text-2">
              {labels.dialogHint.replace("{vendor}", vendorName)}
            </p>

            {!sessionReady ? (
              <p className="mt-4 text-sm text-text-2" aria-busy="true">
                {labels.submitting}
              </p>
            ) : !isSignedIn ? (
              <div className="mt-4 space-y-3">
                <p className="text-sm text-text-2">{labels.signInPrompt}</p>
                <Link
                  href={loginHref}
                  className="inline-flex min-h-11 items-center font-medium text-primary hover:underline"
                  data-testid="pdp-contact-vendor-sign-in"
                >
                  {labels.signInCta}
                </Link>
              </div>
            ) : status === "success" ? (
              <div className="mt-4 space-y-2" data-testid="pdp-contact-vendor-success">
                <p className="font-medium text-text">{labels.successTitle}</p>
                <p className="text-sm text-text-2">
                  {reusedExistingThread ? labels.successContinued : labels.successBody}
                </p>
                <Button
                  type="button"
                  variant="primary"
                  loadingLabel={labels.submitting}
                  onClick={close}
                >
                  {labels.done}
                </Button>
              </div>
            ) : (
              <form
                className="mt-4 space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleSubmit();
                }}
              >
                <FormField label={labels.messageLabel} errorMessage={errorMessage ?? undefined}>
                  <Textarea
                    name="message"
                    value={message}
                    maxLength={maxBodyChars}
                    rows={4}
                    placeholder={labels.messagePlaceholder}
                    disabled={status === "sending"}
                    data-testid="pdp-contact-vendor-message"
                    onChange={(event) => setMessage(event.target.value)}
                  />
                </FormField>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="submit"
                    variant="primary"
                    loading={status === "sending"}
                    loadingLabel={labels.submitting}
                    disabled={status === "sending"}
                    data-testid="pdp-contact-vendor-submit"
                  >
                    {status === "sending" ? labels.submitting : labels.submit}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={labels.submitting}
                    onClick={close}
                    disabled={status === "sending"}
                  >
                    {labels.cancel}
                  </Button>
                </div>
              </form>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

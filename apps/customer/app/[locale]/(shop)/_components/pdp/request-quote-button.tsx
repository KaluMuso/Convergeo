"use client";

import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Modal } from "@vergeo/ui/src/modal";
import { Textarea } from "@vergeo/ui/src/textarea";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";

import { useRequestQuote } from "./use-request-quote";

export type RequestQuoteLabels = {
  cta: string;
  dialogTitle: string;
  dialogHint: string;
  detailsLabel: string;
  detailsPlaceholder: string;
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

export type RequestQuoteButtonProps = {
  locale: string;
  listingId?: string;
  serviceId?: string;
  vendorName: string;
  labels: RequestQuoteLabels;
  variant?: "primary" | "secondary";
  className?: string;
};

export function RequestQuoteButton({
  locale,
  listingId,
  serviceId,
  vendorName,
  labels,
  variant = "secondary",
  className,
}: RequestQuoteButtonProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState("");
  const {
    sessionReady,
    isSignedIn,
    status,
    errorKey,
    reusedExistingThread,
    maxDetailsChars,
    submitRequest,
    reset,
  } = useRequestQuote();

  const loginHref = `/${locale}/login?next=${encodeURIComponent(pathname || `/${locale}`)}`;

  const close = useCallback(() => {
    setOpen(false);
    setDetails("");
    reset();
  }, [reset]);

  const handleSubmit = async () => {
    const ok = await submitRequest({
      listingId,
      serviceId,
      details,
    });
    if (ok) {
      setDetails("");
    }
  };

  const errorMessage =
    errorKey && errorKey in labels.errors
      ? labels.errors[errorKey as keyof RequestQuoteLabels["errors"]]
      : null;

  return (
    <>
      <Button
        type="button"
        variant={variant}
        data-testid="pdp-request-quote-cta"
        className={className ?? "w-full sm:w-auto"}
        loadingLabel={labels.submitting}
        onClick={() => {
          reset();
          setOpen(true);
        }}
      >
        {labels.cta}
      </Button>

      <Modal
        open={open}
        onClose={close}
        title={labels.dialogTitle}
        data-testid="pdp-request-quote-dialog"
        closeOnEscape={status !== "sending"}
        closeOnScrimClick={status !== "sending"}
      >
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
              data-testid="pdp-request-quote-sign-in"
            >
              {labels.signInCta}
            </Link>
          </div>
        ) : status === "success" ? (
          <div className="mt-4 space-y-2" data-testid="pdp-request-quote-success">
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
            <FormField label={labels.detailsLabel} errorMessage={errorMessage ?? undefined}>
              <Textarea
                name="details"
                value={details}
                maxLength={maxDetailsChars}
                rows={5}
                placeholder={labels.detailsPlaceholder}
                disabled={status === "sending"}
                data-testid="pdp-request-quote-details"
                onChange={(event) => setDetails(event.target.value)}
              />
            </FormField>
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                variant="primary"
                loading={status === "sending"}
                loadingLabel={labels.submitting}
                disabled={status === "sending"}
                data-testid="pdp-request-quote-submit"
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
      </Modal>
    </>
  );
}

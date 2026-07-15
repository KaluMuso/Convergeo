"use client";

import { ApiError } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { createBusinessApiClient, type BusinessStatus } from "./business-api";

export type BusinessApplyLabels = {
  legalNameLabel: string;
  legalNamePlaceholder: string;
  registrationLabel: string;
  registrationPlaceholder: string;
  tpinLabel: string;
  tpinPlaceholder: string;
  submit: string;
  submitting: string;
  resubmit: string;
  submitted: string;
  errorRequired: string;
  errorFailed: string;
  errorRateLimited: string;
  errorAlreadyDecided: string;
};

type BusinessApplyFormProps = {
  locale: string;
  initial: BusinessStatus;
  labels: BusinessApplyLabels;
  // Passed from the server page (which already resolved it) so this client bundle
  // does not pull in the Supabase browser client via useSession — keeps the route
  // under the 150 KB gz budget, matching PreferencesForm/AddressForm.
  accessToken: string;
};

function messageForError(error: unknown, labels: BusinessApplyLabels): string {
  if (error instanceof ApiError) {
    if (error.code === "business.already_decided") {
      return labels.errorAlreadyDecided;
    }
    if (error.status === 429) {
      return labels.errorRateLimited;
    }
  }
  return labels.errorFailed;
}

export function BusinessApplyForm({
  locale,
  initial,
  labels,
  accessToken,
}: BusinessApplyFormProps) {
  const router = useRouter();

  const [legalName, setLegalName] = useState(initial.legal_name ?? "");
  const [registrationNo, setRegistrationNo] = useState(initial.registration_no ?? "");
  const [tpin, setTpin] = useState(initial.tpin ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const getToken = useCallback(() => accessToken, [accessToken]);

  const isResubmit = initial.status === "rejected";

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmedName = legalName.trim();
      const trimmedReg = registrationNo.trim();
      if (trimmedName.length < 2 || trimmedReg.length < 2) {
        setError(labels.errorRequired);
        return;
      }
      setSubmitting(true);
      setError(null);
      try {
        const client = createBusinessApiClient(getToken);
        await client.apply({
          legal_name: trimmedName,
          registration_no: trimmedReg,
          tpin: tpin.trim() || null,
        });
        setSubmitted(true);
        router.refresh();
      } catch (submitError) {
        setError(messageForError(submitError, labels));
      } finally {
        setSubmitting(false);
      }
    },
    [legalName, registrationNo, tpin, getToken, labels, router],
  );

  const inputClass =
    "h-11 w-full rounded-md border border-border bg-surface px-3 text-sm text-text";

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit} data-locale={locale}>
      <label className="flex flex-col gap-1 text-sm text-text-2">
        {labels.legalNameLabel}
        <input
          type="text"
          value={legalName}
          onChange={(event) => setLegalName(event.target.value)}
          placeholder={labels.legalNamePlaceholder}
          className={inputClass}
          required
          minLength={2}
          maxLength={200}
        />
      </label>

      <label className="flex flex-col gap-1 text-sm text-text-2">
        {labels.registrationLabel}
        <input
          type="text"
          value={registrationNo}
          onChange={(event) => setRegistrationNo(event.target.value)}
          placeholder={labels.registrationPlaceholder}
          className={inputClass}
          required
          minLength={2}
          maxLength={60}
        />
      </label>

      <label className="flex flex-col gap-1 text-sm text-text-2">
        {labels.tpinLabel}
        <input
          type="text"
          value={tpin}
          onChange={(event) => setTpin(event.target.value)}
          placeholder={labels.tpinPlaceholder}
          className={inputClass}
          maxLength={20}
        />
      </label>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {submitted ? (
        <p role="status" className="text-sm text-primary">
          {labels.submitted}
        </p>
      ) : null}

      <Button type="submit" loading={submitting} loadingLabel={labels.submitting}>
        {isResubmit ? labels.resubmit : labels.submit}
      </Button>
    </form>
  );
}

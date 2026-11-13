"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { useSession } from "../../../../../../lib/customer-session";

import { ServicePayments } from "./service-payments";

type ConfirmResponse = {
  job_id: string;
  order_id: string;
  status: string;
  already_confirmed: boolean;
  balance_ngwee: number;
  released: boolean;
};

type CompleteConfirmProps = {
  jobId: string;
  /** True once the provider has marked the job complete (confirm is otherwise blocked). */
  providerMarked?: boolean;
  /** Allows the current customer page to attempt confirm; the API still rejects before provider mark. */
  allowConfirmAttempt?: boolean;
  onConfirmed?: () => void;
};

export function CompleteConfirm({
  jobId,

  providerMarked = false,
  allowConfirmAttempt = false,
  onConfirmed,
}: CompleteConfirmProps) {
  const t = useTranslations("services.completion.customer");
  const { session } = useSession();
  const [submitting, setSubmitting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(
    () => session?.access_token ?? null,
    [session?.access_token],
  );

  const handleConfirm = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      const result = await client.request<ConfirmResponse>(
        `/jobs/${jobId}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      setAcknowledged(true);
      setRefreshKey((value) => value + 1);
      setSubmitting(false);
      if (result.status === "completed") {
        setConfirmed(true);
        onConfirmed?.();
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("errors.notOwner"));
      } else if (err instanceof ApiError && err.status === 409) {
        setError(t("errors.notMarked"));
      } else if (err instanceof ApiError && err.status === 429) {
        setError(t("errors.rateLimited"));
      } else {
        setError(t("errors.generic"));
      }
      setSubmitting(false);
    }
  }, [getToken, jobId, onConfirmed, t]);

  return (
    <section className="mx-auto w-full max-w-[360px] space-y-4 rounded border border-border bg-surface p-4">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("title")}</h3>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      <ServicePayments jobId={jobId} refreshKey={refreshKey} />
      {acknowledged && !confirmed && (
        <p role="status">{t("awaitingPayment")}</p>
      )}

      <p className="rounded bg-bg-2 p-3 text-xs text-text-2">
        {t("escrowNote")}
      </p>

      {confirmed ? (
        <div className="space-y-1">
          <p className="text-sm font-medium text-success">{t("confirmed")}</p>
          <p className="text-xs text-text-2">{t("reviewUnlocked")}</p>
        </div>
      ) : providerMarked || allowConfirmAttempt ? (
        <>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <Button
            type="button"
            variant="primary"
            loading={submitting}
            loadingLabel={t("confirming")}
            disabled={submitting}
            onClick={() => void handleConfirm()}
          >
            {t("confirmCta")}
          </Button>
        </>
      ) : (
        <p className="text-sm text-text-2">{t("awaitingProvider")}</p>
      )}
    </section>
  );
}

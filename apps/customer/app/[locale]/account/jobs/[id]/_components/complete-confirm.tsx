"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

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
  /** Balance (integer ngwee) settled on confirmation — from the accepted quote spine. */
  balanceNgwee: number;
  /** True once the provider has marked the job complete (confirm is otherwise blocked). */
  providerMarked?: boolean;
  onConfirmed?: () => void;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function CompleteConfirm({
  jobId,
  balanceNgwee,
  providerMarked = false,
  onConfirmed,
}: CompleteConfirmProps) {
  const t = useTranslations("services.completion.customer");
  const { session } = useSession();
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const handleConfirm = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      await client.request<ConfirmResponse>(`/jobs/${jobId}/confirm`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setConfirmed(true);
      onConfirmed?.();
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

      <dl className="text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("balanceLabel")}</dt>
          <dd className="font-mono text-lg font-semibold text-display-ink">
            {formatK(balanceNgwee)}
          </dd>
        </div>
      </dl>

      <p className="rounded bg-surface-2 p-3 text-xs text-text-2">{t("escrowNote")}</p>

      {confirmed ? (
        <div className="space-y-1">
          <p className="text-sm font-medium text-success">{t("confirmed")}</p>
          <p className="text-xs text-text-2">{t("reviewUnlocked")}</p>
        </div>
      ) : providerMarked ? (
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
            {t("confirmCta", { amount: formatK(balanceNgwee) })}
          </Button>
        </>
      ) : (
        <p className="text-sm text-text-2">{t("awaitingProvider")}</p>
      )}
    </section>
  );
}

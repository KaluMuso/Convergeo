"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

export const DEFAULT_DEPOSIT_PCT = 50;

type AcceptResponse = {
  checkout_group_id: string;
  order_id: string;
  deposit_ngwee: number;
  balance_ngwee: number;
  total_job_ngwee: number;
};

type AcceptFlowProps = {
  locale: string;
  jobId: string;
  quoteId: string;
  vendorName: string;
  totalNgwee: number;
  onCancel?: () => void;
};

/** Half-up integer ngwee — mirrors the server deposit math for a consistent preview. */
export function previewDepositNgwee(totalNgwee: number, depositPct: number): number {
  return Math.floor((totalNgwee * depositPct + 50) / 100);
}

export function AcceptFlow({
  locale,
  jobId,
  quoteId,
  vendorName,
  totalNgwee,
  onCancel,
}: AcceptFlowProps) {
  const t = useTranslations("services.accept");
  const { session } = useSession();
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const handleAccept = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      const result = await client.request<AcceptResponse>(
        `/jobs/${jobId}/quotes/${quoteId}/accept`,
        { method: "POST", body: JSON.stringify({}) },
      );
      // Hand off to the group checkout; it shows the amount the API set for this group
      // (pilot: 100% upfront) — the client never computes the deposit itself.
      router.push(`/${locale}/checkout?group=${encodeURIComponent(result.checkout_group_id)}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("errors.notOwner"));
      } else if (err instanceof ApiError && (err.status === 409 || err.status === 422)) {
        setError(t("errors.invalidStatus"));
      } else if (err instanceof ApiError && err.status === 429) {
        setError(t("errors.rateLimited"));
      } else {
        setError(t("errors.generic"));
      }
      setSubmitting(false);
    }
  }, [getToken, jobId, quoteId, locale, router, t]);

  return (
    <section className="space-y-4 rounded border border-border bg-surface p-4">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("title")}</h3>
        <p className="text-sm text-text-2">{t("payIntro", { vendor: vendorName })}</p>
      </header>

      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("totalLabel")}</dt>
          <dd className="font-mono text-display-ink">{formatK(totalNgwee)}</dd>
        </div>
      </dl>

      <p className="rounded bg-bg-2 p-3 text-xs text-text-2">{t("escrowNote")}</p>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="primary"
          loading={submitting}
          loadingLabel={t("submitting")}
          disabled={submitting}
          onClick={() => void handleAccept()}
        >
          {t("payCta")}
        </Button>
        {onCancel ? (
          <Button
            type="button"
            variant="secondary"
            disabled={submitting}
            loadingLabel={t("cancel")}
            onClick={onCancel}
          >
            {t("cancel")}
          </Button>
        ) : null}
      </div>
    </section>
  );
}

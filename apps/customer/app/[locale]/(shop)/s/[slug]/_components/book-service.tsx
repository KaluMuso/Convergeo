"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

const DEFAULT_DEPOSIT_PCT = 50;

type BookResponse = {
  checkout_group_id: string;
  deposit_ngwee: number;
  balance_ngwee: number;
  total_job_ngwee: number;
};

type BookServiceProps = {
  locale: string;
  serviceId: string;
  priceNgwee: number;
  /** Admin-tunable server default; used only for the pre-book preview. */
  depositPct?: number;
};

/** Half-up integer ngwee — mirrors the server deposit math for a consistent preview. */
function previewDepositNgwee(totalNgwee: number, depositPct: number): number {
  return Math.floor((totalNgwee * depositPct + 50) / 100);
}

/**
 * Direct-booking CTA on the service detail page (shown only for bookable
 * services, alongside the RFQ "request a quote" path). Books at the fixed price
 * and hands off to the standard deposit checkout — the same flow RFQ accept uses.
 */
export function BookService({
  locale,
  serviceId,
  priceNgwee,
  depositPct = DEFAULT_DEPOSIT_PCT,
}: BookServiceProps) {
  const t = useTranslations("services.booking");
  const { session } = useSession();
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // One idempotency key per booking attempt, reused across retries so a retried
  // POST can never create a second booking/order.
  const idempotencyKeyRef = useRef<string | null>(null);

  const depositNgwee = useMemo(
    () => previewDepositNgwee(priceNgwee, depositPct),
    [priceNgwee, depositPct],
  );
  const balanceNgwee = priceNgwee - depositNgwee;

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const handleBook = useCallback(async () => {
    if (!session) {
      setError(t("errors.authRequired"));
      return;
    }
    setSubmitting(true);
    setError(null);
    if (!idempotencyKeyRef.current) {
      idempotencyKeyRef.current = crypto.randomUUID();
    }
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      const result = await client.request<BookResponse>(`/services/${serviceId}/book`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: idempotencyKeyRef.current }),
      });
      router.push(`/${locale}/checkout?session=${result.checkout_group_id}&kind=service_deposit`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(t("errors.authRequired"));
      } else if (err instanceof ApiError && err.status === 409) {
        setError(t("errors.notBookable"));
      } else if (err instanceof ApiError && err.status === 422) {
        setError(t("errors.ownService"));
      } else if (err instanceof ApiError && err.status === 429) {
        setError(t("errors.rateLimited"));
      } else {
        setError(t("errors.generic"));
      }
      setSubmitting(false);
    }
  }, [session, t, getToken, serviceId, router, locale]);

  return (
    <section className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-1">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("title")}</h3>
        <p className="text-sm text-text-2">{t("intro", { pct: depositPct })}</p>
      </header>

      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("priceLabel")}</dt>
          <dd className="font-mono text-display-ink">{formatK(priceNgwee)}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("depositLabel")}</dt>
          <dd className="font-mono text-lg font-semibold text-display-ink">
            {formatK(depositNgwee)}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("balanceLabel")}</dt>
          <dd className="font-mono text-display-ink">{formatK(balanceNgwee)}</dd>
        </div>
      </dl>

      <p className="rounded bg-bg-2 p-3 text-xs text-text-2">{t("escrowNote")}</p>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <Button
        type="button"
        variant="primary"
        loading={submitting}
        loadingLabel={t("submitting")}
        disabled={submitting}
        onClick={() => void handleBook()}
      >
        {t("bookCta", { amount: formatK(depositNgwee) })}
      </Button>
    </section>
  );
}

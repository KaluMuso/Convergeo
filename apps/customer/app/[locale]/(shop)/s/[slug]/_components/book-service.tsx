"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { customerAuth, useSession } from "../../../../../../lib/customer-session";

const DEFAULT_DEPOSIT_PCT = 50;

type BookResponse = {
  job_id: string;
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
 * and hands off to the job's authorized funding surface, as RFQ accept does.
 */
export function BookService(props: BookServiceProps) {
  const { session, generation } = useSession();
  return (
    <IdentityBookService
      key={`${generation}:${session?.user.id}:${props.locale}:${props.serviceId}`}
      {...props}
      authGeneration={generation}
      userId={session?.user.id}
    />
  );
}

function IdentityBookService({
  locale,
  serviceId,
  priceNgwee,
  depositPct = DEFAULT_DEPOSIT_PCT,
  authGeneration,
  userId,
}: BookServiceProps & { authGeneration: number; userId?: string }) {
  const t = useTranslations("services.booking");
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // One idempotency key per booking attempt, reused across retries so a retried
  // POST can never create a second booking/order.
  const idempotencyKeyRef = useRef<string | null>(null);
  const active = useRef(false);
  const inFlight = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const isCurrent = useCallback(() => {
    const auth = customerAuth.snapshot();
    return (
      active.current &&
      !auth.loading &&
      !auth.error &&
      auth.generation === authGeneration &&
      auth.session?.user.id === userId
    );
  }, [authGeneration, userId]);

  const depositNgwee = useMemo(
    () => previewDepositNgwee(priceNgwee, depositPct),
    [priceNgwee, depositPct],
  );
  const balanceNgwee = priceNgwee - depositNgwee;

  const getToken = useCallback(
    () => (isCurrent() ? (customerAuth.snapshot().session?.access_token ?? null) : null),
    [isCurrent],
  );

  const handleBook = useCallback(async () => {
    if (!userId) {
      setError(t("errors.authRequired"));
      return;
    }
    if (!isCurrent() || inFlight.current) return;
    inFlight.current = true;
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
      if (!isCurrent()) return;
      if (
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
          result.job_id ?? "",
        )
      )
        throw new Error("booking_job_missing");
      router.push(`/${locale}/account/jobs/${encodeURIComponent(result.job_id)}`);
    } catch (err) {
      if (!isCurrent()) return;
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
      inFlight.current = false;
    }
  }, [userId, isCurrent, t, getToken, serviceId, router, locale]);

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

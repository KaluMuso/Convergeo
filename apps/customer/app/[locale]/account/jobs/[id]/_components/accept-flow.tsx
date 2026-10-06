"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";
import { customerAuth, useSession } from "../../../../../../lib/customer-session";

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
  /** Admin-tunable server default; used only for the pre-accept preview. */
  depositPct?: number;
  onCancel?: () => void;
  onPendingChange?: (pending: boolean) => void;
};

/** Half-up integer ngwee — mirrors the server deposit math for a consistent preview. */
export function previewDepositNgwee(totalNgwee: number, depositPct: number): number {
  return Math.floor((totalNgwee * depositPct + 50) / 100);
}

export function AcceptFlow({ locale, jobId, quoteId, ...props }: AcceptFlowProps) {
  const { session, generation } = useSession();
  if (!session) return null;

  return (
    <ActiveAcceptFlow
      key={`${generation}:${session.user.id}:${locale}:${jobId}:${quoteId}`}
      locale={locale}
      jobId={jobId}
      quoteId={quoteId}
      accessToken={session.access_token}
      authGeneration={generation}
      userId={session.user.id}
      {...props}
    />
  );
}

function ActiveAcceptFlow({
  locale,
  jobId,
  quoteId,
  vendorName,
  totalNgwee,
  depositPct = DEFAULT_DEPOSIT_PCT,
  onCancel,
  onPendingChange,
  accessToken,
  authGeneration,
  userId,
}: AcceptFlowProps & {
  accessToken: string;
  authGeneration: number;
  userId: string;
}) {
  const t = useTranslations("services.accept");
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef(false);
  const acceptInFlight = useRef(false);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const isCurrent = useCallback(() => {
    const auth = customerAuth.snapshot();
    return active.current && auth.generation === authGeneration && auth.session?.user.id === userId;
  }, [authGeneration, userId]);

  const depositNgwee = useMemo(
    () => previewDepositNgwee(totalNgwee, depositPct),
    [totalNgwee, depositPct],
  );
  const balanceNgwee = totalNgwee - depositNgwee;

  const getToken = useCallback(() => accessToken, [accessToken]);

  const handleAccept = useCallback(async () => {
    if (!isCurrent() || acceptInFlight.current) return;
    acceptInFlight.current = true;
    setSubmitting(true);
    setError(null);
    onPendingChange?.(true);
    try {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
      const result = await client.request<AcceptResponse>(
        `/jobs/${jobId}/quotes/${quoteId}/accept`,
        { method: "POST", body: JSON.stringify({}) },
      );
      // The server may have accepted the quote even if this view has gone away.
      if (!isCurrent()) return;
      router.push(`/${locale}/checkout?session=${result.checkout_group_id}&kind=service_deposit`);
    } catch (err) {
      if (!isCurrent()) return;
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
      acceptInFlight.current = false;
      onPendingChange?.(false);
    }
  }, [getToken, isCurrent, jobId, quoteId, locale, onPendingChange, router, t]);

  return (
    <section className="space-y-4 rounded border border-border bg-surface p-4">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("title")}</h3>
        <p className="text-sm text-text-2">{t("intro", { pct: depositPct, vendor: vendorName })}</p>
      </header>

      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("totalLabel")}</dt>
          <dd className="font-mono text-display-ink">{formatK(totalNgwee)}</dd>
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

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="primary"
          loading={submitting}
          loadingLabel={t("submitting")}
          disabled={submitting}
          onClick={() => void handleAccept()}
        >
          {t("confirmCta", { amount: formatK(depositNgwee) })}
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

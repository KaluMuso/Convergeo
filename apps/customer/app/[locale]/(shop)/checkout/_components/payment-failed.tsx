"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";

export type PaymentFailedLabels = {
  timeoutTitle: string;
  timeoutBody: string;
  retry: string;
  retrying: string;
  retryError: string;
  cancelledTitle: string;
  cancelledBody: string;
  cancelledCta: string;
};

type PaymentFailedProps = {
  locale: string;
  amountNgwee: number;
  variant: "failed" | "expired" | "cancelled";
  labels: PaymentFailedLabels;
  loading?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  onBackToCheckout?: () => void;
};

export function PaymentFailed({
  locale,
  amountNgwee,
  variant,
  labels,
  loading = false,
  errorMessage,
  onRetry,
  onBackToCheckout,
}: PaymentFailedProps) {
  const amountLocale = `${locale}-ZM`;
  const formattedAmount = formatK(amountNgwee, { locale: amountLocale });
  const isCancelled = variant === "cancelled";

  const title = isCancelled ? labels.cancelledTitle : labels.timeoutTitle;
  const body = isCancelled
    ? labels.cancelledBody
    : labels.timeoutBody.replace("{amount}", formattedAmount);

  return (
    <div
      className="space-y-5 rounded-card border border-danger/30 bg-surface p-5"
      role="alert"
      data-testid={`payment-${variant}`}
    >
      <div className="space-y-2">
        <h2 className="font-display text-h2 text-display-ink">{title}</h2>
        <p className="font-body text-sm text-text-2">{body}</p>
      </div>

      {errorMessage ? (
        <p className="font-body text-sm text-danger" data-testid="payment-failed-error">
          {errorMessage}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        {isCancelled ? (
          <Button
            type="button"
            size="lg"
            className="w-full"
            variant="secondary"
            loading={false}
            loadingLabel={labels.cancelledCta}
            onClick={onBackToCheckout}
          >
            {labels.cancelledCta}
          </Button>
        ) : (
          <Button
            type="button"
            size="lg"
            className="w-full"
            loading={loading}
            loadingLabel={labels.retrying}
            onClick={onRetry}
            data-testid="payment-retry-button"
          >
            {labels.retry}
          </Button>
        )}
      </div>
    </div>
  );
}

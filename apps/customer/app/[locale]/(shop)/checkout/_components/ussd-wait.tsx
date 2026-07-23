"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { Spinner } from "@vergeo/ui/src/spinner";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { resolveApiBaseUrl } from "../../../../../lib/api-base-url";
import { resolveMomoPollOutcome } from "../_lib/payment-outcome";

import { PaymentFailed, type PaymentFailedLabels } from "./payment-failed";

export type PaymentStatusPayload = {
  checkout_group_id: string;
  payment_id: string | null;
  status: string;
  amount_ngwee: number;
  rail: string | null;
  cod: boolean;
  order_id: string;
  payer_phone: string | null;
};

export type PendingLabels = {
  pageTitle: string;
  loading: string;
  error: string;
  pollAria: string;
  /** Honest confirming copy — never claims paid without order confirmation. */
  successRedirect: string;
  confirmingTitle: string;
  confirmingBody: string;
  codTitle: string;
  codBody: string;
  codCta: string;
  viewOrder: string;
  ussd: UssdWaitLabels;
  failed: PaymentFailedLabels;
};

export type UssdWaitLabels = {
  title: string;
  subtitle: string;
  amountLabel: string;
  mtnHelp: string;
  airtelHelp: string;
  genericHelp: string;
  waiting: string;
  doNotClose: string;
  pollAria: string;
};

type UssdWaitProps = {
  locale: string;
  amountNgwee: number;
  rail: string | null;
  labels: UssdWaitLabels;
};

const INITIAL_POLL_MS = 2000;
const MAX_POLL_MS = 15000;

function getApiBaseUrl(): string | null {
  return resolveApiBaseUrl();
}

function nextPollDelay(attempt: number): number {
  const delay = INITIAL_POLL_MS * 2 ** attempt;
  return Math.min(delay, MAX_POLL_MS);
}

function railHelp(rail: string | null, amount: string, labels: UssdWaitLabels): string {
  if (rail === "mtn") {
    return labels.mtnHelp.replace("{amount}", amount);
  }
  if (rail === "airtel") {
    return labels.airtelHelp.replace("{amount}", amount);
  }
  return labels.genericHelp.replace("{amount}", amount);
}

export function UssdWait({ locale, amountNgwee, rail, labels }: UssdWaitProps) {
  const amountLocale = `${locale}-ZM`;
  const formattedAmount = formatK(amountNgwee, { locale: amountLocale });

  return (
    <div
      className="space-y-5 rounded-card border border-border bg-surface p-5"
      aria-live="polite"
      aria-busy="true"
      aria-label={labels.pollAria}
      data-testid="ussd-wait"
    >
      <div className="flex flex-col items-center gap-4 text-center">
        <Spinner label={labels.waiting} size="lg" />
        <div className="space-y-1">
          <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
          <p className="font-body text-sm text-text-2">
            {labels.subtitle.replace("{amount}", formattedAmount)}
          </p>
        </div>
      </div>

      <div className="rounded-card border border-primary/20 bg-primary/5 px-4 py-3 text-center">
        <p className="font-body text-xs uppercase tracking-wide text-text-3">
          {labels.amountLabel}
        </p>
        <p className="font-mono text-2xl font-semibold text-text">{formattedAmount}</p>
      </div>

      <p className="font-body text-sm text-text-2">{railHelp(rail, formattedAmount, labels)}</p>
      <p className="font-body text-xs text-text-3">{labels.doNotClose}</p>
    </div>
  );
}

type PendingPaymentShellProps = {
  locale: string;
  groupId: string;
  labels: PendingLabels;
};

export function PendingPaymentShell({ locale, groupId, labels }: PendingPaymentShellProps) {
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [statusPayload, setStatusPayload] = useState<PaymentStatusPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const pollAttemptRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const orderPath = statusPayload
    ? `/${locale}/account/orders/${statusPayload.order_id}`
    : `/${locale}/account/orders`;
  const checkoutPath = `/${locale}/checkout`;

  const fetchStatus = useCallback(async (): Promise<PaymentStatusPayload | null> => {
    const token = session?.access_token;
    const apiBase = getApiBaseUrl();
    if (!token || !apiBase) {
      return null;
    }
    const client = createApiClient({
      baseUrl: apiBase,
      getToken: () => token,
    });
    return client.request<PaymentStatusPayload>(`/payments/status?group=${groupId}`);
  }, [groupId, session?.access_token]);

  const schedulePoll = useCallback((fetcher: () => Promise<void>) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    const delay = nextPollDelay(pollAttemptRef.current);
    timeoutRef.current = setTimeout(() => {
      pollAttemptRef.current += 1;
      void fetcher();
    }, delay);
  }, []);

  useEffect(() => {
    if (sessionLoading || !session?.access_token) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        if (!getApiBaseUrl()) {
          if (!cancelled) {
            setLoadError(labels.error);
          }
          return;
        }
        const payload = await fetchStatus();
        if (cancelled || !payload) {
          return;
        }
        setStatusPayload(payload);
        setLoadError(null);

        const outcome = resolveMomoPollOutcome(payload);
        if (outcome === "confirming") {
          // Redirect to the order page (real escrow/payment state) — do not
          // claim a standalone "paid" success without ledger confirmation.
          router.replace(
            payload.order_id
              ? `/${locale}/account/orders/${payload.order_id}`
              : `/${locale}/account/orders`,
          );
          return;
        }

        if (outcome === "cod") {
          return;
        }

        if (outcome === "waiting") {
          schedulePoll(poll);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError && error.code === "forbidden") {
          setLoadError(labels.error);
          return;
        }
        setLoadError(labels.error);
      }
    };

    pollAttemptRef.current = 0;
    void poll();

    return () => {
      cancelled = true;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [
    fetchStatus,
    labels.error,
    locale,
    router,
    schedulePoll,
    session?.access_token,
    sessionLoading,
  ]);

  useEffect(() => {
    if (!statusPayload?.cod) {
      return;
    }
    const timer = setTimeout(() => {
      router.replace(orderPath);
    }, 2500);
    return () => clearTimeout(timer);
  }, [orderPath, router, statusPayload?.cod]);

  const handleRetry = async () => {
    const token = session?.access_token;
    const apiBase = getApiBaseUrl();
    if (!token || !statusPayload || !apiBase) {
      return;
    }
    setRetrying(true);
    setRetryError(null);
    try {
      const client = createApiClient({
        baseUrl: apiBase,
        getToken: () => token,
      });
      const result = await client.request<{
        payment_id: string;
        status: string;
        order_count: number;
      }>("/payments/retry", {
        method: "POST",
        body: JSON.stringify({
          checkout_group_id: groupId,
          payer_number: statusPayload.payer_phone,
        }),
      });
      setStatusPayload({
        ...statusPayload,
        payment_id: result.payment_id,
        status: result.status,
      });
      pollAttemptRef.current = 0;
    } catch {
      setRetryError(labels.failed.retryError);
    } finally {
      setRetrying(false);
    }
  };

  if (sessionLoading || (!statusPayload && !loadError)) {
    return (
      <div className="space-y-4" aria-live="polite">
        <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
        <div className="flex items-center gap-3">
          <Spinner label={labels.loading} />
          <p className="font-body text-sm text-text-3">{labels.loading}</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-4" data-testid="payment-status-error">
        <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
        <p role="alert" className="font-body text-sm text-danger">
          {loadError}
        </p>
      </div>
    );
  }

  if (!statusPayload) {
    return null;
  }

  const amountLocale = `${locale}-ZM`;
  const formattedAmount = formatK(statusPayload.amount_ngwee, { locale: amountLocale });

  if (statusPayload.cod) {
    return (
      <div className="space-y-5" data-testid="payment-cod">
        <h1 className="font-display text-h1 text-display-ink">{labels.codTitle}</h1>
        <div className="space-y-4 rounded-card border border-border bg-surface p-5">
          <p className="font-body text-sm text-text-2">
            {labels.codBody.replace("{amount}", formattedAmount)}
          </p>
          <LinkButton
            href={orderPath}
            variant="primary"
            size="lg"
            className="w-full"
            LinkComponent={Link}
          >
            {labels.codCta}
          </LinkButton>
        </div>
      </div>
    );
  }

  if (statusPayload.status === "success") {
    // Brief confirming state while navigation completes — never a "paid" claim.
    return (
      <div className="space-y-4" data-testid="payment-confirming">
        <h1 className="font-display text-h1 text-display-ink">{labels.confirmingTitle}</h1>
        <p className="font-body text-sm text-text-2">{labels.confirmingBody}</p>
        <Spinner label={labels.confirmingBody} />
      </div>
    );
  }

  if (statusPayload.status === "cancelled") {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
        <PaymentFailed
          locale={locale}
          amountNgwee={statusPayload.amount_ngwee}
          variant="cancelled"
          labels={labels.failed}
          onBackToCheckout={() => router.push(checkoutPath)}
        />
      </div>
    );
  }

  if (statusPayload.status === "failed" || statusPayload.status === "expired") {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
        <PaymentFailed
          locale={locale}
          amountNgwee={statusPayload.amount_ngwee}
          variant={statusPayload.status === "expired" ? "expired" : "failed"}
          labels={labels.failed}
          loading={retrying}
          errorMessage={retryError}
          onRetry={() => void handleRetry()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
      <UssdWait
        locale={locale}
        amountNgwee={statusPayload.amount_ngwee}
        rail={statusPayload.rail}
        labels={labels.ussd}
      />
    </div>
  );
}

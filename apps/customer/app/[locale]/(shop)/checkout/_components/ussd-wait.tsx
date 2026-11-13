"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { Spinner } from "@vergeo/ui/src/spinner";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { resolveApiBaseUrl } from "../../../../../lib/api-base-url";
import { useSession } from "../../../../../lib/customer-session";
import { resolveMomoPollOutcome } from "../_lib/payment-outcome";

import { NextSteps } from "./next-steps";
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
  ticketUnavailableBody: string;
  ussd: UssdWaitLabels;
  failed: PaymentFailedLabels;
  /** UX pass 4 — COD confirmation detail. Templates use {amount}. */
  codConfirmation?: CodConfirmationLabels;
};

export type CodConfirmationLabels = {
  orderNumberLabel: string;
  amountDueLabel: string;
  nextTitle: string;
  step1Title: string;
  step1Body: string;
  step2Title: string;
  step2Body: string;
  step3Title: string;
  step3Body: string;
  helpTitle: string;
  helpBody: string;
  contactCta: string;
  continueShopping: string;
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
  ticketCheckout?: boolean;
  /**
   * Server-created groups (paid ticket / service deposit) land somewhere other than
   * the order page on success (ticket wallet / job thread) and return to
   * `/checkout?group=` rather than the cart checkout. Omitted for cart checkouts.
   */
  groupRoutes?: { success: string; checkout: string };
};

export function PendingPaymentShell({
  locale,
  groupId,
  labels,
  ticketCheckout = false,
  groupRoutes,
}: PendingPaymentShellProps) {
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
  const checkoutPath = groupRoutes?.checkout ?? `/${locale}/checkout`;
  const successPath = groupRoutes?.success ?? null;

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
          // Stop polling and hand the buyer to the effect below. Navigation
          // deliberately does NOT happen here — see the redirect effect.
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
    // `locale`/`router` are deliberately absent: this effect no longer
    // navigates. Redirecting is the separate, state-driven effect below.
  }, [fetchStatus, labels.error, schedulePoll, session?.access_token, sessionLoading]);

  /**
   * Provider success -> authoritative order state, in two committed steps.
   *
   * This used to live inside the polling effect: `setStatusPayload(payload)`
   * and `router.replace(...)` were issued back to back in the same callback,
   * so navigation could begin before React had committed the state that
   * renders the honest `payment-confirming` surface. The buyer could be moved
   * off the pending page without that surface ever entering the DOM, which
   * breaks the contract the E2E certification asserts and, worse, hides the
   * one screen that tells the truth about where the money is.
   *
   * Splitting it fixes the ordering by construction rather than by timing:
   * the poll only records the payload, React commits and paints the
   * `payment-confirming` branch below, and THEN this effect runs and
   * navigates. No sleep, no timer, no artificial delay for Playwright — the
   * effect is exactly React's "after the render this state produced" hook.
   *
   * Both contracts are preserved: the confirming surface is still not a
   * "paid" claim (resolveMomoPollOutcome never returns success), and the
   * authoritative order route is still where the buyer lands.
   */
  useEffect(() => {
    if (!statusPayload) {
      return;
    }
    // One outcome rule, one place: resolveMomoPollOutcome already returns
    // "cod" for a COD group, so the COD timer below stays the only COD path.
    if (resolveMomoPollOutcome(statusPayload) !== "confirming") {
      return;
    }
    router.replace(
      successPath ??
        (statusPayload.order_id
          ? `/${locale}/account/orders/${statusPayload.order_id}`
          : `/${locale}/account/orders`),
    );
  }, [locale, router, statusPayload, successPath]);

  // COD no longer auto-redirects to the order page (UX pass 4): the buyer
  // needs time to read the order number and what happens next. The
  // confirmation offers explicit links to the order and to keep shopping.

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
  const formattedAmount = formatK(statusPayload.amount_ngwee, {
    locale: amountLocale,
  });

  if (statusPayload.cod) {
    const cod = labels.codConfirmation;
    const orderNumber = statusPayload.order_id
      ? statusPayload.order_id.slice(0, 8).toUpperCase()
      : null;
    return (
      <div className="space-y-5" data-testid="payment-cod">
        <h1 className="font-display text-h1 text-display-ink">{labels.codTitle}</h1>
        <div className="space-y-4 rounded-card border border-border bg-surface p-5">
          {cod && orderNumber ? (
            <dl className="grid grid-cols-2 gap-3" data-testid="payment-cod-summary">
              <div className="space-y-0.5">
                <dt className="font-body text-xs text-text-2">{cod.orderNumberLabel}</dt>
                <dd
                  className="font-mono text-h3 font-semibold tracking-wide text-display-ink"
                  data-testid="payment-cod-order-number"
                >
                  {orderNumber}
                </dd>
              </div>
              <div className="space-y-0.5">
                <dt className="font-body text-xs text-text-2">{cod.amountDueLabel}</dt>
                <dd className="font-mono text-h3 font-semibold text-[var(--price)]">
                  {formattedAmount}
                </dd>
              </div>
            </dl>
          ) : null}
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
        {cod ? (
          <>
            <NextSteps
              heading={cod.nextTitle}
              headingId="payment-cod-next"
              headingAs="h2"
              activeIndex={-1}
              testId="payment-cod-next-steps"
              steps={[
                { title: cod.step1Title, body: cod.step1Body },
                { title: cod.step2Title, body: cod.step2Body },
                {
                  title: cod.step3Title,
                  body: cod.step3Body.split("{amount}").join(formattedAmount),
                },
              ]}
            />
            <section
              aria-labelledby="payment-cod-help"
              className="space-y-2 rounded-card border border-border bg-bg-2 p-4"
            >
              <h2 id="payment-cod-help" className="font-body text-sm font-semibold text-text">
                {cod.helpTitle}
              </h2>
              <p className="font-body text-sm text-text-2">{cod.helpBody}</p>
              <Link
                href={`/${locale}/contact`}
                className="inline-flex min-h-11 items-center font-body text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
              >
                {cod.contactCta}
              </Link>
            </section>
            <LinkButton
              href={`/${locale}`}
              variant="secondary"
              size="lg"
              className="w-full"
              LinkComponent={Link}
            >
              {cod.continueShopping}
            </LinkButton>
          </>
        ) : null}
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

  if (
    ticketCheckout &&
    (statusPayload.status === "cancelled" || statusPayload.status === "expired")
  ) {
    return (
      <div
        className="space-y-4 rounded-card border border-danger/30 bg-surface p-5"
        role="alert"
        data-testid="ticket-payment-unavailable"
      >
        <h1 className="font-display text-h1 text-display-ink">
          {statusPayload.status === "cancelled"
            ? labels.failed.cancelledTitle
            : labels.failed.timeoutTitle}
        </h1>
        <p className="font-body text-sm text-text-2">{labels.ticketUnavailableBody}</p>
        <LinkButton
          href={orderPath}
          variant="secondary"
          size="lg"
          className="w-full"
          LinkComponent={Link}
        >
          {labels.viewOrder}
        </LinkButton>
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

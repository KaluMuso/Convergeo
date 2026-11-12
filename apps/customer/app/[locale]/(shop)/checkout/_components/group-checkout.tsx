"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { useSession } from "../../../../../lib/customer-session";
import {
  groupPaths,
  isUuid,
  resumeTarget,
  type CheckoutGroupSummary,
  type GroupPaymentStatus,
} from "../_lib/group-checkout";

import { StepPayment, type ValidatedPayment } from "./step-payment";

import type { CheckoutShellLabels } from "./step-fulfilment";

export type GroupCheckoutLabels = {
  pageTitle: string;
  loading: string;
  error: string;
  loginRequired: string;
  forbidden: string;
  notFound: string;
  expired: string;
  notPayable: string;
  ticketHeading: string;
  serviceHeading: string;
  providerLabel: string;
  tierLineTemplate: string;
  subtotal: string;
  platformFee: string;
  total: string;
  serviceNote: string;
  payCtaTemplate: string;
  viewOrder: string;
  escrowTitle: string;
  escrowSteps: [string, string, string];
  /** Shell-shaped (serialisable) payment labels; templates are filled client-side. */
  payment: CheckoutShellLabels["payment"];
};

type Phase =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "closed"; message: string; summary: CheckoutGroupSummary }
  | { kind: "ready"; summary: CheckoutGroupSummary };

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

function formatWhen(iso: string | null, locale: string): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat(`${locale}-ZM`, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  } catch {
    return date.toISOString();
  }
}

export function GroupCheckout({
  locale,
  groupId,
  labels,
}: {
  locale: string;
  groupId: string | null;
  labels: GroupCheckoutLabels;
}) {
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const accessToken = session?.access_token ?? null;
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const money = (ngwee: number) => formatK(ngwee, { locale: `${locale}-ZM` });
  const paymentLabels = useMemo(() => {
    const { codIneligibleTemplate, ...rest } = labels.payment;
    return {
      ...rest,
      codIneligible: (cap: string) => fill(codIneligibleTemplate, { cap }),
    };
  }, [labels.payment]);

  useEffect(() => {
    if (!isUuid(groupId)) {
      setPhase({ kind: "error", message: labels.notFound });
      return;
    }
    if (sessionLoading || !accessToken) return;
    let cancelled = false;
    setPhase({ kind: "loading" });
    const api = createApiClient({
      baseUrl: getApiBaseUrl(),
      getToken: () => accessToken,
    });
    void (async () => {
      try {
        const summary = await api.request<CheckoutGroupSummary>(
          `/checkout/groups/${encodeURIComponent(groupId)}`,
        );
        if (summary.checkout_group_id !== groupId) throw new Error("group mismatch");
        const paths = groupPaths(locale, groupId, summary.kind, summary.service?.job_id ?? null);
        let status: GroupPaymentStatus | null = null;
        try {
          status = await api.request<GroupPaymentStatus>(
            `/payments/status?group=${encodeURIComponent(groupId)}`,
          );
        } catch (cause) {
          if (!(cause instanceof ApiError && cause.code === "payment.not_found")) throw cause;
        }
        if (cancelled) return;
        // A refresh mid-payment resumes the live attempt instead of starting another.
        const resume = resumeTarget(status, paths);
        if (resume) {
          router.replace(resume);
          return;
        }
        if (summary.expired) {
          setPhase({ kind: "closed", message: labels.expired, summary });
        } else if (!summary.payable) {
          setPhase({ kind: "closed", message: labels.notPayable, summary });
        } else {
          setPhase({ kind: "ready", summary });
        }
      } catch (cause) {
        if (cancelled) return;
        const message =
          cause instanceof ApiError && cause.status === 403
            ? labels.forbidden
            : cause instanceof ApiError && cause.status === 404
              ? labels.notFound
              : labels.error;
        setPhase({ kind: "error", message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    accessToken,
    groupId,
    labels.error,
    labels.expired,
    labels.forbidden,
    labels.notFound,
    labels.notPayable,
    locale,
    router,
    sessionLoading,
  ]);

  const summary = phase.kind === "ready" || phase.kind === "closed" ? phase.summary : null;
  const paths = useMemo(
    () =>
      summary && groupId
        ? groupPaths(locale, groupId, summary.kind, summary.service?.job_id ?? null)
        : null,
    [groupId, locale, summary],
  );

  const startPayment = async (payment: ValidatedPayment) => {
    if (!summary || !paths || !accessToken) throw new Error("not ready");
    const api = createApiClient({
      baseUrl: getApiBaseUrl(),
      getToken: () => accessToken,
    });
    if (payment.method === "card") {
      const card = await api.request<{
        checkout_group_id: string;
        payment_id: string;
      }>("/payments/card/session", {
        method: "POST",
        body: JSON.stringify({ checkout_group_id: summary.checkout_group_id }),
      });
      if (card.checkout_group_id !== summary.checkout_group_id || !isUuid(card.payment_id)) {
        throw new Error("card session mismatch");
      }
      router.replace(paths.card(card.payment_id));
      return;
    }
    const started = await api.request<{
      checkout_group_id: string;
      payment_id: string;
    }>("/payments/retry", {
      method: "POST",
      body: JSON.stringify({
        checkout_group_id: summary.checkout_group_id,
        payer_number: payment.payer_number,
        rail: payment.rail,
      }),
    });
    if (started.checkout_group_id !== summary.checkout_group_id) {
      throw new Error("payment attempt mismatch");
    }
    router.replace(paths.pending);
  };

  const heading = <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>;

  if (sessionLoading || (phase.kind === "loading" && accessToken)) {
    return (
      <section className="space-y-4 px-4 py-6" data-testid="group-checkout" aria-busy="true">
        {heading}
        <p className="font-body text-sm text-text-3" aria-live="polite">
          {labels.loading}
        </p>
      </section>
    );
  }

  if (!accessToken && phase.kind !== "error") {
    const next = `/${locale}/checkout?group=${encodeURIComponent(groupId ?? "")}`;
    return (
      <section className="space-y-4 px-4 py-6" data-testid="group-checkout">
        {heading}
        <LinkButton
          href={`/${locale}/login?next=${encodeURIComponent(next)}`}
          variant="primary"
          size="lg"
          className="w-full"
          LinkComponent={Link}
        >
          {labels.loginRequired}
        </LinkButton>
      </section>
    );
  }

  if (phase.kind === "error") {
    return (
      <section className="space-y-4 px-4 py-6" data-testid="group-checkout">
        {heading}
        <p
          role="alert"
          className="font-body text-sm text-danger"
          data-testid="group-checkout-error"
        >
          {phase.message}
        </p>
        <LinkButton
          href={`/${locale}/account/orders`}
          variant="secondary"
          size="lg"
          className="w-full"
          LinkComponent={Link}
        >
          {labels.viewOrder}
        </LinkButton>
      </section>
    );
  }

  if (!summary || !paths) return null;

  const when = formatWhen(summary.event?.starts_at ?? null, locale);

  return (
    <section className="space-y-6 px-4 py-6" data-testid="group-checkout">
      {heading}

      <div
        className="space-y-3 rounded-card border border-border bg-surface p-4"
        data-testid={`group-summary-${summary.kind}`}
      >
        {summary.kind === "ticket" ? (
          <div className="space-y-1">
            <p className="font-body text-xs uppercase tracking-wide text-text-3">
              {labels.ticketHeading}
            </p>
            {summary.event ? (
              <h2 className="font-display text-h3 text-display-ink">{summary.event.title}</h2>
            ) : null}
            {when || summary.event?.venue ? (
              <p className="font-body text-sm text-text-2">
                {[when, summary.event?.venue].filter(Boolean).join(" · ")}
              </p>
            ) : null}
          </div>
        ) : summary.kind === "service_deposit" ? (
          <div className="space-y-1">
            <p className="font-body text-xs uppercase tracking-wide text-text-3">
              {labels.serviceHeading}
            </p>
            {summary.service ? (
              <p className="font-body text-sm text-text">
                {labels.providerLabel}:{" "}
                <span className="font-semibold">{summary.service.vendor_name}</span>
              </p>
            ) : null}
            <p className="font-body text-sm text-text-2">{labels.serviceNote}</p>
          </div>
        ) : null}

        {summary.kind === "ticket" ? (
          <ul className="space-y-1" data-testid="group-lines">
            {summary.lines.map((line) => (
              <li key={line.order_item_id} className="flex justify-between gap-3 text-sm">
                <span className="text-text">
                  {fill(labels.tierLineTemplate, {
                    tier: line.ticket_type_name ?? line.title ?? "",
                    qty: line.qty,
                  })}
                </span>
                <span className="font-mono text-text">{money(line.line_total_ngwee)}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <dl className="space-y-1 border-t border-border pt-3 text-sm">
          {summary.platform_fee_ngwee > 0 ? (
            <>
              <div className="flex justify-between">
                <dt className="text-text-2">{labels.subtotal}</dt>
                <dd className="font-mono text-text">{money(summary.subtotal_ngwee)}</dd>
              </div>
              <div className="flex justify-between" data-testid="group-platform-fee">
                <dt className="text-text-2">{labels.platformFee}</dt>
                <dd className="font-mono text-text">{money(summary.platform_fee_ngwee)}</dd>
              </div>
            </>
          ) : null}
          <div className="flex justify-between">
            <dt className="font-semibold text-text">{labels.total}</dt>
            <dd
              className="font-mono text-lg font-semibold text-display-ink"
              data-testid="group-total"
            >
              {money(summary.total_ngwee)}
            </dd>
          </div>
        </dl>
      </div>

      {phase.kind === "closed" ? (
        <div className="space-y-4">
          <p
            role="alert"
            className="font-body text-sm text-danger"
            data-testid="group-checkout-closed"
          >
            {phase.message}
          </p>
          <LinkButton
            href={paths.success(summary.order_id)}
            variant="secondary"
            size="lg"
            className="w-full"
            LinkComponent={Link}
          >
            {labels.viewOrder}
          </LinkButton>
        </div>
      ) : (
        <>
          <div className="rounded-card bg-bg-2 p-3">
            <p className="font-body text-xs font-semibold text-text">{labels.escrowTitle}</p>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5 font-body text-xs text-text-2">
              {labels.escrowSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
          <StepPayment
            locale={locale}
            sessionId={summary.checkout_group_id}
            accessToken={accessToken ?? ""}
            labels={paymentLabels}
            preset={{
              options: {
                session_id: summary.checkout_group_id,
                subtotal_ngwee: summary.subtotal_ngwee,
                delivery_fee_ngwee: summary.delivery_fee_ngwee,
                total_ngwee: summary.total_ngwee,
                cod_cap_ngwee: 0,
                cod_eligible: false,
              },
              methods: summary.available_methods,
              continueLabel: fill(labels.payCtaTemplate, {
                amount: money(summary.total_ngwee),
              }),
            }}
            onComplete={(payment) => startPayment(payment)}
          />
        </>
      )}
    </section>
  );
}

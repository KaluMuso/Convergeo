"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { dispatchCutoffState, type DispatchCutoffState } from "../../_lib/dispatch-cutoff";
import {
  isBoundByDispatchCutoff,
  needsVendorAction,
  orderNextStep,
  orderTimelineSteps,
  type OrderGuidanceInput,
  type TimelineEventInput,
} from "../_lib/order-guidance";

const CUTOFF_REFRESH_MS = 60_000;

/** Re-evaluates the 14:00 cut-off once a minute (cheap; no network). */
export function useDispatchCutoff(): DispatchCutoffState {
  const [state, setState] = useState<DispatchCutoffState>(() => dispatchCutoffState());
  useEffect(() => {
    const id = window.setInterval(() => setState(dispatchCutoffState()), CUTOFF_REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);
  return state;
}

type DispatchCutoffBannerProps = {
  cutoff: DispatchCutoffState;
  compact?: boolean;
};

export function DispatchCutoffBanner({ cutoff, compact = false }: DispatchCutoffBannerProps) {
  const t = useTranslations("vendor");

  if (cutoff.phase === "after") {
    return (
      <section
        className="rounded-xl border border-border bg-bg-2 p-3 text-sm text-text"
        role="status"
        data-testid="vendor-dispatch-cutoff"
        data-phase="after"
      >
        <p className="font-semibold">{t("queue.cutoff.after")}</p>
        {compact ? null : <p className="mt-1 text-text-2">{t("queue.cutoff.afterBody")}</p>}
      </section>
    );
  }

  const time =
    cutoff.hours > 0
      ? t("queue.cutoff.timeHoursMinutes", { hours: cutoff.hours, minutes: cutoff.minutes })
      : t("queue.cutoff.timeMinutes", { minutes: cutoff.minutes });

  return (
    <section
      className={`rounded-xl border p-3 text-sm text-text ${
        cutoff.urgent ? "border-danger bg-danger/10" : "border-warning/40 bg-warning/10"
      }`}
      role="status"
      data-testid="vendor-dispatch-cutoff"
      data-phase="before"
      data-urgent={cutoff.urgent ? "true" : "false"}
    >
      <p className="font-semibold">{t("queue.cutoff.before", { time })}</p>
      {compact ? null : (
        <p className="mt-1 text-text-2">
          {cutoff.urgent ? t("queue.cutoff.urgentBody") : t("queue.cutoff.beforeBody")}
        </p>
      )}
    </section>
  );
}

/** One-line hint under an order card: what the next step is. */
export function OrderNextStepHint({ order }: { order: OrderGuidanceInput }) {
  const t = useTranslations("vendor");
  const step = orderNextStep(order);
  if (step === "unknown") {
    return null;
  }
  const actionNeeded = needsVendorAction(order);
  return (
    <p
      className={`mt-1 text-xs ${actionNeeded ? "font-medium text-text" : "text-text-3"}`}
      data-testid="vendor-order-next-hint"
    >
      {t(`queue.nextStep.${step}`)}
    </p>
  );
}

type OrderNextStepCardProps = {
  locale: string;
  order: OrderGuidanceInput & { cod: boolean; paid: boolean };
};

/** "What to do now" / "What happens next" — always tells the vendor where they stand. */
export function OrderNextStepCard({ locale, order }: OrderNextStepCardProps) {
  const t = useTranslations("vendor");
  const cutoff = useDispatchCutoff();
  const step = orderNextStep(order);
  const actionNeeded = needsVendorAction(order);
  const showCutoff = isBoundByDispatchCutoff(order) && order.status !== "cancelled";

  return (
    <section
      className={`flex flex-col gap-2 rounded-xl border p-4 ${
        actionNeeded ? "border-primary bg-primary-tint" : "border-border bg-surface"
      }`}
      aria-labelledby="vendor-order-next-heading"
      data-testid="vendor-order-next-step"
      data-step={step}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-text-2">
        {actionNeeded ? t("orders.guide.headingNow") : t("orders.guide.headingNext")}
      </p>
      <h2 id="vendor-order-next-heading" className="text-base font-semibold text-text">
        {t(`orders.guide.steps.${step}.title`)}
      </h2>
      <p className="text-sm text-text-2">{t(`orders.guide.steps.${step}.body`)}</p>
      {step === "awaitCollection" ? (
        <Link
          className="inline-flex min-h-11 items-center self-start rounded-md border border-border bg-surface px-4 text-sm font-medium text-primary"
          href={`/${locale}/scan`}
        >
          {t("orders.guide.scanCta")}
        </Link>
      ) : null}
      {showCutoff ? <DispatchCutoffBanner cutoff={cutoff} compact /> : null}
    </section>
  );
}

/** Explains who handles money on this order — COD especially. */
export function OrderPaymentExplainer({ cod, paid }: { cod: boolean; paid: boolean }) {
  const t = useTranslations("vendor");
  if (cod) {
    return (
      <div className="flex flex-col gap-1 text-sm" data-testid="vendor-order-cod-explainer">
        <p className="text-text">{t("orders.guide.cod.body")}</p>
        <p className="text-text-2">{t("orders.guide.cod.settlement")}</p>
      </div>
    );
  }
  return (
    <p className="text-sm text-text-2" data-testid="vendor-order-payment-explainer">
      {paid ? t("orders.guide.paidExplainer") : t("orders.guide.unpaidExplainer")}
    </p>
  );
}

type OrderStatusTimelineProps = {
  order: OrderGuidanceInput & { timeline: TimelineEventInput[] };
  statusLabel: (status: string) => string;
};

/** Full lifecycle with done / now / next markers (not only past events). */
export function OrderStatusTimeline({ order, statusLabel }: OrderStatusTimelineProps) {
  const t = useTranslations("vendor");
  const format = useFormatter();
  const steps = orderTimelineSteps(order);

  return (
    <section className="flex flex-col gap-3" aria-labelledby="vendor-order-timeline-heading">
      <h2 id="vendor-order-timeline-heading" className="text-sm font-semibold text-text">
        {t("orders.timeline.heading")}
      </h2>
      <ol className="flex flex-col" data-testid="vendor-order-timeline">
        {steps.map((step, index) => {
          const last = index === steps.length - 1;
          const cancelled = step.status === "cancelled";
          const dotClass =
            step.state === "done"
              ? "border-success bg-success"
              : step.state === "current"
                ? cancelled
                  ? "border-danger bg-danger"
                  : "border-primary bg-surface"
                : "border-border bg-surface";
          const stateLabel =
            step.state === "done"
              ? t("orders.timeline.stateDone")
              : step.state === "current"
                ? t("orders.timeline.stateCurrent")
                : t("orders.timeline.stateUpcoming");
          let when: string | null = null;
          if (step.at) {
            const date = new Date(step.at);
            if (!Number.isNaN(date.getTime())) {
              when = format.dateTime(date, {
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
                timeZone: "Africa/Lusaka",
              });
            }
          }
          return (
            <li
              key={step.status}
              className="relative flex gap-3 pb-4 last:pb-0"
              data-step-status={step.status}
              data-step-state={step.state}
              aria-current={step.state === "current" ? "step" : undefined}
            >
              <div className="flex w-4 flex-col items-center">
                <span
                  aria-hidden="true"
                  className={`mt-1 h-3.5 w-3.5 shrink-0 rounded-full border-2 ${dotClass}`}
                />
                {last ? null : (
                  <span
                    aria-hidden="true"
                    className={`mt-1 w-0.5 flex-1 ${
                      step.state === "done" ? "bg-success" : "bg-border"
                    }`}
                  />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p
                  className={`text-sm ${
                    step.state === "upcoming" ? "text-text-3" : "font-medium text-text"
                  }`}
                >
                  {statusLabel(step.status)}
                  <span className="sr-only">
                    {t("orders.timeline.srState", { state: stateLabel })}
                  </span>
                </p>
                {when ? <p className="text-xs text-text-3">{when}</p> : null}
                {step.note ? (
                  <p className="mt-1 text-sm text-text-2">
                    {t("orders.timeline.note", { note: step.note })}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

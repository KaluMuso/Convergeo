"use client";

import { useTranslations } from "next-intl";

import { progressSteps } from "./order-transitions";

type Props = { status: string; fulfilment: string };

/** Where the order is on its happy path; cancelled orders show a single banner instead. */
export function OrderStatusStepper({ status, fulfilment }: Props) {
  const t = useTranslations("admin.orders.detail");
  if (status === "cancelled") {
    return (
      <p
        role="status"
        className="rounded-md border border-danger/40 bg-danger/5 px-3 py-2 text-sm font-medium text-danger"
      >
        {t("cancelledBanner")}
      </p>
    );
  }
  const steps = progressSteps(fulfilment);
  const current = steps.indexOf(status);
  return (
    <ol className="flex flex-wrap gap-2" aria-label={t("progressLabel")}>
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={step}
            aria-current={active ? "step" : undefined}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              active
                ? "border-primary bg-primary-tint text-primary"
                : done
                  ? "border-success/40 text-success"
                  : "border-border text-muted"
            }`}
          >
            <span className="sr-only">
              {done ? t("stepDone") : active ? t("stepCurrent") : t("stepUpcoming")}{" "}
            </span>
            {t(`statuses.${step}`)}
          </li>
        );
      })}
    </ol>
  );
}

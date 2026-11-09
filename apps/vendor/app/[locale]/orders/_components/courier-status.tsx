"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";

export type VendorCourierStatus =
  "requested" | "accepted" | "picked_up" | "delivered" | "failed" | "cancelled";

/** Vendor projection of a courier dispatch — the API never sends the handover code. */
export type VendorCourierDispatch = {
  status: VendorCourierStatus;
  courier_name: string;
  courier_reference: string | null;
  cod_amount_ngwee: number;
  timeline: Array<{ status: VendorCourierStatus; at: string }>;
};

export type VendorDeliveryResponse = {
  enabled: boolean;
  dispatch: VendorCourierDispatch | null;
};

type CourierStatusCardProps = {
  dispatch: VendorCourierDispatch;
};

export function CourierStatusCard({ dispatch }: CourierStatusCardProps) {
  const t = useTranslations("vendor.orders.courier");
  const steps = [...dispatch.timeline].sort(
    (left, right) => new Date(left.at).getTime() - new Date(right.at).getTime(),
  );

  return (
    <section
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
      aria-labelledby="vendor-courier-heading"
      data-testid="vendor-courier-status"
      data-status={dispatch.status}
    >
      <h2 id="vendor-courier-heading" className="text-sm font-semibold text-text">
        {t("heading")}
      </h2>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-text-2">
          {t("courier")}
          {": "}
          <span className="font-medium text-text">{dispatch.courier_name}</span>
        </p>
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text">
          {t(`statuses.${dispatch.status}`)}
        </span>
      </div>
      {dispatch.courier_reference ? (
        <p className="text-xs text-text-2">{t("reference", { ref: dispatch.courier_reference })}</p>
      ) : null}
      {dispatch.cod_amount_ngwee > 0 ? (
        <p className="text-sm text-text-2">
          {t("codDue", { amount: formatK(dispatch.cod_amount_ngwee) })}
        </p>
      ) : null}
      <ol className="flex flex-col gap-1">
        {steps.map((step) => (
          <li key={`${step.status}-${step.at}`} className="flex justify-between gap-2 text-xs">
            <span className="text-text">{t(`statuses.${step.status}`)}</span>
            <time className="font-mono text-text-2" dateTime={step.at}>
              {new Date(step.at).toLocaleString()}
            </time>
          </li>
        ))}
      </ol>
      <p className="text-xs text-text-3">{t("handoverNote")}</p>
    </section>
  );
}

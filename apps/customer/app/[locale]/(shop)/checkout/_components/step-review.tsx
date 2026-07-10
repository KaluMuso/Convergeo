"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { Checkbox } from "@vergeo/ui/src/checkbox";
import { useState } from "react";

import type { CheckoutSession } from "./step-fulfilment";
import type { PaymentMethod, MomoRail, PaymentOptions } from "./step-payment";

export type ReviewStepLabels = {
  title: string;
  subtitle: string;
  lineItems: string;
  qtyTemplate: string;
  subtotal: string;
  deliveryFees: string;
  total: string;
  paymentMethod: string;
  methodMomo: string;
  methodCard: string;
  methodCod: string;
  railMtn: string;
  railAirtel: string;
  payerNumber: string;
  escrowTitle: string;
  escrowStep1: string;
  escrowStep2: string;
  escrowStep3: string;
  consentLabel: string;
  consentRequired: string;
  placeOrder: string;
  loading: string;
};

export type ReviewPayment = {
  method: PaymentMethod;
  rail: MomoRail | null;
  payer_number: string | null;
};

type StepReviewProps = {
  locale: string;
  session: CheckoutSession;
  totals: PaymentOptions;
  payment: ReviewPayment;
  labels: ReviewStepLabels;
  onPlaceOrder?: () => void;
};

function lineTitle(item: CheckoutSession["vendor_groups"][number]["items"][number]): string {
  return item.title_override?.trim() || item.listing_id;
}

export function StepReview({
  locale,
  session,
  totals,
  payment,
  labels,
  onPlaceOrder,
}: StepReviewProps) {
  const [consent, setConsent] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const amountLocale = `${locale}-ZM`;

  const paymentLabel = (() => {
    if (payment.method === "cod") {
      return labels.methodCod;
    }
    if (payment.method === "card") {
      return labels.methodCard;
    }
    const railLabel = payment.rail === "airtel" ? labels.railAirtel : labels.railMtn;
    return labels.methodMomo.replace("{rail}", railLabel);
  })();

  const handleSubmit = () => {
    if (!consent) {
      setErrorMessage(labels.consentRequired);
      return;
    }
    setErrorMessage(null);
    setLoading(true);
    onPlaceOrder?.();
    setLoading(false);
  };

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
      </div>

      <section className="space-y-3">
        <h3 className="font-body text-sm font-semibold uppercase tracking-wide text-text-3">
          {labels.lineItems}
        </h3>
        {session.vendor_groups.map((group) => (
          <div
            key={group.vendor_id}
            className="space-y-2 rounded-card border border-border bg-surface p-4"
          >
            <p className="font-body text-sm font-semibold text-text">{group.vendor_name}</p>
            <ul className="space-y-2">
              {group.items.map((item) => (
                <li key={item.id} className="flex items-start justify-between gap-2 text-sm">
                  <span className="font-body text-text-2">
                    {lineTitle(item)}{" "}
                    <span className="text-text-3">
                      {labels.qtyTemplate.replace("{qty}", String(item.qty))}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-text">
                    {formatK(item.line_total_ngwee, { locale: amountLocale })}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <div className="space-y-2 rounded-card border border-border bg-bg-2 px-4 py-3 font-mono text-sm">
        <div className="flex justify-between">
          <span>{labels.subtotal}</span>
          <span>{formatK(totals.subtotal_ngwee, { locale: amountLocale })}</span>
        </div>
        <div className="flex justify-between">
          <span>{labels.deliveryFees}</span>
          <span>{formatK(totals.delivery_fee_ngwee, { locale: amountLocale })}</span>
        </div>
        <div className="flex justify-between font-semibold text-text">
          <span>{labels.total}</span>
          <span>{formatK(totals.total_ngwee, { locale: amountLocale })}</span>
        </div>
      </div>

      <div className="rounded-card border border-border bg-surface px-4 py-3 text-sm">
        <p className="font-body font-semibold text-text">{labels.paymentMethod}</p>
        <p className="font-body text-text-2">{paymentLabel}</p>
        {payment.method === "momo" && payment.payer_number ? (
          <p className="font-mono text-xs text-text-3">
            {labels.payerNumber.replace("{number}", payment.payer_number)}
          </p>
        ) : null}
      </div>

      <div className="space-y-2 rounded-card border border-primary/20 bg-primary/5 px-4 py-3">
        <p className="font-body text-sm font-semibold text-text">{labels.escrowTitle}</p>
        <ol className="list-decimal space-y-1 pl-5 font-body text-sm text-text-2">
          <li>{labels.escrowStep1}</li>
          <li>{labels.escrowStep2}</li>
          <li>{labels.escrowStep3}</li>
        </ol>
      </div>

      <Checkbox
        id="checkout-consent"
        label={labels.consentLabel}
        checked={consent}
        onChange={(event) => {
          setConsent(event.target.checked);
          if (event.target.checked) {
            setErrorMessage(null);
          }
        }}
      />

      {errorMessage ? (
        <p role="alert" className="font-body text-sm text-danger">
          {errorMessage}
        </p>
      ) : null}

      <Button
        type="button"
        size="lg"
        className="w-full"
        loading={loading}
        loadingLabel={labels.loading}
        disabled={!consent}
        onClick={handleSubmit}
      >
        {labels.placeOrder}
      </Button>
    </div>
  );
}

"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { Checkbox } from "@vergeo/ui/src/checkbox";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { VariantLineLabel } from "../../_components/cart/variant-line-label";
import {
  formatListingQuantity,
  formatMadeToOrderLeadTime,
  type SaleUnitLabels,
} from "../../_components/sale-quantity";

import { NextSteps } from "./next-steps";

import type { CheckoutSession, FulfilmentGroupResult } from "./step-fulfilment";
import type { PaymentMethod, MomoRail, PaymentOptions } from "./step-payment";

export type ReviewStepLabels = {
  title: string;
  subtitle: string;
  lineItems: string;
  qtyTemplate: string;
  variantOption?: string;
  variantSeparator?: string;
  saleUnits: SaleUnitLabels;
  madeToOrderLeadTime: string;
  subtotal: string;
  deliveryFees: string;
  total: string;
  /** "Coupon {code}" — shown as a negative line when a coupon is applied. */
  discount?: string;
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
  placingOrder: string;
  placeOrderUnavailable: string;
  whatHappensNext: string;
  nextMomo: string;
  nextCard: string;
  nextCod: string;
  /** UX pass 4 — COD-specific review copy. Templates use {amount} / {landmark}. */
  codGuide?: ReviewCodGuideLabels;
};

export type ReviewCodGuideLabels = {
  title: string;
  step1: string;
  step2: string;
  step3: string;
  deliveryTo: string;
  deliveryNoLandmark: string;
  pickupFromSeller: string;
  placeOrderCod: string;
};

export type ReviewFulfilment = {
  groups: FulfilmentGroupResult[];
  landmark: string | null;
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
  fulfilment?: ReviewFulfilment;
  onPlaceOrder?: () => void | Promise<void>;
  /** Coupon / gift disclosures, rendered just above the totals. */
  extras?: ReactNode;
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
  fulfilment,
  onPlaceOrder,
  extras,
}: StepReviewProps) {
  const errorRef = useRef<HTMLParagraphElement | null>(null);
  const submittingRef = useRef(false);
  const nextId = useId();
  const [consent, setConsent] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const amountLocale = `${locale}-ZM`;
  const placeOrderAvailable = typeof onPlaceOrder === "function";

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

  const codGuide = payment.method === "cod" ? labels.codGuide : undefined;
  const totalFormatted = formatK(totals.total_ngwee, { locale: amountLocale });
  const codStepsId = useId();

  const fulfilmentLine = (vendorId: string): string | null => {
    const guide = labels.codGuide;
    const group = fulfilment?.groups.find((entry) => entry.vendor_id === vendorId);
    if (!guide || !group) {
      return null;
    }
    if (group.fulfilment === "pickup") {
      return guide.pickupFromSeller;
    }
    return fulfilment?.landmark
      ? guide.deliveryTo.split("{landmark}").join(fulfilment.landmark)
      : guide.deliveryNoLandmark;
  };

  const nextCopy =
    payment.method === "cod"
      ? labels.nextCod
      : payment.method === "card"
        ? labels.nextCard
        : labels.nextMomo;

  useEffect(() => {
    if (!errorMessage) {
      return;
    }
    const node = errorRef.current;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [errorMessage]);

  const handleSubmit = async () => {
    if (!consent) {
      setErrorMessage(labels.consentRequired);
      return;
    }
    if (!onPlaceOrder) {
      setErrorMessage(labels.placeOrderUnavailable);
      return;
    }
    // Sync + async guards — prevent double-submit while place-order is in flight
    // or while navigation to a truthful pending/COD surface is starting.
    if (loading || submittingRef.current) {
      return;
    }
    const placeOrder = onPlaceOrder;
    submittingRef.current = true;
    setErrorMessage(null);
    setLoading(true);
    try {
      await Promise.resolve(placeOrder());
      // Keep loading/busy on success: placeOrder navigates to payment-cod /
      // payment-confirming (never a local "paid" claim). Re-enable only on error.
    } catch (error) {
      submittingRef.current = false;
      setLoading(false);
      const message =
        error instanceof Error && error.message.trim()
          ? error.message
          : labels.placeOrderUnavailable;
      setErrorMessage(message);
    }
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
            {fulfilmentLine(group.vendor_id) ? (
              <p
                className="font-body text-xs text-text-2"
                data-testid={`review-fulfilment-${group.vendor_id}`}
              >
                {fulfilmentLine(group.vendor_id)}
              </p>
            ) : null}
            <ul className="space-y-2">
              {group.items.map((item) => {
                const leadTimeLabel = formatMadeToOrderLeadTime(
                  item.fulfilment_mode,
                  item.lead_time_days,
                  labels.madeToOrderLeadTime,
                );

                return (
                  <li key={item.id} className="flex items-start justify-between gap-2 text-sm">
                    <span className="min-w-0 break-words font-body text-text-2">
                      <span>
                        {lineTitle(item)}
                        <VariantLineLabel
                          options={item.variant_options}
                          template={labels.variantOption ?? "{value}"}
                          separator={labels.variantSeparator ?? ", "}
                          testId={`review-line-variant-${item.listing_id}`}
                        />{" "}
                        <span className="text-text-3">
                          {labels.qtyTemplate.replace(
                            "{qty}",
                            formatListingQuantity(
                              item.qty,
                              item.sale_unit,
                              item.unit_step_milli,
                              locale,
                              labels.saleUnits,
                            ),
                          )}
                        </span>
                      </span>
                      {leadTimeLabel ? (
                        <span
                          className="block text-xs font-medium text-text-3"
                          data-testid={`checkout-lead-time-${item.listing_id}`}
                        >
                          {leadTimeLabel}
                        </span>
                      ) : null}
                    </span>
                    <span className="shrink-0 font-mono text-text">
                      {formatK(item.line_total_ngwee, { locale: amountLocale })}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </section>

      {extras}

      <div className="space-y-2 rounded-card border border-border bg-bg-2 px-4 py-3 font-mono text-sm">
        <div className="flex justify-between gap-3">
          <span>{labels.subtotal}</span>
          <span>{formatK(totals.subtotal_ngwee, { locale: amountLocale })}</span>
        </div>
        <div className="flex justify-between gap-3">
          <span>{labels.deliveryFees}</span>
          <span>{formatK(totals.delivery_fee_ngwee, { locale: amountLocale })}</span>
        </div>
        {totals.discount_ngwee && totals.discount_ngwee > 0 ? (
          <div className="flex justify-between gap-3 text-success" data-testid="review-discount">
            <span>{(labels.discount ?? "{code}").replace("{code}", totals.coupon_code ?? "")}</span>
            <span>−{formatK(totals.discount_ngwee, { locale: amountLocale })}</span>
          </div>
        ) : null}
        <div className="flex justify-between gap-3 font-semibold text-text">
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

      {codGuide ? (
        // COD is honest about money: nothing is charged now, so the escrow
        // "you paid → held" triad is NOT shown for this method.
        <NextSteps
          heading={codGuide.title}
          headingId={codStepsId}
          testId="checkout-review-cod-steps"
          steps={[
            { title: codGuide.step1 },
            { title: codGuide.step2 },
            { title: codGuide.step3.split("{amount}").join(totalFormatted) },
          ]}
        />
      ) : (
        <>
          <div
            className="space-y-2 rounded-card border border-border bg-surface px-4 py-3"
            aria-labelledby={nextId}
          >
            <p id={nextId} className="font-body text-sm font-semibold text-text">
              {labels.whatHappensNext}
            </p>
            <p className="font-body text-sm text-text-2">{nextCopy}</p>
          </div>

          <div className="space-y-2 rounded-card border border-primary/20 bg-primary/5 px-4 py-3">
            <p className="font-body text-sm font-semibold text-text">{labels.escrowTitle}</p>
            <ol className="list-decimal space-y-1 pl-5 font-body text-sm text-text-2">
              <li>{labels.escrowStep1}</li>
              <li>{labels.escrowStep2}</li>
              <li>{labels.escrowStep3}</li>
            </ol>
          </div>
        </>
      )}

      {!placeOrderAvailable ? (
        <p
          role="status"
          className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 font-body text-sm text-text"
          data-testid="checkout-place-order-unavailable"
        >
          {labels.placeOrderUnavailable}
        </p>
      ) : null}

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
        <p ref={errorRef} role="alert" className="font-body text-sm text-danger">
          {errorMessage}
        </p>
      ) : null}

      <p className="sr-only" aria-live="polite">
        {loading ? labels.placingOrder : ""}
      </p>

      <Button
        type="button"
        size="lg"
        className="w-full min-h-11"
        loading={loading}
        loadingLabel={labels.placingOrder}
        disabled={!consent || loading || !placeOrderAvailable}
        aria-busy={loading}
        data-testid="checkout-place-order"
        onClick={() => {
          void handleSubmit();
        }}
      >
        {codGuide ? codGuide.placeOrderCod : labels.placeOrder}
      </Button>
    </div>
  );
}

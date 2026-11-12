"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Radio } from "@vergeo/ui/src/radio";
import Link from "next/link";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import {
  DEFAULT_COUNTRY_CODE,
  formatE164,
  isValidZambianMobile,
  normalizeNationalNumber,
} from "../../../(auth)/_components/auth-utils";
import { getApiBaseUrl } from "../../../../../lib/api-base-url";

import { PaymentRailChoice } from "./payment-rail-choice";

export type PaymentMethod = "momo" | "card" | "cod";
export type MomoRail = "mtn" | "airtel";

export type PaymentStepLabels = {
  title: string;
  subtitle: string;
  momo: string;
  card: string;
  cod: string;
  momoHelp: string;
  cardHelp: string;
  codHelp: string;
  railMtn: string;
  railAirtel: string;
  payerLabel: string;
  payerHelp: string;
  payerPlaceholder: string;
  countryCode: string;
  nationalNumber: string;
  cardExplainer: string;
  codIneligible: (cap: string) => string;
  codUnavailableTitle: string;
  selected: string;
  unavailable: string;
  continue: string;
  loading: string;
  required: string;
  invalidPayer: string;
  railRequired: string;
  codRejected: string;
  railRejected: string;
  error: string;
  /** Shown when the API payment kill-switch blocks momo/card initiation. */
  paymentsDisabled: string;
  /** UX pass 4 — plain-language COD explainer. Templates use {amount} / {cap} / {total}. */
  codGuide?: PaymentCodGuideLabels;
};

export type PaymentCodGuideLabels = {
  title: string;
  step1: string;
  step2: string;
  step3: string;
  capNote: string;
  overCap: string;
  editCart: string;
};

function fill(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (result, [key, value]) => result.split(`{${key}}`).join(value),
    template,
  );
}

export type PaymentOptions = {
  session_id: string;
  subtotal_ngwee: number;
  delivery_fee_ngwee: number;
  total_ngwee: number;
  cod_cap_ngwee: number;
  cod_eligible: boolean;
};

export type ValidatedPayment = {
  method: PaymentMethod;
  rail: MomoRail | null;
  payer_number: string | null;
};

/**
 * Pre-resolved options for a server-created checkout group (paid ticket / service
 * deposit). The amount comes from `GET /checkout/groups/{id}`; the cart-session
 * option fetch and `/checkout/steps/payment` validation are skipped, COD is never
 * offered, and `onComplete` starts the payment (errors surface in this step).
 */
export type PresetPayment = {
  options: PaymentOptions;
  methods: ReadonlyArray<"momo" | "card">;
  continueLabel?: string;
};

type StepPaymentProps = {
  locale: string;
  sessionId: string;
  accessToken: string;
  labels: PaymentStepLabels;
  onComplete: (payment: ValidatedPayment, options: PaymentOptions) => void | Promise<void>;
  preset?: PresetPayment;
};

function MethodOption({ selected, children }: { selected: boolean; children: ReactNode }) {
  return (
    <div
      className={[
        "rounded-card border p-4 transition-[border-color,background-color] duration-fast ease-std motion-reduce:transition-none",
        selected
          ? "border-primary bg-primary/5"
          : "border-border bg-surface hover:border-primary/50",
      ].join(" ")}
      data-selected={selected ? "true" : "false"}
    >
      {children}
    </div>
  );
}

export function StepPayment({
  locale,
  sessionId,
  accessToken,
  labels,
  onComplete,
  preset,
}: StepPaymentProps) {
  const errorRef = useRef<HTMLParagraphElement | null>(null);
  const groupLabelId = useId();
  const [options, setOptions] = useState<PaymentOptions | null>(preset?.options ?? null);
  const [method, setMethod] = useState<PaymentMethod>(
    preset && !preset.methods.includes("momo") ? "card" : "momo",
  );
  const [rail, setRail] = useState<MomoRail>("mtn");
  const [nationalNumber, setNationalNumber] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(!preset);
  const offers = (candidate: PaymentMethod) =>
    preset ? (preset.methods as ReadonlyArray<PaymentMethod>).includes(candidate) : true;

  useEffect(() => {
    if (preset) {
      return;
    }
    let cancelled = false;
    const loadOptions = async () => {
      setInitializing(true);
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => accessToken,
        });
        const response = await client.request<PaymentOptions>(
          `/checkout/steps/payment-options?session_id=${encodeURIComponent(sessionId)}`,
        );
        if (!cancelled) {
          setOptions(response);
          if (!response.cod_eligible && method === "cod") {
            setMethod("momo");
          }
        }
      } catch {
        if (!cancelled) {
          setErrorMessage(labels.error);
        }
      } finally {
        if (!cancelled) {
          setInitializing(false);
        }
      }
    };
    void loadOptions();
    return () => {
      cancelled = true;
    };
  }, [accessToken, labels.error, method, preset, sessionId]);

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
    setErrorMessage(null);

    if (method === "momo") {
      if (!nationalNumber.trim()) {
        setErrorMessage(labels.required);
        return;
      }
      if (!isValidZambianMobile(nationalNumber)) {
        setErrorMessage(labels.invalidPayer);
        return;
      }
    }

    setLoading(true);
    if (preset) {
      try {
        await onComplete(
          {
            method,
            rail: method === "momo" ? rail : null,
            payer_number:
              method === "momo" ? formatE164(DEFAULT_COUNTRY_CODE, nationalNumber) : null,
          },
          preset.options,
        );
        // Success navigates away; keep the button busy so it cannot double-submit.
      } catch (error) {
        setErrorMessage(
          error instanceof ApiError && error.code === "payments_disabled"
            ? labels.paymentsDisabled
            : error instanceof ApiError && error.code === "checkout.invalid_payer_number"
              ? labels.invalidPayer
              : labels.error,
        );
        setLoading(false);
      }
      return;
    }
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      const payerNumber =
        method === "momo" ? formatE164(DEFAULT_COUNTRY_CODE, nationalNumber) : undefined;
      const response = await client.request<PaymentOptions & ValidatedPayment>(
        "/checkout/steps/payment",
        {
          method: "POST",
          body: JSON.stringify({
            session_id: sessionId,
            method,
            rail: method === "momo" ? rail : undefined,
            payer_number: payerNumber,
          }),
        },
      );
      onComplete(
        {
          method: response.method,
          rail: response.rail,
          payer_number: response.payer_number,
        },
        {
          session_id: response.session_id,
          subtotal_ngwee: response.subtotal_ngwee,
          delivery_fee_ngwee: response.delivery_fee_ngwee,
          total_ngwee: response.total_ngwee,
          cod_cap_ngwee: response.cod_cap_ngwee,
          cod_eligible: response.cod_eligible,
        },
      );
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "checkout.cod_ineligible") {
          setErrorMessage(labels.codRejected);
          return;
        }
        if (error.code === "checkout.rail_not_allowed") {
          setErrorMessage(labels.railRejected);
          return;
        }
        if (error.code === "checkout.invalid_payer_number") {
          setErrorMessage(labels.invalidPayer);
          return;
        }
        if (error.code === "checkout.rail_required") {
          setErrorMessage(labels.railRequired);
          return;
        }
        if (error.code === "payments_disabled") {
          setErrorMessage(labels.paymentsDisabled);
          return;
        }
      }
      setErrorMessage(labels.error);
    } finally {
      setLoading(false);
    }
  };

  if (initializing || !options) {
    return (
      <p className="font-body text-sm text-text-3" aria-live="polite">
        {labels.loading}
      </p>
    );
  }

  const codCapFormatted = formatK(options.cod_cap_ngwee, {
    locale: `${locale}-ZM`,
  });
  const totalFormatted = formatK(options.total_ngwee, { locale: `${locale}-ZM` });
  const codGuide = labels.codGuide;

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h2 id={groupLabelId} className="font-display text-h2 text-display-ink">
          {labels.title}
        </h2>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
      </div>

      <div
        role="radiogroup"
        aria-labelledby={groupLabelId}
        className="flex flex-col gap-3"
        data-testid="checkout-payment-methods"
      >
        {offers("momo") ? (
          <MethodOption selected={method === "momo"}>
            <div className="flex items-start justify-between gap-3">
              <Radio
                name="payment-method"
                label={labels.momo}
                checked={method === "momo"}
                onChange={() => {
                  setMethod("momo");
                  setErrorMessage(null);
                }}
              />
              {method === "momo" ? (
                <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-surface">
                  {labels.selected}
                </span>
              ) : null}
            </div>
            <p className="mt-2 pl-8 font-body text-sm text-text-2">{labels.momoHelp}</p>
          </MethodOption>
        ) : null}

        {offers("card") ? (
          <MethodOption selected={method === "card"}>
            <div className="flex items-start justify-between gap-3">
              <Radio
                name="payment-method"
                label={labels.card}
                checked={method === "card"}
                onChange={() => {
                  setMethod("card");
                  setErrorMessage(null);
                }}
              />
              {method === "card" ? (
                <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-surface">
                  {labels.selected}
                </span>
              ) : null}
            </div>
            <p className="mt-2 pl-8 font-body text-sm text-text-2">{labels.cardHelp}</p>
          </MethodOption>
        ) : null}

        {preset ? null : options.cod_eligible ? (
          <MethodOption selected={method === "cod"}>
            <div className="flex items-start justify-between gap-3">
              <Radio
                name="payment-method"
                label={labels.cod}
                checked={method === "cod"}
                onChange={() => {
                  setMethod("cod");
                  setErrorMessage(null);
                }}
              />
              {method === "cod" ? (
                <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-surface">
                  {labels.selected}
                </span>
              ) : null}
            </div>
            <p className="mt-2 pl-8 font-body text-sm text-text-2">{labels.codHelp}</p>
            {codGuide && method === "cod" ? (
              <div
                className="mt-3 space-y-2 rounded-md bg-bg-2 px-3 py-3"
                data-testid="checkout-cod-guide"
              >
                <p className="font-body text-sm font-semibold text-text">{codGuide.title}</p>
                <ul className="list-disc space-y-1 pl-5 font-body text-sm text-text-2">
                  <li>{codGuide.step1}</li>
                  <li>{fill(codGuide.step2, { amount: totalFormatted })}</li>
                  <li>{codGuide.step3}</li>
                </ul>
                <p className="font-body text-xs text-text-3">
                  {fill(codGuide.capNote, { cap: codCapFormatted })}
                </p>
              </div>
            ) : null}
          </MethodOption>
        ) : (
          <div
            className="rounded-card border border-dashed border-border bg-bg-2 p-4"
            data-testid="checkout-cod-unavailable"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-body text-sm font-semibold text-text-3">{labels.cod}</p>
                <p className="mt-1 font-body text-sm font-medium text-text">
                  {labels.codUnavailableTitle}
                </p>
                <p className="mt-1 font-body text-sm text-text-2">
                  {labels.codIneligible(codCapFormatted)}
                </p>
                {codGuide ? (
                  <>
                    <p className="mt-2 font-body text-sm text-text-2">
                      {fill(codGuide.overCap, {
                        total: totalFormatted,
                        cap: codCapFormatted,
                      })}
                    </p>
                    <Link
                      href={`/${locale}/cart`}
                      className="mt-1 inline-flex min-h-11 items-center font-body text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
                    >
                      {codGuide.editCart}
                    </Link>
                  </>
                ) : null}
              </div>
              <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-text-3">
                {labels.unavailable}
              </span>
            </div>
          </div>
        )}
      </div>

      {method === "momo" ? (
        <div className="space-y-4 rounded-card border border-border bg-surface p-4">
          <div className="flex flex-col gap-2" role="radiogroup" aria-label={labels.momo}>
            <PaymentRailChoice
              name="momo-rail"
              rail="mtn"
              label={labels.railMtn}
              checked={rail === "mtn"}
              onChange={() => {
                setRail("mtn");
              }}
            />
            <PaymentRailChoice
              name="momo-rail"
              rail="airtel"
              label={labels.railAirtel}
              checked={rail === "airtel"}
              onChange={() => {
                setRail("airtel");
              }}
            />
          </div>
          <FormField
            label={labels.payerLabel}
            helpText={labels.payerHelp}
            errorMessage={errorMessage ?? undefined}
            required
            requiredMarker="*"
            asGroup
          >
            {/* Input carries `w-full` from field styles, which beats `w-24` in the
                generated CSS — size the prefix via a wrapper so the row fits 360px. */}
            <div className="flex min-w-0 gap-2">
              <div className="w-24 shrink-0">
                <Input
                  size="lg"
                  className="text-center font-mono"
                  value={DEFAULT_COUNTRY_CODE}
                  readOnly
                  aria-label={labels.countryCode}
                />
              </div>
              <Input
                size="lg"
                className="min-w-0 flex-1 font-mono"
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder={labels.payerPlaceholder}
                aria-label={labels.nationalNumber}
                aria-required
                value={nationalNumber}
                error={Boolean(errorMessage)}
                onChange={(event) => {
                  setNationalNumber(normalizeNationalNumber(event.target.value));
                }}
              />
            </div>
          </FormField>
        </div>
      ) : null}

      {method === "card" ? (
        <div className="rounded-card border border-border bg-bg-2 px-4 py-3">
          <p className="font-body text-sm text-text-2">{labels.cardExplainer}</p>
        </div>
      ) : null}

      {errorMessage && method !== "momo" ? (
        <p
          ref={errorRef}
          role="alert"
          className="font-body text-sm text-danger"
          data-testid="checkout-payment-error"
        >
          {errorMessage}
        </p>
      ) : null}

      {errorMessage && method === "momo" ? (
        <span ref={errorRef} className="sr-only" aria-hidden="true" />
      ) : null}

      {preset && preset.methods.length === 0 ? (
        <p
          role="alert"
          className="font-body text-sm text-danger"
          data-testid="checkout-payments-off"
        >
          {labels.paymentsDisabled}
        </p>
      ) : (
        <Button
          type="button"
          size="lg"
          className="w-full"
          loading={loading}
          loadingLabel={labels.loading}
          disabled={loading}
          onClick={() => {
            void handleSubmit();
          }}
        >
          {preset?.continueLabel ?? labels.continue}
        </Button>
      )}
    </div>
  );
}

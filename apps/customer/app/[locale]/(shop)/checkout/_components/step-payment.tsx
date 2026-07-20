"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Radio } from "@vergeo/ui/src/radio";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import {
  DEFAULT_COUNTRY_CODE,
  formatE164,
  isValidZambianMobile,
  normalizeNationalNumber,
} from "../../../(auth)/_components/auth-utils";
import { getApiBaseUrl } from "../../../../../lib/api-base-url";

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
};

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

type StepPaymentProps = {
  locale: string;
  sessionId: string;
  accessToken: string;
  labels: PaymentStepLabels;
  onComplete: (payment: ValidatedPayment, options: PaymentOptions) => void;
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
}: StepPaymentProps) {
  const errorRef = useRef<HTMLParagraphElement | null>(null);
  const groupLabelId = useId();
  const [options, setOptions] = useState<PaymentOptions | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("momo");
  const [rail, setRail] = useState<MomoRail>("mtn");
  const [nationalNumber, setNationalNumber] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
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
  }, [accessToken, labels.error, method, sessionId]);

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

  const codCapFormatted = formatK(options.cod_cap_ngwee, { locale: `${locale}-ZM` });

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

        {options.cod_eligible ? (
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
          </MethodOption>
        ) : (
          <div
            className="rounded-card border border-dashed border-border bg-bg-2 p-4"
            data-testid="checkout-cod-unavailable"
            aria-disabled="true"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-body text-sm font-semibold text-text-3">{labels.cod}</p>
                <p className="mt-1 font-body text-sm font-medium text-text">
                  {labels.codUnavailableTitle}
                </p>
                <p className="mt-1 font-body text-sm text-text-3">
                  {labels.codIneligible(codCapFormatted)}
                </p>
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
          <div className="flex flex-col gap-2">
            <Radio
              name="momo-rail"
              label={labels.railMtn}
              checked={rail === "mtn"}
              onChange={() => {
                setRail("mtn");
              }}
            />
            <Radio
              name="momo-rail"
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
          >
            <div className="flex gap-2">
              <Input
                size="lg"
                className="w-24 shrink-0 text-center font-mono"
                value={DEFAULT_COUNTRY_CODE}
                readOnly
                aria-label={labels.countryCode}
              />
              <Input
                size="lg"
                className="min-w-0 flex-1 font-mono"
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder={labels.payerPlaceholder}
                aria-label={labels.nationalNumber}
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
        {labels.continue}
      </Button>
    </div>
  );
}

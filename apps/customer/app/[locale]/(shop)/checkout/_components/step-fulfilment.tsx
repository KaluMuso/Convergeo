"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Radio } from "@vergeo/ui/src/radio";
import { Stepper } from "@vergeo/ui/src/stepper";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ReservationCountdown } from "./reservation-countdown";
import { StepContact, type ContactStepLabels } from "./step-contact";
import {
  StepPayment,
  type PaymentOptions,
  type PaymentStepLabels,
  type ValidatedPayment,
} from "./step-payment";
import { StepReview, type ReviewPayment, type ReviewStepLabels } from "./step-review";

export type PickupLocation = {
  landmark: string;
  lat: number;
  lng: number;
  hours: Record<string, unknown>;
};

export type VendorGroupSession = {
  vendor_id: string;
  vendor_name: string;
  items: Array<{
    id: string;
    listing_id: string;
    vendor_id: string;
    qty: number;
    unit_price_ngwee: number;
    line_total_ngwee: number;
    title_override: string | null;
  }>;
  subtotal_ngwee: number;
  delivery_eligible: boolean;
  pickup_location: PickupLocation | null;
};

export type CheckoutSession = {
  session_id: string;
  expires_at: string;
  reservation_ttl_min: number;
  vendor_groups: VendorGroupSession[];
  subtotal_ngwee: number;
  contact_skipped: boolean;
};

export type FulfilmentStepLabels = {
  title: string;
  subtitle: string;
  delivery: string;
  pickup: string;
  landmarkLabel: string;
  landmarkPlaceholder: string;
  landmarkHelp: string;
  zoneFee: (amount: string) => string;
  zoneFree: string;
  zoneLabel: (zone: string) => string;
  pickupAt: (landmark: string) => string;
  pickupHours: (hours: string) => string;
  outsideZone: string;
  mixedHint: string;
  continue: string;
  subtotal: string;
  deliveryFees: string;
  total: string;
  loading: string;
  error: string;
};

export type CountdownLabels = {
  label: string;
  expired: string;
  ariaLive: (time: string) => string;
};

type GroupChoice = {
  vendor_id: string;
  fulfilment: "delivery" | "pickup";
};

type FulfilmentTotals = {
  subtotal_ngwee: number;
  delivery_fee_ngwee: number;
  total_ngwee: number;
};

type StepFulfilmentProps = {
  locale: string;
  session: CheckoutSession;
  accessToken: string;
  labels: FulfilmentStepLabels;
  countdownLabels: CountdownLabels;
  reservationExpiredMessage: string;
  cartPath: string;
  onComplete?: (totals: FulfilmentTotals) => void;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function formatHours(hours: Record<string, unknown>): string {
  const entries = Object.entries(hours);
  if (entries.length === 0) {
    return "—";
  }
  return entries.map(([day, value]) => `${day}: ${String(value)}`).join(", ");
}

export function StepFulfilment({
  locale,
  session,
  accessToken,
  labels,
  countdownLabels,
  reservationExpiredMessage,
  cartPath,
  onComplete,
}: StepFulfilmentProps) {
  const router = useRouter();
  const [landmark, setLandmark] = useState("");
  const [choices, setChoices] = useState<GroupChoice[]>(
    session.vendor_groups.map((group) => ({
      vendor_id: group.vendor_id,
      fulfilment: group.delivery_eligible ? "delivery" : "pickup",
    })),
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [totals, setTotals] = useState<{
    subtotal_ngwee: number;
    delivery_fee_ngwee: number;
    total_ngwee: number;
  } | null>(null);

  const handleExpired = useCallback(() => {
    router.push(`${cartPath}?notice=reservation_expired`);
  }, [cartPath, router]);

  const setGroupFulfilment = (vendorId: string, fulfilment: "delivery" | "pickup") => {
    setChoices((current) =>
      current.map((choice) => (choice.vendor_id === vendorId ? { ...choice, fulfilment } : choice)),
    );
    setTotals(null);
  };

  const handleSubmit = async () => {
    setErrorMessage(null);
    const deliveryNeeded = choices.some((choice) => choice.fulfilment === "delivery");
    if (deliveryNeeded && !landmark.trim()) {
      setErrorMessage(labels.landmarkLabel);
      return;
    }

    setLoading(true);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });
      const response = await client.request<{
        subtotal_ngwee: number;
        delivery_fee_ngwee: number;
        total_ngwee: number;
      }>("/checkout/steps/fulfilment", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          address: deliveryNeeded ? { landmark: landmark.trim() } : undefined,
          groups: choices,
        }),
      });
      setTotals(response);
      onComplete?.(response);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "checkout.reservation_expired") {
          router.push(`${cartPath}?notice=reservation_expired`);
          return;
        }
        if (error.code === "checkout.outside_delivery_zone") {
          setErrorMessage(labels.outsideZone);
          return;
        }
      }
      setErrorMessage(labels.error);
    } finally {
      setLoading(false);
    }
  };

  const displaySubtotal = totals?.subtotal_ngwee ?? session.subtotal_ngwee;
  const displayDelivery = totals?.delivery_fee_ngwee ?? 0;
  const displayTotal = totals?.total_ngwee ?? session.subtotal_ngwee;

  return (
    <div className="space-y-5">
      <ReservationCountdown
        expiresAt={session.expires_at}
        label={countdownLabels.label}
        expiredLabel={countdownLabels.expired}
        ariaLiveLabel={countdownLabels.ariaLive}
        onExpired={handleExpired}
      />

      <div className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
        <p className="font-body text-xs text-text-3">{labels.mixedHint}</p>
      </div>

      {choices.some((choice) => choice.fulfilment === "delivery") ? (
        <FormField
          label={labels.landmarkLabel}
          helpText={labels.landmarkHelp}
          required
          requiredMarker="*"
        >
          <Input
            size="lg"
            value={landmark}
            placeholder={labels.landmarkPlaceholder}
            onChange={(event) => {
              setLandmark(event.target.value);
              setTotals(null);
            }}
          />
        </FormField>
      ) : null}

      <div className="space-y-4">
        {session.vendor_groups.map((group) => {
          const choice = choices.find((item) => item.vendor_id === group.vendor_id);
          const fulfilment = choice?.fulfilment ?? "pickup";
          const pickup = group.pickup_location;

          return (
            <section
              key={group.vendor_id}
              className="space-y-3 rounded-card border border-border bg-surface p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-body text-base font-semibold text-text">{group.vendor_name}</h3>
                <span className="font-mono text-sm text-text-2">
                  {formatK(group.subtotal_ngwee, { locale: `${locale}-ZM` })}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <Radio
                  name={`fulfilment-${group.vendor_id}`}
                  label={labels.delivery}
                  checked={fulfilment === "delivery"}
                  disabled={!group.delivery_eligible}
                  onChange={() => {
                    setGroupFulfilment(group.vendor_id, "delivery");
                  }}
                />
                <Radio
                  name={`fulfilment-${group.vendor_id}`}
                  label={labels.pickup}
                  checked={fulfilment === "pickup"}
                  onChange={() => {
                    setGroupFulfilment(group.vendor_id, "pickup");
                  }}
                />
              </div>

              {fulfilment === "pickup" && pickup ? (
                <div className="rounded-md bg-bg-2 px-3 py-2 text-sm text-text-2">
                  <p>{labels.pickupAt(pickup.landmark)}</p>
                  <p className="text-xs text-text-3">
                    {labels.pickupHours(formatHours(pickup.hours))}
                  </p>
                </div>
              ) : null}

              {fulfilment === "delivery" && !group.delivery_eligible ? (
                <p className="text-xs text-warning">{labels.outsideZone}</p>
              ) : null}
            </section>
          );
        })}
      </div>

      <div className="space-y-2 rounded-card border border-border bg-bg-2 px-4 py-3 font-mono text-sm">
        <div className="flex justify-between">
          <span>{labels.subtotal}</span>
          <span>{formatK(displaySubtotal, { locale: `${locale}-ZM` })}</span>
        </div>
        <div className="flex justify-between">
          <span>{labels.deliveryFees}</span>
          <span>{formatK(displayDelivery, { locale: `${locale}-ZM` })}</span>
        </div>
        <div className="flex justify-between font-semibold text-text">
          <span>{labels.total}</span>
          <span>{formatK(displayTotal, { locale: `${locale}-ZM` })}</span>
        </div>
      </div>

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
        onClick={() => {
          void handleSubmit();
        }}
      >
        {labels.continue}
      </Button>

      <p className="sr-only" aria-live="assertive">
        {reservationExpiredMessage}
      </p>
    </div>
  );
}

export type CheckoutShellLabels = {
  pageTitle: string;
  stepAnnouncementTemplate: string;
  doneIndicator: string;
  steps: {
    contact: string;
    fulfilment: string;
    payment: string;
    review: string;
  };
  contact: Omit<ContactStepLabels, "otpDigit" | "resendIn" | "throttled"> & {
    otpDigitTemplate: string;
    resendInTemplate: string;
    throttledTemplate: string;
  };
  fulfilment: Omit<FulfilmentStepLabels, "zoneFee" | "zoneLabel" | "pickupAt" | "pickupHours"> & {
    zoneFeeTemplate: string;
    zoneLabelTemplate: string;
    pickupAtTemplate: string;
    pickupHoursTemplate: string;
  };
  payment: Omit<PaymentStepLabels, "codIneligible"> & { codIneligibleTemplate: string };
  review: {
    title: string;
    subtitle: string;
    lineItems: string;
    qtyTemplate: string;
    subtotal: string;
    deliveryFees: string;
    total: string;
    paymentMethod: string;
    methodMomoTemplate: string;
    methodCard: string;
    methodCod: string;
    railMtn: string;
    railAirtel: string;
    payerNumberTemplate: string;
    escrowTitle: string;
    escrowStep1: string;
    escrowStep2: string;
    escrowStep3: string;
    consentLabel: string;
    consentRequired: string;
    placeOrder: string;
    loading: string;
  };
  countdown: Omit<CountdownLabels, "ariaLive"> & { ariaLiveTemplate: string };
  reservationExpired: string;
  loading: string;
  error: string;
  emptyCart: string;
};

function fillTemplate(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce(
    (result, [key, value]) => result.replace(`{${key}}`, String(value)),
    template,
  );
}

type ResolvedCheckoutLabels = {
  pageTitle: string;
  stepAnnouncement: (current: number, total: number) => string;
  doneIndicator: string;
  steps: CheckoutShellLabels["steps"];
  contact: ContactStepLabels;
  fulfilment: FulfilmentStepLabels;
  payment: PaymentStepLabels;
  review: ReviewStepLabels;
  countdown: CountdownLabels;
  reservationExpired: string;
  loading: string;
  error: string;
  emptyCart: string;
};

function resolveLabels(messages: CheckoutShellLabels): ResolvedCheckoutLabels {
  return {
    pageTitle: messages.pageTitle,
    stepAnnouncement: (current, total) =>
      fillTemplate(messages.stepAnnouncementTemplate, { current, total }),
    doneIndicator: messages.doneIndicator,
    steps: messages.steps,
    contact: {
      title: messages.contact.title,
      subtitle: messages.contact.subtitle,
      phoneLabel: messages.contact.phoneLabel,
      phoneHelp: messages.contact.phoneHelp,
      phonePlaceholder: messages.contact.phonePlaceholder,
      countryCode: messages.contact.countryCode,
      nationalNumber: messages.contact.nationalNumber,
      sendOtp: messages.contact.sendOtp,
      verifyOtp: messages.contact.verifyOtp,
      otpAria: messages.contact.otpAria,
      otpDigit: messages.contact.otpDigitTemplate,
      resend: messages.contact.resend,
      resendIn: messages.contact.resendInTemplate,
      changePhone: messages.contact.changePhone,
      loading: messages.contact.loading,
      required: messages.contact.required,
      invalidPhone: messages.contact.invalidPhone,
      sendFailed: messages.contact.sendFailed,
      wrongCode: messages.contact.wrongCode,
      expired: messages.contact.expired,
      throttled: messages.contact.throttledTemplate,
      generic: messages.contact.generic,
      skippedLoggedIn: messages.contact.skippedLoggedIn,
    },
    fulfilment: {
      title: messages.fulfilment.title,
      subtitle: messages.fulfilment.subtitle,
      delivery: messages.fulfilment.delivery,
      pickup: messages.fulfilment.pickup,
      landmarkLabel: messages.fulfilment.landmarkLabel,
      landmarkPlaceholder: messages.fulfilment.landmarkPlaceholder,
      landmarkHelp: messages.fulfilment.landmarkHelp,
      zoneFee: (amount) => fillTemplate(messages.fulfilment.zoneFeeTemplate, { amount }),
      zoneFree: messages.fulfilment.zoneFree,
      zoneLabel: (zone) => fillTemplate(messages.fulfilment.zoneLabelTemplate, { zone }),
      pickupAt: (landmark) => fillTemplate(messages.fulfilment.pickupAtTemplate, { landmark }),
      pickupHours: (hours) => fillTemplate(messages.fulfilment.pickupHoursTemplate, { hours }),
      outsideZone: messages.fulfilment.outsideZone,
      mixedHint: messages.fulfilment.mixedHint,
      continue: messages.fulfilment.continue,
      subtotal: messages.fulfilment.subtotal,
      deliveryFees: messages.fulfilment.deliveryFees,
      total: messages.fulfilment.total,
      loading: messages.fulfilment.loading,
      error: messages.fulfilment.error,
    },
    payment: {
      title: messages.payment.title,
      subtitle: messages.payment.subtitle,
      momo: messages.payment.momo,
      card: messages.payment.card,
      cod: messages.payment.cod,
      railMtn: messages.payment.railMtn,
      railAirtel: messages.payment.railAirtel,
      payerLabel: messages.payment.payerLabel,
      payerHelp: messages.payment.payerHelp,
      payerPlaceholder: messages.payment.payerPlaceholder,
      countryCode: messages.payment.countryCode,
      nationalNumber: messages.payment.nationalNumber,
      cardExplainer: messages.payment.cardExplainer,
      codIneligible: (cap) => fillTemplate(messages.payment.codIneligibleTemplate, { cap }),
      continue: messages.payment.continue,
      loading: messages.payment.loading,
      required: messages.payment.required,
      invalidPayer: messages.payment.invalidPayer,
      railRequired: messages.payment.railRequired,
      codRejected: messages.payment.codRejected,
      railRejected: messages.payment.railRejected,
      error: messages.payment.error,
    },
    review: {
      title: messages.review.title,
      subtitle: messages.review.subtitle,
      lineItems: messages.review.lineItems,
      qtyTemplate: messages.review.qtyTemplate,
      subtotal: messages.review.subtotal,
      deliveryFees: messages.review.deliveryFees,
      total: messages.review.total,
      paymentMethod: messages.review.paymentMethod,
      methodMomo: messages.review.methodMomoTemplate,
      methodCard: messages.review.methodCard,
      methodCod: messages.review.methodCod,
      railMtn: messages.review.railMtn,
      railAirtel: messages.review.railAirtel,
      payerNumber: messages.review.payerNumberTemplate,
      escrowTitle: messages.review.escrowTitle,
      escrowStep1: messages.review.escrowStep1,
      escrowStep2: messages.review.escrowStep2,
      escrowStep3: messages.review.escrowStep3,
      consentLabel: messages.review.consentLabel,
      consentRequired: messages.review.consentRequired,
      placeOrder: messages.review.placeOrder,
      loading: messages.review.loading,
    },
    countdown: {
      label: messages.countdown.label,
      expired: messages.countdown.expired,
      ariaLive: (time) => fillTemplate(messages.countdown.ariaLiveTemplate, { time }),
    },
    reservationExpired: messages.reservationExpired,
    loading: messages.loading,
    error: messages.error,
    emptyCart: messages.emptyCart,
  };
}

type CheckoutShellProps = {
  locale: string;
  labels: CheckoutShellLabels;
};

export function CheckoutShell({ locale, labels: messageLabels }: CheckoutShellProps) {
  const labels = resolveLabels(messageLabels);
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [step, setStep] = useState(0);
  const [checkoutSession, setCheckoutSession] = useState<CheckoutSession | null>(null);
  const [fulfilmentTotals, setFulfilmentTotals] = useState<FulfilmentTotals | null>(null);
  const [paymentSelection, setPaymentSelection] = useState<ValidatedPayment | null>(null);
  const [paymentOptions, setPaymentOptions] = useState<PaymentOptions | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);

  const cartPath = `/${locale}/cart`;

  const initSession = useCallback(
    async (accessToken: string) => {
      setInitializing(true);
      setErrorMessage(null);
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => accessToken,
        });
        const response = await client.request<CheckoutSession>("/checkout/session", {
          method: "POST",
        });
        setCheckoutSession(response);
        setStep(response.contact_skipped ? 1 : 0);
      } catch (error) {
        if (error instanceof ApiError) {
          if (error.code === "checkout.cart_empty") {
            router.push(cartPath);
            return;
          }
          if (error.details.notice_key === "checkout.checkout.stockUnavailable") {
            router.push(`${cartPath}?notice=stock_unavailable`);
            return;
          }
        }
        setErrorMessage(labels.error);
      } finally {
        setInitializing(false);
      }
    },
    [cartPath, labels.error, router],
  );

  useEffect(() => {
    if (sessionLoading || !session?.access_token || checkoutSession || initializing) {
      return;
    }
    if (step === 0 && !session.user?.phone) {
      return;
    }
    void initSession(session.access_token);
  }, [session, sessionLoading, checkoutSession, initializing, initSession, step]);

  const handleContactComplete = async () => {
    const supabase = await import("@vergeo/auth/browser-client").then((mod) =>
      mod.createBrowserClient(),
    );
    const { data } = await supabase.auth.getSession();
    const nextToken = data.session?.access_token;
    if (!nextToken) {
      setErrorMessage(labels.error);
      return;
    }
    setStep(1);
    await initSession(nextToken);
  };

  const steps = [
    { key: "contact", label: labels.steps.contact },
    { key: "fulfilment", label: labels.steps.fulfilment },
    { key: "payment", label: labels.steps.payment },
    { key: "review", label: labels.steps.review },
  ];

  if (sessionLoading || initializing) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
        <p className="font-body text-sm text-text-3" aria-live="polite">
          {labels.loading}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>

      <Stepper
        steps={steps}
        currentStep={step}
        stepAnnouncement={(current, total) => labels.stepAnnouncement(current, total)}
        doneIndicator={labels.doneIndicator}
        LinkComponent={Link}
      />

      {errorMessage ? (
        <p role="alert" className="font-body text-sm text-danger">
          {errorMessage}
        </p>
      ) : null}

      {step === 0 && !checkoutSession ? (
        <StepContact labels={labels.contact} onComplete={() => void handleContactComplete()} />
      ) : null}

      {step === 1 && checkoutSession && session?.access_token ? (
        <StepFulfilment
          locale={locale}
          session={checkoutSession}
          accessToken={session.access_token}
          labels={labels.fulfilment}
          countdownLabels={labels.countdown}
          reservationExpiredMessage={labels.reservationExpired}
          cartPath={cartPath}
          onComplete={(totals) => {
            setFulfilmentTotals(totals);
            setStep(2);
          }}
        />
      ) : null}

      {step === 2 && checkoutSession && session?.access_token ? (
        <StepPayment
          locale={locale}
          sessionId={checkoutSession.session_id}
          accessToken={session.access_token}
          labels={labels.payment}
          onComplete={(payment, options) => {
            setPaymentSelection(payment);
            setPaymentOptions(options);
            setStep(3);
          }}
        />
      ) : null}

      {step === 3 && checkoutSession && fulfilmentTotals && paymentSelection && paymentOptions ? (
        <StepReview
          locale={locale}
          session={checkoutSession}
          totals={paymentOptions}
          payment={paymentSelection as ReviewPayment}
          labels={labels.review}
        />
      ) : null}
    </div>
  );
}

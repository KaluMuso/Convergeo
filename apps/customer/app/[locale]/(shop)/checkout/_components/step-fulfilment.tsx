"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { Stepper } from "@vergeo/ui/src/stepper";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import {
  customerAuth,
  getReadyCustomerSession,
  useSession,
} from "../../../../../lib/customer-session";
import { classifyPlaceOrderError, placeOrder } from "../_lib/place-order";

import {
  ContactStepIntro,
  ContactStepSkeleton,
  StepContact,
  type ContactStepLabels,
} from "./step-contact";
import { StepReview, type ReviewPayment, type ReviewStepLabels } from "./step-review";

import type { PaymentOptions, PaymentStepLabels, ValidatedPayment } from "./step-payment";
import type { FulfilmentMode, SaleUnit } from "../../_components/sale-quantity";

/** Lazy — step 3 is only reached after contact + fulfilment; keeps /checkout first-load JS in budget. */
const StepPayment = dynamic(() => import("./step-payment").then((mod) => mod.StepPayment), {
  ssr: false,
  loading: () => <div aria-hidden="true" className="min-h-48" />,
});

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
    sale_unit?: SaleUnit;
    unit_step_milli?: number;
    min_steps?: number;
    fulfilment_mode?: FulfilmentMode;
    lead_time_days?: number | null;
    listing_variant_id?: string | null;
    variant_options?: Array<{ group: string; value: string }>;
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
  addressLabel: string;
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
  /** UX pass 4 guidance — optional so older label fixtures keep compiling. */
  guide?: FulfilmentGuideLabels;
};

export type FulfilmentGuideLabels = {
  deliveryHelp: string;
  pickupHelp: string;
  groupHint: string;
  tipsTitle: string;
  tip1: string;
  tip2: string;
  tip3: string;
  landmarkRequired: string;
  cutoffTitle: string;
  cutoffBefore: string;
  cutoffAfter: string;
  cutoffMadeToOrder: string;
};

export type CountdownLabels = {
  label: string;
  expired: string;
  ariaLive: (time: string) => string;
};

export type GroupChoice = {
  vendor_id: string;
  fulfilment: "delivery" | "pickup";
};

export type FulfilmentGroupResult = {
  vendor_id: string;
  fulfilment: "delivery" | "pickup";
  delivery_zone: string | null;
  delivery_fee_ngwee: number;
  subtotal_ngwee: number;
};

export type FulfilmentTotals = {
  subtotal_ngwee: number;
  delivery_fee_ngwee: number;
  total_ngwee: number;
  groups: FulfilmentGroupResult[];
  /** Required by POST /orders when any group uses delivery. */
  addressId: string | null;
  /** Display-only: the landmark the buyer typed, echoed on the review step. */
  landmark?: string | null;
};

/** Lazy — step 2 is only reached after contact; keeps /checkout first-load JS in budget. */
const StepFulfilment = dynamic(
  () => import("./step-fulfilment-step").then((mod) => mod.StepFulfilment),
  { ssr: false, loading: () => <div aria-hidden="true" className="min-h-48" /> },
);

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
    variantOption?: string;
    variantSeparator?: string;
    saleUnits: ReviewStepLabels["saleUnits"];
    madeToOrderLeadTime: string;
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
    deliveryConsent?: { label: string; hint: string; saveFailed: string };
    placeOrder: string;
    loading: string;
    placingOrder: string;
    placeOrderUnavailable: string;
    whatHappensNext: string;
    nextMomo: string;
    nextCard: string;
    nextCod: string;
    codGuide?: ReviewStepLabels["codGuide"];
  };
  countdown: Omit<CountdownLabels, "ariaLive"> & { ariaLiveTemplate: string };
  reservationExpired: string;
  loading: string;
  error: string;
  emptyCart: string;
  retry: string;
  backToCart: string;
  /** `{cap}` — shown at checkout start when no payment method can take this total. */
  overCodCapTemplate?: string;
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
  retry: string;
  backToCart: string;
  overCodCap: ((cap: string) => string) | null;
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
      addressLabel: messages.fulfilment.addressLabel,
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
      guide: messages.fulfilment.guide,
    },
    payment: {
      title: messages.payment.title,
      subtitle: messages.payment.subtitle,
      momo: messages.payment.momo,
      card: messages.payment.card,
      cod: messages.payment.cod,
      momoHelp: messages.payment.momoHelp,
      cardHelp: messages.payment.cardHelp,
      codHelp: messages.payment.codHelp,
      railMtn: messages.payment.railMtn,
      railAirtel: messages.payment.railAirtel,
      payerLabel: messages.payment.payerLabel,
      payerHelp: messages.payment.payerHelp,
      payerPlaceholder: messages.payment.payerPlaceholder,
      countryCode: messages.payment.countryCode,
      nationalNumber: messages.payment.nationalNumber,
      cardExplainer: messages.payment.cardExplainer,
      codIneligible: (cap) => fillTemplate(messages.payment.codIneligibleTemplate, { cap }),
      codUnavailableTitle: messages.payment.codUnavailableTitle,
      selected: messages.payment.selected,
      unavailable: messages.payment.unavailable,
      continue: messages.payment.continue,
      loading: messages.payment.loading,
      required: messages.payment.required,
      invalidPayer: messages.payment.invalidPayer,
      railRequired: messages.payment.railRequired,
      codRejected: messages.payment.codRejected,
      railRejected: messages.payment.railRejected,
      error: messages.payment.error,
      paymentsDisabled: messages.payment.paymentsDisabled,
      codGuide: messages.payment.codGuide,
    },
    review: {
      title: messages.review.title,
      subtitle: messages.review.subtitle,
      lineItems: messages.review.lineItems,
      qtyTemplate: messages.review.qtyTemplate,
      variantOption: messages.review.variantOption,
      variantSeparator: messages.review.variantSeparator,
      saleUnits: messages.review.saleUnits,
      madeToOrderLeadTime: messages.review.madeToOrderLeadTime,
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
      deliveryConsent: messages.review.deliveryConsent,
      placeOrder: messages.review.placeOrder,
      loading: messages.review.loading,
      placingOrder: messages.review.placingOrder,
      placeOrderUnavailable: messages.review.placeOrderUnavailable,
      whatHappensNext: messages.review.whatHappensNext,
      nextMomo: messages.review.nextMomo,
      nextCard: messages.review.nextCard,
      nextCod: messages.review.nextCod,
      codGuide: messages.review.codGuide,
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
    retry: messages.retry,
    backToCart: messages.backToCart,
    overCodCap: messages.overCodCapTemplate
      ? (cap) => fillTemplate(messages.overCodCapTemplate ?? "", { cap })
      : null,
  };
}

type CheckoutShellProps = {
  locale: string;
  labels: CheckoutShellLabels;
};

export function CheckoutShell({ locale, labels: messageLabels }: CheckoutShellProps) {
  const identity = useSession();
  // Reset all checkout state (including child stores and order idempotency) at
  // the render boundary. A returning account is still a different generation.
  return (
    <IdentityCheckoutShell
      key={`${identity.generation}:${identity.session?.user.id ?? "anonymous"}`}
      locale={locale}
      labels={messageLabels}
      identity={identity}
    />
  );
}

function IdentityCheckoutShell({
  locale,
  labels: messageLabels,
  identity,
}: CheckoutShellProps & { identity: ReturnType<typeof useSession> }) {
  const labels = resolveLabels(messageLabels);
  const router = useRouter();
  const { session, loading: sessionLoading, generation, error: authError } = identity;
  const retrying = useRef(false);
  const mounted = useRef(false);
  const started = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const isCurrent = useCallback(() => {
    const current = customerAuth.snapshot();
    return (
      mounted.current &&
      !current.loading &&
      !current.error &&
      current.generation === generation &&
      current.session?.user.id === session?.user.id
    );
  }, [generation, session?.user.id]);
  const [step, setStep] = useState(0);
  const [checkoutSession, setCheckoutSession] = useState<CheckoutSession | null>(null);
  const [fulfilmentTotals, setFulfilmentTotals] = useState<FulfilmentTotals | null>(null);
  const [paymentSelection, setPaymentSelection] = useState<ValidatedPayment | null>(null);
  const [paymentOptions, setPaymentOptions] = useState<PaymentOptions | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);
  // Formatted COD cap when this total can be paid no way at all (over the COD
  // cap while online payments are off) — said up front, not at the payment step.
  const [overCodCap, setOverCodCap] = useState<string | null>(null);
  const [idempotencyKey] = useState(() =>
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `ord-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
  );

  const cartPath = `/${locale}/cart`;

  const initSession = useCallback(
    async (accessToken: string) => {
      if (!isCurrent() || started.current) return;
      started.current = true;
      setInitializing(true);
      setErrorMessage(null);
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => accessToken,
        });
        // Auth may remount this shell before the OTP component resumes. Persist
        // the accepted account phone before asking the server for its snapshot.
        const contact = await client.request<{ verified: boolean }>("/checkout/steps/contact", {
          method: "POST",
          body: JSON.stringify(session?.user.phone ? { phone: session.user.phone } : {}),
        });
        if (!isCurrent()) return;
        if (contact.verified !== true) throw new Error("checkout.contact_unverified");
        const response = await client.request<CheckoutSession>("/checkout/session", {
          method: "POST",
        });
        if (!isCurrent()) return;
        if (!response.vendor_groups.length) {
          setErrorMessage(labels.error);
          started.current = false;
          return;
        }
        setCheckoutSession(response);
        // Contact was explicitly verified above; contact_skipped is a profile
        // snapshot hint, not a reason to hide a completed Contact step.
        setStep(1);
      } catch (error) {
        if (!isCurrent()) return;
        started.current = false;
        if (error instanceof ApiError) {
          if (error.code === "checkout.cart_empty") {
            router.push(cartPath);
            return;
          }
          if (
            error.details.notice_key === "checkout.checkout.stockUnavailable" ||
            error.details.redirect_to === "cart"
          ) {
            // Stock ran out or the cart needs review (price, minimum quantity,
            // withdrawn listing): retrying here can never succeed.
            router.push(`${cartPath}?notice=stock_unavailable`);
            return;
          }
        }
        setErrorMessage(labels.error);
      } finally {
        if (isCurrent()) setInitializing(false);
      }
    },
    [cartPath, labels.error, router, isCurrent, session?.user.phone],
  );

  useEffect(() => {
    if (
      sessionLoading ||
      authError ||
      errorMessage ||
      !session?.access_token ||
      checkoutSession ||
      initializing
    ) {
      return;
    }
    if (step === 0 && !session.user?.phone) {
      return;
    }
    void initSession(session.access_token);
  }, [
    session,
    sessionLoading,
    authError,
    errorMessage,
    checkoutSession,
    initializing,
    initSession,
    step,
  ]);

  const checkoutSessionId = checkoutSession?.session_id ?? null;
  const accessToken = session?.access_token ?? null;
  useEffect(() => {
    if (!checkoutSessionId || !accessToken) return;
    let cancelled = false;
    void (async () => {
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => accessToken,
        });
        const options = await client.request<PaymentOptions>(
          `/checkout/steps/payment-options?session_id=${encodeURIComponent(checkoutSessionId)}`,
        );
        if (cancelled || !isCurrent()) return;
        const methods = options?.available_methods;
        if (Array.isArray(methods) && methods.length === 0) {
          setOverCodCap(formatK(options.cod_cap_ngwee, { locale: `${locale}-ZM` }));
        }
      } catch {
        // Advisory only: the payment step still explains what is available.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, checkoutSessionId, isCurrent, locale]);

  const handleContactComplete = async () => {
    let nextToken: string | undefined;
    try {
      nextToken = (await getReadyCustomerSession())?.access_token;
    } catch {
      if (isCurrent()) setErrorMessage(labels.error);
      return;
    }
    if (!isCurrent()) return;
    if (!nextToken) {
      setErrorMessage(labels.error);
      return;
    }
    await initSession(nextToken);
  };

  const steps = [
    { key: "contact", label: labels.steps.contact },
    { key: "fulfilment", label: labels.steps.fulfilment },
    { key: "payment", label: labels.steps.payment },
    { key: "review", label: labels.steps.review },
  ];

  const busy = sessionLoading || initializing;
  const showContact = step === 0 && !checkoutSession;

  // Keep public contact copy in the same DOM slot across both session-loading
  // boundaries. Only the controls wait for auth; mounting StepContact earlier
  // would also run its authenticated completion effect earlier.
  const renderShell = (content: ReactNode) => (
    <div className="space-y-6" aria-busy={busy || undefined}>
      <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>

      <Stepper
        steps={steps}
        currentStep={step}
        stepAnnouncement={(current, total) => labels.stepAnnouncement(current, total)}
        doneIndicator={labels.doneIndicator}
        LinkComponent={Link}
      />

      {showContact ? (
        <div className="space-y-4">
          <ContactStepIntro labels={labels.contact} />
          {content}
        </div>
      ) : (
        content
      )}
    </div>
  );

  if (busy) {
    // Preserve the Stepper and form geometry (Run #68 CLS) while rendering the
    // real public intro immediately instead of revealing the LCP text late.
    return renderShell(
      <ContactStepSkeleton loadingLabel={labels.loading} showIntro={!showContact} />,
    );
  }

  return renderShell(
    <>
      {authError || errorMessage ? (
        <div className="space-y-3">
          <p role="alert" className="font-body text-sm text-danger">
            {authError ? labels.error : errorMessage}
          </p>
          <Button
            loadingLabel={labels.loading}
            onClick={() => {
              if (retrying.current) return;
              retrying.current = true;
              void (async () => {
                try {
                  if (authError) await getReadyCustomerSession(true);
                  else if (session?.access_token) await initSession(session.access_token);
                } catch {
                  if (mounted.current) setErrorMessage(labels.error);
                } finally {
                  retrying.current = false;
                }
              })();
            }}
          >
            {labels.retry}
          </Button>
          <Link href={cartPath}>{labels.backToCart}</Link>
        </div>
      ) : null}

      {step === 0 && !checkoutSession && !authError && !errorMessage && !session?.user.phone ? (
        <StepContact
          labels={labels.contact}
          onComplete={() => void handleContactComplete()}
          showIntro={false}
        />
      ) : null}

      {step === 1 && overCodCap && labels.overCodCap ? (
        <div role="status" className="space-y-2" data-testid="checkout-over-cod-cap">
          <p className="font-body text-sm text-danger">{labels.overCodCap(overCodCap)}</p>
          <Link href={cartPath} className="font-body text-sm underline">
            {labels.backToCart}
          </Link>
        </div>
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
            if (!isCurrent()) return;
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
            if (!isCurrent()) return;
            setPaymentSelection(payment);
            setPaymentOptions(options);
            setStep(3);
          }}
        />
      ) : null}

      {step === 3 &&
      checkoutSession &&
      fulfilmentTotals &&
      paymentSelection &&
      paymentOptions &&
      session?.access_token ? (
        <StepReview
          locale={locale}
          session={checkoutSession}
          totals={paymentOptions}
          payment={paymentSelection as ReviewPayment}
          fulfilment={{
            groups: fulfilmentTotals.groups,
            landmark: fulfilmentTotals.landmark ?? null,
          }}
          labels={labels.review}
          onPlaceOrder={async () => {
            if (!isCurrent()) throw new Error(labels.review.placeOrderUnavailable);
            if (!fulfilmentTotals.groups.length) {
              throw new Error(labels.review.placeOrderUnavailable);
            }
            try {
              await placeOrder({
                locale,
                accessToken: session.access_token,
                apiBaseUrl: getApiBaseUrl(),
                sessionId: checkoutSession.session_id,
                payment: paymentSelection as ReviewPayment,
                groups: fulfilmentTotals.groups.map((group) => ({
                  vendor_id: group.vendor_id,
                  fulfilment: group.fulfilment,
                  delivery_zone: group.delivery_zone,
                  delivery_fee_ngwee: group.delivery_fee_ngwee,
                  subtotal_ngwee: group.subtotal_ngwee,
                })),
                addressId: fulfilmentTotals.addressId,
                idempotencyKey,
                navigate: (href) => {
                  if (isCurrent()) router.push(href);
                },
              });
            } catch (error) {
              const failure = classifyPlaceOrderError(error);
              if (failure.kind === "return_to_cart") {
                // The hold lapsed or the cart moved on: only a fresh checkout can
                // succeed, so explain it on the cart instead of looping here.
                if (isCurrent()) router.push(`${cartPath}?notice=${failure.notice}`);
                return;
              }
              if (failure.kind === "redo_fulfilment") {
                // Choices recorded before this release, or an address that no
                // longer prices into the quoted zone: confirm fulfilment again.
                if (isCurrent()) {
                  setFulfilmentTotals(null);
                  setPaymentSelection(null);
                  setPaymentOptions(null);
                  setStep(1);
                }
                return;
              }
              throw new Error(
                failure.kind === "cod_ineligible"
                  ? labels.payment.codRejected
                  : labels.review.placeOrderUnavailable,
              );
            }
            if (paymentSelection.method === "cod") {
              // The order took its lines out of the cart; refresh the shared
              // store so the header badge stops counting what was just bought.
              void import("../../_components/cart/mini-cart-drawer")
                .then(({ refreshCart }) => refreshCart())
                .catch(() => undefined);
            }
          }}
        />
      ) : null}
    </>,
  );
}

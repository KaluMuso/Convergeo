import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { CheckoutShell } from "./_components/step-fulfilment";

import type { CheckoutShellLabels } from "./_components/step-fulfilment";
import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

function buildCheckoutLabels(locale: string, messages: AbstractIntlMessages): CheckoutShellLabels {
  const t = createTranslator({ locale, messages, namespace: "checkout" });

  return {
    pageTitle: t("checkout.pageTitle"),
    stepAnnouncementTemplate: t("checkout.stepAnnouncement"),
    doneIndicator: t("checkout.doneIndicator"),
    steps: {
      contact: t("checkout.steps.contact"),
      fulfilment: t("checkout.steps.fulfilment"),
      payment: t("checkout.steps.payment"),
      review: t("checkout.steps.review"),
    },
    contact: {
      title: t("checkout.contact.title"),
      subtitle: t("checkout.contact.subtitle"),
      phoneLabel: t("checkout.contact.phoneLabel"),
      phoneHelp: t("checkout.contact.phoneHelp"),
      phonePlaceholder: t("checkout.contact.phonePlaceholder"),
      countryCode: t("checkout.contact.countryCode"),
      nationalNumber: t("checkout.contact.nationalNumber"),
      sendOtp: t("checkout.contact.sendOtp"),
      verifyOtp: t("checkout.contact.verifyOtp"),
      otpAria: t("checkout.contact.otpAria"),
      otpDigitTemplate: t("checkout.contact.otpDigit"),
      resend: t("checkout.contact.resend"),
      resendInTemplate: t("checkout.contact.resendIn"),
      changePhone: t("checkout.contact.changePhone"),
      loading: t("checkout.contact.loading"),
      required: t("checkout.contact.required"),
      invalidPhone: t("checkout.contact.invalidPhone"),
      sendFailed: t("checkout.contact.sendFailed"),
      wrongCode: t("checkout.contact.wrongCode"),
      expired: t("checkout.contact.expired"),
      throttledTemplate: t("checkout.contact.throttled"),
      generic: t("checkout.contact.generic"),
      skippedLoggedIn: t("checkout.contact.skippedLoggedIn"),
    },
    fulfilment: {
      title: t("checkout.fulfilment.title"),
      subtitle: t("checkout.fulfilment.subtitle"),
      delivery: t("checkout.fulfilment.delivery"),
      pickup: t("checkout.fulfilment.pickup"),
      landmarkLabel: t("checkout.fulfilment.landmarkLabel"),
      landmarkPlaceholder: t("checkout.fulfilment.landmarkPlaceholder"),
      landmarkHelp: t("checkout.fulfilment.landmarkHelp"),
      zoneFeeTemplate: t("checkout.fulfilment.zoneFee"),
      zoneFree: t("checkout.fulfilment.zoneFree"),
      zoneLabelTemplate: t("checkout.fulfilment.zoneLabel"),
      pickupAtTemplate: t("checkout.fulfilment.pickupAt"),
      pickupHoursTemplate: t("checkout.fulfilment.pickupHours"),
      outsideZone: t("checkout.fulfilment.outsideZone"),
      mixedHint: t("checkout.fulfilment.mixedHint"),
      continue: t("checkout.fulfilment.continue"),
      subtotal: t("checkout.fulfilment.subtotal"),
      deliveryFees: t("checkout.fulfilment.deliveryFees"),
      total: t("checkout.fulfilment.total"),
      loading: t("checkout.contact.loading"),
      error: t("checkout.error"),
    },
    payment: {
      title: t("checkout.payment.title"),
      subtitle: t("checkout.payment.subtitle"),
      momo: t("checkout.payment.momo"),
      card: t("checkout.payment.card"),
      cod: t("checkout.payment.cod"),
      momoHelp: t("checkout.payment.momoHelp"),
      cardHelp: t("checkout.payment.cardHelp"),
      codHelp: t("checkout.payment.codHelp"),
      railMtn: t("checkout.payment.railMtn"),
      railAirtel: t("checkout.payment.railAirtel"),
      payerLabel: t("checkout.payment.payerLabel"),
      payerHelp: t("checkout.payment.payerHelp"),
      payerPlaceholder: t("checkout.payment.payerPlaceholder"),
      countryCode: t("checkout.payment.countryCode"),
      nationalNumber: t("checkout.payment.nationalNumber"),
      cardExplainer: t("checkout.payment.cardExplainer"),
      codIneligibleTemplate: t("checkout.payment.codIneligible"),
      codUnavailableTitle: t("checkout.payment.codUnavailableTitle"),
      selected: t("checkout.payment.selected"),
      unavailable: t("checkout.payment.unavailable"),
      continue: t("checkout.payment.continue"),
      loading: t("checkout.payment.loading"),
      required: t("checkout.payment.required"),
      invalidPayer: t("checkout.payment.invalidPayer"),
      railRequired: t("checkout.payment.railRequired"),
      codRejected: t("checkout.payment.codRejected"),
      railRejected: t("checkout.payment.railRejected"),
      error: t("checkout.payment.error"),
      paymentsDisabled: t("checkout.payment.paymentsDisabled"),
    },
    review: {
      title: t("checkout.review.title"),
      subtitle: t("checkout.review.subtitle"),
      lineItems: t("checkout.review.lineItems"),
      qtyTemplate: t("checkout.review.qty"),
      subtotal: t("checkout.review.subtotal"),
      deliveryFees: t("checkout.review.deliveryFees"),
      total: t("checkout.review.total"),
      paymentMethod: t("checkout.review.paymentMethod"),
      methodMomoTemplate: t("checkout.review.methodMomo"),
      methodCard: t("checkout.review.methodCard"),
      methodCod: t("checkout.review.methodCod"),
      railMtn: t("checkout.review.railMtn"),
      railAirtel: t("checkout.review.railAirtel"),
      payerNumberTemplate: t("checkout.review.payerNumber"),
      escrowTitle: t("checkout.review.escrowTitle"),
      escrowStep1: t("checkout.review.escrowStep1"),
      escrowStep2: t("checkout.review.escrowStep2"),
      escrowStep3: t("checkout.review.escrowStep3"),
      consentLabel: t("checkout.review.consentLabel"),
      consentRequired: t("checkout.review.consentRequired"),
      placeOrder: t("checkout.review.placeOrder"),
      loading: t("checkout.review.loading"),
      placingOrder: t("checkout.review.placingOrder"),
      placeOrderUnavailable: t("checkout.review.placeOrderUnavailable"),
      whatHappensNext: t("checkout.review.whatHappensNext"),
      nextMomo: t("checkout.review.nextMomo"),
      nextCard: t("checkout.review.nextCard"),
      nextCod: t("checkout.review.nextCod"),
    },
    countdown: {
      label: t("checkout.countdown.label"),
      expired: t("checkout.countdown.expired"),
      ariaLiveTemplate: t("checkout.countdown.ariaLive"),
    },
    reservationExpired: t("checkout.reservationExpired"),
    loading: t("checkout.loading"),
    error: t("checkout.error"),
    emptyCart: t("checkout.emptyCart"),
  };
}

export default async function CheckoutPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const checkoutMessages = await loadNamespace(locale as Locale, "checkout");
  const messages = { ...baseMessages, checkout: checkoutMessages } as AbstractIntlMessages;
  const labels = buildCheckoutLabels(locale, messages);

  return (
    <div className="lg:mx-auto lg:w-full lg:max-w-2xl">
      <CheckoutShell locale={locale} labels={labels} />
    </div>
  );
}

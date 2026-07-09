import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { CheckoutShell } from "./_components/step-fulfilment";

import type { CheckoutShellLabels } from "./_components/step-fulfilment";

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

  return <CheckoutShell locale={locale} labels={labels} />;
}

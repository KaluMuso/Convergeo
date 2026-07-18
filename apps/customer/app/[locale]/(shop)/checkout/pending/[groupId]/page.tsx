import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { PendingPaymentShell, type PendingLabels } from "../../_components/ussd-wait";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string; groupId: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({
    locale,
    groupId: "00000000-0000-0000-0000-000000000000",
  }));
}

function buildPendingLabels(locale: string, messages: AbstractIntlMessages): PendingLabels {
  const t = createTranslator({ locale, messages, namespace: "checkout" });

  return {
    pageTitle: t("checkout.pending.pageTitle"),
    loading: t("checkout.pending.loading"),
    error: t("checkout.pending.error"),
    pollAria: t("checkout.pending.pollAria"),
    successRedirect: t("checkout.pending.successRedirect"),
    confirmingTitle: t("checkout.pending.confirmingTitle"),
    confirmingBody: t("checkout.pending.confirmingBody"),
    codTitle: t("checkout.pending.codTitle"),
    codBody: t("checkout.pending.codBody"),
    codCta: t("checkout.pending.codCta"),
    viewOrder: t("checkout.pending.viewOrder"),
    ussd: {
      title: t("checkout.ussd.title"),
      subtitle: t("checkout.ussd.subtitle"),
      amountLabel: t("checkout.ussd.amountLabel"),
      mtnHelp: t("checkout.ussd.mtnHelp"),
      airtelHelp: t("checkout.ussd.airtelHelp"),
      genericHelp: t("checkout.ussd.genericHelp"),
      waiting: t("checkout.ussd.waiting"),
      doNotClose: t("checkout.ussd.doNotClose"),
      pollAria: t("checkout.pending.pollAria"),
    },
    failed: {
      timeoutTitle: t("checkout.pending.timeoutTitle"),
      timeoutBody: t("checkout.pending.timeoutBody"),
      retry: t("checkout.pending.retry"),
      retrying: t("checkout.pending.retrying"),
      retryError: t("checkout.pending.retryError"),
      cancelledTitle: t("checkout.pending.cancelledTitle"),
      cancelledBody: t("checkout.pending.cancelledBody"),
      cancelledCta: t("checkout.pending.cancelledCta"),
    },
  };
}

export default async function PendingCheckoutPage({ params }: PageProps) {
  const { locale, groupId } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const checkoutMessages = await loadNamespace(locale as Locale, "checkout");
  const messages = { ...baseMessages, checkout: checkoutMessages } as AbstractIntlMessages;
  const labels = buildPendingLabels(locale, messages);

  return (
    <div className="lg:mx-auto lg:w-full lg:max-w-2xl">
      <PendingPaymentShell locale={locale} groupId={groupId} labels={labels} />
    </div>
  );
}

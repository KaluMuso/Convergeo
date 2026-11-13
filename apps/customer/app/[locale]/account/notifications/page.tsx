import { LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { notificationClientMessages } from "../../_components/notification-bell-island";

import { CustomerNotificationsPage } from "./notifications-client";

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

export default async function AccountNotificationsPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const messages = await notificationClientMessages(locale);
  const t = createTranslator({ locale, messages, namespace: "notifications" });

  return (
    <section aria-labelledby="notifications-heading" className="mt-6 flex flex-col gap-4">
      <div>
        <h2 id="notifications-heading" className="font-display text-h2 text-display-ink">
          {t("center.title")}
        </h2>
        <p className="mt-1 text-sm text-text-2">{t("center.pageDescription")}</p>
      </div>
      <NextIntlClientProvider locale={locale} messages={messages}>
        <CustomerNotificationsPage locale={locale} />
      </NextIntlClientProvider>
    </section>
  );
}

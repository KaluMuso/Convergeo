import { LOCALES, loadMessages, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { SentryInit } from "../sentry-init";

import type { Metadata, Viewport } from "next";

import "../globals.css";

export const metadata: Metadata = {
  title: "Vergeo5 Admin",
  robots: {
    index: false,
    follow: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

const NAV_ITEMS = [
  { href: "", key: "home" },
  { href: "kyc", key: "kyc" },
  { href: "moderation", key: "moderation" },
  { href: "disputes", key: "disputes" },
  { href: "orders", key: "orders" },
  { href: "config", key: "config" },
  { href: "merch", key: "merch" },
  { href: "support", key: "support" },
] as const;

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function LocaleLayout({ children, params }: LayoutProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const [commonMessages, adminBundle] = await Promise.all([
    getMessages(),
    loadMessages(locale as Locale, ["admin"]),
  ]);
  const t = createTranslator({
    locale,
    namespace: "admin",
    messages: { admin: adminBundle.admin } as AbstractIntlMessages,
  });

  const messages = {
    ...commonMessages,
    admin: adminBundle.admin,
  };

  return (
    <html lang={locale}>
      <body className="antialiased">
        <NextIntlClientProvider messages={messages}>
          {/* Lazy Sentry loader — renders null; pulls the SDK into an async chunk. */}
          <SentryInit />
          <div className="min-h-dvh bg-[#FAF7F2] text-[#2A2118]">
            <header className="border-b border-[#E8DFD0] bg-[#241B30] text-[#EEEAE3]">
              <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-wide text-[#9F94B0]">
                    {t("shell.eyebrow")}
                  </p>
                  <h1 className="font-serif text-xl text-[#EEEAE3]">{t("title")}</h1>
                  <p className="text-xs text-[#9F94B0]">{t("shell.environment")}</p>
                </div>
                <Link
                  className="inline-flex min-h-11 items-center justify-center rounded-md border border-[#9F94B0]/40 px-4 text-sm font-medium text-[#EEEAE3]"
                  href={`/${locale}/login`}
                >
                  {t("shell.signOut")}
                </Link>
              </div>
            </header>

            <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-4 lg:flex-row">
              <nav
                aria-label={t("title")}
                className="flex shrink-0 flex-row gap-2 overflow-x-auto lg:w-56 lg:flex-col lg:overflow-visible"
              >
                {NAV_ITEMS.map((item) => {
                  const href = item.href ? `/${locale}/${item.href}` : `/${locale}`;
                  return (
                    <Link
                      key={item.key}
                      className="inline-flex min-h-11 shrink-0 items-center rounded-md border border-[#E8DFD0] bg-white px-3 text-sm font-medium text-[#2A2118] hover:border-[#2D4A7A] hover:text-[#2D4A7A]"
                      href={href}
                    >
                      {t(`nav.${item.key}`)}
                    </Link>
                  );
                })}
              </nav>

              <main className="min-w-0 flex-1 rounded-lg border border-[#E8DFD0] bg-white p-4 shadow-sm">
                {children}
              </main>
            </div>
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

import { LOCALES, loadMessages, type Locale } from "@vergeo/i18n";
import { fontVariables } from "@vergeo/ui/fonts";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { SentryInit } from "../sentry-init";

import { AdminShell } from "./_components/admin-shell";

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

  const messages = {
    ...commonMessages,
    admin: adminBundle.admin,
  };

  return (
    <html lang={locale} className={fontVariables()}>
      <head>
        {/* Pre-paint theme bootstrap — avoids a light/dark flash before hydration. */}
        <ThemeScript />
      </head>
      <body className="font-body antialiased">
        <ThemeProvider>
          <NextIntlClientProvider messages={messages}>
            {/* Lazy Sentry loader — renders null; pulls the SDK into an async chunk. */}
            <SentryInit />
            {/* Authenticated chrome; renders bare children on the login route. */}
            <AdminShell locale={locale}>{children}</AdminShell>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

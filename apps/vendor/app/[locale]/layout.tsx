import { LOCALES, type Locale } from "@vergeo/i18n";
import { fontVariables } from "@vergeo/ui/fonts";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import { notFound } from "next/navigation";
import { createTranslator, NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { SentryInit } from "../sentry-init";

import type { Metadata, Viewport } from "next";

import "../globals.css";

export const metadata: Metadata = {
  title: "Vergeo5 Vendor",
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
  const messages = await getMessages();
  const tCommon = createTranslator({ locale, messages, namespace: "common" });

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
            <div className="flex min-h-dvh flex-col">
              <header className="flex items-center justify-end border-b border-border bg-surface px-4 py-2">
                <ThemeToggle
                  label={tCommon("theme.label")}
                  lightLabel={tCommon("theme.light")}
                  darkLabel={tCommon("theme.dark")}
                  systemLabel={tCommon("theme.system")}
                />
              </header>
              <div className="flex-1">{children}</div>
            </div>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { fontVariables } from "@vergeo/ui/fonts";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { resolveVendorNavCapabilities } from "../../lib/nav-capabilities";
import { SentryInit } from "../sentry-init";

import { VendorShell } from "./_components/vendor-shell";

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
  // Shared request config only ships `common`. Vendor chrome and feature pages
  // also need `vendor`, `nav`, `services`, and `events`.
  const [baseMessages, extra] = await Promise.all([
    getMessages(),
    Promise.all(
      (["vendor", "nav", "services", "events"] as const).map(async (namespace) => [
        namespace,
        await loadNamespace(locale as Locale, namespace),
      ]),
    ),
  ]);
  const messages = { ...baseMessages, ...Object.fromEntries(extra) };
  const navCapabilities = await resolveVendorNavCapabilities();

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
            {/* Authenticated chrome; header + nav, bare children on the login route. */}
            <VendorShell locale={locale} capabilities={navCapabilities}>
              {children}
            </VendorShell>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

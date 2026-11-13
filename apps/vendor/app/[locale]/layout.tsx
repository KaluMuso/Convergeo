import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { fontVariables } from "@vergeo/ui/fonts";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import { ToastProvider } from "@vergeo/ui/src/toast";
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
  // The vendor dashboard's client views call useTranslations("vendor"), so the
  // namespace must live on the app-wide provider — the shared request config
  // only ships `common`, which previously left those views rendering raw keys.
  const [baseMessages, vendorMessages, serviceMessages, notificationMessages] = await Promise.all([
    getMessages(),
    loadNamespace(locale as Locale, "vendor"),
    loadNamespace(locale as Locale, "services"),
    loadNamespace(locale as Locale, "notifications"),
  ]);
  const notificationsAll = notificationMessages as Record<string, unknown>;
  const messages = {
    ...baseMessages,
    vendor: vendorMessages,
    services: serviceMessages,
    // Notification center copy only — not the WhatsApp/SMS/email templates.
    notifications: { center: notificationsAll.center, inApp: notificationsAll.inApp },
  };
  const navCapabilities = await resolveVendorNavCapabilities();

  // Translated toast copy for emitToastKey() call sites (common.toast).
  const toastCopy = (
    (baseMessages as Record<string, unknown>).common as Record<string, unknown> | undefined
  )?.toast as Record<string, unknown> | undefined;
  const toastDismiss = typeof toastCopy?.dismiss === "string" ? toastCopy.dismiss : undefined;

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
            <ToastProvider dismissLabel={toastDismiss} copy={toastCopy}>
              <VendorShell locale={locale} capabilities={navCapabilities}>
                {children}
              </VendorShell>
            </ToastProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

import { LOCALES, loadNamespace, type Locale } from "@vergeo/i18n";
import { fontVariables } from "@vergeo/ui/fonts";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import { ToastProvider } from "@vergeo/ui/src/toast";
import { notFound } from "next/navigation";
import { type AbstractIntlMessages, NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BASE_SPEC, pickMessages, specNamespaces } from "../../lib/route-messages";
import { SentryInit } from "../sentry-init";

import { AdminShell } from "./_components/admin-shell";

import type { Metadata, Viewport } from "next";

import "../globals.css";

export const metadata: Metadata = {
  title: {
    template: "%s · Convergeo Admin",
    default: "Convergeo Admin",
  },
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
  // Only the shell chrome ships here (BASE_SPEC: nav, shell, title, notification bell).
  // Each route segment layout adds the branches its client views read through
  // <RouteMessages>; shipping every catalog on every document cost ~36 kB gzip.
  const baseNamespaces = specNamespaces(BASE_SPEC);
  const [commonMessages, baseLoaded] = await Promise.all([
    getMessages(),
    Promise.all(baseNamespaces.map((namespace) => loadNamespace(locale as Locale, namespace))),
  ]);
  const messages: Record<string, unknown> = { ...commonMessages };
  baseNamespaces.forEach((namespace, index) => {
    messages[namespace] = pickMessages(
      baseLoaded[index] ?? {},
      BASE_SPEC[namespace as keyof typeof BASE_SPEC],
    );
  });

  // Translated toast copy for emitToastKey() call sites (common.toast).
  const toastCopy = (
    (commonMessages as Record<string, unknown>).common as Record<string, unknown> | undefined
  )?.toast as Record<string, unknown> | undefined;
  const toastDismiss = typeof toastCopy?.dismiss === "string" ? toastCopy.dismiss : undefined;

  return (
    <html lang={locale} className={fontVariables()} suppressHydrationWarning>
      <head>
        {/* Pre-paint theme bootstrap — avoids a light/dark flash before hydration. */}
        <ThemeScript />
      </head>
      <body className="font-body antialiased">
        <ThemeProvider>
          <NextIntlClientProvider messages={messages as AbstractIntlMessages}>
            {/* Lazy Sentry loader — renders null; pulls the SDK into an async chunk. */}
            <SentryInit />
            {/* Authenticated chrome; renders bare children on the login route. */}
            <ToastProvider dismissLabel={toastDismiss} copy={toastCopy}>
              <AdminShell locale={locale}>{children}</AdminShell>
            </ToastProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

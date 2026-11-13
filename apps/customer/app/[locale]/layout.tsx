import { AnalyticsProvider } from "@vergeo/analytics/provider";
import {
  isSeoIndexableLocale,
  loadNamespace,
  LOCALES,
  robotsForLocalePublication,
  type Locale,
} from "@vergeo/i18n";
import { fontVariables } from "@vergeo/ui/fonts";
import { Footer } from "@vergeo/ui/src/footer";
import { SeasonalThemeStyle } from "@vergeo/ui/src/seasonal-theme";
import { getMetadataBase } from "@vergeo/ui/src/seo/metadata";
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import { ToastProvider } from "@vergeo/ui/src/toast";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { NextIntlClientProvider } from "next-intl";
import {
  getMessages,
  getTranslations,
  setRequestLocale,
} from "next-intl/server";

import { SentryInit } from "../sentry-init";

import { type LegalTranslator } from "./(marketing)/legal/_components/legal-shell";
import { CustomerAuthBarrier } from "./_components/customer-auth-barrier";
import { LazyFloatingActions } from "./_components/lazy-floating-actions";
import { LocaleSwitcher } from "./_components/locale-switcher";
import { ServiceWorkerRegister } from "./_components/service-worker-register";

import type { FloatingActionsLabels } from "./_components/floating-actions";
import type { Metadata, Viewport } from "next";

import "../globals.css";

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

/**
 * Locale-wide SEO publication gate (CUST-SEO-02).
 * Unapproved locales (bem/nya until native review) stay routable but noindex,follow.
 * Child routes may still set stricter robots (e.g. search noindex,nofollow).
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "common" });
  const appName = t("app.name");
  const description = t("meta.defaultDescription");

  const defaultTitle = t("meta.defaultTitle");

  const base: Metadata = {
    metadataBase: getMetadataBase(),
    title: {
      template: `%s | ${appName}`,
      default: defaultTitle,
    },
    description,
    applicationName: appName,
    icons: {
      icon: [
        { url: "/favicon.ico", sizes: "any" },
        { url: "/brand/convergeo-icon-192.png", sizes: "192x192", type: "image/png" },
        { url: "/brand/convergeo-icon-512.png", sizes: "512x512", type: "image/png" },
      ],
      apple: [{ url: "/brand/convergeo-icon-180.png", sizes: "180x180", type: "image/png" }],
      shortcut: "/favicon.ico",
    },
    openGraph: {
      siteName: appName,
      type: "website",
      locale,
      title: defaultTitle,
      description,
    },
    twitter: {
      card: "summary_large_image",
      title: defaultTitle,
      description,
    },
  };

  if (!isSeoIndexableLocale(locale)) {
    return {
      ...base,
      robots: robotsForLocalePublication(locale),
    };
  }

  return base;
}

export default async function LocaleLayout({ children, params }: LayoutProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const [legalMessages, checkoutMessages] = await Promise.all([
    loadNamespace(locale as Locale, "legal"),
    loadNamespace(locale as Locale, "checkout"),
  ]);
  const messages = {
    ...baseMessages,
    legal: legalMessages,
    checkout: checkoutMessages,
  } as AbstractIntlMessages;

  const tLegal = createTranslator({
    locale,
    messages,
    namespace: "legal",
  }) as unknown as LegalTranslator;
  const tCommon = createTranslator({
    locale,
    messages,
    namespace: "common",
  }) as unknown as LegalTranslator;
  const tCheckout = createTranslator({
    locale,
    messages,
    namespace: "checkout",
  });
  const year = new Date().getFullYear();
  const fabCopy = ((messages.common as AbstractIntlMessages | undefined)?.fab ??
    {}) as Record<string, string>;
  const fabLabels: FloatingActionsLabels = {
    ask: fabCopy.ask ?? "",
    askTitle: fabCopy.askTitle ?? "",
    askHint: fabCopy.askHint ?? "",
    askPlaceholder: fabCopy.askPlaceholder ?? "",
    send: fabCopy.send ?? "",
    voiceStart: fabCopy.voiceStart ?? "",
    voiceStop: fabCopy.voiceStop ?? "",
    listening: fabCopy.listening ?? "",
    voiceUnsupported: fabCopy.voiceUnsupported ?? "",
    close: fabCopy.close ?? "",
    showFooter: fabCopy.showFooter ?? "",
    hideFooter: fabCopy.hideFooter ?? "",
  };
  // Translated toast copy for emitToastKey() call sites (no i18n hook needed there).
  const toastCopy = ((messages.common as AbstractIntlMessages | undefined)
    ?.toast ?? {}) as Record<string, unknown>;
  const appName = tCommon("app.name");
  const localeSwitcherLabels = {
    ariaLabel: tCommon("locale.switchAria"),
    names: {
      en: tCommon("locale.names.en"),
      bem: tCommon("locale.names.bem"),
      nya: tCommon("locale.names.nya"),
      fr: tCommon("locale.names.fr"),
    },
  };

  const footerColumns = [
    {
      key: "legal",
      heading: tLegal("footer.legalHeading"),
      links: [
        {
          key: "terms",
          href: `/${locale}/legal/terms`,
          label: tLegal("footer.links.terms"),
        },
        {
          key: "privacy",
          href: `/${locale}/legal/privacy`,
          label: tLegal("footer.links.privacy"),
        },
        {
          key: "returns",
          href: `/${locale}/legal/returns`,
          label: tLegal("footer.links.returns"),
        },
        {
          key: "vendorAgreement",
          href: `/${locale}/legal/vendor-agreement`,
          label: tLegal("footer.links.vendorAgreement"),
        },
      ],
    },
    {
      key: "help",
      heading: tLegal("footer.helpHeading"),
      links: [
        {
          key: "help",
          href: `/${locale}/help`,
          label: tLegal("footer.links.help"),
        },
        {
          key: "contact",
          href: `/${locale}/contact`,
          label: tLegal("footer.links.contact"),
        },
      ],
    },
    {
      key: "sell",
      heading: tLegal("footer.sellHeading"),
      links: [
        {
          key: "sell",
          href: `/${locale}/sell`,
          label: tLegal("footer.links.sell"),
        },
      ],
    },
  ];

  return (
    <html lang={locale} className={fontVariables()}>
      <head>
        {/* Pre-paint theme bootstrap — sets <html data-theme> before first paint
            so the token palette (and body bg/text) never flash. Default choice
            is system (ThemeScript collapses missing/invalid storage to OS). */}
        <ThemeScript />
        {/* Seasonal brand re-skin (SELECTION.md §8). Operator-selected via the
            NEXT_PUBLIC_SEASONAL_THEME env (single knob both apps read) —
            server-rendered inline CSS, so the seasonal palette is present on
            first paint with no flash and no client cost. Overrides win by
            specificity (see seasonalThemeCss), and the dark block applies once
            <ThemeScript /> stamps data-theme. Default preset ⇒ renders null. */}
        <SeasonalThemeStyle preset={process.env.NEXT_PUBLIC_SEASONAL_THEME} />
      </head>
      <body className="flex min-h-dvh flex-col font-body antialiased">
        <ThemeProvider>
          <NextIntlClientProvider messages={messages}>
            <ToastProvider
              dismissLabel={tCommon("toast.dismiss")}
              copy={toastCopy}
            >
              {/* Lazy Sentry loader — renders null; pulls the SDK into an async chunk. */}
              <SentryInit />
              {/* Probe `/sw.js` before registering — never register a missing worker. */}
              <ServiceWorkerRegister />
              {/* Consent-aware GA4 mirror; SSR-safe (renders null, no CLS). GA4 fires
                only on consent — the anonymized server log is the source of truth. */}
              <AnalyticsProvider
                measurementId={process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID}
              />
              <CustomerAuthBarrier
                labels={{
                  title: tCheckout("cart.mergeRecoveryTitle"),
                  body: tCheckout("cart.mergeRecoveryBody"),
                  conflictLine: String(tCheckout.raw("cart.mergeConflictLine")),
                  priceLine: String(tCheckout.raw("cart.mergePriceLine")),
                  unnamedItem: String(tCheckout.raw("cart.mergeUnnamedItem")),
                  wholesaleTerms: String(
                    tCheckout.raw("cart.mergeWholesaleTerms"),
                  ),
                  priceNeedsReview: tCheckout("cart.mergePriceNeedsReview"),
                  accountChoice: tCheckout("cart.mergeAccountChoice"),
                  guestChoice: tCheckout("cart.mergeGuestChoice"),
                  apply: tCheckout("cart.mergeApply"),
                  retry: tCheckout("cart.mergeRetry"),
                  signOut: tCheckout("cart.mergeSignOut"),
                  failure: tCheckout("cart.mergeFailure"),
                }}
              />
              <div className="flex flex-1 flex-col">{children}</div>
              {/* Footer inline on most pages; on home it becomes an overlay sheet
                behind the floating toggle (keeps the infinite feed clear). */}
              <LazyFloatingActions
                locale={locale}
                labels={fabLabels}
                footer={
                  <Footer
                    appName={appName}
                    copyright={tLegal("footer.copyright", { year, appName })}
                    columns={footerColumns}
                    paymentNote={tCommon("paymentTrust.footerPaymentNote")}
                    tagline={tCommon("meta.defaultDescription")}
                    // Pilot is cash on delivery only: no escrow claim site-wide.
                    sealLabel={tCommon("paymentTrust.footerSeal")}
                    LinkComponent={Link}
                    trailing={
                      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
                        <LocaleSwitcher
                          locale={locale}
                          labels={localeSwitcherLabels}
                        />
                        <p
                          className="m-0 text-micro"
                          style={{ color: "var(--panel-muted)" }}
                        >
                          <Link
                            href={`/${locale}/account/preferences`}
                            className="inline-flex min-h-11 items-center underline-offset-2 hover:underline"
                            style={{ color: "var(--panel-muted)" }}
                          >
                            {tCommon("theme.displayPreferences")}
                          </Link>
                        </p>
                      </div>
                    }
                  />
                }
              />
            </ToastProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

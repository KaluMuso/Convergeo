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
import { ThemeProvider } from "@vergeo/ui/src/theme-provider";
import { ThemeScript } from "@vergeo/ui/src/theme-script";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { SentryInit } from "../sentry-init";

import { type LegalTranslator } from "./(marketing)/legal/_components/legal-shell";
import { LocaleSwitcher } from "./_components/locale-switcher";
import { ServiceWorkerRegister } from "./_components/service-worker-register";

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
  const base: Metadata = {
    title: {
      template: "%s | Vergeo5",
      default: "Vergeo5",
    },
    description: "Discover products, services, and events across Zambia.",
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
  const legalMessages = await loadNamespace(locale as Locale, "legal");
  const messages = {
    ...baseMessages,
    legal: legalMessages,
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
  const year = new Date().getFullYear();
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
      </head>
      <body className="flex min-h-dvh flex-col font-body antialiased">
        <ThemeProvider>
          <NextIntlClientProvider messages={messages}>
            {/* Lazy Sentry loader — renders null; pulls the SDK into an async chunk. */}
            <SentryInit />
            {/* Probe `/sw.js` before registering — never register a missing worker. */}
            <ServiceWorkerRegister />
            {/* Consent-aware GA4 mirror; SSR-safe (renders null, no CLS). GA4 fires
                only on consent — the anonymized server log is the source of truth. */}
            <AnalyticsProvider measurementId={process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID} />
            <div className="flex flex-1 flex-col">{children}</div>
            <Footer
              appName={appName}
              copyright={tLegal("footer.copyright", { year, appName })}
              columns={footerColumns}
              paymentNote={tLegal("footer.paymentNote")}
              LinkComponent={Link}
              trailing={
                <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
                  <LocaleSwitcher locale={locale} labels={localeSwitcherLabels} />
                  <p className="m-0 text-micro" style={{ color: "var(--panel-muted)" }}>
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
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

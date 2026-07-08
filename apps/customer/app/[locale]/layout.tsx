import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { Footer } from "../../../../packages/ui/src/footer";

import { type LegalTranslator } from "./(marketing)/legal/_components/legal-shell";

import type { Metadata, Viewport } from "next";

import "../globals.css";

export const metadata: Metadata = {
  title: {
    template: "%s | Vergeo5",
    default: "Vergeo5",
  },
  description: "Discover products, services, and events across Zambia.",
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
  const baseMessages = await getMessages();
  const legalMessages = await loadNamespace(locale as Locale, "legal");
  const messages = { ...baseMessages, legal: legalMessages } as AbstractIntlMessages;

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
    <html lang={locale}>
      <body className="flex min-h-dvh flex-col antialiased">
        <NextIntlClientProvider messages={messages}>
          <div className="flex flex-1 flex-col">{children}</div>
          <Footer
            appName={appName}
            copyright={tLegal("footer.copyright", { year, appName })}
            columns={footerColumns}
            paymentNote={tLegal("footer.paymentNote")}
            LinkComponent={Link}
          />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

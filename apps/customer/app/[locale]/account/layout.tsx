import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { IconAccount, IconAsk, IconHome, IconOrders, IconSearch } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BottomNavClient } from "../(shop)/_components/bottom-nav-client";

import { AccountNav } from "./_components/account-nav";
import { requireAuthenticatedAccount } from "./_components/account-server";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type AccountLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function AccountLayout({ children, params }: AccountLayoutProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  await requireAuthenticatedAccount(locale);

  const baseMessages = await getMessages();
  const accountMessages = await loadNamespace(locale as Locale, "account");
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = {
    ...baseMessages,
    account: accountMessages,
    catalog: catalogMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account" });
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tCatalog = createTranslator({ locale, messages, namespace: "catalog" });

  const bottomItems = [
    {
      key: "home",
      icon: <IconHome />,
      label: tCatalog("home.nav.home"),
      href: `/${locale}`,
    },
    {
      key: "browse",
      icon: <IconSearch />,
      label: tCatalog("home.nav.browse"),
      href: `/${locale}/search`,
    },
    {
      key: "ask",
      icon: <IconAsk />,
      label: tCatalog("home.nav.ask"),
      href: `/${locale}/ask`,
    },
    {
      key: "orders",
      icon: <IconOrders />,
      label: tCatalog("home.nav.orders"),
      href: `/${locale}/account/orders`,
    },
    {
      key: "account",
      icon: <IconAccount />,
      label: tCatalog("home.nav.account"),
      href: `/${locale}/account`,
    },
  ];

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-20 pt-8 lg:pb-12">
      <a
        href="#account-main"
        className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
      >
        {tCommon("nav.skipToContent")}
      </a>
      <main id="account-main" tabIndex={-1} className="focus-visible:outline-none">
        <header className="mb-2 flex flex-wrap items-end justify-between gap-3">
          <h1 className="font-display text-h1 text-display-ink">{t("title")}</h1>
          <Link
            href={`/${locale}`}
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
          >
            {t("hub.backToShop")}
          </Link>
        </header>
        <AccountNav
          locale={locale}
          labels={{
            ariaLabel: t("title"),
            overview: t("nav.overview"),
            orders: t("nav.orders"),
            tickets: t("nav.tickets"),
            jobs: t("nav.jobs"),
            saved: t("nav.saved"),
            addresses: t("nav.addresses"),
            preferences: t("nav.preferences"),
            profile: t("nav.profile"),
            business: t("nav.business"),
            privacy: t("nav.privacy"),
            signOut: t("nav.signOut"),
            signingOut: t("nav.signingOut"),
          }}
        />
        {children}
      </main>
      <BottomNavClient
        items={bottomItems}
        ariaLabel={tCatalog("home.nav.bottomAriaLabel")}
        locale={locale}
      />
    </div>
  );
}

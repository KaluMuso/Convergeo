import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { IconAccount, IconAsk, IconHome, IconOrders, IconSearch } from "@vergeo/ui/src/icons";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BottomNavClient } from "../(shop)/_components/bottom-nav-client";

import { AccountAppHeader } from "./_components/account-app-header";
import { ACCOUNT_BOTTOM_NAV_ENABLED } from "./_components/account-feature-flags";
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
  const [accountMessages, catalogMessages, commonMessages, navMessages] = await Promise.all([
    loadNamespace(locale as Locale, "account"),
    loadNamespace(locale as Locale, "catalog"),
    loadNamespace(locale as Locale, "common"),
    loadNamespace(locale as Locale, "nav"),
  ]);
  const messages = {
    ...baseMessages,
    account: accountMessages,
    catalog: catalogMessages,
    common: commonMessages,
    nav: navMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account" });
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tNav = createTranslator({ locale, messages, namespace: "nav" });

  const localeSwitcherLabels = {
    ariaLabel: tCommon("locale.switchAria"),
    names: {
      en: tCommon("locale.names.en"),
      bem: tCommon("locale.names.bem"),
      nya: tCommon("locale.names.nya"),
      fr: tCommon("locale.names.fr"),
    },
  };

  const bottomItems = [
    {
      key: "home",
      icon: <IconHome />,
      label: tNav("shop.home"),
      href: `/${locale}`,
    },
    {
      key: "browse",
      icon: <IconSearch />,
      label: tNav("shop.browse"),
      href: `/${locale}/search`,
    },
    {
      key: "ask",
      icon: <IconAsk />,
      label: tNav("shop.ask"),
      href: `/${locale}/ask`,
    },
    {
      key: "orders",
      icon: <IconOrders />,
      label: tNav("shop.orders"),
      href: `/${locale}/account/orders`,
    },
    {
      key: "account",
      icon: <IconAccount />,
      label: tNav("shop.account"),
      href: `/${locale}/account`,
    },
  ];

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#account-main"
        className="sr-only rounded bg-primary text-sm font-medium text-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:inline-flex focus:min-h-11 focus:items-center focus:px-4 focus:shadow-focusRing"
      >
        {tNav("skipToContent")}
      </a>
      <AccountAppHeader
        locale={locale}
        labels={{
          appName: tCommon("app.name"),
          navAriaLabel: tNav("account.ariaLabel"),
          searchPlaceholder: tNav("shop.searchPlaceholder"),
          cart: tNav("shop.cart"),
          cartWithCount: tNav("shop.cartWithCount"),
          accountMenuAria: tNav("account.menuAria"),
          accountOverview: t("nav.overview"),
          accountOrders: t("nav.orders"),
          accountPreferences: t("nav.preferences"),
          signOut: t("nav.signOut"),
          signingOut: t("nav.signingOut"),
        }}
        localeSwitcherLabels={localeSwitcherLabels}
        catalogMessages={catalogMessages as Record<string, unknown>}
      />
      <div className="mx-auto w-full max-w-3xl flex-1 px-4 pb-20 pt-8 lg:pb-12">
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
      </div>
      {ACCOUNT_BOTTOM_NAV_ENABLED ? (
        <BottomNavClient
          items={bottomItems}
          ariaLabel={tNav("shop.bottomAriaLabel")}
          locale={locale}
        />
      ) : null}
    </div>
  );
}

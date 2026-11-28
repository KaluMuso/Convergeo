import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { IconAccount, IconAsk, IconHome, IconOrders, IconSearch } from "@vergeo/ui/src/icons";
import { PageHeader } from "@vergeo/ui/src/page-header";
import Link from "next/link";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BottomNavClient } from "../(shop)/_components/bottom-nav-client";
import { LazyCartHostSlot } from "../(shop)/_components/cart/lazy-cart-host-slot";
import { ShopHeaderSlot } from "../(shop)/_components/shop-header-slot";
import { socialContactsEnabled } from "../../../lib/social/flag-server";
import { TopUtilityBarSlot } from "../_components/top-utility-bar-slot";

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
  const showPeople = await socialContactsEnabled();

  const baseMessages = await getMessages();
  const [accountMessages, commonMessages, navMessages, ordersMessages, checkoutMessages] =
    await Promise.all([
      loadNamespace(locale as Locale, "account"),
      loadNamespace(locale as Locale, "common"),
      loadNamespace(locale as Locale, "nav"),
      loadNamespace(locale as Locale, "orders"),
      loadNamespace(locale as Locale, "checkout"),
    ]);
  const messages = {
    ...baseMessages,
    account: accountMessages,
    common: commonMessages,
    nav: navMessages,
    orders: ordersMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account" });
  const tNav = createTranslator({ locale, messages, namespace: "nav" });

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
      <TopUtilityBarSlot locale={locale} />
      {/* Same header as the shop pages (All Categories, search, Shops/Services/Events). */}
      <ShopHeaderSlot locale={locale} mainId="account-main" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-[calc(6rem+env(safe-area-inset-bottom,0px))] pt-6 sm:px-6 lg:px-6 lg:pb-12">
        <main id="account-main" tabIndex={-1} className="focus-visible:outline-none">
          <PageHeader
            title={t("title")}
            actions={
              <Link
                href={`/${locale}`}
                className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
              >
                {t("hub.backToShop")}
              </Link>
            }
            className="mb-2"
          />
          <AccountNav
            locale={locale}
            showPeople={showPeople}
            labels={{
              ariaLabel: t("title"),
              overview: t("nav.overview"),
              orders: t("nav.orders"),
              rewards: t("nav.rewards"),
              tickets: t("nav.tickets"),
              jobs: t("nav.jobs"),
              quotes: t("nav.quotes"),
              saved: t("nav.saved"),
              following: t("nav.following"),
              people: showPeople ? t("nav.people") : undefined,
              addresses: t("nav.addresses"),
              preferences: t("nav.preferences"),
              profile: t("nav.profile"),
              business: t("nav.business"),
              privacy: t("nav.privacy"),
              signOut: t("nav.signOut"),
              signingOut: t("nav.signingOut"),
            }}
          />
          {/*
           * Client i18n context for account pages. The root provider only carries
           * `common`, so fully-client pages here (e.g. privacy) that call
           * useTranslations("account.*") need the `account` namespace supplied
           * explicitly — otherwise every key renders as MISSING_MESSAGE. The
           * jobs/tickets subtrees add their own `services`/`events` providers.
           */}
          <NextIntlClientProvider
            locale={locale}
            messages={{
              account: accountMessages,
              common: commonMessages,
              orders: ordersMessages,
              nav: navMessages,
            }}
          >
            {children}
          </NextIntlClientProvider>
        </main>
      </div>
      {/* The header cart button opens the mini-cart drawer, which lives in this host. */}
      <NextIntlClientProvider
        locale={locale}
        messages={{ checkout: checkoutMessages, common: commonMessages }}
      >
        <LazyCartHostSlot locale={locale} />
      </NextIntlClientProvider>
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

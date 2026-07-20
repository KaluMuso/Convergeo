import { loadNamespace, type Locale } from "@vergeo/i18n";
import {
  IconAccount,
  IconAsk,
  IconCart,
  IconHome,
  IconOrders,
  IconSearch,
} from "@vergeo/ui/src/icons";
import Link from "next/link";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BottomNavClient } from "./_components/bottom-nav-client";
import { DesktopHeader } from "./_components/desktop-header";
import { MobileTopNav } from "./_components/mobile-top-nav";
import { ServiceInfoBar } from "./_components/service-info-bar";

type ShopLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function ShopLayout({ children, params }: ShopLayoutProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = {
    ...baseMessages,
    catalog: catalogMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "catalog" });
  const tCommon = createTranslator({ locale, messages, namespace: "common" });

  const bottomItems = [
    {
      key: "home",
      icon: <IconHome />,
      label: t("home.nav.home"),
      href: `/${locale}`,
    },
    {
      key: "browse",
      icon: <IconSearch />,
      label: t("home.nav.browse"),
      href: `/${locale}/search`,
    },
    {
      key: "ask",
      icon: <IconAsk />,
      label: t("home.nav.ask"),
      href: `/${locale}/ask`,
    },
    {
      key: "orders",
      icon: <IconOrders />,
      label: t("home.nav.orders"),
      href: `/${locale}/account/orders`,
    },
    {
      key: "account",
      icon: <IconAccount />,
      label: t("home.nav.account"),
      href: `/${locale}/account`,
    },
  ];

  return (
    // Shop client components (`useTranslations("catalog")`) need the catalog
    // namespace. Root layout only ships `common` (+ `legal` for the footer).
    <NextIntlClientProvider locale={locale} messages={messages}>
      <ServiceInfoBar
        labels={{
          ariaLabel: t("home.serviceBar.ariaLabel"),
          message: t("home.serviceBar.message"),
        }}
      />
      {/* Mobile/tablet chrome (<1024px). Hidden on lg+ where the desktop header takes over. */}
      <MobileTopNav
        locale={locale}
        logo={
          <Link href={`/${locale}`} className="font-display text-lg text-primary">
            {tCommon("app.name")}
          </Link>
        }
        searchSlot={
          <Link
            href={`/${locale}/search`}
            className="flex h-11 w-full max-w-md items-center gap-2 rounded-pill border border-border bg-surface px-4 text-sm text-text-3 transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            <IconSearch className="text-text-2" />
            <span className="truncate">{t("home.nav.searchPlaceholder")}</span>
          </Link>
        }
        cartIcon={<IconCart />}
        cartLabel={t("home.nav.cart")}
        cartWithCountLabel={t("home.nav.cartWithCount")}
        skipLinkTargetId="shop-main"
        skipLinkLabel={tCommon("nav.skipToContent")}
        navAriaLabel={t("home.nav.ariaLabel")}
        condensed
      />
      <DesktopHeader
        locale={locale}
        labels={{
          appName: tCommon("app.name"),
          skipToContent: tCommon("nav.skipToContent"),
          navAriaLabel: t("home.nav.desktopAriaLabel"),
          searchPlaceholder: t("home.nav.searchPlaceholder"),
          searchSubmit: t("home.nav.searchSubmit"),
          allCategories: t("home.nav.allCategories"),
          categoriesPanelAria: t("home.nav.categoriesPanelAria"),
          categoriesLoading: t("home.nav.categoriesLoading"),
          categoriesEmpty: t("home.nav.categoriesEmpty"),
          viewAllCategories: t("home.nav.viewAllCategories"),
          directory: t("home.nav.directory"),
          services: t("home.nav.services"),
          events: t("home.nav.events"),
          askVergeo: t("home.nav.askVergeo"),
          account: t("home.nav.account"),
          cart: t("home.nav.cart"),
          cartWithCount: t("home.nav.cartWithCount"),
        }}
      />
      <main
        id="shop-main"
        tabIndex={-1}
        className="mx-auto w-full max-w-lg flex-1 px-4 pb-20 pt-4 focus-visible:outline-none lg:max-w-7xl lg:px-6 lg:pb-12 lg:pt-6"
      >
        {children}
      </main>
      <BottomNavClient
        items={bottomItems}
        ariaLabel={t("home.nav.bottomAriaLabel")}
        locale={locale}
      />
    </NextIntlClientProvider>
  );
}

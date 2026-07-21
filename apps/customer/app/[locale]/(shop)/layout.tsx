import { loadNamespace, type Locale } from "@vergeo/i18n";
import {
  IconAccount,
  IconAsk,
  IconCart,
  IconHome,
  IconOrders,
  IconSearch,
} from "@vergeo/ui/src/icons";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BottomNavClient } from "./_components/bottom-nav-client";
import { ServiceInfoBar } from "./_components/service-info-bar";
import { ShopHeader } from "./_components/shop-header";
import { ShopLocaleSwitcher } from "./_components/shop-locale-switcher";

type ShopLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function ShopLayout({ children, params }: ShopLayoutProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const baseMessages = await getMessages();
  const [catalogMessages, searchMessages, navMessages] = await Promise.all([
    loadNamespace(locale as Locale, "catalog"),
    loadNamespace(locale as Locale, "search"),
    loadNamespace(locale as Locale, "nav"),
  ]);
  const messages = {
    ...baseMessages,
    catalog: catalogMessages,
    search: searchMessages,
    nav: navMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "nav" });
  const tCatalog = createTranslator({ locale, messages, namespace: "catalog" });
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tSearch = createTranslator({ locale, messages, namespace: "search" });
  const localeSwitcherLabels = {
    ariaLabel: tCommon("locale.switchAria"),
    names: {
      en: tCommon("locale.names.en"),
      bem: tCommon("locale.names.bem"),
      nya: tCommon("locale.names.nya"),
      fr: tCommon("locale.names.fr"),
    },
  };
  const localeSwitcher = <ShopLocaleSwitcher locale={locale} labels={localeSwitcherLabels} />;

  const bottomItems = [
    {
      key: "home",
      icon: <IconHome />,
      label: t("shop.home"),
      href: `/${locale}`,
    },
    {
      key: "browse",
      icon: <IconSearch />,
      label: t("shop.browse"),
      href: `/${locale}/search`,
    },
    {
      key: "ask",
      icon: <IconAsk />,
      label: t("shop.ask"),
      href: `/${locale}/ask`,
    },
    {
      key: "orders",
      icon: <IconOrders />,
      label: t("shop.orders"),
      href: `/${locale}/account/orders`,
    },
    {
      key: "account",
      icon: <IconAccount />,
      label: t("shop.account"),
      href: `/${locale}/account`,
    },
  ];

  const suppliesItem = {
    key: "supplies",
    icon: <IconCart />,
    label: t("shop.supplies"),
    href: `/${locale}/supplies`,
  };

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <ServiceInfoBar
        labels={{
          ariaLabel: tCatalog("home.serviceBar.ariaLabel"),
          message: tCatalog("home.serviceBar.message"),
        }}
      />
      <ShopHeader
        locale={locale}
        localeSwitcher={localeSwitcher}
        labels={{
          appName: tCommon("app.name"),
          skipToContent: tCommon("nav.skipToContent"),
          navAriaLabel: t("shop.ariaLabel"),
          desktopAriaLabel: t("shop.desktopAriaLabel"),
          searchPlaceholder: t("shop.searchPlaceholder"),
          searchSubmit: t("shop.searchSubmit"),
          allCategories: t("shop.allCategories"),
          categoriesPanelAria: t("shop.categoriesPanelAria"),
          categoriesLoading: t("shop.categoriesLoading"),
          categoriesEmpty: t("shop.categoriesEmpty"),
          viewAllCategories: t("shop.viewAllCategories"),
          featuredTitle: t("shop.featuredTitle"),
          featuredPromo: t("shop.featuredPromo"),
          featuredPromoCta: t("shop.featuredPromoCta"),
          directory: t("shop.directory"),
          services: t("shop.services"),
          events: t("shop.events"),
          askVergeo: t("shop.askVergeo"),
          supplies: t("shop.supplies"),
          account: t("shop.account"),
          cart: t("shop.cart"),
          cartWithCount: t("shop.cartWithCount"),
          searchInput: {
            placeholder: t("shop.searchPlaceholder"),
            submit: t("shop.searchSubmit"),
            ariaLabel: tSearch("input.ariaLabel"),
            suggestionsLabel: tSearch("input.suggestionsLabel"),
            noSuggestions: tSearch("input.noSuggestions"),
            recentTitle: tSearch("recent.title"),
          },
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
        ariaLabel={t("shop.bottomAriaLabel")}
        locale={locale}
        suppliesItem={suppliesItem}
      />
    </NextIntlClientProvider>
  );
}

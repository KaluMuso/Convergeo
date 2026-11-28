import { loadNamespace, type Locale } from "@vergeo/i18n";
import { IconAccount, IconAsk, IconHome, IconOrders, IconSearch } from "@vergeo/ui/src/icons";
import { createTranslator, NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { TopUtilityBarSlot } from "../_components/top-utility-bar-slot";

import { BottomNavClient } from "./_components/bottom-nav-client";
import { LazyCartHostSlot } from "./_components/cart/lazy-cart-host-slot";
import InstallPrompt from "./_components/install-prompt";
import { ServiceInfoBar } from "./_components/service-info-bar";
import { ShopHeaderSlot } from "./_components/shop-header-slot";

type ShopLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function ShopLayout({ children, params }: ShopLayoutProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const baseMessages = await getMessages();
  const [catalogMessages, searchMessages, navMessages, checkoutMessages] = await Promise.all([
    loadNamespace(locale as Locale, "catalog"),
    loadNamespace(locale as Locale, "search"),
    loadNamespace(locale as Locale, "nav"),
    loadNamespace(locale as Locale, "checkout"),
  ]);
  const messages = {
    ...baseMessages,
    catalog: catalogMessages,
    search: searchMessages,
    nav: navMessages,
    checkout: checkoutMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "nav" });
  const tCatalog = createTranslator({ locale, messages, namespace: "catalog" });
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

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <TopUtilityBarSlot locale={locale} />
      <ShopHeaderSlot locale={locale} />
      <ServiceInfoBar
        labels={{
          ariaLabel: tCatalog("home.serviceBar.ariaLabel"),
          message: tCatalog("home.serviceBar.message"),
        }}
      />
      <main
        id="shop-main"
        tabIndex={-1}
        className="shop-main mx-auto w-full max-w-[1400px] flex-1 px-3 pb-20 pt-2 focus-visible:outline-none md:px-5 md:pt-3 lg:px-6 lg:pb-12 lg:pt-4"
      >
        {children}
      </main>
      <BottomNavClient items={bottomItems} ariaLabel={t("shop.bottomAriaLabel")} locale={locale} />
      <LazyCartHostSlot locale={locale} />
      {/* Lets a returning PWA user explicitly activate a waiting worker. */}
      <InstallPrompt />
    </NextIntlClientProvider>
  );
}

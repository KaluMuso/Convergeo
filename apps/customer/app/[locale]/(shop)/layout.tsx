import { loadNamespace, type Locale } from "@vergeo/i18n";
import { ThemeToggle } from "@vergeo/ui/src/theme-toggle";
import { TopNav } from "@vergeo/ui/src/top-nav";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BottomNavClient } from "./_components/bottom-nav-client";
import { DesktopHeader } from "./_components/desktop-header";

type ShopLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

function navIcon(glyph: string) {
  return (
    <span aria-hidden className="text-base leading-none">
      {glyph}
    </span>
  );
}

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
      icon: navIcon("🏠"),
      label: t("home.nav.home"),
      href: `/${locale}`,
    },
    {
      key: "browse",
      icon: navIcon("🔍"),
      label: t("home.nav.browse"),
      href: `/${locale}/search`,
    },
    {
      key: "ask",
      icon: navIcon("✦"),
      label: t("home.nav.ask"),
      href: `/${locale}/ask`,
    },
    {
      key: "orders",
      icon: navIcon("📋"),
      label: t("home.nav.orders"),
      href: `/${locale}/account`,
    },
    {
      key: "account",
      icon: navIcon("👤"),
      label: t("home.nav.account"),
      href: `/${locale}/account`,
    },
  ];

  return (
    <>
      {/* Mobile/tablet chrome (<1024px) — unchanged. Hidden on lg+ where the
          desktop header below takes over. */}
      <TopNav
        className="lg:hidden"
        logo={
          <Link href={`/${locale}`} className="font-display text-lg text-primary">
            {tCommon("app.name")}
          </Link>
        }
        searchSlot={
          <Link
            href={`/${locale}/search`}
            className="flex h-11 w-full max-w-md items-center rounded-pill border border-border bg-surface px-4 text-sm text-text-3"
          >
            {t("home.nav.searchPlaceholder")}
          </Link>
        }
        actions={
          <ThemeToggle
            label={tCommon("theme.label")}
            lightLabel={tCommon("theme.light")}
            darkLabel={tCommon("theme.dark")}
            systemLabel={tCommon("theme.system")}
          />
        }
        cartIcon={navIcon("🛒")}
        cartCount={0}
        cartHref={`/${locale}/cart`}
        cartLabel={t("home.nav.cart")}
        skipLinkTargetId="shop-main"
        skipLinkLabel={tCommon("nav.skipToContent")}
        navAriaLabel={t("home.nav.ariaLabel")}
        LinkComponent={Link}
        condensed
      />
      <DesktopHeader
        locale={locale}
        labels={{
          appName: tCommon("app.name"),
          navAriaLabel: t("home.nav.desktopAriaLabel"),
          searchPlaceholder: t("home.nav.searchPlaceholder"),
          browse: t("home.nav.browse"),
          services: t("home.nav.services"),
          events: t("home.nav.events"),
          askVergeo: t("home.nav.askVergeo"),
          account: t("home.nav.account"),
          cart: t("home.nav.cart"),
          themeLabel: tCommon("theme.label"),
          themeLight: tCommon("theme.light"),
          themeDark: tCommon("theme.dark"),
          themeSystem: tCommon("theme.system"),
        }}
      />
      <main
        id="shop-main"
        className="mx-auto w-full max-w-lg flex-1 px-4 pb-20 pt-4 lg:max-w-7xl lg:px-6 lg:pb-12 lg:pt-6"
      >
        {children}
      </main>
      <BottomNavClient
        items={bottomItems}
        ariaLabel={t("home.nav.bottomAriaLabel")}
        locale={locale}
      />
    </>
  );
}

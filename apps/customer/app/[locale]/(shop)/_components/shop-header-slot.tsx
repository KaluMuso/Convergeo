import { loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages } from "next-intl/server";

import { NotificationBellIsland } from "../../_components/notification-bell-island";

import { buildMegaMenuLabels } from "./mega-menu/labels";
import { MEGA_MENU_FALLBACK_ROOT_SLUGS } from "./mega-menu-fallback-slugs";
import { MobileHeaderSearch } from "./mobile-header-search";
import { ShopHeader } from "./shop-header";

function fallbackCategoryRootLabels(t: (key: string) => string): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const slug of MEGA_MENU_FALLBACK_ROOT_SLUGS) {
    labels[slug] = t(`shop.fallbackCategoryRoots.${slug}`);
  }
  return labels;
}

/**
 * The full shop header (logo, All Categories, search, Shops/Services/Events,
 * account, cart). Shared by the shop layout and the account layout so every
 * signed-in page carries the same header as the rest of the site.
 */
export async function ShopHeaderSlot({ locale, mainId }: { locale: string; mainId?: string }) {
  const baseMessages = await getMessages();
  const [searchMessages, navMessages, checkoutMessages] = await Promise.all([
    loadNamespace(locale as Locale, "search"),
    loadNamespace(locale as Locale, "nav"),
    loadNamespace(locale as Locale, "checkout"),
  ]);
  const messages = {
    ...baseMessages,
    search: searchMessages,
    nav: navMessages,
    checkout: checkoutMessages,
  } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "nav" });
  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const tSearch = createTranslator({ locale, messages, namespace: "search" });
  const tCheckout = createTranslator({
    locale,
    messages,
    namespace: "checkout",
  });

  return (
    <ShopHeader
      locale={locale}
      mainId={mainId}
      notificationSlot={<NotificationBellIsland locale={locale} />}
      mobileSearchSlot={
        <MobileHeaderSearch
          locale={locale}
          triggerLabel={t("shop.searchPlaceholder")}
          sheetTitle={tSearch("title")}
          askLabel={t("shop.askVergeo")}
          labels={{
            placeholder: t("shop.searchPlaceholder"),
            submit: t("shop.searchSubmit"),
            ariaLabel: tSearch("input.ariaLabel"),
            suggestionsLabel: tSearch("input.suggestionsLabel"),
            noSuggestions: tSearch("input.noSuggestions"),
            recentTitle: tSearch("recent.title"),
          }}
        />
      }
      labels={{
        appName: tCommon("app.name"),
        skipToContent: t("skipToContent"),
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
        fallbackCategoryRoots: fallbackCategoryRootLabels(t),
        megaMenu: buildMegaMenuLabels(t),
        directory: t("shop.directory"),
        services: t("shop.services"),
        events: t("shop.events"),
        askVergeo: t("shop.askVergeo"),
        account: t("shop.account"),
        cart: t("shop.cart"),
        // Interpolated with the live cart count in the header client component.
        cartWithCount: String(t.raw("shop.cartWithCount")),
        openCart: tCheckout("cart.openCart"),
        theme: {
          label: tCommon("theme.label"),
          light: tCommon("theme.light"),
          dark: tCommon("theme.dark"),
          system: tCommon("theme.system"),
        },
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
  );
}

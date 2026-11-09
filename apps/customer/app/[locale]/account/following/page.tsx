import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountTranslator } from "../_components/account-server";

import { FollowFeedPanel } from "./_components/follow-feed-panel";

import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export const metadata: Metadata = { robots: { index: false, follow: false } };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/** New products from stores the customer follows (/me/follows/feed). */
export default async function AccountFollowingPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);
  const t = await getAccountTranslator(locale);
  const base = await getMessages();
  const catalog = await loadNamespace(locale as Locale, "catalog");
  const tCatalog = createTranslator({
    locale,
    messages: { ...base, catalog } as AbstractIntlMessages,
    namespace: "catalog",
  });

  return (
    <FollowFeedPanel
      locale={locale}
      labels={{
        title: t("following.title"),
        description: t("following.description"),
        emptyTitle: t("following.emptyTitle"),
        emptyBody: t("following.emptyBody"),
        browseVendors: t("following.browseVendors"),
        signIn: t("following.signIn"),
        signInCta: t("following.signInCta"),
        loadFailed: t("following.loadFailed"),
        retry: t("following.retry"),
        loadMore: t("following.loadMore"),
        loading: t("common.loading"),
        grid: {
          vendor: tCatalog.raw("plp.card.vendor") as string,
          noReviews: tCatalog("plp.card.noReviews"),
          reviewCount: tCatalog.raw("plp.card.reviewCount") as string,
          quickAdd: tCatalog("plp.card.quickAdd"),
          wishlist: tCatalog("plp.card.wishlist"),
          outOfStock: tCatalog("plp.card.outOfStock"),
          discount: tCatalog.raw("plp.card.discount") as string,
        },
      }}
    />
  );
}

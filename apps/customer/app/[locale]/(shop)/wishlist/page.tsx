import { createServerClient } from "@vergeo/auth/server-client";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { cookies } from "next/headers";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { SavedItemsPanel } from "./_components/saved-items-panel";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function WishlistPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const baseMessages = await getMessages();
  const accountMessages = await loadNamespace(locale as Locale, "account");
  const messages = { ...baseMessages, account: accountMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account" });

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6">
      <SavedItemsPanel
        locale={locale}
        signedIn={Boolean(user)}
        labels={{
          title: t("saved.title"),
          description: t("saved.description"),
          disclaimer: t("saved.disclaimer"),
          emptyTitle: t("saved.emptyTitle"),
          emptyBody: t("saved.emptyBody"),
          browseCta: t("saved.browseCta"),
          loading: t("saved.loading"),
          loadError: t("saved.loadError"),
          remove: t("saved.remove"),
          removeLabel: t("saved.removeLabel"),
          moveToCart: t("saved.moveToCart"),
          movingToCart: t("saved.movingToCart"),
          viewProduct: t("saved.viewProduct"),
          unavailable: t("saved.unavailable"),
          outOfStock: t("saved.outOfStock"),
          fromPrice: t("saved.fromPrice"),
          signedOutNote: t("saved.signedOutNote"),
        }}
      />
    </div>
  );
}

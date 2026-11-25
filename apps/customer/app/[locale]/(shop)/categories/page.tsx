import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { PageHeader } from "@vergeo/ui/src/page-header";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { BackToTop } from "../_components/back-to-top";
import { fetchCategoriesResult } from "../_components/merch-data";

import { resolveCategoriesBrowseView } from "./categories-view";

import type { Metadata } from "next";

import { CustomerRouteShell } from "@/components/customer-route-shell";

export const revalidate = 300;

type PageProps = {
  params: Promise<{ locale: string }>;
};

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getCatalogTranslator(locale: string): Promise<CatalogTranslator> {
  const baseMessages = await getMessages();
  const catalogMessages = await loadNamespace(locale as Locale, "catalog");
  const messages = {
    ...baseMessages,
    catalog: catalogMessages,
  } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "catalog",
  }) as unknown as CatalogTranslator;
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getCatalogTranslator(locale);
  const result = await fetchCategoriesResult();
  const view = resolveCategoriesBrowseView(result);
  const indexable = view.kind === "populated";

  return {
    title: t("browseCategories.title"),
    description: t("browseCategories.subtitle"),
    alternates: buildCanonicalAlternates(locale, "categories"),
    openGraph: {
      title: t("browseCategories.title"),
      description: t("browseCategories.subtitle"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "categories"),
    },
    robots: { index: indexable, follow: indexable },
  };
}

export default async function CategoriesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const t = await getCatalogTranslator(locale);
  const result = await fetchCategoriesResult();
  const view = resolveCategoriesBrowseView(result);

  return (
    <CustomerRouteShell className="flex max-w-5xl flex-col gap-6">
      <PageHeader title={t("browseCategories.title")} subtitle={t("browseCategories.subtitle")} />

      {view.kind === "populated" ? (
        <>
          <ul className="grid list-none grid-cols-1 gap-6 p-0 sm:grid-cols-2 lg:grid-cols-3">
            {view.tree.map((category) => (
              <li key={category.id} className="min-w-0 space-y-2">
                <Link
                  href={`/${locale}/c/${category.slug}`}
                  className="font-display text-h3 text-display-ink transition-colors hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
                >
                  {category.name}
                </Link>
                {category.children.length > 0 ? (
                  <ul className="list-none space-y-1.5 p-0">
                    {category.children.map((child) => (
                      <li key={child.id}>
                        <Link
                          href={`/${locale}/c/${child.slug}`}
                          className="block min-h-11 py-1 text-sm text-text-2 transition-colors hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
                        >
                          {child.name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
          <BackToTop label={t("plp.backToTop")} />
        </>
      ) : view.kind === "empty" ? (
        <EmptyState
          title={t("browseCategories.emptyTitle")}
          body={t("browseCategories.emptyBody")}
          illustration="no-products"
          data-testid="categories-empty"
        />
      ) : (
        <EmptyState
          title={t("browseCategories.unavailableTitle")}
          body={t("browseCategories.unavailableBody")}
          illustration="offline"
          data-testid={`categories-unavailable-${view.reason}`}
        />
      )}
    </CustomerRouteShell>
  );
}

import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { buildCategoryTree } from "../_components/category-mega-menu";
import { fetchCategories } from "../_components/merch-data";

import type { Metadata } from "next";

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
  const messages = { ...baseMessages, catalog: catalogMessages } as AbstractIntlMessages;

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
  };
}

export default async function CategoriesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const t = await getCatalogTranslator(locale);
  const rows = await fetchCategories();
  const tree = buildCategoryTree(
    rows.map((row) => ({
      id: row.id,
      name: row.name,
      slug: row.slug,
      position: row.position,
      parent_id: row.parent_id,
      prohibited: row.prohibited,
    })),
  );

  return (
    <div className="flex flex-col gap-6 lg:mx-auto lg:w-full lg:max-w-5xl">
      <header className="space-y-2">
        <h1 className="font-display text-h1 text-display-ink">{t("browseCategories.title")}</h1>
        <p className="text-body text-text-2">{t("browseCategories.subtitle")}</p>
      </header>

      {tree.length === 0 ? (
        <EmptyState
          title={t("browseCategories.emptyTitle")}
          body={t("browseCategories.emptyBody")}
        />
      ) : (
        <ul className="grid list-none grid-cols-1 gap-6 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {tree.map((category) => (
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
      )}
    </div>
  );
}

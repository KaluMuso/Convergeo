import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getArticleBySlug, getArticleSlugs, getRelatedArticles } from "../_lib/content";
import { Markdown } from "../_lib/markdown";

import type { Metadata } from "next";

export const dynamicParams = false;

type MarketingTranslator = (key: string, values?: Record<string, string | number>) => string;

async function getMarketingTranslator(locale: string): Promise<MarketingTranslator> {
  const baseMessages = await getMessages();
  const marketingMessages = await loadNamespace(locale as Locale, "marketing");
  const messages = { ...baseMessages, marketing: marketingMessages } as AbstractIntlMessages;
  return createTranslator({
    locale,
    messages,
    namespace: "marketing.help",
  }) as unknown as MarketingTranslator;
}

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
};

export function generateStaticParams() {
  return LOCALES.flatMap((locale) => getArticleSlugs().map((slug) => ({ locale, slug })));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  const article = getArticleBySlug(slug);
  if (!article) {
    return {};
  }
  return {
    title: article.title,
    description: article.summary,
    alternates: { canonical: `/${locale}/help/${slug}` },
  };
}

export default async function HelpArticlePage({ params }: PageProps) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const article = getArticleBySlug(slug);
  if (!article) {
    notFound();
  }

  const t = await getMarketingTranslator(locale);
  const related = getRelatedArticles(article);

  const articleSchema = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.summary,
    articleSection: t(`categories.${article.category}`),
  };

  return (
    <main id="marketing-main" className="mx-auto w-full max-w-2xl px-4 py-8">
      <script
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleSchema) }}
        type="application/ld+json"
      />

      <nav className="mb-6">
        <Link
          className="inline-flex min-h-11 items-center text-sm text-primary underline-offset-2 hover:underline"
          href={`/${locale}/help`}
        >
          {t("article.backToHelp")}
        </Link>
      </nav>

      <header className="mb-6 space-y-2">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">
          {t("article.inCategory", { category: t(`categories.${article.category}`) })}
        </p>
        <h1 className="font-display text-h1 text-display-ink">{article.title}</h1>
      </header>

      <article className="mb-10">
        <Markdown content={article.body} />
      </article>

      {related.length > 0 ? (
        <section className="mb-10 space-y-3">
          <h2 className="font-display text-h3 text-display-ink">{t("article.relatedHeading")}</h2>
          <ul className="space-y-2">
            {related.map((item) => (
              <li key={item.slug}>
                <Link
                  className="text-primary underline-offset-2 hover:underline"
                  href={`/${locale}/help/${item.slug}`}
                >
                  {item.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="space-y-3 rounded-lg border border-border bg-bg-2 p-6">
        <h2 className="font-display text-h3 text-display-ink">{t("article.notHelpful")}</h2>
        <LinkButton href={`/${locale}/contact`} variant="primary" LinkComponent={Link}>
          {t("article.contactCta")}
        </LinkButton>
      </section>
    </main>
  );
}

"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { HELP_CATEGORIES, searchArticles, type HelpSearchDoc } from "../_lib/search";

type HelpSearchProps = {
  index: HelpSearchDoc[];
  locale: string;
};

function ArticleLink({ doc, locale }: { doc: HelpSearchDoc; locale: string }) {
  return (
    <li>
      <Link
        className="block rounded-lg border border-border p-4 transition-colors hover:bg-bg-2"
        href={`/${locale}/help/${doc.slug}`}
      >
        <span className="block font-body font-semibold text-text">{doc.title}</span>
        {doc.summary ? <span className="mt-1 block text-sm text-text-2">{doc.summary}</span> : null}
      </Link>
    </li>
  );
}

export function HelpSearch({ index, locale }: HelpSearchProps) {
  const t = useTranslations("marketing.help");
  const [query, setQuery] = useState("");

  const results = useMemo(() => searchArticles(index, query), [index, query]);
  const isSearching = query.trim().length > 0;

  const grouped = useMemo(
    () =>
      HELP_CATEGORIES.map((category) => ({
        category,
        docs: index.filter((doc) => doc.category === category),
      })).filter((group) => group.docs.length > 0),
    [index],
  );

  return (
    <div className="space-y-6">
      <div className="relative">
        <label className="sr-only" htmlFor="help-search">
          {t("search.label")}
        </label>
        <input
          id="help-search"
          type="search"
          value={query}
          placeholder={t("search.placeholder")}
          className="h-12 w-full rounded-lg border border-border bg-surface px-4 font-body text-text placeholder:text-text-3 focus-visible:shadow-focusRing focus-visible:outline-none"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {isSearching ? (
        <section aria-live="polite" className="space-y-3">
          <p className="text-sm text-text-2">
            {t("search.resultsCount", { count: results.length })}
          </p>
          {results.length === 0 ? (
            <div className="rounded-lg border border-border bg-bg-2 p-6 text-center">
              <p className="font-body text-text">{t("search.noResults")}</p>
              <p className="mt-1 text-sm text-text-2">{t("search.noResultsHint")}</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {results.map((doc) => (
                <ArticleLink key={doc.slug} doc={doc} locale={locale} />
              ))}
            </ul>
          )}
        </section>
      ) : (
        <div className="space-y-8">
          {grouped.map((group) => (
            <section key={group.category} className="space-y-3">
              <h2 className="font-display text-h3 text-display-ink">
                {t(`categories.${group.category}`)}
              </h2>
              <ul className="space-y-3">
                {group.docs.map((doc) => (
                  <ArticleLink key={doc.slug} doc={doc} locale={locale} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

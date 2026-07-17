"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { NamespaceCatalog, TranslationCatalog } from "../_lib/catalog";

type Lens = "l10n" | "i18n";
type StatusFilter = "all" | "missing" | "translated";

function pct(count: number, total: number): number {
  return total === 0 ? 100 : Math.round((count / total) * 100);
}

function CoverageBar({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-2" aria-hidden>
      <div className="h-full rounded-full bg-primary" style={{ width: `${value}%` }} />
    </div>
  );
}

export function TranslatorView({ catalog }: { catalog: TranslationCatalog }) {
  const t = useTranslations("admin.translations");
  const [lens, setLens] = useState<Lens>("l10n");
  const [locale, setLocale] = useState<string>(catalog.translatableLocales[0] ?? "");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("all");

  const localeName = (code: string) => code.toUpperCase();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-xl font-semibold">{t("heading")}</h1>
        <p className="text-sm text-text-2">{t("subheading")}</p>
      </div>

      {/* Lens toggle — segregates the internationalization (key inventory) view
          from the localization (per-locale translation coverage) view. */}
      <div className="flex gap-2" role="tablist" aria-label={t("lensLabel")}>
        {(["l10n", "i18n"] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={lens === value}
            onClick={() => {
              setLens(value);
              setExpanded(null);
            }}
            className={
              lens === value
                ? "min-h-11 rounded-md border border-primary bg-primary/10 px-3 text-sm font-medium text-primary"
                : "min-h-11 rounded-md border border-border bg-surface px-3 text-sm font-medium text-text hover:border-primary"
            }
          >
            {t(`lens.${value}`)}
          </button>
        ))}
      </div>

      {lens === "l10n" ? (
        <>
          {/* Locale picker + overall coverage for the chosen locale. */}
          <div className="flex flex-wrap items-center gap-2">
            {catalog.translatableLocales.map((code) => {
              const overall = pct(catalog.perLocale[code] ?? 0, catalog.totalKeys);
              return (
                <button
                  key={code}
                  type="button"
                  onClick={() => {
                    setLocale(code);
                    setExpanded(null);
                  }}
                  className={
                    locale === code
                      ? "min-h-11 rounded-md border border-primary bg-primary/10 px-3 text-sm font-medium text-primary"
                      : "min-h-11 rounded-md border border-border bg-surface px-3 text-sm font-medium text-text hover:border-primary"
                  }
                >
                  {t("localeChip", { locale: localeName(code), percent: overall })}
                </button>
              );
            })}
          </div>

          <section className="rounded-lg border border-border bg-card p-3 shadow-sm">
            <p className="text-sm text-text-2">
              {t("localeSummary", {
                locale: localeName(locale),
                translated: catalog.perLocale[locale] ?? 0,
                total: catalog.totalKeys,
                percent: pct(catalog.perLocale[locale] ?? 0, catalog.totalKeys),
              })}
            </p>
          </section>

          <ul className="flex flex-col gap-2">
            {catalog.namespaces.map((ns) => {
              const count = ns.perLocale[locale] ?? 0;
              const percent = pct(count, ns.totalKeys);
              const isOpen = expanded === ns.namespace;
              return (
                <li key={ns.namespace} className="rounded-lg border border-border bg-surface p-3">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 text-left"
                    onClick={() => setExpanded(isOpen ? null : ns.namespace)}
                    aria-expanded={isOpen}
                  >
                    <span className="min-w-0">
                      <span className="font-medium text-text">{ns.namespace}</span>
                      <span className="ml-2 text-xs text-text-3">{t(`pages.${ns.namespace}`)}</span>
                    </span>
                    <span className="shrink-0 text-xs text-text-2">
                      {t("coverageCount", { translated: count, total: ns.totalKeys, percent })}
                    </span>
                  </button>
                  <div className="mt-2">
                    <CoverageBar value={percent} />
                  </div>
                  {isOpen ? (
                    <KeyList
                      ns={ns}
                      locale={locale}
                      status={status}
                      onStatus={setStatus}
                      labels={{
                        all: t("filter.all"),
                        missing: t("filter.missing"),
                        translated: t("filter.translated"),
                        translatedTag: t("tag.translated"),
                        missingTag: t("tag.missing"),
                        emptyFiltered: t("emptyFiltered"),
                      }}
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        // i18n lens: the raw key inventory grouped by namespace (= where strings live).
        <ul className="flex flex-col gap-2">
          {catalog.namespaces.map((ns) => {
            const isOpen = expanded === ns.namespace;
            return (
              <li key={ns.namespace} className="rounded-lg border border-border bg-surface p-3">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 text-left"
                  onClick={() => setExpanded(isOpen ? null : ns.namespace)}
                  aria-expanded={isOpen}
                >
                  <span className="min-w-0">
                    <span className="font-medium text-text">{ns.namespace}</span>
                    <span className="ml-2 text-xs text-text-3">{t(`pages.${ns.namespace}`)}</span>
                  </span>
                  <span className="shrink-0 text-xs text-text-2">
                    {t("keyCount", { count: ns.totalKeys })}
                  </span>
                </button>
                {isOpen ? (
                  <ul className="mt-2 flex flex-col divide-y divide-border">
                    {ns.keys.map((row) => (
                      <li key={row.key} className="flex flex-col gap-0.5 py-2">
                        <code className="text-xs text-primary">{`${ns.namespace}.${row.key}`}</code>
                        <span className="text-sm text-text-2">{row.en}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {/* Adding a language: file-based today; live editing is a planned follow-up. */}
      <section className="rounded-lg border border-dashed border-border bg-bg-2 p-3">
        <h2 className="text-sm font-semibold text-text">{t("addLanguage.title")}</h2>
        <p className="mt-1 text-xs text-text-2">{t("addLanguage.body")}</p>
        <ol className="mt-2 flex list-decimal flex-col gap-1 pl-4 text-xs text-text-2">
          <li>{t("addLanguage.step1")}</li>
          <li>{t("addLanguage.step2")}</li>
          <li>{t("addLanguage.step3")}</li>
        </ol>
      </section>
    </div>
  );
}

function KeyList({
  ns,
  locale,
  status,
  onStatus,
  labels,
}: {
  ns: NamespaceCatalog;
  locale: string;
  status: StatusFilter;
  onStatus: (value: StatusFilter) => void;
  labels: {
    all: string;
    missing: string;
    translated: string;
    translatedTag: string;
    missingTag: string;
    emptyFiltered: string;
  };
}) {
  const rows = ns.keys.filter((row) => {
    const translated = (row.present as string[]).includes(locale);
    if (status === "missing") return !translated;
    if (status === "translated") return translated;
    return true;
  });

  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex gap-2 text-xs">
        {(["all", "missing", "translated"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onStatus(value)}
            className={
              status === value
                ? "rounded-full border border-primary bg-primary/10 px-2 py-0.5 font-medium text-primary"
                : "rounded-full border border-border px-2 py-0.5 text-text-2 hover:border-primary"
            }
          >
            {labels[value]}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-text-3">{labels.emptyFiltered}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {rows.map((row) => {
            const translated = (row.present as string[]).includes(locale);
            return (
              <li key={row.key} className="flex items-start justify-between gap-3 py-2">
                <span className="min-w-0">
                  <code className="text-xs text-primary">{row.key}</code>
                  <span className="mt-0.5 block text-sm text-text-2">{row.en}</span>
                </span>
                <span
                  className={
                    translated
                      ? "shrink-0 text-xs font-medium text-success"
                      : "shrink-0 text-xs text-text-3"
                  }
                >
                  {translated ? labels.translatedTag : labels.missingTag}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

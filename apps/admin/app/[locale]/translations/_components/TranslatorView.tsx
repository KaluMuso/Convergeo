"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { deleteOverride, listOverrides, overrideKey, upsertOverride } from "../_lib/overrides-api";

import type { CatalogKey, NamespaceCatalog, TranslationCatalog } from "../_lib/catalog";

type Lens = "l10n" | "i18n";
type StatusFilter = "all" | "missing" | "translated";

function pct(count: number, total: number): number {
  return total === 0 ? 100 : Math.round((count / total) * 100);
}

/** Rebuild a nested message object from flat dotted keys (for JSON export). */
function unflatten(flat: Record<string, string>): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  for (const [dotted, value] of Object.entries(flat)) {
    const parts = dotted.split(".");
    let node = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const part = parts[i] as string;
      if (typeof node[part] !== "object" || node[part] === null) {
        node[part] = {};
      }
      node = node[part] as Record<string, unknown>;
    }
    node[parts[parts.length - 1] as string] = value;
  }
  return root;
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
  // Override values keyed by `locale namespace messageKey`.
  const [overrides, setOverrides] = useState<Map<string, string>>(new Map());
  const [overridesError, setOverridesError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listOverrides()
      .then((map) => {
        if (active) {
          setOverrides(map);
        }
      })
      .catch(() => {
        if (active) {
          setOverridesError(t("errors.loadOverrides"));
        }
      });
    return () => {
      active = false;
    };
  }, [t]);

  const hasValue = useCallback(
    (ns: string, row: CatalogKey, code: string): boolean =>
      row.present.includes(code as never) || overrides.has(overrideKey(code, ns, row.key)),
    [overrides],
  );

  const localeCount = useCallback(
    (ns: NamespaceCatalog, code: string): number =>
      ns.keys.reduce((sum, row) => (hasValue(ns.namespace, row, code) ? sum + 1 : sum), 0),
    [hasValue],
  );

  const overallCount = useMemo(() => {
    const totals = new Map<string, number>();
    for (const code of catalog.translatableLocales) {
      let sum = 0;
      for (const ns of catalog.namespaces) {
        sum += localeCount(ns, code);
      }
      totals.set(code, sum);
    }
    return totals;
  }, [catalog.namespaces, catalog.translatableLocales, localeCount]);

  const onSaved = useCallback((code: string, ns: string, key: string, value: string) => {
    setOverrides((prev) => new Map(prev).set(overrideKey(code, ns, key), value));
  }, []);

  const onCleared = useCallback((code: string, ns: string, key: string) => {
    setOverrides((prev) => {
      const next = new Map(prev);
      next.delete(overrideKey(code, ns, key));
      return next;
    });
  }, []);

  const exportNamespace = useCallback(
    (ns: NamespaceCatalog, code: string) => {
      const flat: Record<string, string> = {};
      for (const row of ns.keys) {
        const override = overrides.get(overrideKey(code, ns.namespace, row.key));
        const value = override ?? row.values[code];
        if (value !== undefined) {
          flat[row.key] = value;
        }
      }
      const blob = new Blob([`${JSON.stringify(unflatten(flat), null, 2)}\n`], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${code}-${ns.namespace}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    },
    [overrides],
  );

  const localeName = (code: string) => code.toUpperCase();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-xl font-semibold">{t("heading")}</h1>
        <p className="text-sm text-text-2">{t("subheading")}</p>
      </div>

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

      {overridesError ? (
        <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {overridesError}
        </p>
      ) : null}

      {lens === "l10n" ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {catalog.translatableLocales.map((code) => (
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
                {t("localeChip", {
                  locale: localeName(code),
                  percent: pct(overallCount.get(code) ?? 0, catalog.totalKeys),
                })}
              </button>
            ))}
          </div>

          <section className="rounded-lg border border-border bg-surface p-3 shadow-sm">
            <p className="text-sm text-text-2">
              {t("localeSummary", {
                locale: localeName(locale),
                translated: overallCount.get(locale) ?? 0,
                total: catalog.totalKeys,
                percent: pct(overallCount.get(locale) ?? 0, catalog.totalKeys),
              })}
            </p>
          </section>

          <ul className="flex flex-col gap-2">
            {catalog.namespaces.map((ns) => {
              const count = localeCount(ns, locale);
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
                    <EditableKeyList
                      ns={ns}
                      locale={locale}
                      overrides={overrides}
                      status={status}
                      onStatus={setStatus}
                      onSaved={(key, value) => onSaved(locale, ns.namespace, key, value)}
                      onCleared={(key) => onCleared(locale, ns.namespace, key)}
                      onExport={() => exportNamespace(ns, locale)}
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
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

function EditableKeyList({
  ns,
  locale,
  overrides,
  status,
  onStatus,
  onSaved,
  onCleared,
  onExport,
}: {
  ns: NamespaceCatalog;
  locale: string;
  overrides: Map<string, string>;
  status: StatusFilter;
  onStatus: (value: StatusFilter) => void;
  onSaved: (key: string, value: string) => void;
  onCleared: (key: string) => void;
  onExport: () => void;
}) {
  const t = useTranslations("admin.translations");

  const isTranslated = (row: CatalogKey): boolean =>
    row.present.includes(locale as never) ||
    overrides.has(overrideKey(locale, ns.namespace, row.key));

  const rows = ns.keys.filter((row) => {
    if (status === "missing") return !isTranslated(row);
    if (status === "translated") return isTranslated(row);
    return true;
  });

  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
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
              {t(`filter.${value}`)}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onExport}
          className="rounded-md border border-border px-2 py-1 text-xs font-medium text-text hover:border-primary"
        >
          {t("exportNamespace")}
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-text-3">{t("emptyFiltered")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {rows.map((row) => (
            <EditableRow
              key={row.key}
              ns={ns.namespace}
              locale={locale}
              row={row}
              override={overrides.get(overrideKey(locale, ns.namespace, row.key))}
              onSaved={onSaved}
              onCleared={onCleared}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function EditableRow({
  ns,
  locale,
  row,
  override,
  onSaved,
  onCleared,
}: {
  ns: string;
  locale: string;
  row: CatalogKey;
  override: string | undefined;
  onSaved: (key: string, value: string) => void;
  onCleared: (key: string) => void;
}) {
  const t = useTranslations("admin.translations");
  const current = override ?? row.values[locale] ?? "";
  const [draft, setDraft] = useState<string>(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = draft !== current;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await upsertOverride({ locale, namespace: ns, message_key: row.key, value: draft });
      onSaved(row.key, draft);
    } catch {
      setError(t("errors.save"));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteOverride({ locale, namespace: ns, message_key: row.key });
      onCleared(row.key);
      setDraft(row.values[locale] ?? "");
    } catch {
      setError(t("errors.save"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="flex flex-col gap-1 py-2">
      <div className="flex items-center justify-between gap-2">
        <code className="text-xs text-primary">{row.key}</code>
        {override !== undefined ? (
          <span className="text-xs font-medium text-success">{t("tag.override")}</span>
        ) : null}
      </div>
      <p className="text-xs text-text-3">{row.en}</p>
      <div className="flex items-start gap-2">
        <textarea
          className="min-h-11 w-full rounded-md border border-border bg-bg px-2 py-1 text-sm text-text"
          rows={1}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("valuePlaceholder")}
          aria-label={row.key}
        />
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || !dirty || draft.length === 0}
          className="shrink-0 rounded-md border border-primary bg-primary/10 px-2 py-1 text-xs font-medium text-primary disabled:opacity-40"
        >
          {t("save")}
        </button>
        {override !== undefined ? (
          <button
            type="button"
            onClick={() => void clear()}
            disabled={busy}
            className="shrink-0 rounded-md border border-border px-2 py-1 text-xs text-text-2 hover:border-primary disabled:opacity-40"
          >
            {t("clear")}
          </button>
        ) : null}
      </div>
      {error ? <p className="text-xs text-danger">{error}</p> : null}
    </li>
  );
}

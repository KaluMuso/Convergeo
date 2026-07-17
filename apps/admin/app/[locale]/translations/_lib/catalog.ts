import {
  DEFAULT_LOCALE,
  flattenMessages,
  LOCALES,
  loadRawNamespace,
  NAMESPACES,
  type Locale,
  type Namespace,
} from "@vergeo/i18n";

export type CatalogKey = {
  key: string;
  /** English source value (the string to translate). */
  en: string;
  /** Non-default locales that define this key (i.e. do NOT fall back to English). */
  present: Locale[];
  /** Current file value per non-default locale that defines the key (for editing). */
  values: Record<string, string>;
};

export type NamespaceCatalog = {
  namespace: Namespace;
  totalKeys: number;
  /** Translated-key count per non-default locale. */
  perLocale: Record<string, number>;
  keys: CatalogKey[];
};

export type TranslationCatalog = {
  locales: Locale[];
  defaultLocale: Locale;
  /** Locales that need translations (everything except the English source). */
  translatableLocales: Locale[];
  namespaces: NamespaceCatalog[];
  totalKeys: number;
  perLocale: Record<string, number>;
};

/**
 * Build the full translation catalog by reading each locale's OWN namespace files
 * (no English fallback), so coverage reflects what is actually translated. English
 * is the source of truth for the key set; a non-default locale "has" a key only if
 * its own file defines it.
 */
export async function buildTranslationCatalog(): Promise<TranslationCatalog> {
  const translatable = LOCALES.filter((locale) => locale !== DEFAULT_LOCALE);
  const namespaces: NamespaceCatalog[] = [];
  const grandPerLocale: Record<string, number> = Object.fromEntries(
    translatable.map((locale) => [locale, 0]),
  );
  let grandTotal = 0;

  for (const namespace of NAMESPACES) {
    const enRaw = await loadRawNamespace(DEFAULT_LOCALE, namespace);
    const enFlat = enRaw ? flattenMessages(enRaw) : {};
    const enKeys = Object.keys(enFlat);

    const localeFlat: Record<string, Record<string, string>> = {};
    for (const locale of translatable) {
      const raw = await loadRawNamespace(locale, namespace);
      localeFlat[locale] = raw ? flattenMessages(raw) : {};
    }

    const keys: CatalogKey[] = enKeys.map((key) => {
      const present = translatable.filter((locale) => key in (localeFlat[locale] ?? {}));
      const values: Record<string, string> = {};
      for (const locale of present) {
        values[locale] = localeFlat[locale]?.[key] ?? "";
      }
      return { key, en: enFlat[key] ?? "", present, values };
    });

    const perLocale: Record<string, number> = {};
    for (const locale of translatable) {
      const flat = localeFlat[locale] ?? {};
      const count = enKeys.filter((key) => key in flat).length;
      perLocale[locale] = count;
      grandPerLocale[locale] = (grandPerLocale[locale] ?? 0) + count;
    }
    grandTotal += enKeys.length;

    namespaces.push({ namespace, totalKeys: enKeys.length, perLocale, keys });
  }

  return {
    locales: [...LOCALES],
    defaultLocale: DEFAULT_LOCALE,
    translatableLocales: translatable,
    namespaces,
    totalKeys: grandTotal,
    perLocale: grandPerLocale,
  };
}

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

    const localeKeys: Record<string, Set<string>> = {};
    for (const locale of translatable) {
      const raw = await loadRawNamespace(locale, namespace);
      localeKeys[locale] = new Set(raw ? Object.keys(flattenMessages(raw)) : []);
    }

    const keys: CatalogKey[] = enKeys.map((key) => ({
      key,
      en: enFlat[key] ?? "",
      present: translatable.filter((locale) => localeKeys[locale]?.has(key)),
    }));

    const perLocale: Record<string, number> = {};
    for (const locale of translatable) {
      const set = localeKeys[locale];
      const count = set ? enKeys.filter((key) => set.has(key)).length : 0;
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

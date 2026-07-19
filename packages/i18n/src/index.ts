export { formatDate, formatK, formatNumber } from "./format";
export { flattenMessages, loadRawNamespace, localeNamespaceKeys } from "./catalog";
export { deepMergeMessages } from "./deep-merge";
export { DEFAULT_LOCALE, LOCALES, type Locale } from "./locales";
export {
  extractIcuPlaceholders,
  isUnexpectedEnglishFallback,
  keyMatchesPhase1Prefix,
  PHASE1_CRITICAL_LOCALES,
  PHASE1_CRITICAL_NAMESPACES,
  PHASE1_CRITICAL_PREFIXES,
} from "./phase1-critical";
export {
  isSeoIndexableLocale,
  listSeoIndexableLocales,
  resolveSeoAlternateLocales,
  robotsForLocalePublication,
  SEO_INDEXABLE_LOCALES,
  type SeoIndexableLocale,
} from "./seo-publication";
export {
  default as requestConfig,
  clearMessageCache,
  getLoadedNamespaceKeys,
  loadMessages,
  loadNamespace,
  NAMESPACES,
  type Namespace,
  resolveMessage,
} from "./request";

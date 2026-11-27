import { DEFAULT_LOCALE, LOCALES, type Locale } from "@vergeo/i18n";

import bemCommon from "../../../packages/i18n/messages/bem/common.json";
import enCommon from "../../../packages/i18n/messages/en/common.json";
import frCommon from "../../../packages/i18n/messages/fr/common.json";
import nyaCommon from "../../../packages/i18n/messages/nya/common.json";

export type ErrorPageCopy = (typeof enCommon)["errorPage"];

// `global-error` replaces the root layout, so there is no intl provider: resolve the
// shared `common.errorPage` copy statically. zh has none yet and falls back to English.
const byLocale: Partial<Record<Locale, ErrorPageCopy>> = {
  en: enCommon.errorPage,
  bem: bemCommon.errorPage,
  nya: nyaCommon.errorPage,
  fr: frCommon.errorPage,
};

export function resolveLocaleFromPathname(pathname: string): Locale {
  const segment = pathname.split("/").filter(Boolean)[0];
  return LOCALES.includes(segment as Locale) ? (segment as Locale) : DEFAULT_LOCALE;
}

export function resolveErrorPageCopy(locale: string): ErrorPageCopy {
  const normalized = LOCALES.includes(locale as Locale) ? (locale as Locale) : DEFAULT_LOCALE;
  return byLocale[normalized] ?? enCommon.errorPage;
}

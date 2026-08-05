import bemCommon from "../../../packages/i18n/messages/bem/common.json";
import enCommon from "../../../packages/i18n/messages/en/common.json";
import frCommon from "../../../packages/i18n/messages/fr/common.json";
import nyaCommon from "../../../packages/i18n/messages/nya/common.json";
import { DEFAULT_LOCALE, LOCALES, type Locale } from "@vergeo/i18n";

type ErrorPageCopy = (typeof enCommon)["errorPage"];

const commonByLocale: Partial<Record<Locale, { errorPage: ErrorPageCopy }>> = {
  en: enCommon,
  bem: bemCommon,
  nya: nyaCommon,
  fr: frCommon,
};

export function resolveErrorPageCopy(locale: string): ErrorPageCopy {
  const normalized = LOCALES.includes(locale as Locale) ? (locale as Locale) : DEFAULT_LOCALE;
  return commonByLocale[normalized]?.errorPage ?? enCommon.errorPage;
}

export function resolveLocaleFromPathname(pathname: string): Locale {
  const segment = pathname.split("/").filter(Boolean)[0];
  return LOCALES.includes(segment as Locale) ? (segment as Locale) : DEFAULT_LOCALE;
}

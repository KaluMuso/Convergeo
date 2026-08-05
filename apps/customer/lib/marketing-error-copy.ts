import bemMarketing from "../../../packages/i18n/messages/bem/marketing.json";
import enMarketing from "../../../packages/i18n/messages/en/marketing.json";
import frMarketing from "../../../packages/i18n/messages/fr/marketing.json";
import nyaMarketing from "../../../packages/i18n/messages/nya/marketing.json";
import { DEFAULT_LOCALE, LOCALES, type Locale } from "@vergeo/i18n";

type MarketingErrorCopy = (typeof enMarketing)["error"];

const marketingByLocale: Partial<Record<Locale, { error: MarketingErrorCopy }>> = {
  en: enMarketing,
  bem: bemMarketing,
  nya: nyaMarketing,
  fr: frMarketing,
};

export function resolveMarketingErrorCopy(locale: string): MarketingErrorCopy {
  const normalized = LOCALES.includes(locale as Locale) ? (locale as Locale) : DEFAULT_LOCALE;
  return marketingByLocale[normalized]?.error ?? enMarketing.error;
}

export function resolveLocaleFromPathname(pathname: string): Locale {
  const segment = pathname.split("/").filter(Boolean)[0];
  return LOCALES.includes(segment as Locale) ? (segment as Locale) : DEFAULT_LOCALE;
}

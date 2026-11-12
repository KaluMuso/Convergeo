/**
 * Locale tagline for the Edge OG image. Imports ONLY the tiny `common` namespace
 * JSON (not `@vergeo/i18n`, whose full message graph would push the OG worker over
 * Vercel's 1 MB limit). Unknown locales fall back to English.
 */
import bem from "../../../../packages/i18n/messages/bem/common.json";
import en from "../../../../packages/i18n/messages/en/common.json";
import fr from "../../../../packages/i18n/messages/fr/common.json";
import nya from "../../../../packages/i18n/messages/nya/common.json";
import zh from "../../../../packages/i18n/messages/zh/common.json";

const TAGLINES: Record<string, string> = {
  en: en.app.tagline,
  fr: fr.app.tagline,
  zh: zh.app.tagline,
  bem: bem.app.tagline,
  nya: nya.app.tagline,
};

export function resolveOgTagline(locale: string | undefined): string {
  return (locale && TAGLINES[locale]) || en.app.tagline;
}

import { createTranslator, type AbstractIntlMessages } from "next-intl";

/**
 * The COD trust line lives under `common.codTrust` (packages/i18n common.json),
 * and `getMessages()` only ships the `common` namespace at its root. Reading a
 * bare `codTrust` namespace never resolved: `MISSING_MESSAGE` at build and the raw
 * key shown to buyers on the COD checkout/pending/order pages.
 */
export function codTrustLine(locale: string, messages: AbstractIntlMessages): string {
  const t = createTranslator({
    locale,
    messages,
    namespace: "common.codTrust",
  }) as unknown as (key: string) => string;
  return t("line");
}

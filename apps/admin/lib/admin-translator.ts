import { loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";

export type AdminTranslator = (key: string, values?: Record<string, string | number>) => string;

/**
 * `getTranslations(namespace)` from `next-intl/server` reads the ambient
 * request-config messages, which ship `common` alone
 * (packages/i18n/src/request.ts) — every admin page needs its own `admin`
 * namespace loaded explicitly, the same way the layout does for the client
 * provider. Using `getTranslations("admin.xxx")` directly resolves nothing
 * and silently falls back to the raw key (MISSING_MESSAGE, logged but not
 * thrown), which is why admin page headers rendered literal `title`/
 * `subtitle` text in production.
 */
export async function getAdminTranslator(
  locale: string,
  namespace: string,
): Promise<AdminTranslator> {
  const adminMessages = await loadNamespace(locale as Locale, "admin");
  return createTranslator({
    locale,
    messages: { admin: adminMessages } as AbstractIntlMessages,
    namespace,
  }) as unknown as AdminTranslator;
}

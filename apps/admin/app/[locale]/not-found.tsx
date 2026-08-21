import { loadNamespace, DEFAULT_LOCALE, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("common");
  // `getTranslations("nav")` reads only the ambient request-config messages,
  // which ship `common` alone (packages/i18n/src/request.ts) — this file is
  // reached whenever an ancestor layout's `notFound()` fires before that
  // layout's own NextIntlClientProvider adds `nav`, e.g. for a request whose
  // locale segment fails the admin middleware's locale matcher. Load `nav`
  // directly instead of depending on any ancestor's provider.
  let locale: string = DEFAULT_LOCALE;
  try {
    locale = await getLocale();
  } catch {
    locale = DEFAULT_LOCALE;
  }
  const navMessages = await loadNamespace(locale as Locale, "nav");
  const tNav = createTranslator({
    locale,
    messages: { nav: navMessages } as AbstractIntlMessages,
    namespace: "nav",
  });

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
      <h1 className="text-lg font-semibold">{t("app.name")}</h1>
      <p className="text-sm text-muted">{tNav("shop.home")}</p>
      <Link
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
        href="/en"
      >
        {tNav("shop.home")}
      </Link>
    </main>
  );
}

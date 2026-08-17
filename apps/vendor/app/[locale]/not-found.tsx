import { DEFAULT_LOCALE, loadNamespace } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";

type StaticTranslator = (key: string) => string;

function translatorFor(
  locale: string,
  namespace: "common" | "nav",
  messages: AbstractIntlMessages,
): StaticTranslator {
  return createTranslator({ locale, messages, namespace }) as unknown as StaticTranslator;
}

export default async function NotFound() {
  const [commonMessages, navMessages] = await Promise.all([
    loadNamespace(DEFAULT_LOCALE, "common"),
    loadNamespace(DEFAULT_LOCALE, "nav"),
  ]);
  const messages = { common: commonMessages, nav: navMessages } as AbstractIntlMessages;
  const t = translatorFor(DEFAULT_LOCALE, "common", messages);
  const tNav = translatorFor(DEFAULT_LOCALE, "nav", messages);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
      <h1 className="text-lg font-semibold">{t("app.name")}</h1>
      <p className="text-sm text-text-2">{tNav("shop.home")}</p>
      <Link
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium text-text"
        href={`/${DEFAULT_LOCALE}`}
      >
        {tNav("shop.home")}
      </Link>
    </main>
  );
}

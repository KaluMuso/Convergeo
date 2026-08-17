import { DEFAULT_LOCALE, loadNamespace } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator } from "next-intl";

export default async function NotFound() {
  const [commonMessages, navMessages] = await Promise.all([
    loadNamespace(DEFAULT_LOCALE, "common"),
    loadNamespace(DEFAULT_LOCALE, "nav"),
  ]);
  const messages = { common: commonMessages, nav: navMessages };
  const t = createTranslator({ locale: DEFAULT_LOCALE, messages, namespace: "common" });
  const tNav = createTranslator({ locale: DEFAULT_LOCALE, messages, namespace: "nav" });

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
      <h1 className="text-lg font-semibold">{t("app.name")}</h1>
      <p className="text-sm text-muted">{tNav("shop.home")}</p>
      <Link
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-4 text-sm font-medium"
        href={`/${DEFAULT_LOCALE}`}
      >
        {tNav("shop.home")}
      </Link>
    </main>
  );
}

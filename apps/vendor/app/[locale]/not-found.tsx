import Link from "next/link";
import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("common");
  const tNav = await getTranslations("nav");

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col items-start justify-center gap-4 p-4">
      <h1 className="text-lg font-semibold">{t("app.name")}</h1>
      <p className="text-sm text-text-2">{tNav("shop.home")}</p>
      <Link
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-sm font-medium text-text"
        href="/en"
      >
        {tNav("shop.home")}
      </Link>
    </main>
  );
}

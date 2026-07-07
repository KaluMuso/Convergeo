import { LOCALES } from "@vergeo/i18n";
import Link from "next/link";
import { getTranslations, setRequestLocale } from "next-intl/server";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function HomePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("common");
  const switchLocale = locale === "en" ? "fr" : "en";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col gap-4 p-4">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-gray-500">{t("app.name")}</p>
        <h1 className="text-xl font-semibold">{t("nav.home")}</h1>
      </header>
      <p className="text-sm text-gray-700">{t("greeting", { name: t("app.name") })}</p>
      <nav>
        <Link
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-gray-300 px-4 text-sm font-medium"
          href={`/${switchLocale}`}
        >
          {switchLocale.toUpperCase()}
        </Link>
      </nav>
    </main>
  );
}

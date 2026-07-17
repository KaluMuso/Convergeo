import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { TranslatorView } from "./_components/TranslatorView";
import { buildTranslationCatalog } from "./_lib/catalog";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function TranslationsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  // Built from the committed message files (English is the source of truth), so the
  // coverage reflects what ships. File-based today; the panel documents adding a
  // language, and live DB-backed editing is a planned follow-up.
  const catalog = await buildTranslationCatalog();

  return <TranslatorView catalog={catalog} />;
}

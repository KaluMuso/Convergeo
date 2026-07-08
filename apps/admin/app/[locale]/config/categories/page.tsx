import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { CategoryTreeEditor } from "../_components/CategoryTreeEditor";
import { ConfigPageShell } from "../_components/ConfigPageShell";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function CategoriesConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="categories"
      titleKey="categories.title"
      subtitleKey="categories.subtitle"
    >
      <CategoryTreeEditor />
    </ConfigPageShell>
  );
}

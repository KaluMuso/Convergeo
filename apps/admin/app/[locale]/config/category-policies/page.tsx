import { LOCALES } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { CategoryPolicyEditor } from "../_components/CategoryPolicyEditor";
import { ConfigPageShell } from "../_components/ConfigPageShell";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function CategoryPoliciesConfigPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <ConfigPageShell
      locale={locale}
      active="category-policies"
      titleKey="categoryPolicies.title"
      subtitleKey="categoryPolicies.subtitle"
    >
      <CategoryPolicyEditor />
    </ConfigPageShell>
  );
}

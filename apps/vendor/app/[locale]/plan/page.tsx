import { LOCALES, loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import { PlanPicker } from "./_components/plan-picker";

import type { Metadata } from "next";

type PageProps = { params: Promise<{ locale: string }> };

type PickerMessages = { picker: { title: string; intro: string } };

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const plans = vendor.plans as PickerMessages;
  return { title: plans.picker.title, robots: { index: false, follow: false } };
}

export default async function PlanPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const vendor = await loadNamespace(locale as Locale, "vendor");
  const plans = vendor.plans as PickerMessages;
  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="m-0 font-display text-h1 font-bold text-display-ink">
          {plans.picker.title}
        </h1>
        <p className="m-0 text-sm text-text-2">{plans.picker.intro}</p>
      </header>
      <PlanPicker locale={locale} />
    </main>
  );
}

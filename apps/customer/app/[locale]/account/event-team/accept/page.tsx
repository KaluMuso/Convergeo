import { LOCALES } from "@vergeo/i18n";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { EventTeamAcceptForm } from "./_components/event-team-accept-form";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function EventTeamAcceptPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("events.teamAccept");

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4 px-4 py-8">
      <header className="space-y-1">
        <h1 className="font-display text-xl">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>
      <Suspense fallback={null}>
        <EventTeamAcceptForm />
      </Suspense>
    </div>
  );
}

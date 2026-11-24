import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import dynamic from "next/dynamic";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { PeopleSubnav } from "../_components/people-subnav";

const RequestsPanel = dynamic(
  () => import("../_components/requests-panel").then((m) => m.RequestsPanel),
  { ssr: false },
);

type PageProps = { params: Promise<{ locale: string }> };

export default async function PeopleRequestsPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) return null;
  setRequestLocale(locale);
  const social = await loadNamespace(locale as Locale, "social");
  const t = createTranslator({
    locale,
    messages: { social } as AbstractIntlMessages,
    namespace: "social",
  });
  return (
    <>
      <h2 className="mb-4 font-display text-h2 text-display-ink">{t("requests.title")}</h2>
      <PeopleSubnav locale={locale} />
      <RequestsPanel />
    </>
  );
}

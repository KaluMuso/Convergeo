import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { headers } from "next/headers";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { AddPeoplePanel } from "../_components/add-people-panel";
import { PeopleSubnav } from "../_components/people-subnav";

type PageProps = { params: Promise<{ locale: string }> };

export default async function PeopleAddPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) return null;
  setRequestLocale(locale);
  const social = await loadNamespace(locale as Locale, "social");
  const t = createTranslator({
    locale,
    messages: { social } as AbstractIntlMessages,
    namespace: "social",
  });
  const host = (await headers()).get("x-forwarded-host") ?? (await headers()).get("host");
  const proto = (await headers()).get("x-forwarded-proto") ?? "https";
  const siteOrigin = host ? `${proto}://${host}` : "https://www.vergeo5.com";
  return (
    <>
      <h2 className="mb-4 font-display text-h2 text-display-ink">{t("add.title")}</h2>
      <PeopleSubnav locale={locale} />
      <AddPeoplePanel locale={locale} siteOrigin={siteOrigin} />
    </>
  );
}
